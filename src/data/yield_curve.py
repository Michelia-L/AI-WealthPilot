"""
China treasury par-yield curve for LDI liability discounting.

Cascade, following the project's provider-routing philosophy (paid
structured source first, free source as fallback):

1. Tushare Pro ``yc_cb`` — 中债国债收益率曲线 (ts_code='1001.CB',
   curve_type='0' par yield). A separately-permissioned interface:
   degrades silently on permission/network errors and activates
   automatically once the account's tier covers it.
2. akshare ``bond_china_yield`` — free ChinaBond source, same curve.

Both normalize to ``{tenor_years: rate_decimal}``. Every failure path
returns None — callers then fall back to the flat risk-free leg.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from src.config import TUSHARE_TOKEN
from src.data import akshare_provider

logger = logging.getLogger(__name__)

# akshare tenor columns (Chinese labels) → years.
_AK_TENOR_COLUMNS = {
    "3月": 0.25,
    "6月": 0.5,
    "1年": 1.0,
    "3年": 3.0,
    "5年": 5.0,
    "7年": 7.0,
    "10年": 10.0,
    "30年": 30.0,
}
_AK_TREASURY_CURVE_NAME = "中债国债收益率曲线"

# Tushare yc_cb selectors: 1001.CB = treasury curve, 0 = par (到期) yield.
_TS_TS_CODE = "1001.CB"
_TS_CURVE_TYPE = "0"

_LOOKBACK_DAYS = 10


def _window(lookback_days: int = _LOOKBACK_DAYS) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def _from_tushare() -> Optional[dict[float, float]]:
    """Tier 1: Tushare Pro yc_cb (separately-permissioned interface)."""
    if not TUSHARE_TOKEN:
        return None
    try:
        import tushare as ts

        start, end = _window()
        df = ts.pro_api(TUSHARE_TOKEN).yc_cb(
            ts_code=_TS_TS_CODE,
            curve_type=_TS_CURVE_TYPE,
            start_date=start,
            end_date=end,
        )
        if df is None or df.empty:
            return None
        latest_date = df["trade_date"].max()
        latest = df[df["trade_date"] == latest_date]
        curve = {
            float(row["curve_term"]): float(row["yield"]) / 100.0
            for _, row in latest.iterrows()
            if pd.notna(row["yield"]) and float(row["curve_term"]) > 0
        }
        return curve or None
    except Exception as e:  # permission, network, schema — all degrade
        logger.warning("tushare yc_cb unavailable, falling back: %s", e)
        return None


def _from_akshare() -> Optional[dict[float, float]]:
    """Tier 2: akshare bond_china_yield (free ChinaBond source)."""
    if not akshare_provider.is_available():
        return None
    try:
        import akshare as ak

        start, end = _window()
        df = ak.bond_china_yield(start_date=start, end_date=end)
        rows = df[df["曲线名称"] == _AK_TREASURY_CURVE_NAME]
        if rows.empty:
            return None
        latest = rows.sort_values("日期").iloc[-1]
        curve = {
            tenor: float(latest[col]) / 100.0
            for col, tenor in _AK_TENOR_COLUMNS.items()
            if col in rows.columns and pd.notna(latest[col])
        }
        return curve or None
    except Exception as e:
        logger.warning("akshare bond_china_yield failed: %s", e)
        return None


def fetch_china_treasury_curve() -> Optional[tuple[dict[float, float], str]]:
    """Latest ChinaBond treasury par-yield curve.

    Returns:
        Tuple of (curve {tenor_years: rate_decimal}, source label
        'tushare'/'akshare'), or None when every tier fails.
    """
    curve = _from_tushare()
    if curve:
        return curve, "tushare"
    curve = _from_akshare()
    if curve:
        return curve, "akshare"
    return None


# Curve History (for curve-based liability statistics)

def _pivot_history(df: pd.DataFrame, date_col: str) -> Optional[pd.DataFrame]:
    """Pivot raw provider rows into a date × tenor yield-history frame.

    Shared normalization: DatetimeIndex ascending, float tenor-year
    columns ascending, values as decimal rates.
    """
    pivot = df.pivot_table(
        index=date_col, columns="curve_term", values="yield", aggfunc="last"
    )
    if pivot.empty:
        return None
    pivot = pivot.sort_index().sort_index(axis=1)
    pivot.columns = pivot.columns.astype(float)
    pivot.index = pd.to_datetime(pivot.index)
    return pivot / 100.0


def _from_tushare_history(
    start: str, end: str
) -> Optional[pd.DataFrame]:
    """History tier 1: Tushare Pro yc_cb over the window."""
    if not TUSHARE_TOKEN:
        return None
    try:
        import tushare as ts

        df = ts.pro_api(TUSHARE_TOKEN).yc_cb(
            ts_code=_TS_TS_CODE,
            curve_type=_TS_CURVE_TYPE,
            start_date=start,
            end_date=end,
        )
        if df is None or df.empty:
            return None
        df = df[df["yield"].notna() & (df["curve_term"] > 0)]
        if df.empty:
            return None
        return _pivot_history(df, "trade_date")
    except Exception as e:  # permission, network, schema — all degrade
        logger.warning("tushare yc_cb history unavailable, falling back: %s", e)
        return None


def _from_akshare_history(
    start: str, end: str
) -> Optional[pd.DataFrame]:
    """History tier 2: akshare bond_china_yield over the window."""
    if not akshare_provider.is_available():
        return None
    try:
        import akshare as ak

        df = ak.bond_china_yield(start_date=start, end_date=end)
        rows = df[df["曲线名称"] == _AK_TREASURY_CURVE_NAME]
        if rows.empty:
            return None
        cols = {c: t for c, t in _AK_TENOR_COLUMNS.items() if c in rows.columns}
        if not cols:
            return None
        out = rows[["日期", *cols.keys()]].copy()
        out["日期"] = pd.to_datetime(out["日期"])
        out = (
            out.set_index("日期")
            .rename(columns=cols)
            .sort_index()
            .apply(pd.to_numeric, errors="coerce")
        )
        out = out.dropna(how="all") / 100.0
        return out if not out.empty else None
    except Exception as e:
        logger.warning("akshare bond_china_yield history failed: %s", e)
        return None


def fetch_china_treasury_curve_history(
    lookback_days: int = 365,
) -> Optional[tuple[pd.DataFrame, str]]:
    """ChinaBond treasury par-yield curve history (daily, per tenor).

    Same provider cascade as fetch_china_treasury_curve. Used to
    estimate liability volatility directly from yield changes at the
    liability duration point.

    Args:
        lookback_days: History window in calendar days (default ~1y).

    Returns:
        Tuple of (history DataFrame — DatetimeIndex ascending, float
        tenor-year columns, decimal rates —, source label), or None
        when every tier fails.
    """
    start, end = _window(lookback_days)
    hist = _from_tushare_history(start, end)
    if hist is not None and not hist.empty:
        return hist, "tushare"
    hist = _from_akshare_history(start, end)
    if hist is not None and not hist.empty:
        return hist, "akshare"
    return None


def rate_at(curve: dict[float, float], t: float) -> float:
    """Linear-interpolated par yield at tenor ``t`` (years).

    Below the shortest tenor the curve is held flat at the shortest rate;
    beyond the longest, flat at the longest.
    """
    tenors = sorted(curve)
    if not tenors:
        raise ValueError("rate_at requires a non-empty curve")
    if t <= tenors[0]:
        return curve[tenors[0]]
    if t >= tenors[-1]:
        return curve[tenors[-1]]
    for lo, hi in zip(tenors, tenors[1:]):
        if lo <= t <= hi:
            frac = (t - lo) / (hi - lo)
            return curve[lo] + frac * (curve[hi] - curve[lo])
    return curve[tenors[-1]]  # unreachable; keeps the type checker happy
