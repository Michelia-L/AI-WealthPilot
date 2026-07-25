"""
Tushare Pro data provider — paid, structured backbone for CN assets.

Covers the tickers listed in ``TUSHARE_TICKER_MAP`` (yfinance ticker →
tushare ts_code) with daily bars via ``index_daily``. yfinance remains the
fallback: the router in ``market_data.fetch_price_history`` only engages
this provider when a token is configured and the request is daily.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd

from src.config import TUSHARE_TICKER_MAP, TUSHARE_TOKEN

logger = logging.getLogger(__name__)

# Lazily-initialized pro_api client (module import must not require the
# package or the token — tests monkeypatch this accessor).
_pro = None

# Period string → approximate calendar days of lookback.
_PERIOD_DAYS = {
    "1mo": 31,
    "3mo": 93,
    "6mo": 186,
    "1y": 366,
    "2y": 732,
    "3y": 1096,
    "5y": 1826,
    "10y": 3652,
}


def is_configured() -> bool:
    """Whether a Tushare token is available."""
    return bool(TUSHARE_TOKEN)


def _get_pro():
    """Return the cached tushare pro_api client, creating it on first use."""
    global _pro
    if _pro is None:
        import tushare as ts

        _pro = ts.pro_api(TUSHARE_TOKEN)
    return _pro


def _period_start(period: str) -> str:
    """Convert a yfinance-style period string to a YYYYMMDD start date."""
    days = _PERIOD_DAYS.get(period)
    if days is None:
        raise ValueError(f"不支持的区间：{period}")
    start = pd.Timestamp.now() - pd.Timedelta(days=days)
    return start.strftime("%Y%m%d")


def fetch_index_history(tickers: list[str], period: str) -> pd.DataFrame:
    """Fetch CN index daily closes via Tushare ``index_daily``.

    Args:
        tickers: yfinance-style tickers, all present in TUSHARE_TICKER_MAP.
        period: yfinance-style period string ("1y" / "3y" / "5y" / "10y" ...).

    Returns:
        DataFrame indexed by trading date (ascending), one close column per
        requested yfinance ticker. Tickers with an empty upstream response
        surface as all-NaN columns (the caller's poison guards handle them).

    Raises:
        ValueError: Unknown ticker (not in the routing map) or bad period.
    """
    unknown = [t for t in tickers if t not in TUSHARE_TICKER_MAP]
    if unknown:
        raise ValueError(f"未配置 Tushare 路由的 ticker：{', '.join(unknown)}")

    pro = _get_pro()
    start = _period_start(period)
    end = datetime.now().strftime("%Y%m%d")

    series = []
    for ticker in tickers:
        ts_code = TUSHARE_TICKER_MAP[ticker]
        df = pro.index_daily(ts_code=ts_code, start_date=start, end_date=end)
        if df is None or df.empty:
            logger.warning("Tushare index_daily 无数据：%s（%s）", ticker, ts_code)
            series.append(pd.Series(name=ticker, dtype=float))
            continue
        closes = df.set_index(pd.to_datetime(df["trade_date"], format="%Y%m%d"))[
            "close"
        ].sort_index()
        closes.name = ticker
        series.append(closes)

    panel = pd.concat(series, axis=1)
    # Ensure every requested ticker exists as a column (possibly all-NaN).
    for ticker in tickers:
        if ticker not in panel.columns:
            panel[ticker] = float("nan")
    return panel[tickers]
