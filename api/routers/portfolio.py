"""
Portfolio optimization endpoints.

POST /api/portfolio/optimize wraps the MVO / Resampled-MVO / Black-Litterman
/ Mean-CVaR / LDI-surplus engines in src.portfolio.optimizer, mirroring the
call sequence of the Streamlit optimizer page. Returns portfolio metrics
plus Plotly figures (efficient frontier + CAL, allocation pie) ready for
plotly.js.

POST /api/portfolio/optimize/async runs the same computation as a background
task (Phase 5c) with SSE progress on GET /api/portfolio/tasks/{id}/events —
the resampled method is minute-level (n_simulations × n_points SLSQP solves)
and would otherwise hold an HTTP request open the whole time.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api.cache import TTLCache
from api.db import ProfileRecord, get_session
from api.i18n import get_request_locale, msg
from api.profile_convert import profile_from_data
from api.routers.market import _fig_json
from api.schemas import (
    AssetClassInfo,
    AssetClassesResponse,
    AssetStat,
    BLInsight,
    GoalFeasibility,
    OptimizeRequest,
    OptimizeResponse,
    PortfolioBacktestRequest,
    PortfolioBacktestResponse,
    PortfolioResult,
    PortfolioTaskCreatedResponse,
    RecommendationResponse,
    RiskConstraintsInfo,
    SurplusInsight,
)
from api.tasks import (
    BackgroundTask,
    TaskRegistry,
    task_events_stream,
)
from src.agents.portfolio_recommender import recommend_portfolio
from src.config import (
    BASE_CURRENCY,
    CME_INFLATION_ASSUMPTION,
    CME_TICKER_TO_OPTIMIZER_ASSET,
    DEFAULT_ASSET_CLASSES,
    LDI_DEFAULT_PROXY,
    LDI_PROXY_DURATIONS,
    TRADING_DAYS_PER_YEAR,
)
from src.data.market_data import (
    compute_returns,
    fetch_price_history,
    fetch_risk_free_rate,
)
from src.portfolio.backtest import InsufficientDataError, run_backtest
from src.portfolio.cme_engine import compute_cme
from src.portfolio.inflation import resolve_personal_inflation, suggest_inflation_preset
from src.data.yield_curve import fetch_china_treasury_curve, rate_at
from src.portfolio.liabilities import (
    estimate_liability_stats,
    goals_to_liability,
    retirement_income_stream,
    stream_to_liability,
)
from src.portfolio.optimizer import BlackLittermanOptimizer, PortfolioOptimizer
from src.portfolio.risk_constraints import build_group_constraints, caps_for_tolerance
from src.portfolio.views import ViewInput
from src.visualization.charts import (
    plot_allocation_pie,
    plot_backtest_equity,
    plot_drawdown,
    plot_efficient_frontier,
)

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_prices_cache: TTLCache = TTLCache()
_rf_cache: TTLCache = TTLCache()
_backtest_cache: TTLCache = TTLCache()
_curve_cache: TTLCache = TTLCache()

PRICES_TTL_SECONDS = 300
RISK_FREE_RATE_TTL_SECONDS = 3600
BACKTEST_TTL_SECONDS = 600
YIELD_CURVE_TTL_SECONDS = 3600
FRONTIER_POINTS = 50
RESAMPLED_FRONTIER_POINTS = 20
RANDOM_PORTFOLIOS = 1000


@router.get(
    "/asset-classes",
    response_model=AssetClassesResponse,
    summary="Optimization asset universe (DEFAULT_ASSET_CLASSES)",
)
def get_asset_classes() -> AssetClassesResponse:
    return AssetClassesResponse(
        asset_classes={
            key: AssetClassInfo(**info) for key, info in DEFAULT_ASSET_CLASSES.items()
        }
    )


@router.get(
    "/recommendation",
    response_model=RecommendationResponse,
    summary="Personalized allocation for a client profile (P12)",
)
def get_recommendation(
    profile_id: int, request: Request, session: Session = Depends(get_session)
) -> RecommendationResponse:
    """Risk-score-driven allocation from src portfolio_recommender: the
    profile's final score maps to a target volatility, and the MVO engine
    solves the min-volatility portfolio (goal-aware) on the full universe."""
    record = session.get(ProfileRecord, profile_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail=msg("common.profile_not_found", get_request_locale(request), id=profile_id),
        )
    profile = profile_from_data(record.data)

    returns = _fetch_returns(
        list(DEFAULT_ASSET_CLASSES.keys()), "5y", get_request_locale(request)
    )
    rf = _effective_risk_free_rate(None)
    rec = recommend_portfolio(profile, returns, rf)
    return RecommendationResponse(
        profile_id=profile_id,
        profile_name=profile.name,
        risk_level=rec.risk_level,
        as_of=datetime.now(timezone.utc),
        allocation={k: float(v) for k, v in rec.suggested_allocation.items()},
        expected_return=float(rec.expected_return),
        expected_volatility=float(rec.expected_volatility),
        sharpe_ratio=float(rec.sharpe_ratio),
        rationale=rec.rationale,
        goal_status=rec.goal_status or None,
        goal_name=rec.goal_name or None,
        goal_required_return=(
            float(rec.goal_required_return)
            if rec.goal_required_return is not None
            else None
        ),
        goals=[GoalFeasibility(**d) for d in rec.goal_details],
    )


@router.post(
    "/backtest",
    response_model=PortfolioBacktestResponse,
    summary="Backtest an arbitrary long-only weight map (optimizer results)",
)
def backtest_weights(
    req: PortfolioBacktestRequest, request: Request
) -> PortfolioBacktestResponse:
    """Run the monthly-rebalanced backtest for a caller-supplied portfolio
    (e.g. the optimizer's selected weights), benchmarked vs 60/40."""
    locale = get_request_locale(request)
    if not req.weights or len(req.weights) > 30:
        raise HTTPException(
            status_code=422, detail=msg("portfolio.invalid_weights", locale)
        )
    if any(v < -0.001 for v in req.weights.values()):
        raise HTTPException(
            status_code=422, detail=msg("portfolio.long_only", locale)
        )
    total = sum(req.weights.values())
    if not 0.5 <= total <= 1.5:
        raise HTTPException(
            status_code=422,
            detail=msg("portfolio.bad_weight_total", locale, total=total),
        )

    cache_key = (
        "pbt:"
        + hashlib.sha1(
            sorted(req.weights.items()).__repr__().encode("utf-8")
        ).hexdigest()[:12]
        + f":{req.period}:{req.annual_fee_rate}:{locale}"
    )

    def _compute() -> PortfolioBacktestResponse:
        try:
            result = run_backtest(
                req.weights,
                req.period,
                annual_fee_rate=req.annual_fee_rate,
                fee_source="manual",
                locale=locale,
            )
        except InsufficientDataError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

        equity = result.pop("_equity")
        drawdown = result.pop("_drawdown")
        return PortfolioBacktestResponse(
            period=result["period"],
            as_of=result["as_of"],
            weights=result["weights"],
            metrics=result["metrics"],
            benchmark=result["benchmark"],
            yearly=result["yearly"],
            equity_chart=_fig_json(
                plot_backtest_equity(equity, result["benchmark"]["name"])
            ),
            drawdown_chart=_fig_json(
                plot_drawdown(drawdown["portfolio"], drawdown["benchmark"])
            ),
            stress=result["stress"],
            fee=result["fee"],
            notes=result["notes"],
        )

    return _backtest_cache.get_or_set(cache_key, BACKTEST_TTL_SECONDS, _compute)


def _resolve_asset_keys(requested: list[str], locale: str = "zh") -> list[str]:
    """Filter requested keys to the known universe, preserving order."""
    seen: set[str] = set()
    keys: list[str] = []
    for k in requested:
        if k in DEFAULT_ASSET_CLASSES and k not in seen:
            seen.add(k)
            keys.append(k)
    if len(keys) < 2:
        raise HTTPException(
            status_code=422,
            detail=msg(
                "portfolio.min_assets",
                locale,
                keys=", ".join(DEFAULT_ASSET_CLASSES.keys()),
            ),
        )
    return keys


def _fetch_returns(keys: list[str], period: str, locale: str = "zh") -> pd.DataFrame:
    """Daily simple returns with columns renamed to asset display names."""
    tickers = [DEFAULT_ASSET_CLASSES[k]["ticker"] for k in keys]
    cache_key = f"prices:{period}|{','.join(sorted(tickers))}"

    def _load() -> pd.DataFrame:
        prices = fetch_price_history(tickers, period=period)
        if prices.empty:
            raise HTTPException(
                status_code=502,
                detail="No price data returned from the market data provider.",
            )
        # Reject instruments whose series came back missing or all-NaN — the
        # failure is transient upstream, and caching such a frame would
        # poison every request for the whole TTL window.
        bad = [
            t
            for t in tickers
            if t not in prices.columns or prices[t].dropna().empty
        ]
        if bad:
            raise HTTPException(
                status_code=502,
                detail=msg("portfolio.price_fetch_failed", locale, tickers=", ".join(bad)),
            )
        return prices

    prices = _prices_cache.get_or_set(cache_key, PRICES_TTL_SECONDS, _load)
    # fetch_price_history preserves the requested ticker order in columns
    prices = prices[tickers]
    prices.columns = [DEFAULT_ASSET_CLASSES[k]["name"] for k in keys]
    return compute_returns(prices, method="simple")


def _effective_risk_free_rate(override: Optional[float]) -> float:
    if override is not None:
        return override
    # Optimizer returns are FX-adjusted to the base currency (fetch_price_history
    # default adjust_currency=True), so the Sharpe rf must use the same leg.
    return _rf_cache.get_or_set(
        "rf",
        RISK_FREE_RATE_TTL_SECONDS,
        lambda: fetch_risk_free_rate(currency=BASE_CURRENCY),
    )


def _effective_discount_curve() -> tuple[Optional[dict[float, float]], str]:
    """ChinaBond treasury curve for LDI liability discounting.

    Successful fetches are TTL-cached; a miss is evicted so the next
    request retries instead of pinning the flat fallback for a whole
    TTL window. Returns (curve, source_label) — (None, "flat_risk_free")
    when the provider cascade has nothing.
    """
    result = _curve_cache.get_or_set(
        "cgb_curve", YIELD_CURVE_TTL_SECONDS, fetch_china_treasury_curve
    )
    if result is None:
        _curve_cache.invalidate("cgb_curve")
        return None, "flat_risk_free"
    curve, _provider = result
    return curve, "china_treasury_curve"


def _result_payload(result: dict, asset_names: list[str]) -> PortfolioResult:
    """Normalize an optimizer result-dict into the API schema."""
    weight_std = result.get("weight_std")
    cvar = result.get("cvar")
    risk_rc = result.get("risk_contributions")
    return PortfolioResult(
        weights={k: float(v) for k, v in result["weights"].items()},
        ann_return=float(result["return"]),
        ann_volatility=float(result["volatility"]),
        sharpe=float(result["sharpe"]),
        success=bool(result.get("success", True)),
        weight_std=(
            {name: float(std) for name, std in zip(asset_names, weight_std)}
            if weight_std is not None
            else None
        ),
        cvar=float(cvar) if cvar is not None else None,
        risk_contributions=(
            {k: float(v) for k, v in risk_rc.items()}
            if risk_rc is not None
            else None
        ),
    )


def _resolve_expected_returns(
    req: OptimizeRequest, keys: list[str], returns: pd.DataFrame, locale: str = "zh"
) -> tuple[Optional[pd.Series], Optional[list[str]]]:
    """Resolve the expected-return vector for expected_return_source='cme'.

    Maps CME asset classes onto the optimizer universe by proxy ticker
    (CME_TICKER_TO_OPTIMIZER_ASSET); uncovered assets keep their sample
    mean and are reported for disclosure. Returns (None, None) under the
    default sample source. Raises 422 for black-litterman (equilibrium μ
    conflicts) and 502 when every CME data source has failed.
    """
    if req.expected_return_source != "cme":
        return None, None
    if req.method == "black-litterman":
        raise HTTPException(
            status_code=422, detail=msg("portfolio.cme_source_not_bl", locale)
        )
    try:
        cme_report, _cache_status = compute_cme()
    except RuntimeError:
        raise HTTPException(
            status_code=502, detail=msg("portfolio.cme_unavailable", locale)
        ) from None

    cme_by_key = {}
    for ac in cme_report.asset_classes:
        opt_key = CME_TICKER_TO_OPTIMIZER_ASSET.get(ac.ticker)
        if opt_key:
            cme_by_key[opt_key] = ac.expected_return

    sample_means = returns.mean() * TRADING_DAYS_PER_YEAR
    values = {}
    fallback: list[str] = []
    for key in keys:
        name = DEFAULT_ASSET_CLASSES[key]["name"]
        if key in cme_by_key:
            values[name] = float(cme_by_key[key])
        else:
            values[name] = float(sample_means[name])
            fallback.append(name)
    return pd.Series(values), fallback


def _resolve_risk_constraints(
    req: OptimizeRequest, session: Session, locale: str = "zh"
) -> Optional[RiskConstraintsInfo]:
    """Resolve a request's profile_id into risk-level group caps (fail fast).

    Returns None when no profile_id is given. Raises 404 for a missing
    profile, 422 when the stored tolerance label is unknown or the method
    is not classic MVO. Pure metadata — safe to resolve before handing the
    request to a background executor (no session use off the event loop).
    """
    if req.profile_id is None:
        return None
    if req.method == "surplus":
        # With the surplus method, profile_id drives liability derivation
        # (see _resolve_surplus_raw), not risk-level group caps.
        return None
    record = session.get(ProfileRecord, req.profile_id)
    if record is None:
        raise HTTPException(
            status_code=404, detail=msg("common.profile_not_found", locale, id=req.profile_id)
        )
    tolerance_level = (record.data.get("risk_profile") or {}).get("tolerance_level") or ""
    try:
        caps = caps_for_tolerance(tolerance_level, locale)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if req.method != "mvo":
        raise HTTPException(
            status_code=422, detail=msg("portfolio.risk_constraints_mvo_only", locale)
        )
    return RiskConstraintsInfo(
        profile_id=record.id,
        profile_name=record.name,
        risk_level=tolerance_level,
        caps=caps,
    )


def _resolve_surplus_raw(
    req: OptimizeRequest, session: Session, locale: str = "zh"
) -> Optional[dict]:
    """Resolve the raw liability inputs for the surplus method (fail fast).

    Pure metadata resolved in the endpoint (DB access) so background
    executors never touch a session — same pattern as
    _resolve_risk_constraints. The liability growth rate is intentionally
    NOT resolved here: the risk-free leg is only known after data prep.

    Returns None for non-surplus methods. Raises 404 for a missing
    profile, 422 for unusable liability inputs.
    """
    if req.method != "surplus":
        return None

    cfg = req.surplus  # None → defaults below
    proxy = (cfg.proxy if cfg else None) or LDI_DEFAULT_PROXY
    if proxy not in LDI_PROXY_DURATIONS:
        raise HTTPException(
            status_code=422,
            detail=msg(
                "portfolio.surplus_invalid_proxy", locale,
                proxy=proxy, options=", ".join(LDI_PROXY_DURATIONS),
            ),
        )
    growth_source = cfg.growth_source if cfg else "inflation"

    # Explicit channel wins when both liability numbers are supplied.
    if cfg and cfg.liability_ratio is not None and cfg.liability_duration is not None:
        return {
            "source": "manual",
            "liability_ratio": float(cfg.liability_ratio),
            "liability_duration": float(cfg.liability_duration),
            "proxy": proxy,
            "growth_source": growth_source,
            "custom_growth": cfg.custom_growth,
            "inflation_preset": cfg.inflation_preset,
            "age": None,
        }

    # Retirement-income channel: an inflation-linked stream from explicit
    # parameters; the asset base comes from the profile's investable
    # assets (when profile_id is given) or the explicit asset_value.
    if (
        cfg
        and cfg.years_to_retirement is not None
        and cfg.distribution_years is not None
        and cfg.annual_income is not None
    ):
        asset_value: Optional[float] = None
        age = None
        if req.profile_id is not None:
            record = session.get(ProfileRecord, req.profile_id)
            if record is None:
                raise HTTPException(
                    status_code=404,
                    detail=msg("common.profile_not_found", locale, id=req.profile_id),
                )
            asset_value = float(
                (record.data.get("financial") or {}).get("investable_assets", 0.0)
            )
            age = record.data.get("age")
            if asset_value <= 0:
                raise HTTPException(
                    status_code=422,
                    detail=msg("portfolio.surplus_profile_unusable", locale),
                )
        elif cfg.asset_value is not None:
            asset_value = float(cfg.asset_value)
        if asset_value is None:
            raise HTTPException(
                status_code=422,
                detail=msg("portfolio.surplus_requires_inputs", locale),
            )
        return {
            "source": "retirement",
            "years_to_retirement": int(cfg.years_to_retirement),
            "distribution_years": int(cfg.distribution_years),
            "annual_income": float(cfg.annual_income),
            "asset_value": asset_value,
            "age": age,
            "proxy": proxy,
            "growth_source": growth_source,
            "custom_growth": cfg.custom_growth,
            "inflation_preset": cfg.inflation_preset,
        }

    # Profile channel: derive the liability stream from goals + assets.
    if req.profile_id is not None:
        record = session.get(ProfileRecord, req.profile_id)
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=msg("common.profile_not_found", locale, id=req.profile_id),
            )
        goals = record.data.get("goals") or []
        investable = float((record.data.get("financial") or {}).get("investable_assets", 0.0))
        usable = any(float(g.get("target_amount", 0.0)) > 0 for g in goals) and investable > 0
        if not usable:
            raise HTTPException(
                status_code=422,
                detail=msg("portfolio.surplus_profile_unusable", locale),
            )
        return {
            "source": "profile",
            "goals": goals,
            "investable_assets": investable,
            "age": record.data.get("age"),
            "proxy": proxy,
            "growth_source": growth_source,
            "custom_growth": cfg.custom_growth if cfg else None,
            "inflation_preset": cfg.inflation_preset if cfg else None,
        }

    raise HTTPException(
        status_code=422, detail=msg("portfolio.surplus_requires_inputs", locale)
    )


def _run_mvo(
    returns: pd.DataFrame, req: OptimizeRequest, group_constraints: Optional[dict] = None,
    expected_returns: Optional[pd.Series] = None,
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Traditional or Resampled (Michaud) MVO. Returns (optimizer, selected,
    max_sharpe, min_vol, frontier, random_portfolios, params_echo).

    When group_constraints is given (classic MVO only), the selected
    portfolio honors those per-group min/max limits while the max_sharpe /
    min_vol control portfolios stay unconstrained as a cost reference.
    """
    optimizer = PortfolioOptimizer(
        returns, risk_free_rate=req.risk_free_rate, expected_returns=expected_returns
    )
    max_sharpe = optimizer.maximize_sharpe(allow_short=req.allow_short)
    min_vol = optimizer.minimize_volatility(allow_short=req.allow_short)

    if req.method == "resampled":
        if req.mode == "max-sharpe":
            selected = optimizer.resampled_maximize_sharpe(
                n_simulations=req.n_simulations, allow_short=req.allow_short
            )
        else:
            selected = optimizer.resampled_minimize_volatility(
                n_simulations=req.n_simulations, allow_short=req.allow_short
            )
        frontier = optimizer.resampled_efficient_frontier(
            n_points=RESAMPLED_FRONTIER_POINTS,
            n_simulations=req.n_simulations,
            allow_short=req.allow_short,
        )
    else:
        if group_constraints:
            if req.mode == "max-sharpe":
                selected = optimizer.maximize_sharpe(
                    allow_short=req.allow_short, group_constraints=group_constraints
                )
            else:
                selected = optimizer.optimize_with_asset_class_constraints(
                    group_constraints, allow_short=req.allow_short
                )
        else:
            selected = max_sharpe if req.mode == "max-sharpe" else min_vol
        frontier = optimizer.efficient_frontier(
            n_points=FRONTIER_POINTS, allow_short=req.allow_short
        )

    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, {}


def _run_bl(
    returns: pd.DataFrame, req: OptimizeRequest, locale: str = "zh"
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Black-Litterman optimization. Requires at least one view."""
    bl_cfg = req.bl
    views = bl_cfg.views if bl_cfg else []
    if not views:
        raise HTTPException(
            status_code=422,
            detail=msg("portfolio.bl_requires_view", locale),
        )

    keys = _resolve_asset_keys(req.assets, locale)
    names = [DEFAULT_ASSET_CLASSES[k]["name"] for k in keys]
    name_of = dict(zip(keys, names))

    market_weights = None
    if bl_cfg and bl_cfg.market_weights:
        w = np.array([bl_cfg.market_weights.get(k, 0.0) for k in keys], dtype=float)
        if w.sum() > 0:
            market_weights = w / w.sum()

    optimizer = BlackLittermanOptimizer(
        returns,
        risk_free_rate=req.risk_free_rate,
        market_cap_weights=market_weights,
        delta=bl_cfg.delta if bl_cfg else 2.5,
        tau=bl_cfg.tau if bl_cfg else 0.025,
    )

    view_inputs = [
        ViewInput(
            view_type=v.view_type,
            asset_long=name_of.get(v.asset_long, v.asset_long),
            asset_short=(
                name_of.get(v.asset_short, v.asset_short) if v.asset_short else None
            ),
            expected_return=v.expected_return,
            confidence=v.confidence,
        )
        for v in views
    ]
    try:
        optimizer.apply_views(view_inputs, locale=locale)
        max_sharpe = optimizer.bl_maximize_sharpe(allow_short=req.allow_short)
        min_vol = optimizer.bl_minimize_volatility(allow_short=req.allow_short)
        frontier = optimizer.bl_efficient_frontier(
            n_points=FRONTIER_POINTS, allow_short=req.allow_short
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    selected = max_sharpe if req.mode == "max-sharpe" else min_vol
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)

    equilibrium = optimizer.implied_equilibrium_returns()
    posterior = optimizer.mu_bl
    insight = BLInsight(
        equilibrium_returns={n: float(r) for n, r in zip(names, equilibrium)},
        posterior_returns={n: float(r) for n, r in zip(names, posterior)},
    )
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, insight


def _run_cvar(
    returns: pd.DataFrame, req: OptimizeRequest,
    expected_returns: Optional[pd.Series] = None,
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Mean-CVaR optimization (Rockafellar-Uryasev LP on daily scenarios).

    A single frontier solve feeds both the chart and the max-STARR
    reference point. Mode mapping: min-vol → the global min-CVaR
    portfolio; max-sharpe → the frontier point maximizing
    (return − rf) / CVaR (Stable Tail Adjusted Return Ratio).
    """
    optimizer = PortfolioOptimizer(returns, risk_free_rate=req.risk_free_rate, expected_returns=expected_returns)
    beta = req.cvar_confidence

    frontier = optimizer.cvar_efficient_frontier(
        n_points=FRONTIER_POINTS, beta=beta, allow_short=req.allow_short
    )
    min_cvar = optimizer.minimize_cvar(beta=beta, allow_short=req.allow_short)

    # Max-STARR reference: the frontier point with the best return per
    # unit of tail loss. Falls back to the min-CVaR portfolio when every
    # frontier target was infeasible (the downstream empty-frontier check
    # then surfaces a clean 422).
    max_ratio = min_cvar
    if not frontier.empty:
        weight_cols = [
            c for c in frontier.columns
            if c not in ("return", "volatility", "sharpe", "cvar")
        ]
        ratio = (frontier["return"] - optimizer.risk_free_rate) / frontier["cvar"]
        best = frontier.loc[ratio.idxmax()]
        max_ratio = {
            "weights": {name: float(best[name]) for name in weight_cols},
            "return": float(best["return"]),
            "volatility": float(best["volatility"]),
            "sharpe": float(best["sharpe"]),
            "cvar": float(best["cvar"]),
            "success": True,
        }

    max_sharpe = max_ratio
    min_vol = min_cvar
    selected = max_ratio if req.mode == "max-sharpe" else min_cvar
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, {}


def _run_surplus(
    returns: pd.DataFrame,
    req: OptimizeRequest,
    rf: float,
    surplus_raw: dict,
    proxy_returns: Optional[pd.Series],
    expected_returns: Optional[pd.Series] = None,
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """LDI surplus optimization (Sharpe-Tint): assets minus liabilities.

    Three liability channels — explicit ratio/duration, profile goals
    (nominal, discounted at rf, drift μ_L = rf), and the retirement
    income stream (inflation-linked at the resolved growth g, discounted
    at rf, drift μ_L = g). Liability risk stats come from the
    duration-scaled bond proxy; returns the standard tuple with a
    SurplusInsight in the extra slot.
    """
    # Liability growth rate g — the escalation rate of inflation-linked
    # cash flows (the retirement stream; the manual channel also uses it
    # as drift). The liability discount rate y is always the risk-free
    # leg rf, and nominal goal streams drift at y — see liabilities.py.
    growth_source = surplus_raw["growth_source"]
    if growth_source == "risk_free":
        growth = rf
    elif growth_source == "custom":
        growth = float(surplus_raw["custom_growth"])
    else:  # inflation — personal preset (age-suggested on profile channels)
        preset = surplus_raw.get("inflation_preset")
        if preset is None:
            preset = suggest_inflation_preset(surplus_raw.get("age"))
        growth = resolve_personal_inflation(CME_INFLATION_ASSUMPTION, preset)

    # Liability spec per channel: ratio k = L/A, duration, drift μ_L.
    # Discounting: ChinaBond treasury curve when the provider cascade has
    # one, otherwise the flat risk-free leg.
    curve, discount_source = _effective_discount_curve()
    discount = curve if curve is not None else rf

    source = surplus_raw["source"]
    cash_flows: Optional[int] = None
    horizon: Optional[float] = None
    if source == "manual":
        k = surplus_raw["liability_ratio"]
        duration = surplus_raw["liability_duration"]
        mu_L = growth
    elif source == "profile":
        pv, duration = goals_to_liability(surplus_raw["goals"], discount)
        k = pv / surplus_raw["investable_assets"]
        mu_L = rf
        positive = [
            g for g in surplus_raw["goals"]
            if float(g.get("target_amount", 0.0)) > 0
        ]
        cash_flows = len(positive)
        horizon = float(max(int(g.get("years", 0)) for g in positive))
    else:  # retirement — inflation-linked income stream
        flows = retirement_income_stream(
            surplus_raw["years_to_retirement"],
            surplus_raw["distribution_years"],
            surplus_raw["annual_income"],
        )
        pv, duration = stream_to_liability(flows, discount, growth)
        k = pv / surplus_raw["asset_value"]
        mu_L = growth
        cash_flows = len(flows)
        horizon = float(flows[-1][1])

    # Representative discount rate: curve rate at the liability duration.
    discount_rate_value = (
        float(rate_at(curve, duration)) if curve is not None else float(rf)
    )

    # Liability stats via the duration-scaled bond proxy
    proxy_key = surplus_raw["proxy"]
    if proxy_returns is None:
        # Proxy already sits inside the requested universe.
        proxy_returns = returns[DEFAULT_ASSET_CLASSES[proxy_key]["name"]]
    mu_L, sigma_L, cov_vec = estimate_liability_stats(
        proxy_returns,
        returns,
        proxy_duration=LDI_PROXY_DURATIONS[proxy_key],
        liability_duration=duration,
        growth_rate=mu_L,
    )

    optimizer = PortfolioOptimizer(returns, risk_free_rate=req.risk_free_rate, expected_returns=expected_returns)
    max_sharpe = optimizer.maximize_surplus_sharpe(
        k, mu_L, sigma_L, cov_vec, allow_short=req.allow_short
    )
    min_vol = optimizer.minimize_surplus_volatility(
        k, mu_L, sigma_L, cov_vec, allow_short=req.allow_short
    )
    frontier = optimizer.surplus_efficient_frontier(
        k, mu_L, sigma_L, cov_vec,
        n_points=FRONTIER_POINTS, allow_short=req.allow_short,
    )
    selected = max_sharpe if req.mode == "max-sharpe" else min_vol
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)

    insight = SurplusInsight(
        liability_ratio=float(k),
        funding_ratio=float(1.0 / k),
        liability_duration=float(duration),
        liability_growth=float(mu_L),
        discount_rate=discount_rate_value,
        discount_source=discount_source,
        proxy=proxy_key,
        source=source,
        cash_flows=cash_flows,
        horizon_years=horizon,
    )
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, insight


def _run_risk_parity(
    returns: pd.DataFrame,
    req: OptimizeRequest,
    expected_returns: Optional[pd.Series] = None,
    locale: str = "zh",
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Risk parity (Equal Risk Contribution).

    The ERC portfolio is return-agnostic, so mode does not apply: the
    selected slot carries the ERC portfolio while the max_sharpe/min_vol
    slots hold classic MVO portfolios as benchmarks on the same efficient
    frontier. Long-only by construction (Spinu log-barrier).
    """
    if req.allow_short:
        raise HTTPException(
            status_code=422, detail=msg("portfolio.rp_long_only", locale)
        )
    optimizer = PortfolioOptimizer(
        returns, risk_free_rate=req.risk_free_rate,
        expected_returns=expected_returns,
    )
    selected = optimizer.risk_parity()
    max_sharpe = optimizer.maximize_sharpe(allow_short=False)
    min_vol = optimizer.minimize_volatility(allow_short=False)
    frontier = optimizer.efficient_frontier(
        n_points=FRONTIER_POINTS, allow_short=False
    )
    random_ports = optimizer.random_portfolios(n_portfolios=RANDOM_PORTFOLIOS)
    return optimizer, selected, max_sharpe, min_vol, frontier, random_ports, {}


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Run portfolio optimization (MVO / Resampled / Black-Litterman / Mean-CVaR / Surplus / Risk-Parity)",
)
def optimize(
    req: OptimizeRequest, request: Request, session: Session = Depends(get_session)
) -> OptimizeResponse:
    locale = get_request_locale(request)
    risk_info = _resolve_risk_constraints(req, session, locale)
    surplus_raw = _resolve_surplus_raw(req, session, locale)
    keys, returns, rf, proxy_returns = _prepare_optimize(req, locale)
    return _solve_optimize(
        req, keys, returns, rf, risk_info, locale, surplus_raw, proxy_returns
    )


def _prepare_optimize(
    req: OptimizeRequest, locale: str = "zh"
) -> tuple[list[str], pd.DataFrame, float, Optional[pd.Series]]:
    """Resolve asset keys, fetch returns (TTL-cached) and the risk-free rate.

    For the surplus method the bond proxy is appended to the same fetch
    when it is not already in the universe, so its series is date-aligned
    with the assets and shares the same TTL cache entry; the proxy column
    is split back out (4th return value) before the optimizer sees the
    frame. Non-surplus methods always return None for it.
    """
    keys = _resolve_asset_keys(req.assets, locale)
    fetch_keys = list(keys)
    extra_proxy_key = None
    if req.method == "surplus":
        proxy_key = (req.surplus.proxy if req.surplus else None) or LDI_DEFAULT_PROXY
        if proxy_key not in fetch_keys:
            fetch_keys.append(proxy_key)
            extra_proxy_key = proxy_key
    returns = _fetch_returns(fetch_keys, req.period, locale)
    proxy_returns = None
    if extra_proxy_key is not None:
        proxy_col = DEFAULT_ASSET_CLASSES[extra_proxy_key]["name"]
        proxy_returns = returns[proxy_col]
        returns = returns.drop(columns=[proxy_col])
    rf = _effective_risk_free_rate(req.risk_free_rate)
    return keys, returns, rf, proxy_returns


def _solve_optimize(
    req: OptimizeRequest,
    keys: list[str],
    returns: pd.DataFrame,
    rf: float,
    risk_constraints: Optional[RiskConstraintsInfo] = None,
    locale: str = "zh",
    surplus_raw: Optional[dict] = None,
    proxy_returns: Optional[pd.Series] = None,
) -> OptimizeResponse:
    """The CPU-heavy half: optimize, build charts, assemble the response."""
    req.risk_free_rate = rf

    # Risk caps apply to classic MVO only; groups absent from the selected
    # universe yield no constraint, in which case nothing is reported.
    group_constraints = None
    if risk_constraints is not None and req.method == "mvo":
        group_constraints = build_group_constraints(risk_constraints.caps, keys)

    # CME-sourced expected returns (default: historical sample means).
    expected_returns, cme_fallback = _resolve_expected_returns(req, keys, returns, locale)

    if req.method == "black-litterman":
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra = (
            _run_bl(returns, req, locale)
        )
    elif req.method == "mean-cvar":
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra = (
            _run_cvar(returns, req, expected_returns)
        )
    elif req.method == "surplus":
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra = (
            _run_surplus(returns, req, rf, surplus_raw, proxy_returns, expected_returns)
        )
    elif req.method == "risk-parity":
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra = (
            _run_risk_parity(returns, req, expected_returns, locale)
        )
    else:
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, extra = (
            _run_mvo(returns, req, group_constraints, expected_returns)
        )

    # Every frontier point failing to solve yields an empty/malformed frame;
    # surface a clean 422 instead of a downstream KeyError.
    if frontier.empty or "volatility" not in frontier.columns:
        raise HTTPException(
            status_code=422,
            detail=msg("portfolio.frontier_failed", locale),
        )

    asset_names = list(returns.columns)
    frontier_fig = plot_efficient_frontier(
        frontier=frontier,
        random_portfolios=random_ports,
        max_sharpe=max_sharpe,
        min_vol=min_vol,
        # No CAL on the surplus frontier: a surplus is not an investment
        # scalable at the risk-free rate, so the ray would be misleading.
        risk_free_rate=None if req.method == "surplus" else req.risk_free_rate,
    )
    allocation_fig = plot_allocation_pie(
        selected["weights"], title="Asset Allocation — Selected Portfolio"
    )

    asset_stats = [
        AssetStat(
            key=k,
            ticker=DEFAULT_ASSET_CLASSES[k]["ticker"],
            name=DEFAULT_ASSET_CLASSES[k]["name"],
            ann_return=float(optimizer.mean_returns[DEFAULT_ASSET_CLASSES[k]["name"]]),
            ann_volatility=float(
                np.sqrt(optimizer.cov_matrix.loc[DEFAULT_ASSET_CLASSES[k]["name"], DEFAULT_ASSET_CLASSES[k]["name"]])
            ),
        )
        for k in keys
    ]

    return OptimizeResponse(
        as_of=datetime.now(timezone.utc),
        params={
            "assets": keys,
            "period": req.period,
            "risk_free_rate": req.risk_free_rate,
            "method": req.method,
            "mode": req.mode,
            "allow_short": req.allow_short,
            "n_simulations": req.n_simulations if req.method == "resampled" else None,
            "cvar_confidence": (
                req.cvar_confidence if req.method == "mean-cvar" else None
            ),
            "expected_return_source": req.expected_return_source,
            "cme_fallback_assets": cme_fallback,
            "trading_days": int(len(returns)),
        },
        selected=_result_payload(selected, asset_names),
        max_sharpe=_result_payload(max_sharpe, asset_names),
        min_vol=_result_payload(min_vol, asset_names),
        frontier_chart=_fig_json(frontier_fig),
        allocation_chart=_fig_json(allocation_fig),
        asset_stats=asset_stats,
        bl=extra if isinstance(extra, BLInsight) else None,
        surplus=extra if isinstance(extra, SurplusInsight) else None,
        risk_constraints=risk_constraints if group_constraints else None,
    )


# ---------------------------------------------------------------------------
# Async optimization tasks (Phase 5c — resampled MVO is minute-level)
# ---------------------------------------------------------------------------

registry = TaskRegistry()


async def _run_optimize_task(
    task: BackgroundTask,
    req: OptimizeRequest,
    risk_constraints: Optional[RiskConstraintsInfo] = None,
    locale: str = "zh",
    surplus_raw: Optional[dict] = None,
) -> None:
    """Fetch data, then optimize in an executor (CPU-heavy) with progress events.

    risk_constraints / surplus_raw are resolved in the endpoint (DB access)
    before the task is created, so the executor threads never touch a session.
    """
    try:
        loop = asyncio.get_running_loop()
        await task.publish(
            {"type": "node", "node": "fetch", "label": msg("portfolio.node_fetch", locale)}
        )
        keys, returns, rf, proxy_returns = await loop.run_in_executor(
            None, _prepare_optimize, req, locale
        )
        label = (
            msg("portfolio.node_solve_resampled", locale, n_simulations=req.n_simulations)
            if req.method == "resampled"
            else msg("portfolio.node_solve", locale)
        )
        await task.publish({"type": "node", "node": "solve", "label": label})
        result = await loop.run_in_executor(
            None, _solve_optimize, req, keys, returns, rf, risk_constraints,
            locale, surplus_raw, proxy_returns,
        )
        task.status = "completed"
        await task.publish({"type": "done", "result": result.model_dump(mode="json")})
    except HTTPException as e:
        task.status = "failed"
        await task.publish({"type": "error", "message": str(e.detail)})
    except Exception as e:
        task.status = "failed"
        await task.publish(
            {"type": "error", "message": msg("portfolio.optimize_failed", locale, error=e)}
        )


@router.post(
    "/optimize/async",
    response_model=PortfolioTaskCreatedResponse,
    status_code=202,
    summary="Create an async optimization task; poll /tasks/{id}/events (SSE)",
)
async def optimize_async(
    req: OptimizeRequest, request: Request, session: Session = Depends(get_session)
) -> PortfolioTaskCreatedResponse:
    locale = get_request_locale(request)
    # Validate everything that doesn't need market data up front, so bad
    # requests fail fast with 422 instead of surfacing on the event stream.
    _resolve_asset_keys(req.assets, locale)
    if req.method == "black-litterman" and not (req.bl and req.bl.views):
        raise HTTPException(
            status_code=422,
            detail=msg("portfolio.bl_requires_view", locale),
        )
    if req.method == "black-litterman" and req.expected_return_source == "cme":
        raise HTTPException(
            status_code=422,
            detail=msg("portfolio.cme_source_not_bl", locale),
        )
    if req.method == "risk-parity" and req.allow_short:
        raise HTTPException(
            status_code=422,
            detail=msg("portfolio.rp_long_only", locale),
        )
    # Profile lookup + cap resolution happen here, not in the executor.
    risk_info = _resolve_risk_constraints(req, session, locale)
    surplus_raw = _resolve_surplus_raw(req, session, locale)
    task = registry.create(
        "optimize", method=req.method, n_simulations=req.n_simulations
    )
    asyncio.create_task(_run_optimize_task(task, req, risk_info, locale, surplus_raw))
    return PortfolioTaskCreatedResponse(task_id=task.task_id)


@router.get("/tasks/{task_id}/events")
async def optimize_task_events(task_id: str, request: Request) -> StreamingResponse:
    stream = task_events_stream(registry, task_id, get_request_locale(request))
    if stream is None:
        raise HTTPException(
            status_code=404, detail=msg("common.task_not_found", get_request_locale(request))
        )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
