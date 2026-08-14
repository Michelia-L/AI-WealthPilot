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


def _window() -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=_LOOKBACK_DAYS)
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
