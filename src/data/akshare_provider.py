"""
AKShare provider — free CN-native backup tier (no token required).

Sina-sourced index daily bars via ``ak.stock_zh_index_daily``. Sits between
Tushare Pro and yfinance in the CN routing chain: structured paid source
first, free CN-native source second, yfinance as the last resort. The
package is an optional dependency — absence degrades the chain silently.
"""

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# yfinance ticker → sina index symbol (shXXXXXX / szXXXXXX).
_INDEX_SYMBOL = {
    "000300.SS": "sh000300",  # CSI 300 index
}

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


def is_available() -> bool:
    """Whether the optional akshare package is importable."""
    try:
        import akshare  # noqa: F401

        return True
    except ImportError:
        return False


def supports(ticker: str) -> bool:
    """Whether this provider covers the given yfinance ticker."""
    return ticker in _INDEX_SYMBOL


def _fetch_symbol_close(symbol: str) -> pd.DataFrame:
    """Pull the full daily history for one sina index symbol (network)."""
    import akshare as ak

    return ak.stock_zh_index_daily(symbol=symbol)


def fetch_index_history(tickers: list[str], period: str) -> pd.DataFrame:
    """Fetch CN index daily closes via akshare (sina source).

    Args:
        tickers: yfinance-style tickers, all supported by this provider.
        period: yfinance-style period string; the upstream returns full
            history, which is sliced locally to the lookback window.

    Returns:
        DataFrame indexed by trading date (ascending), one close column per
        requested yfinance ticker.

    Raises:
        ValueError: Unknown ticker or bad period.
    """
    unknown = [t for t in tickers if t not in _INDEX_SYMBOL]
    if unknown:
        raise ValueError(f"未配置 akshare 路由的 ticker：{', '.join(unknown)}")
    days = _PERIOD_DAYS.get(period)
    if days is None:
        raise ValueError(f"不支持的区间：{period}")
    start = pd.Timestamp.now() - pd.Timedelta(days=days)

    series = []
    for ticker in tickers:
        df = _fetch_symbol_close(_INDEX_SYMBOL[ticker])
        if df is None or df.empty:
            logger.warning("akshare 无数据：%s", ticker)
            series.append(pd.Series(name=ticker, dtype=float))
            continue
        df = df[pd.to_datetime(df["date"]) >= start]
        closes = df.set_index(pd.to_datetime(df["date"]))["close"].sort_index()
        closes.name = ticker
        series.append(closes)

    panel = pd.concat(series, axis=1)
    for ticker in tickers:
        if ticker not in panel.columns:
            panel[ticker] = float("nan")
    return panel[tickers]


# ChinaBond treasury yield curve identifiers used for the CNY risk-free leg.
# ak.bond_china_yield stacks several curve families (treasury, commercial
# paper, bank bonds) into one frame keyed by the "曲线名称" column.
_CGB_CURVE_NAME = "中债国债收益率曲线"
_CGB_1Y_COLUMN = "1年"


def _fetch_bond_china_yield(start_date: str, end_date: str) -> pd.DataFrame:
    """Pull the ChinaBond yield-curve history for a date window (network).

    The upstream window must span less than one year; dates use ``YYYYMMDD``.
    """
    import akshare as ak

    return ak.bond_china_yield(start_date=start_date, end_date=end_date)


def fetch_cgb_yield_1y(lookback_days: int = 31) -> Optional[float]:
    """Latest 1-year China government bond yield, in percent.

    Filters the stacked ChinaBond frame to the treasury curve, then takes
    the newest non-null 1-year quote within a short trailing window (the
    series is not published on weekends/holidays).

    Returns:
        Yield in percent (e.g. 1.146 for 1.146%), or None when the frame
        is empty or lacks the treasury 1-year column.
    """
    end = pd.Timestamp.now()
    start = end - pd.Timedelta(days=lookback_days)
    df = _fetch_bond_china_yield(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"))
    if df is None or df.empty:
        return None
    if "曲线名称" in df.columns:
        df = df[df["曲线名称"] == _CGB_CURVE_NAME]
    if df.empty or _CGB_1Y_COLUMN not in df.columns:
        return None
    if "日期" in df.columns:
        df = df.sort_values("日期")
    series = pd.to_numeric(df[_CGB_1Y_COLUMN], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.iloc[-1])
