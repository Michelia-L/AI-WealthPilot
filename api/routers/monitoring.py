"""
Portfolio monitoring & rebalancing endpoints (P10).

Thin transport shell over src.portfolio.monitoring.compute_monitoring:
the core raises KeyError (document missing) / ValueError (no SAA),
which this router translates into 404 / 422.

POST /advice streams an AI interpretation of the monitoring result as
Server-Sent Events, reusing the advisor SSE protocol verbatim (reasoning
and token events, then a terminal done/error event).
"""

import json
from datetime import date
from typing import Any, Generator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api.cache import TTLCache
from api.db import ProfileRecord, get_session
from api.i18n import get_request_locale, msg
from api.profile_convert import profile_from_data
from api.routers.market import _fig_json
from api.schemas import (
    BacktestResponse,
    MonitoringFleetResponse,
    MonitoringResponse,
    RebalanceAdviceRequest,
)
from src.agents.profiler import ClientProfile
from src.agents.demo_mode import demo_rebalance_stream, is_demo_mode
from src.agents.rebalance_advisor import (
    AdvisorReport,
    generate_rebalance_advice_stream,
    is_api_configured,
)
from src.portfolio.backtest import (
    VALID_PERIODS as BACKTEST_PERIODS,
    InsufficientDataError,
    run_backtest,
)
from src.portfolio.monitoring import (
    compute_fleet_status,
    compute_monitoring,
    resolve_saa_weights,
)
from src.visualization.charts import plot_backtest_equity, plot_drawdown

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _is_valid_document_id(document_id: str) -> bool:
    """Same charset rule as ips._find_ips_file (keeps lookups inside IPS_DIR)."""
    return bool(document_id) and all(
        c.isalnum() or c in "_-" for c in document_id
    )


# ---------------------------------------------------------------------------
# Fleet-wide band status (P17 — overview alert lamp)
# ---------------------------------------------------------------------------

_fleet_status_cache = TTLCache()
FLEET_STATUS_CACHE_TTL_SECONDS = 86400  # the date in the key expires it daily


# NOTE: declared BEFORE /{document_id} — "status" satisfies the document_id
# charset, so registering it later would let the path-parameter route
# swallow it and return 404.
@router.get(
    "/status",
    response_model=MonitoringFleetResponse,
    summary="Band-status overview across all stored IPS documents",
)
def get_fleet_status(request: Request, refresh: bool = False) -> MonitoringFleetResponse:
    locale = get_request_locale(request)
    # Date inside the key: the first request of a new day misses the cache
    # and recomputes — the lazy "daily auto re-check" semantic. Locale is
    # part of the key because fleet item notes are localized.
    key = f"fleet-status:{date.today().isoformat()}:{locale}"
    if refresh:
        _fleet_status_cache.invalidate(key)
    return _fleet_status_cache.get_or_set(
        key,
        FLEET_STATUS_CACHE_TTL_SECONDS,
        lambda: MonitoringFleetResponse(**compute_fleet_status(locale=locale)),
    )


@router.get(
    "/{document_id}",
    response_model=MonitoringResponse,
    summary="Drift monitoring and rebalancing diagnostics for a stored IPS",
)
def get_monitoring(document_id: str, request: Request) -> MonitoringResponse:
    locale = get_request_locale(request)
    if not _is_valid_document_id(document_id):
        raise HTTPException(status_code=404, detail=msg("common.ips_doc_not_found", locale))
    try:
        result = compute_monitoring(document_id, locale=locale)
    except KeyError:
        raise HTTPException(status_code=404, detail=msg("common.ips_doc_not_found", locale))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return MonitoringResponse(**result)


# ---------------------------------------------------------------------------
# Portfolio backtesting (P13 — src/portfolio/backtest.py)
# ---------------------------------------------------------------------------

_backtest_cache = TTLCache()
BACKTEST_CACHE_TTL_SECONDS = 600  # NAV panels are stable intraday


def _resolve_annual_fee_rate(fee_schedule: dict, locale: str = "zh") -> tuple[float, list[str]]:
    """
    Extract the annual fee-drag rate from an IPS fee_schedule block (P18).

    Prefers the all-in total_expense_ratio (positive values only); falls
    back to management + custody + transaction-cost components when the TER
    is missing or non-positive. Returns (rate, notes worded per ``locale``);
    a missing or all-zero disclosure yields rate 0. Out-of-range rates are
    NOT clipped here — run_backtest owns the [0, 10%] plausibility cap.
    """
    def _num(key: str) -> float:
        try:
            return float(fee_schedule.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    if not fee_schedule:
        return 0.0, [msg("monitoring.fee_no_disclosure", locale)]

    ter = _num("total_expense_ratio")
    if ter > 0:
        return ter, []

    components = (
        _num("management_fee_rate")
        + _num("custody_fee_rate")
        + _num("transaction_cost_estimate")
    )
    if components > 0:
        return components, [
            msg("monitoring.fee_ter_missing", locale, components=components)
        ]
    return 0.0, [msg("monitoring.fee_no_disclosure", locale)]


@router.get(
    "/{document_id}/backtest",
    response_model=BacktestResponse,
    summary="Monthly-rebalanced backtest + stress tests for a stored IPS SAA",
)
def get_backtest(
    document_id: str, request: Request, period: str = "5y"
) -> BacktestResponse:
    locale = get_request_locale(request)
    if not _is_valid_document_id(document_id):
        raise HTTPException(status_code=404, detail=msg("common.ips_doc_not_found", locale))
    if period not in BACKTEST_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=msg(
                "monitoring.invalid_backtest_period",
                locale,
                period=period,
                options="、".join(BACKTEST_PERIODS),
            ),
        )

    def _compute() -> BacktestResponse:
        try:
            saa = resolve_saa_weights(document_id, locale=locale)
        except KeyError:
            raise HTTPException(status_code=404, detail=msg("common.ips_doc_not_found", locale))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        fee_rate, fee_notes = _resolve_annual_fee_rate(saa["fee_schedule"], locale)
        try:
            result = run_backtest(
                saa["weights"],
                period,
                annual_fee_rate=fee_rate,
                fee_source="ips_fee_schedule",
            )
        except InsufficientDataError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        equity = result.pop("_equity")
        drawdown = result.pop("_drawdown")
        names = saa["names"]
        return BacktestResponse(
            document_id=document_id,
            client_name=saa["client_name"],
            period=result["period"],
            as_of=result["as_of"],
            weights={names.get(t, t): w for t, w in result["weights"].items()},
            metrics=result["metrics"],
            benchmark=result["benchmark"],
            yearly=result["yearly"],
            equity_chart=_fig_json(plot_backtest_equity(equity, result["benchmark"]["name"])),
            drawdown_chart=_fig_json(
                plot_drawdown(drawdown["portfolio"], drawdown["benchmark"])
            ),
            stress=result["stress"],
            fee=result["fee"],
            notes=saa["notes"] + fee_notes + result["notes"],
        )

    # Locale is part of the key because the notes payload is localized.
    return _backtest_cache.get_or_set(
        f"backtest:{document_id}:{period}:{locale}", BACKTEST_CACHE_TTL_SECONDS, _compute
    )


# ---------------------------------------------------------------------------
# AI rebalancing advice (SSE streaming, same event protocol as /advisor)
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _advice_event_stream(
    monitoring: dict, profile: Optional[ClientProfile], locale: str
) -> Generator[str, None, None]:
    """Yield SSE lines: reasoning/token events, then one terminal done/error event."""
    holder: list[AdvisorReport] = []

    def _run() -> Generator[str, None, None]:
        # Demo mode (P20): replay the recorded fixture instead of the LLM.
        stream = (
            demo_rebalance_stream(monitoring, profile)
            if is_demo_mode()
            else generate_rebalance_advice_stream(monitoring, profile, locale=locale)
        )
        report = yield from stream
        holder.append(report)

    try:
        for event in _run():
            # Generators yield reasoning/token event dicts; tolerate legacy
            # plain-string streams by wrapping them as token events.
            if not isinstance(event, dict):
                event = {"type": "token", "text": event}
            yield _sse(event)
    except Exception as e:  # defensive: src/ generator already swallows API errors
        yield _sse({"type": "error", "message": msg("common.stream_interrupted", locale, error=e)})
        return

    if not holder:
        yield _sse({"type": "error", "message": msg("common.no_report_generated", locale)})
        return
    report = holder[0]
    yield _sse(
        {
            "type": "done",
            "success": report.success,
            "model": report.model,
            "prompt_tokens": report.prompt_tokens,
            "completion_tokens": report.completion_tokens,
            "total_tokens": report.total_tokens,
            "reasoning_tokens": report.reasoning_tokens,
            "error_message": report.error_message,
        }
    )


@router.post(
    "/advice",
    summary="Stream AI rebalancing advice for a stored IPS (SSE)",
)
def stream_rebalance_advice(
    payload: RebalanceAdviceRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> StreamingResponse:
    locale = get_request_locale(request)
    if not is_api_configured() and not is_demo_mode():
        raise HTTPException(
            status_code=503,
            detail=msg("common.llm_not_configured", locale),
        )
    if not _is_valid_document_id(payload.document_id):
        raise HTTPException(status_code=404, detail=msg("common.ips_doc_not_found", locale))
    try:
        monitoring = compute_monitoring(payload.document_id, locale=locale)
    except KeyError:
        raise HTTPException(status_code=404, detail=msg("common.ips_doc_not_found", locale))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    profile: Optional[ClientProfile] = None
    if payload.profile_id is not None:
        record = session.get(ProfileRecord, payload.profile_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=msg("common.profile_not_found", locale, id=payload.profile_id),
            )
        profile = profile_from_data(record.data)

    return StreamingResponse(
        _advice_event_stream(monitoring, profile, locale),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
