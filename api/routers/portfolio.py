"""
Portfolio optimization endpoints.

POST /api/portfolio/optimize wraps the MVO / Resampled-MVO / Black-Litterman
engines in src.portfolio.optimizer, mirroring the call sequence of the
Streamlit optimizer page. Returns portfolio metrics plus Plotly figures
(efficient frontier + CAL, allocation pie) ready for plotly.js.

These are heavy synchronous computations (frontier = dozens of SLSQP solves;
resampled adds n_simulations × n_points). Acceptable for a local tool with
a loading state — Phase 4 will move long runs to background jobs.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException

from api.cache import TTLCache
from api.routers.market import _fig_json
from api.schemas import (
    AssetClassInfo,
    AssetClassesResponse,
    AssetStat,
    BLInsight,
    OptimizeRequest,
    OptimizeResponse,
    PortfolioResult,
)
from src.config import DEFAULT_ASSET_CLASSES
from src.data.market_data import (
    compute_returns,
    fetch_price_history,
    fetch_risk_free_rate,
)
from src.portfolio.optimizer import BlackLittermanOptimizer, PortfolioOptimizer
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
    prices = _prices_cache.get_or_set(
        cache_key,
        PRICES_TTL_SECONDS,
        lambda: fetch_price_history(tickers, period=period),
    )
    if prices.empty:
        raise HTTPException(
            status_code=502,
            detail="No price data returned from the market data provider.",
        )
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


def _run_mvo(
    returns: pd.DataFrame, req: OptimizeRequest
) -> tuple[PortfolioOptimizer, dict, dict, dict, pd.DataFrame, pd.DataFrame, dict]:
    """Traditional or Resampled (Michaud) MVO. Returns (optimizer, selected,
    max_sharpe, min_vol, frontier, random_portfolios, params_echo)."""
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
def optimize(req: OptimizeRequest) -> OptimizeResponse:
    keys = _resolve_asset_keys(req.assets)
    returns = _fetch_returns(keys, req.period)
    req.risk_free_rate = _effective_risk_free_rate(req.risk_free_rate)

    if req.method == "black-litterman":
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, bl_extra = (
            _run_bl(returns, req)
        )
    else:
        optimizer, selected, max_sharpe, min_vol, frontier, random_ports, bl_extra = (
            _run_mvo(returns, req)
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
    )
