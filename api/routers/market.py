"""
Read-only market data endpoints: universe metadata, quotes, risk-free rate,
and the aggregated dashboard analytics bundle.

All endpoints are thin wrappers over src.data / src.visualization / src.portfolio.
They are declared with plain `def` so FastAPI runs them in a threadpool — the
underlying yfinance calls are blocking I/O.
"""

import json
import math
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from api.cache import TTLCache
from api.schemas import (
    AnalyticsResponse,
    AssetInfo,
    Quote,
    QuotesResponse,
    RiskFreeRateResponse,
    RiskStat,
    UniverseResponse,
)
from src.config import ASSET_UNIVERSE, TRADING_DAYS_PER_YEAR
from src.data.market_data import (
    compute_correlation_matrix,
    compute_returns,
    fetch_price_history,
    fetch_risk_free_rate,
    get_latest_quotes,
)
from src.portfolio.risk_metrics import max_drawdown, sharpe_ratio, value_at_risk
from src.visualization.charts import plot_correlation_heatmap, plot_price_history

router = APIRouter(prefix="/market", tags=["market"])

_quotes_cache: TTLCache = TTLCache()
_rf_cache: TTLCache = TTLCache()
_analytics_cache: TTLCache = TTLCache()

QUOTES_TTL_SECONDS = 300  # 5 min — matches a dashboard's freshness expectations
ANALYTICS_TTL_SECONDS = 300
RISK_FREE_RATE_TTL_SECONDS = 3600  # 1 h — the rate moves slowly

# Mirrors the analysis horizons offered by the Streamlit dashboard.
VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "3y", "5y"}


def _parse_tickers(tickers: Optional[str]) -> list[str]:
    """Parse a comma-separated ticker list, filtering to the known universe."""
    if not tickers:
        return list(ASSET_UNIVERSE.keys())
    requested = [t.strip() for t in tickers.split(",") if t.strip()]
    valid = [t for t in requested if t in ASSET_UNIVERSE]
    if not valid:
        raise HTTPException(
            status_code=400,
            detail="No valid tickers provided. Valid tickers: "
            + ", ".join(ASSET_UNIVERSE.keys()),
        )
    return valid


def _clean_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to JSON-safe records (NaN -> None)."""
    records = []
    for row in df.to_dict(orient="records"):
        records.append({k: (None if pd.isna(v) else v) for k, v in row.items()})
    return records


def _with_display_meta(record: dict) -> dict:
    """Attach ASSET_UNIVERSE display metadata (currency/symbol/color) to a quote row."""
    info = ASSET_UNIVERSE.get(record.get("ticker", ""), {})
    return {
        **record,
        "currency": info.get("currency", "USD"),
        "symbol": info.get("symbol", ""),
        "color": info.get("color", "#D4AF37"),
    }


def _sanitize(obj: Any) -> Any:
    """Recursively replace NaN/Inf floats with None for strict-JSON safety."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


def _fig_json(fig) -> dict:
    """Serialize a Plotly figure to a JSON-safe dict.

    fig.to_json() already encodes NaN as null and numpy arrays as base64
    typed arrays (decoded natively by plotly.js); _sanitize is defense-in-depth.
    """
    return _sanitize(json.loads(fig.to_json()))


def _compute_stats(prices: pd.DataFrame) -> list[dict]:
    """Per-asset annualized return/volatility, Sharpe, max drawdown, daily VaR."""
    returns_df = compute_returns(prices, method="simple")
    records: list[dict] = []
    for col in returns_df.columns:
        ret = returns_df[col].dropna()
        price_series = prices[col].dropna()
        if len(ret) < 20:
            continue
        info = ASSET_UNIVERSE.get(col, {})
        records.append(
            {
                "ticker": col,
                "name": info.get("name", col),
                "ann_return": float(ret.mean() * TRADING_DAYS_PER_YEAR),
                "ann_volatility": float(ret.std() * np.sqrt(TRADING_DAYS_PER_YEAR)),
                "sharpe": float(sharpe_ratio(ret)),
                "max_drawdown": float(max_drawdown(price_series)["max_drawdown"]),
                "var_95": float(value_at_risk(ret, confidence=0.95)),
            }
        )
    return records


def _build_analytics(tickers: list[str], period: str) -> dict:
    """Fetch prices and build the full analytics payload (charts + stats)."""
    prices = fetch_price_history(tickers, period=period)
    if prices.empty:
        raise HTTPException(
            status_code=502,
            detail="No price data returned from the market data provider.",
        )

    price_fig = plot_price_history(
        prices, normalize=False, title=f"Asset Performance — {period}"
    )
    corr_fig = None
    if prices.shape[1] >= 2:
        corr_fig = plot_correlation_heatmap(compute_correlation_matrix(prices))

    return {
        "period": period,
        "tickers": tickers,
        "as_of": datetime.now(timezone.utc),
        "price_chart": _fig_json(price_fig),
        "correlation_chart": _fig_json(corr_fig) if corr_fig is not None else None,
        "stats": _compute_stats(prices),
    }


@router.get(
    "/universe",
    response_model=UniverseResponse,
    summary="Static metadata for the full asset universe",
)
def get_universe() -> UniverseResponse:
    return UniverseResponse(
        assets={ticker: AssetInfo(**info) for ticker, info in ASSET_UNIVERSE.items()}
    )


@router.get(
    "/quotes",
    response_model=QuotesResponse,
    summary="Latest quotes, optionally filtered to a comma-separated ticker list",
)
def get_quotes(tickers: Optional[str] = Query(None)) -> QuotesResponse:
    selected = _parse_tickers(tickers)
    cache_key = "quotes:" + ",".join(sorted(selected))
    records = _quotes_cache.get_or_set(
        cache_key,
        QUOTES_TTL_SECONDS,
        lambda: [_with_display_meta(r) for r in _clean_records(get_latest_quotes(selected))],
    )
    return QuotesResponse(
        as_of=datetime.now(timezone.utc),
        quotes=[Quote(**record) for record in records],
    )


@router.get(
    "/risk-free-rate",
    response_model=RiskFreeRateResponse,
    summary="Current annualized risk-free rate (FRED → yfinance → static fallback)",
)
def get_risk_free_rate() -> RiskFreeRateResponse:
    rate = _rf_cache.get_or_set("rf", RISK_FREE_RATE_TTL_SECONDS, fetch_risk_free_rate)
    return RiskFreeRateResponse(rate=rate, as_of=datetime.now(timezone.utc))


@router.get(
    "/analytics",
    response_model=AnalyticsResponse,
    summary="Dashboard analytics: price chart, correlation heatmap, risk stats",
)
def get_analytics(
    period: str = Query("1y", description="Analysis horizon"),
    tickers: Optional[str] = Query(None, description="Comma-separated tickers"),
) -> AnalyticsResponse:
    if period not in VALID_PERIODS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Valid: {sorted(VALID_PERIODS)}",
        )
    selected = _parse_tickers(tickers)
    cache_key = f"analytics:{period}|{','.join(sorted(selected))}"
    payload = _analytics_cache.get_or_set(
        cache_key, ANALYTICS_TTL_SECONDS, lambda: _build_analytics(selected, period)
    )
    return AnalyticsResponse(**payload)
