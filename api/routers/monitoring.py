"""
Portfolio monitoring & rebalancing endpoints (P10).

Thin transport shell over src.portfolio.monitoring.compute_monitoring:
the core raises KeyError (document missing) / ValueError (no SAA),
which this router translates into 404 / 422.

POST /advice streams an AI interpretation of the monitoring result as
Server-Sent Events, reusing the advisor SSE protocol verbatim (token
events, then a terminal done/error event).
"""

import json
from typing import Any, Generator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api.db import ProfileRecord, get_session
from api.profile_convert import profile_from_data
from api.schemas import MonitoringResponse, RebalanceAdviceRequest
from src.agents.profiler import ClientProfile
from src.agents.rebalance_advisor import (
    AdvisorReport,
    generate_rebalance_advice_stream,
    is_api_configured,
)
from src.portfolio.monitoring import compute_monitoring

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


def _is_valid_document_id(document_id: str) -> bool:
    """Same charset rule as ips._find_ips_file (keeps lookups inside IPS_DIR)."""
    return bool(document_id) and all(
        c.isalnum() or c in "_-" for c in document_id
    )


@router.get(
    "/{document_id}",
    response_model=MonitoringResponse,
    summary="Drift monitoring and rebalancing diagnostics for a stored IPS",
)
def get_monitoring(document_id: str) -> MonitoringResponse:
    if not _is_valid_document_id(document_id):
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    try:
        result = compute_monitoring(document_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return MonitoringResponse(**result)


# ---------------------------------------------------------------------------
# AI rebalancing advice (SSE streaming, same event protocol as /advisor)
# ---------------------------------------------------------------------------


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _advice_event_stream(
    monitoring: dict, profile: Optional[ClientProfile]
) -> Generator[str, None, None]:
    """Yield SSE lines: token events, then one terminal done/error event."""
    holder: list[AdvisorReport] = []

    def _run() -> Generator[str, None, None]:
        report = yield from generate_rebalance_advice_stream(monitoring, profile)
        holder.append(report)

    try:
        for text in _run():
            yield _sse({"type": "token", "text": text})
    except Exception as e:  # defensive: src/ generator already swallows API errors
        yield _sse({"type": "error", "message": f"流式生成中断: {e}"})
        return

    if not holder:
        yield _sse({"type": "error", "message": "生成器未返回报告"})
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
            "error_message": report.error_message,
        }
    )


@router.post(
    "/advice",
    summary="Stream AI rebalancing advice for a stored IPS (SSE)",
)
def stream_rebalance_advice(
    payload: RebalanceAdviceRequest, session: Session = Depends(get_session)
) -> StreamingResponse:
    if not is_api_configured():
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY 未配置，请在 api 服务的 .env 中设置后重启。",
        )
    if not _is_valid_document_id(payload.document_id):
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    try:
        monitoring = compute_monitoring(payload.document_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="IPS 文档不存在")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    profile: Optional[ClientProfile] = None
    if payload.profile_id is not None:
        record = session.get(ProfileRecord, payload.profile_id)
        if record is None:
            raise HTTPException(
                status_code=404, detail=f"画像不存在（id={payload.profile_id}）"
            )
        profile = profile_from_data(record.data)

    return StreamingResponse(
        _advice_event_stream(monitoring, profile),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
