"""
Portfolio optimization endpoints.

POST /api/portfolio/optimize wraps the MVO / Resampled-MVO / Black-Litterman
engines in src.portfolio.optimizer, mirroring the call sequence of the
Streamlit optimizer page. Returns portfolio metrics plus Plotly figures
(efficient frontier + CAL, allocation pie) ready for plotly.js.

POST /api/portfolio/optimize/async runs the same computation as a background
task (Phase 5c) with SSE progress on GET /api/portfolio/tasks/{id}/events —
the resampled method is minute-level (n_simulations × n_points SLSQP solves)
and would otherwise hold an HTTP request open the whole time.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from api.cache import TTLCache
from api.db import ProfileRecord, get_session
from api.profile_convert import profile_from_data
from api.routers.market import _fig_json
from api.schemas import (
    AssetClassInfo,
    AssetClassesResponse,
    AssetStat,
    BLInsight,
    OptimizeRequest,
    OptimizeResponse,
    PortfolioResult,
    PortfolioTaskCreatedResponse,
    RecommendationResponse,
    RiskConstraintsInfo,
)
from api.tasks import (
    BackgroundTask,
    TaskRegistry,
    task_events_stream,
)
from src.agents.portfolio_recommender import recommend_portfolio
from src.config import DEFAULT_ASSET_CLASSES
from src.data.market_data import (
    compute_returns,
    fetch_price_history,
    fetch_risk_free_rate,
)
from src.portfolio.optimizer import BlackLittermanOptimizer, PortfolioOptimizer
from src.portfolio.risk_constraints import build_group_constraints, caps_for_tolerance
from src.portfolio.views import ViewInput
from src.visualization.charts import plot_allocation_pie, plot_efficient_frontier

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

_prices_cache: TTLCache = TTLCache()
_rf_cache: TTLCache = TTLCache()

PRICES_TTL_SECONDS = 300
RISK_FREE_RATE_TTL_SECONDS = 3600
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
    profile_id: int, session: Session = Depends(get_session)
) -> RecommendationResponse:
    """Risk-score-driven allocation from src portfolio_recommender: the
    profile's final score maps to a target volatility, and the MVO engine
    solves the min-volatility portfolio (goal-aware) on the full universe."""
    record = session.get(ProfileRecord, profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"画像不存在（id={profile_id}）")
    profile = profile_from_data(record.data)

    returns = _fetch_returns(list(DEFAULT_ASSET_CLASSES.keys()), "5y")
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
    )


def _resolve_asset_keys(requested: list[str]) -> list[str]:
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
            detail="At least 2 valid asset classes are required. Valid keys: "
            + ", ".join(DEFAULT_ASSET_CLASSES.keys()),
        )
    return keys


def _fetch_returns(keys: list[str], period: str) -> pd.DataFrame:
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
                detail=f"行情数据获取失败（{', '.join(bad)}），请稍后重试。",
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
    return _rf_cache.get_or_set("rf", RISK_FREE_RATE_TTL_SECONDS, fetch_risk_free_rate)


def _result_payload(result: dict, asset_names: list[str]) -> PortfolioResult:
    """Normalize an optimizer result-dict into the API schema."""
    weight_std = result.get("weight_std")
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
    )


def _resolve_risk_constraints(
    req: OptimizeRequest, session: Session
) -> Optional[RiskConstraintsInfo]:
    """Resolve a request's profile_id into risk-level group caps (fail fast).

    Returns None when no profile_id is given. Raises 404 for a missing
    profile, 422 when the stored tolerance label is unknown or the method
    is not classic MVO. Pure metadata — safe to resolve before handing the
    request to a background executor (no session use off the event loop).
    """
    if req.profile_id is None:
        return None
    record = session.get(ProfileRecord, req.profile_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"画像不存在（id={req.profile_id}）")
    tolerance_level = (record.data.get("risk_profile") or {}).get("tolerance_level") or ""
    try:
        caps = caps_for_tolerance(tolerance_level)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    if req.method != "mvo":
        raise HTTPException(status_code=422, detail="风险约束当前仅支持经典 MVO 方法")
    return RiskConstraintsInfo(
        profile_id=record.id,
        profile_name=record.name,
        risk_level=tolerance_level,
        caps=caps,
    )


def _run_mvo(
    returns: pd.DataFrame, req: OptimizeRequest, group_constraints: Optional[dict] = None
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Traditional or Resampled (Michaud) MVO. Returns (optimizer, selected,
    max_sharpe, min_vol, frontier, random_portfolios, params_echo).

    When group_constraints is given (classic MVO only), the selected
    portfolio honors those per-group min/max limits while the max_sharpe /
    min_vol control portfolios stay unconstrained as a cost reference.
    """
    optimizer = PortfolioOptimizer(returns, risk_free_rate=req.risk_free_rate)
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
    returns: pd.DataFrame, req: OptimizeRequest
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Black-Litterman optimization. Requires at least one view."""
    bl_cfg = req.bl
    views = bl_cfg.views if bl_cfg else []
    if not views:
        raise HTTPException(
            status_code=422,
            detail="Black-Litterman requires at least one investor view "
            "(bl.views must be non-empty).",
        )

    keys = _resolve_asset_keys(req.assets)
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
        optimizer.apply_views(view_inputs)
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


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Run portfolio optimization (MVO / Resampled / Black-Litterman)",
)
def optimize(req: OptimizeRequest, session: Session = Depends(get_session)) -> OptimizeResponse:
    risk_info = _resolve_risk_constraints(req, session)
    keys, returns, rf = _prepare_optimize(req)
    return _solve_optimize(req, keys, returns, rf, risk_info)


def _prepare_optimize(req: OptimizeRequest) -> tuple[list[str], pd.DataFrame, float]:
    """Resolve asset keys, fetch returns (TTL-cached) and the risk-free rate."""
    keys = _resolve_asset_keys(req.assets)
    returns = _fetch_returns(keys, req.period)
    rf = _effective_risk_free_rate(req.risk_free_rate)
    return keys, returns, rf


def _solve_optimize(
    req: OptimizeRequest,
    keys: list[str],
    returns: pd.DataFrame,
    rf: float,
    risk_constraints: Optional[RiskConstraintsInfo] = None,
) -> OptimizeResponse:
    """The CPU-heavy half: optimize, build charts, assemble the response."""
    req.risk_free_rate = rf

    # Risk caps apply to classic MVO only; groups absent from the selected
    # universe yield no constraint, in which case nothing is reported.
    group_constraints = None
    if risk_constraints is not None and req.method == "mvo":
        group_constraints = build_group_constraints(risk_constraints.caps, keys)

    if req.method == "black-litterman":
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, bl_extra = (
            _run_bl(returns, req)
        )
    else:
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, bl_extra = (
            _run_mvo(returns, req, group_constraints)
        )

    # Every frontier point failing to solve yields an empty/malformed frame;
    # surface a clean 422 instead of a downstream KeyError.
    if frontier.empty or "volatility" not in frontier.columns:
        raise HTTPException(
            status_code=422,
            detail="有效前沿求解失败：当前资产组合在该历史窗口下无法构成有效前沿，"
            "请调整资产选择或历史窗口。",
        )

    asset_names = list(returns.columns)
    frontier_fig = plot_efficient_frontier(
        frontier=frontier,
        random_portfolios=random_ports,
        max_sharpe=max_sharpe,
        min_vol=min_vol,
        risk_free_rate=req.risk_free_rate,
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
            "trading_days": int(len(returns)),
        },
        selected=_result_payload(selected, asset_names),
        max_sharpe=_result_payload(max_sharpe, asset_names),
        min_vol=_result_payload(min_vol, asset_names),
        frontier_chart=_fig_json(frontier_fig),
        allocation_chart=_fig_json(allocation_fig),
        asset_stats=asset_stats,
        bl=bl_extra if isinstance(bl_extra, BLInsight) else None,
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
) -> None:
    """Fetch data, then optimize in an executor (CPU-heavy) with progress events.

    risk_constraints is resolved in the endpoint (DB access) before the task
    is created, so the executor threads never touch a session.
    """
    try:
        loop = asyncio.get_running_loop()
        await task.publish({"type": "node", "node": "fetch", "label": "获取行情数据"})
        keys, returns, rf = await loop.run_in_executor(None, _prepare_optimize, req)
        label = (
            f"重采样优化计算中（{req.n_simulations} 次模拟，通常需要数分钟）"
            if req.method == "resampled"
            else "组合优化计算中"
        )
        await task.publish({"type": "node", "node": "solve", "label": label})
        result = await loop.run_in_executor(
            None, _solve_optimize, req, keys, returns, rf, risk_constraints
        )
        task.status = "completed"
        await task.publish({"type": "done", "result": result.model_dump(mode="json")})
    except HTTPException as e:
        task.status = "failed"
        await task.publish({"type": "error", "message": str(e.detail)})
    except Exception as e:
        task.status = "failed"
        await task.publish({"type": "error", "message": f"优化失败: {e}"})


@router.post(
    "/optimize/async",
    response_model=PortfolioTaskCreatedResponse,
    status_code=202,
    summary="Create an async optimization task; poll /tasks/{id}/events (SSE)",
)
async def optimize_async(
    req: OptimizeRequest, session: Session = Depends(get_session)
) -> PortfolioTaskCreatedResponse:
    # Validate everything that doesn't need market data up front, so bad
    # requests fail fast with 422 instead of surfacing on the event stream.
    _resolve_asset_keys(req.assets)
    if req.method == "black-litterman" and not (req.bl and req.bl.views):
        raise HTTPException(
            status_code=422,
            detail="Black-Litterman requires at least one investor view "
            "(bl.views must be non-empty).",
        )
    # Profile lookup + cap resolution happen here, not in the executor.
    risk_info = _resolve_risk_constraints(req, session)
    task = registry.create(
        "optimize", method=req.method, n_simulations=req.n_simulations
    )
    asyncio.create_task(_run_optimize_task(task, req, risk_info))
    return PortfolioTaskCreatedResponse(task_id=task.task_id)


@router.get("/tasks/{task_id}/events")
async def optimize_task_events(task_id: str) -> StreamingResponse:
    stream = task_events_stream(registry, task_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
