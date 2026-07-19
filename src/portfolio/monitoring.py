"""
AI WealthPilot - Portfolio Monitoring & Rebalancing (P10)

Computes post-IPS portfolio monitoring diagnostics for a stored IPS document:

    1. Load the strategic asset allocation (SAA) from the IPS JSON store
    2. Normalize target weights (cash plug when the SAA sums below 100%,
       proportional rescaling when it exceeds 100%)
    3. Attach Capital Market Expectations (CME) metrics per asset class
    4. Compute portfolio-level expected return / volatility / Sharpe under
       both target weights and drifted (market-value) weights
    5. Measure allocation drift since the IPS was saved
    6. Flag out-of-band asset classes and derive rebalancing trades

This module is pure computation. The FastAPI layer
(api/routers/monitoring.py) translates KeyError/ValueError into HTTP
status codes. All numbers are raw floats (0-1 decimals); dates are ISO
strings; human-readable caveats are collected in ``notes`` (Chinese).

"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.agents import ips_storage
from src.config import IPS_ASSET_CLASS_TICKERS
from src.data.market_data import fetch_price_history
from src.portfolio.cme_engine import compute_cme
from src.portfolio.cme_models import AssetClassCME

logger = logging.getLogger(__name__)


# SAA Chinese display name -> IPS_ASSET_CLASS_TICKERS config key.
# Ordered: the first keyword contained in the SAA asset_class name wins.
_SAA_KEYWORDS: list[tuple[str, str]] = [
    ("国内权益", "domestic_equity"),
    ("A股", "domestic_equity"),
    ("沪深300", "domestic_equity"),
    ("国际权益", "international_equity_dm"),
    ("发达市场", "international_equity_dm"),
    ("港股", "international_equity_hk"),
    ("恒生", "international_equity_hk"),
    ("固定收益", "fixed_income"),
    ("固收", "fixed_income"),
    ("债", "fixed_income"),
    ("黄金", "alternative_gold"),
    ("Gold", "alternative_gold"),
    ("REIT", "alternative_reit"),
    ("房地产", "alternative_reit"),
    ("现金", "cash"),
    ("货币", "cash"),
    ("Cash", "cash"),
]


# Public Entry Point

def compute_monitoring(document_id: str) -> dict:
    """
    Compute drift monitoring and rebalancing diagnostics for a stored IPS.

    Args:
        document_id: IPS document stem (filename without .json).

    Returns:
        Dict matching the api.schemas.MonitoringResponse contract.

    Raises:
        KeyError: If the IPS document does not exist.
        ValueError: If the document has no strategic allocation (SAA).
    """
    filepath = _find_ips_file(document_id)
    if filepath is None:
        raise KeyError(f"IPS document not found: {document_id}")

    record = ips_storage.load_ips(filepath)
    ips = record.get("ips", {})
    meta = record.get("metadata", {})
    saa = ips.get("investment_guidelines", {}).get("strategic_allocation") or []
    if not saa:
        raise ValueError("IPS 文档缺少战略性资产配置（strategic_allocation），无法执行组合监控。")

    notes: list[str] = []
    holdings = _build_holdings(saa, notes)
    _normalize_weights(holdings, notes)

    # CME alignment (use the engine's own cache; never force a refresh here)
    report, cache_status = compute_cme()
    cme_by_ticker = {ac.ticker: ac for ac in report.asset_classes}
    for h in holdings:
        h["cme"] = cme_by_ticker.get(h["ticker"]) if h["ticker"] else None
        if h["ticker"] and h["cme"] is None:
            notes.append(
                f"资产类别「{h['name']}」（{h['ticker']}）未包含在 CME 报告中，"
                "组合指标计算将其剔除。"
            )

    rf = report.risk_free_rate
    corr = report.correlation_matrix
    noted_corr_pairs: set[tuple[str, str]] = set()

    portfolio = _portfolio_metrics(
        [h["target_weight"] for h in holdings],
        [h["cme"] for h in holdings],
        corr, rf, notes, noted_corr_pairs,
    )

    # Market-value drift since the IPS was saved
    saved_at = meta.get("saved_at", "") or ""
    saved_date = _parse_saved_date(saved_at, notes)
    period_returns = _compute_period_returns(holdings, saved_date, notes)
    _apply_drift(holdings, period_returns, notes)
    _apply_bands(holdings)

    if any(h["drifted_weight"] is None for h in holdings):
        # Partial weights would make drifted-weight portfolio metrics
        # misleading, so degrade the whole block to nulls.
        drifted_portfolio = {
            "expected_return": None,
            "volatility": None,
            "sharpe": None,
        }
        notes.append("部分资产缺少区间行情数据，漂移口径的组合指标整体退化为 null。")
    else:
        drifted_portfolio = _portfolio_metrics(
            [h["drifted_weight"] for h in holdings],
            [h["cme"] for h in holdings],
            corr, rf, notes, noted_corr_pairs,
        )

    rebalance = _compute_rebalance(holdings)

    return {
        "document_id": document_id,
        "client_name": meta.get("client_name") or ips.get("client_name", "Unknown"),
        "saved_at": saved_at,
        "as_of": datetime.now().date().isoformat(),
        "cme_cache_status": cache_status,
        "portfolio": portfolio,
        "drifted_portfolio": drifted_portfolio,
        "holdings": [_serialize_holding(h) for h in holdings],
        "rebalance": rebalance,
        "notes": notes,
    }


# IPS Document Loading

def _find_ips_file(document_id: str) -> Optional[Path]:
    """Locate an IPS file by stem; glob keeps lookups inside IPS_DIR."""
    if not document_id or not all(c.isalnum() or c in "_-" for c in document_id):
        return None
    matches = list(ips_storage.IPS_DIR.glob(f"{document_id}.json"))
    return matches[0] if matches else None


# SAA Mapping & Weight Normalization

def _match_asset_class_key(name: str) -> Optional[str]:
    """Map an SAA Chinese display name to an IPS_ASSET_CLASS_TICKERS key."""
    for keyword, key in _SAA_KEYWORDS:
        if keyword in name:
            return key
    return None


def _build_holdings(saa: list[dict], notes: list[str]) -> list[dict]:
    """Convert raw SAA entries into internal holding records."""
    holdings = []
    for entry in saa:
        name = str(entry.get("asset_class", "")).strip()
        key = _match_asset_class_key(name)
        ticker = None
        if key is not None:
            ticker = IPS_ASSET_CLASS_TICKERS.get(key, {}).get("ticker")
        else:
            notes.append(f"资产类别「{name}」无法映射到已知代理，ticker 记为 null。")
        holdings.append({
            "key": key,
            "name": name,
            "ticker": ticker,
            "target_weight": float(entry.get("target_weight", 0.0) or 0.0),
            "min_weight": float(entry.get("min_weight", 0.0) or 0.0),
            "max_weight": float(entry.get("max_weight", 0.0) or 0.0),
            "period_return": None,
            "drifted_weight": None,
            "drift_pp": None,
            "band_status": "unknown",
            "cme": None,
        })
    return holdings


def _normalize_weights(holdings: list[dict], notes: list[str]) -> None:
    """
    Normalize SAA target weights in place.

    Sum < 99.9%  -> plug the gap with cash (merged into an existing cash
                    holding, or appended as a synthetic one).
    Sum > 100.1% -> rescale all weights proportionally.
    """
    total = sum(h["target_weight"] for h in holdings)

    if total < 0.999:
        deficit = 1.0 - total
        cash = next((h for h in holdings if h["key"] == "cash"), None)
        if cash is not None:
            cash["target_weight"] += deficit
            cash["min_weight"] += deficit
            cash["max_weight"] += deficit
            notes.append(
                f"SAA 目标权重合计 {total:.1%}，差额 {deficit:.1%} "
                "已并入现金等价物的 target/min/max。"
            )
        else:
            info = IPS_ASSET_CLASS_TICKERS["cash"]
            holdings.append({
                "key": "cash",
                "name": info["name"],
                "ticker": info["ticker"],
                "target_weight": deficit,
                # Synthetic plug: no policy band exists, use [0, target].
                "min_weight": 0.0,
                "max_weight": deficit,
                "period_return": None,
                "drifted_weight": None,
                "drift_pp": None,
                "band_status": "unknown",
                "cme": None,
            })
            notes.append(
                f"SAA 目标权重合计 {total:.1%}，已补入现金等价物 holding"
                f"（目标权重 {deficit:.1%}，政策区间按 [0, {deficit:.1%}] 处理）。"
            )
    elif total > 1.001:
        scale = 1.0 / total
        for h in holdings:
            h["target_weight"] *= scale
            h["min_weight"] *= scale
            h["max_weight"] *= scale
        notes.append(
            f"SAA 目标权重合计 {total:.1%} 超过 100%，"
            f"已按比例归一化（缩放系数 {scale:.4f}）。"
        )


# Portfolio-Level Metrics (CME-based)

def _effective_volatility(ac: AssetClassCME) -> float:
    """Prefer Bayesian-blended volatility, fall back to historical."""
    if ac.blended_volatility is not None:
        return float(ac.blended_volatility)
    return float(ac.volatility)


def _portfolio_metrics(
    weights: list[Optional[float]],
    cmes: list[Optional[AssetClassCME]],
    correlation_matrix: dict[str, dict[str, float]],
    risk_free_rate: float,
    notes: list[str],
    noted_corr_pairs: set[tuple[str, str]],
) -> dict:
    """
    Compute portfolio expected return, volatility and Sharpe for a weight set.

    mu_p = sum(w_i * mu_i); sigma_p = sqrt(w' * Sigma * w) where Sigma is
    built from the CME correlation matrix (keyed by asset class name) and
    per-asset (blended) volatilities. Holdings without CME data are excluded
    (already noted by the caller); missing correlation pairs default to 0.
    """
    result = {"expected_return": None, "volatility": None, "sharpe": None}
    known = [
        (w, ac) for w, ac in zip(weights, cmes)
        if ac is not None and w is not None
    ]
    if not known:
        return result

    ws = np.array([w for w, _ in known], dtype=float)
    mus = np.array([ac.expected_return for _, ac in known], dtype=float)
    vols = np.array([_effective_volatility(ac) for _, ac in known], dtype=float)
    names = [ac.name for _, ac in known]

    n = len(known)
    corr_mat = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            c = correlation_matrix.get(names[i], {}).get(names[j])
            if c is None:
                c = correlation_matrix.get(names[j], {}).get(names[i])
            if c is None:
                pair = (names[i], names[j])
                if pair not in noted_corr_pairs:
                    noted_corr_pairs.add(pair)
                    notes.append(
                        f"相关性矩阵缺失资产对「{names[i]} × {names[j]}」，按 0 处理。"
                    )
                c = 0.0
            corr_mat[i, j] = corr_mat[j, i] = float(c)

    cov = np.outer(vols, vols) * corr_mat
    mu_p = float(ws @ mus)
    var_p = float(ws @ cov @ ws)
    sigma_p = float(np.sqrt(var_p)) if var_p > 0 else 0.0
    sharpe = (mu_p - risk_free_rate) / sigma_p if sigma_p > 0 else None

    return {
        "expected_return": mu_p,
        "volatility": sigma_p,
        "sharpe": float(sharpe) if sharpe is not None else None,
    }


# Drift Measurement (market-value weights since saved_at)

def _parse_saved_date(saved_at: str, notes: list[str]) -> Optional[date]:
    """Parse metadata.saved_at (ISO) into a date; None if unusable."""
    if not saved_at:
        notes.append("metadata.saved_at 缺失，无法计算区间收益与漂移。")
        return None
    try:
        return datetime.fromisoformat(saved_at).date()
    except (ValueError, TypeError):
        notes.append(
            f"metadata.saved_at（{saved_at!r}）无法解析为 ISO 日期，"
            "无法计算区间收益与漂移。"
        )
        return None


def _choose_period(days: int) -> str:
    """Map elapsed days to the smallest yfinance period string covering them."""
    for limit, period in (
        (31, "1mo"), (93, "3mo"), (186, "6mo"), (366, "1y"),
        (731, "2y"), (1826, "5y"), (3652, "10y"),
    ):
        if days <= limit:
            return period
    return "max"


def _compute_period_returns(
    holdings: list[dict],
    saved_date: Optional[date],
    notes: list[str],
) -> dict[str, Optional[float]]:
    """
    Fetch per-ticker total returns from saved_at to the latest close.

    Tickers with missing data or a window shorter than 2 observations
    get None (degraded to band_status 'unknown' downstream).
    """
    tickers = sorted({h["ticker"] for h in holdings if h["ticker"]})
    result: dict[str, Optional[float]] = {t: None for t in tickers}
    if saved_date is None or not tickers:
        return result

    elapsed_days = max((datetime.now().date() - saved_date).days, 1)
    period = _choose_period(elapsed_days)

    try:
        prices = fetch_price_history(
            tickers=tickers,
            period=period,
            interval="1d",
            adjust_currency=False,
        )
    except Exception as e:
        logger.warning("Price history fetch failed for monitoring: %s", e)
        notes.append(f"行情数据获取失败（{e}），区间收益记为 null。")
        return result

    cutoff = pd.Timestamp(saved_date)
    for t in tickers:
        if t not in prices.columns:
            notes.append(f"ticker {t} 无行情数据，区间收益记为 null。")
            continue
        series = prices[t].dropna()
        if getattr(series.index, "tz", None) is not None:
            series = series.copy()
            series.index = series.index.tz_localize(None)
        window = series[series.index >= cutoff]
        if len(window) < 2:
            notes.append(
                f"ticker {t} 自 {saved_date.isoformat()} 以来的行情窗口太短"
                f"（{len(window)} 个观测点），区间收益记为 null。"
            )
            continue
        result[t] = float(window.iloc[-1] / window.iloc[0] - 1.0)
    return result


def _apply_drift(
    holdings: list[dict],
    period_returns: dict[str, Optional[float]],
    notes: list[str],
) -> None:
    """
    Compute drifted (market-value) weights in place.

    drifted_i = w_i * (1 + R_i) / sum_j(w_j * (1 + R_j))

    Holdings without a period return keep drifted_weight=None; for the
    normalization denominator they are treated as unchanged (R = 0).
    """
    for h in holdings:
        r = period_returns.get(h["ticker"]) if h["ticker"] else None
        h["period_return"] = r

    missing = [h["name"] for h in holdings if h["period_return"] is None]
    if missing and len(missing) < len(holdings):
        notes.append(
            f"以下资产缺少区间收益，漂移归一化时按其权重不变（R=0）处理："
            f"{'、'.join(missing)}。"
        )

    factors = [
        (1.0 + h["period_return"]) if h["period_return"] is not None else 1.0
        for h in holdings
    ]
    gross = sum(h["target_weight"] * f for h, f in zip(holdings, factors))
    if gross <= 0:
        return
    for h, f in zip(holdings, factors):
        if h["period_return"] is not None:
            h["drifted_weight"] = h["target_weight"] * f / gross


def _apply_bands(holdings: list[dict]) -> None:
    """Compute drift_pp and band_status in place."""
    for h in holdings:
        if h["drifted_weight"] is None:
            h["drift_pp"] = None
            h["band_status"] = "unknown"
            continue
        h["drift_pp"] = h["drifted_weight"] - h["target_weight"]
        if h["drifted_weight"] > h["max_weight"]:
            h["band_status"] = "above"
        elif h["drifted_weight"] < h["min_weight"]:
            h["band_status"] = "below"
        else:
            h["band_status"] = "within"


# Rebalancing

def _compute_rebalance(holdings: list[dict]) -> dict:
    """
    Derive rebalancing trades for out-of-band asset classes.

    weight_pp = target - drifted: positive means buy back up to target,
    negative means sell down to target.
    """
    trades = []
    for h in holdings:
        if h["band_status"] not in ("above", "below"):
            continue
        weight_pp = h["target_weight"] - h["drifted_weight"]
        trades.append({
            "key": h["key"],
            "name": h["name"],
            "action": "buy" if weight_pp > 0 else "sell",
            "weight_pp": float(weight_pp),
        })
    return {"needed": bool(trades), "trades": trades}


# Serialization

def _serialize_holding(h: dict) -> dict:
    """Convert an internal holding record to the API contract shape."""
    ac: Optional[AssetClassCME] = h["cme"]
    metrics = None
    if ac is not None:
        metrics = {
            "expected_return": float(ac.expected_return),
            "volatility": _effective_volatility(ac),
            "sharpe": float(ac.sharpe_ratio),
            "max_drawdown": float(ac.max_drawdown),
            "var_95": float(ac.var_95),
            "cvar_95": float(ac.cvar_95),
        }
    return {
        "key": h["key"],
        "name": h["name"],
        "ticker": h["ticker"],
        "target_weight": float(h["target_weight"]),
        "min_weight": float(h["min_weight"]),
        "max_weight": float(h["max_weight"]),
        "drifted_weight": (
            float(h["drifted_weight"]) if h["drifted_weight"] is not None else None
        ),
        "drift_pp": float(h["drift_pp"]) if h["drift_pp"] is not None else None,
        "band_status": h["band_status"],
        "period_return": (
            float(h["period_return"]) if h["period_return"] is not None else None
        ),
        "metrics": metrics,
    }
