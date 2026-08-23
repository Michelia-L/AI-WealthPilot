"""Deterministic synthetic market data for DEMO_MODE (KI-002).

When DEMO_MODE is on, the market data layer serves these synthetic series
instead of hitting yfinance/akshare, so the whole app (market dashboard,
optimizer, monitoring, backtest) runs fully offline. Each ticker's series
is a GBM seeded from the ticker's stable hash on a business-day grid ending
at a fixed reference date — output never drifts between runs, which keeps
e2e snapshots and demo screens reproducible.
"""

import hashlib
from typing import Optional

import numpy as np
import pandas as pd

from src.config import ASSET_UNIVERSE

# Fixed grid anchor: every series ends here regardless of the wall clock.
REFERENCE_END = pd.Timestamp("2026-08-21")

# Period string -> number of trading days, mirroring the dashboard's options.
_PERIOD_DAYS = {
    "1mo": 22,
    "3mo": 66,
    "6mo": 132,
    "1y": 260,
    "3y": 780,
    "5y": 1300,
}

# Per-category GBM parameters: (annual drift, annual volatility, start price).
# Start prices are plausible magnitudes for the dominant instrument in the
# category; a per-ticker multiplier (0.6-1.4x) differentiates siblings.
_CATEGORY_PARAMS: dict[str, tuple[float, float, float]] = {
    "Crypto": (0.15, 0.60, 60_000.0),
    "Commodity": (0.06, 0.19, 2_000.0),
    "Currency": (0.00, 0.06, 100.0),
    "US Equity": (0.08, 0.16, 5_000.0),
    "CN Equity": (0.03, 0.20, 4_000.0),
    "HK Equity": (0.04, 0.22, 20_000.0),
    "JP Equity": (0.06, 0.18, 38_000.0),
    "KR Equity": (0.03, 0.20, 2_600.0),
    "TW Equity": (0.08, 0.18, 22_000.0),
    "UK Equity": (0.04, 0.14, 8_000.0),
    "EU Equity": (0.06, 0.17, 18_000.0),
    "IN Equity": (0.08, 0.15, 24_000.0),
    # VIX-like: high vol, clamped below to stay in a plausible band.
    "Volatility": (0.00, 0.80, 20.0),
}
_DEFAULT_PARAMS = (0.05, 0.18, 100.0)

# Volatility indices are mean-reverting in reality; a plain GBM wanders to
# silly levels, so clamp the synthetic path into a plausible band.
_VOLATILITY_CLAMP = (9.0, 85.0)


def _ticker_seed(ticker: str) -> int:
    """Stable per-ticker seed (Python's builtin hash() is salted per process)."""
    digest = hashlib.sha256(ticker.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little")


def _series(ticker: str, n_days: int) -> pd.Series:
    """One ticker's synthetic close series on the fixed business-day grid."""
    category = ASSET_UNIVERSE.get(ticker, {}).get("category", "")
    drift, vol, start = _CATEGORY_PARAMS.get(category, _DEFAULT_PARAMS)

    seed = _ticker_seed(ticker)
    rng = np.random.default_rng(seed)
    # Per-ticker start multiplier in [0.6, 1.4) so same-category siblings differ.
    start *= 0.6 + rng.random() * 0.8

    daily_mu = (drift - 0.5 * vol**2) / 252
    daily_sigma = vol / np.sqrt(252)
    log_returns = rng.normal(daily_mu, daily_sigma, n_days)
    prices = start * np.exp(np.cumsum(log_returns))
    if category == "Volatility":
        prices = np.clip(prices, *_VOLATILITY_CLAMP)

    index = pd.bdate_range(end=REFERENCE_END, periods=n_days)
    return pd.Series(prices, index=index, name=ticker)


def demo_price_history(
    tickers: list[str],
    period: str = "5y",
    interval: str = "1d",
) -> pd.DataFrame:
    """Synthetic adjusted-close frame with the real fetch_price_history shape.

    ``interval``/currency arguments of the real path are accepted by the
    caller but intentionally ignored: synthetic series are daily and have no
    FX notion. Unknown ``period`` falls back to the 1y window.
    """
    n_days = _PERIOD_DAYS.get(period, _PERIOD_DAYS["1y"])
    frame = pd.concat([_series(t, n_days) for t in tickers], axis=1)
    return frame.reindex(columns=tickers)


def demo_quote_record(ticker: str) -> Optional[dict]:
    """Synthetic quote record with the real _fetch_quote_record shape."""
    closes = _series(ticker, _PERIOD_DAYS["1mo"])
    info = ASSET_UNIVERSE.get(ticker, {})
    return {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "category": info.get("category", "Unknown"),
        "price": float(closes.iloc[-1]),
        "previous_close": float(closes.iloc[-2]),
    }
