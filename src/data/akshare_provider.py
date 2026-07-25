"""
AKShare provider — free CN-native backup tier (no token required).

Sina-sourced index daily bars via ``ak.stock_zh_index_daily``. Sits between
Tushare Pro and yfinance in the CN routing chain: structured paid source
first, free CN-native source second, yfinance as the last resort. The
package is an optional dependency — absence degrades the chain silently.
"""

import logging

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
