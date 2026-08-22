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
strings; human-readable caveats are collected in ``notes`` — bilingual
via the ``locale`` parameter (Chinese by default, so direct callers keep
the pre-i18n behavior).

``compute_fleet_status`` (P17) reuses the same SAA parsing and drift/band
helpers for a lightweight all-documents band check (no CME alignment)
backing the overview-page alert lamp.

"""

import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.agents import ips_storage
from src.config import ASSET_CLASS_ALIASES, IPS_ASSET_CLASS_TICKERS
from src.data.market_data import fetch_price_history
from src.portfolio.cme_engine import compute_cme
from src.portfolio.cme_models import AssetClassCME

logger = logging.getLogger(__name__)


# SAA display name -> IPS_ASSET_CLASS_TICKERS config key, flattened from the
# shared ASSET_CLASS_ALIASES table (P25 single source; bilingual aliases).
# Ordered: the first keyword contained in the SAA asset_class name wins.
_SAA_KEYWORDS: list[tuple[str, str]] = [
    (alias, key) for key, aliases in ASSET_CLASS_ALIASES.items() for alias in aliases
]


# Bilingual user-facing caveats (``notes`` lists and fleet-item ``note``
# fields). zh keeps the pre-i18n wording verbatim; routers resolve the
# request locale and pass it down, direct callers default to zh. Kept here
# rather than in api/i18n.py because src/ must not import from the api/
# transport shell.
_NOTE_STRINGS: dict[str, dict[str, str]] = {
    "missing_saa_monitoring": {
        "zh": "IPS 文档缺少战略性资产配置（strategic_allocation），无法执行组合监控。",
        "en": "The IPS document has no strategic asset allocation (strategic_allocation); portfolio monitoring cannot run.",
    },
    "missing_saa_weights": {
        "zh": "IPS 文档缺少战略性资产配置（strategic_allocation），无法解析组合权重。",
        "en": "The IPS document has no strategic asset allocation (strategic_allocation); portfolio weights cannot be resolved.",
    },
    "not_in_cme": {
        "zh": "资产类别「{name}」（{ticker}）未包含在 CME 报告中，组合指标计算将其剔除。",
        "en": "Asset class '{name}' ({ticker}) is not covered by the CME report and is excluded from the portfolio metrics.",
    },
    "drifted_metrics_null": {
        "zh": "部分资产缺少区间行情数据，漂移口径的组合指标整体退化为 null。",
        "en": "Some assets lack price data for the period; the drifted-weight portfolio metrics degrade to null.",
    },
    "merged_proxy": {
        "zh": "SAA 中多条资产类别映射到同一代理 {ticker}，权重已合并。",
        "en": "Multiple SAA asset classes map to the same proxy {ticker}; their weights were merged.",
    },
    "dropped_unmapped": {
        "zh": "以下资产无法映射到行情代理，已从权重解析结果中剔除：{names}。",
        "en": "The following assets cannot be mapped to a market proxy and were dropped from the resolved weights: {names}.",
    },
    "unmapped_asset": {
        "zh": "资产类别「{name}」无法映射到已知代理，ticker 记为 null。",
        "en": "Asset class '{name}' cannot be mapped to a known proxy; ticker set to null.",
    },
    "cash_plug_existing": {
        "zh": "SAA 目标权重合计 {total:.1%}，差额 {deficit:.1%} 已并入现金等价物的 target/min/max。",
        "en": "SAA target weights sum to {total:.1%}; the {deficit:.1%} gap was merged into the cash-equivalent target/min/max.",
    },
    "cash_plug_new": {
        "zh": "SAA 目标权重合计 {total:.1%}，已补入现金等价物 holding（目标权重 {deficit:.1%}，政策区间按 [0, {deficit:.1%}] 处理）。",
        "en": "SAA target weights sum to {total:.1%}; a cash-equivalent holding was added (target weight {deficit:.1%}, policy band treated as [0, {deficit:.1%}]).",
    },
    "rescaled": {
        "zh": "SAA 目标权重合计 {total:.1%} 超过 100%，已按比例归一化（缩放系数 {scale:.4f}）。",
        "en": "SAA target weights sum to {total:.1%} (over 100%); they were rescaled proportionally (factor {scale:.4f}).",
    },
    "missing_corr_pair": {
        "zh": "相关性矩阵缺失资产对「{name_i} × {name_j}」，按 0 处理。",
        "en": "Correlation matrix is missing the pair '{name_i} × {name_j}'; treated as 0.",
    },
    "saved_at_missing": {
        "zh": "metadata.saved_at 缺失，无法计算区间收益与漂移。",
        "en": "metadata.saved_at is missing; period returns and drift cannot be computed.",
    },
    "saved_at_unparseable": {
        "zh": "metadata.saved_at（{saved_at!r}）无法解析为 ISO 日期，无法计算区间收益与漂移。",
        "en": "metadata.saved_at ({saved_at!r}) cannot be parsed as an ISO date; period returns and drift cannot be computed.",
    },
    "fetch_failed_returns": {
        "zh": "行情数据获取失败（{error}），区间收益记为 null。",
        "en": "Failed to fetch market data ({error}); period returns recorded as null.",
    },
    "no_price_data": {
        "zh": "ticker {ticker} 无行情数据，区间收益记为 null。",
        "en": "No market data for ticker {ticker}; period return recorded as null.",
    },
    "window_too_short": {
        "zh": "ticker {ticker} 自 {since} 以来的行情窗口太短（{n_obs} 个观测点），区间收益记为 null。",
        "en": "Market data window for ticker {ticker} since {since} is too short ({n_obs} observations); period return recorded as null.",
    },
    "drift_missing_returns": {
        "zh": "以下资产缺少区间收益，漂移归一化时按其权重不变（R=0）处理：{names}。",
        "en": "The following assets have no period return and are treated as unchanged (R=0) in the drift normalization: {names}.",
    },
    "fleet_fetch_failed": {
        "zh": "行情数据获取失败（{error}），漂移状态记为 unknown。",
        "en": "Failed to fetch market data ({error}); drift status recorded as unknown.",
    },
    "fleet_missing_saa": {
        "zh": "IPS 文档缺少战略性资产配置（strategic_allocation），无法执行漂移检查。",
        "en": "The IPS document has no strategic asset allocation (strategic_allocation); the drift check cannot run.",
    },
    "fleet_parse_failed": {
        "zh": "IPS 文档解析失败（{error}），漂移状态记为 unknown。",
        "en": "Failed to parse the IPS document ({error}); drift status recorded as unknown.",
    },
    "fleet_insufficient_data": {
        "zh": "行情数据不足，无法判定漂移状态。",
        "en": "Insufficient market data to determine the drift status.",
    },
}


def _t(key: str, locale: str, **fmt) -> str:
    """Render one bilingual note; unknown locales fall back to Chinese."""
    entry = _NOTE_STRINGS[key]
    template = entry.get(locale) or entry["zh"]
    return template.format(**fmt) if fmt else template


def _list_sep(locale: str) -> str:
    """List separator matching the note language (、 for zh, comma for en)."""
    return "、" if locale == "zh" else ", "


# Public Entry Point


def compute_monitoring(document_id: str, locale: str = "zh") -> dict:
    """
    Compute drift monitoring and rebalancing diagnostics for a stored IPS.

    Args:
        document_id: IPS document stem (filename without .json).
        locale: Language of the human-readable ``notes`` ("zh" / "en").

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
        raise ValueError(_t("missing_saa_monitoring", locale))

    notes: list[str] = []
    holdings = _build_holdings(saa, notes, locale)
    _normalize_weights(holdings, notes, locale)

    # CME alignment (use the engine's own cache; never force a refresh here)
    report, cache_status = compute_cme()
    cme_by_ticker = {ac.ticker: ac for ac in report.asset_classes}
    for h in holdings:
        h["cme"] = cme_by_ticker.get(h["ticker"]) if h["ticker"] else None
        if h["ticker"] and h["cme"] is None:
            notes.append(_t("not_in_cme", locale, name=h["name"], ticker=h["ticker"]))

    rf = report.risk_free_rate
    corr = report.correlation_matrix
    noted_corr_pairs: set[tuple[str, str]] = set()

    portfolio = _portfolio_metrics(
        [h["target_weight"] for h in holdings],
        [h["cme"] for h in holdings],
        corr,
        rf,
        notes,
        noted_corr_pairs,
        locale,
    )

    # Market-value drift since the IPS was saved
    saved_at = meta.get("saved_at", "") or ""
    saved_date = _parse_saved_date(saved_at, notes, locale)
    period_returns = _compute_period_returns(holdings, saved_date, notes, locale)
    _apply_drift(holdings, period_returns, notes, locale)
    _apply_bands(holdings)

    if any(h["drifted_weight"] is None for h in holdings):
        # Partial weights would make drifted-weight portfolio metrics
        # misleading, so degrade the whole block to nulls.
        drifted_portfolio = {
            "expected_return": None,
            "volatility": None,
            "sharpe": None,
        }
        notes.append(_t("drifted_metrics_null", locale))
    else:
        drifted_portfolio = _portfolio_metrics(
            [h["drifted_weight"] for h in holdings],
            [h["cme"] for h in holdings],
            corr,
            rf,
            notes,
            noted_corr_pairs,
            locale,
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


def resolve_saa_weights(document_id: str, locale: str = "zh") -> dict:
    """
    Resolve a stored IPS document's SAA into normalized ticker weights.

    Shared SAA parsing entry point: reuses the same document lookup, keyword
    mapping, cash plug and weight normalization as compute_monitoring, so
    consumers (e.g. the P13 backtest engine) never duplicate those rules.
    Holdings that cannot be mapped to a proxy ticker are dropped here; the
    caller is expected to renormalize over the remaining weights.

    Args:
        document_id: IPS document stem (filename without .json).
        locale: Language of the parsing caveats ("zh" / "en").

    Returns:
        Dict with keys:
            client_name: str
            weights: {ticker: normalized target weight} (mapped holdings only)
            names: {ticker: SAA asset class display name}
            notes: list[str] — parsing caveats worded per ``locale``
            fee_schedule: dict — the IPS fee disclosure block (P18), {}
                when the document does not carry one

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
        raise ValueError(_t("missing_saa_weights", locale))

    notes: list[str] = []
    holdings = _build_holdings(saa, notes, locale)
    _normalize_weights(holdings, notes, locale)

    weights: dict[str, float] = {}
    names: dict[str, str] = {}
    dropped: list[str] = []
    merged: set[str] = set()
    for h in holdings:
        if not h["ticker"]:
            dropped.append(h["name"])
            continue
        if h["ticker"] in weights:
            weights[h["ticker"]] += h["target_weight"]
            if h["ticker"] not in merged:
                merged.add(h["ticker"])
                notes.append(_t("merged_proxy", locale, ticker=h["ticker"]))
        else:
            weights[h["ticker"]] = h["target_weight"]
            names[h["ticker"]] = h["name"]
    if dropped:
        notes.append(
            _t("dropped_unmapped", locale, names=_list_sep(locale).join(dropped))
        )

    return {
        "client_name": meta.get("client_name") or ips.get("client_name", "Unknown"),
        "weights": weights,
        "names": names,
        "notes": notes,
        "fee_schedule": ips.get("fee_schedule") or {},
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
    """Map an SAA display name (zh or en) to an IPS_ASSET_CLASS_TICKERS key."""
    for keyword, key in _SAA_KEYWORDS:
        if keyword in name:
            return key
    return None


def _build_holdings(
    saa: list[dict], notes: list[str], locale: str = "zh"
) -> list[dict]:
    """Convert raw SAA entries into internal holding records."""
    holdings = []
    for entry in saa:
        name = str(entry.get("asset_class", "")).strip()
        key = _match_asset_class_key(name)
        ticker = None
        if key is not None:
            ticker = IPS_ASSET_CLASS_TICKERS.get(key, {}).get("ticker")
        else:
            notes.append(_t("unmapped_asset", locale, name=name))
        holdings.append(
            {
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
            }
        )
    return holdings


def _normalize_weights(
    holdings: list[dict], notes: list[str], locale: str = "zh"
) -> None:
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
            notes.append(_t("cash_plug_existing", locale, total=total, deficit=deficit))
        else:
            info = IPS_ASSET_CLASS_TICKERS["cash"]
            holdings.append(
                {
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
                }
            )
            notes.append(_t("cash_plug_new", locale, total=total, deficit=deficit))
    elif total > 1.001:
        scale = 1.0 / total
        for h in holdings:
            h["target_weight"] *= scale
            h["min_weight"] *= scale
            h["max_weight"] *= scale
        notes.append(_t("rescaled", locale, total=total, scale=scale))


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
    locale: str = "zh",
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
        (w, ac)
        for w, ac in zip(weights, cmes, strict=False)
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
                        _t(
                            "missing_corr_pair",
                            locale,
                            name_i=names[i],
                            name_j=names[j],
                        )
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


def _parse_saved_date(
    saved_at: str, notes: list[str], locale: str = "zh"
) -> Optional[date]:
    """Parse metadata.saved_at (ISO) into a date; None if unusable."""
    if not saved_at:
        notes.append(_t("saved_at_missing", locale))
        return None
    try:
        return datetime.fromisoformat(saved_at).date()
    except (ValueError, TypeError):
        notes.append(_t("saved_at_unparseable", locale, saved_at=saved_at))
        return None


def _choose_period(days: int) -> str:
    """Map elapsed days to the smallest yfinance period string covering them."""
    for limit, period in (
        (31, "1mo"),
        (93, "3mo"),
        (186, "6mo"),
        (366, "1y"),
        (731, "2y"),
        (1826, "5y"),
        (3652, "10y"),
    ):
        if days <= limit:
            return period
    return "max"


def _period_return_from_series(
    series: pd.Series, cutoff: pd.Timestamp
) -> tuple[Optional[float], int]:
    """
    Total return of one price series from cutoff to its latest observation.

    The series is cleaned (NaNs dropped, timezone stripped) and sliced to
    observations at/after cutoff. Returns (None, n) when fewer than 2
    observations remain, so callers can note the exact window length.
    """
    series = series.dropna()
    if getattr(series.index, "tz", None) is not None:
        series = series.copy()
        series.index = series.index.tz_localize(None)
    window = series[series.index >= cutoff]
    if len(window) < 2:
        return None, len(window)
    return float(window.iloc[-1] / window.iloc[0] - 1.0), len(window)


def _compute_period_returns(
    holdings: list[dict],
    saved_date: Optional[date],
    notes: list[str],
    locale: str = "zh",
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
        notes.append(_t("fetch_failed_returns", locale, error=e))
        return result

    cutoff = pd.Timestamp(saved_date)
    for t in tickers:
        if t not in prices.columns:
            notes.append(_t("no_price_data", locale, ticker=t))
            continue
        ret, n_obs = _period_return_from_series(prices[t], cutoff)
        if ret is None:
            notes.append(
                _t(
                    "window_too_short",
                    locale,
                    ticker=t,
                    since=saved_date.isoformat(),
                    n_obs=n_obs,
                )
            )
            continue
        result[t] = ret
    return result


def _apply_drift(
    holdings: list[dict],
    period_returns: dict[str, Optional[float]],
    notes: list[str],
    locale: str = "zh",
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
            _t("drift_missing_returns", locale, names=_list_sep(locale).join(missing))
        )

    factors = [
        (1.0 + h["period_return"]) if h["period_return"] is not None else 1.0
        for h in holdings
    ]
    gross = sum(h["target_weight"] * f for h, f in zip(holdings, factors, strict=False))
    if gross <= 0:
        return
    for h, f in zip(holdings, factors, strict=False):
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


# Fleet-Wide Status Aggregation (P17 — overview alert lamp)


def compute_fleet_status(locale: str = "zh") -> dict:
    """
    Lightweight drift-band check across all stored IPS documents.

    Powers the overview-page alert lamp: every saved IPS is parsed with the
    exact same SAA mapping / normalization rules as compute_monitoring, but
    only band status is derived — no CME alignment, no portfolio metrics,
    no rebalance trades (compute_cme is deliberately never called here).

    A single shared fetch_price_history call covers the union of all mapped
    tickers over a period sized for the oldest saved_at; each document then
    slices its own drift window (saved_at -> latest close) out of that frame.

    Degradation rules (this function never raises):
        - price fetch failure        -> every document 'unknown' + note
        - missing SAA / parse error  -> that document 'unknown' + note
        - window shorter than 2 obs  -> affected tickers 'unknown'

    Args:
        locale: Language of the per-item ``note`` fields ("zh" / "en").

    Returns:
        Dict matching the api.schemas.MonitoringFleetResponse contract.
    """
    today = datetime.now().date()
    entries = _parse_fleet_documents(locale)

    # One shared fetch for the union of tickers, sized for the oldest SAA.
    tickers = sorted(
        {
            h["ticker"]
            for e in entries
            if e["holdings"]
            for h in e["holdings"]
            if h["ticker"]
        }
    )
    saved_dates = [e["saved_date"] for e in entries if e["saved_date"] is not None]

    prices: Optional[pd.DataFrame] = None
    fetch_note: Optional[str] = None
    if tickers and saved_dates:
        elapsed_days = max((today - min(saved_dates)).days, 1)
        try:
            prices = fetch_price_history(
                tickers=tickers,
                period=_choose_period(elapsed_days),
                interval="1d",
                adjust_currency=False,
            )
        except Exception as e:
            logger.warning("Fleet status price fetch failed: %s", e)
            fetch_note = _t("fleet_fetch_failed", locale, error=e)

    price_as_of = None
    if prices is not None and len(prices.index) > 0:
        price_as_of = pd.Timestamp(prices.index.max()).date().isoformat()

    items = [_fleet_item(e, prices, fetch_note, locale) for e in entries]
    items.sort(key=lambda item: item["saved_at"], reverse=True)

    return {
        "as_of": today.isoformat(),
        "price_as_of": price_as_of,
        "items": items,
        "summary": {
            "total": len(items),
            "breach": sum(1 for i in items if i["status"] == "breach"),
            "ok": sum(1 for i in items if i["status"] == "ok"),
            "unknown": sum(1 for i in items if i["status"] == "unknown"),
        },
    }


def _parse_fleet_documents(locale: str = "zh") -> list[dict]:
    """
    Enumerate stored IPS documents and parse each SAA into holdings.

    A document that fails to parse (corrupt payload, non-numeric weights,
    ...) degrades to an entry with ``error`` set — it never aborts the
    fleet run.
    """
    entries = []
    for summary in ips_storage.list_ips_documents():
        entry: dict = {
            "document_id": Path(summary["filepath"]).stem,
            "client_name": summary.get("client_name") or "Unknown",
            "saved_at": summary.get("saved_at", "") or "",
            "holdings": None,
            "saved_date": None,
            "notes": [],
            "error": None,
        }
        try:
            record = ips_storage.load_ips(Path(summary["filepath"]))
            ips = record.get("ips", {})
            meta = record.get("metadata", {})
            entry["client_name"] = (
                meta.get("client_name")
                or ips.get("client_name")
                or entry["client_name"]
            )
            entry["saved_at"] = meta.get("saved_at", "") or entry["saved_at"]
            saa = ips.get("investment_guidelines", {}).get("strategic_allocation") or []
            if not saa:
                entry["error"] = _t("fleet_missing_saa", locale)
            else:
                holdings = _build_holdings(saa, entry["notes"], locale)
                _normalize_weights(holdings, entry["notes"], locale)
                entry["holdings"] = holdings
                entry["saved_date"] = _parse_saved_date(
                    entry["saved_at"], entry["notes"], locale
                )
        except Exception as e:
            logger.warning(
                "Fleet status: cannot parse IPS document %s: %s",
                summary.get("filepath"),
                e,
            )
            entry["error"] = _t("fleet_parse_failed", locale, error=e)
        entries.append(entry)
    return entries


def _fleet_item(
    entry: dict,
    prices: Optional[pd.DataFrame],
    fetch_note: Optional[str],
    locale: str = "zh",
) -> dict:
    """
    Derive one document's fleet-status row from the shared price frame.

    Status: 'breach' when any holding sits above/below its policy band,
    'ok' when at least one holding has a known (within) band, otherwise
    'unknown' with a note (worded per ``locale``) explaining why.
    """
    item = {
        "document_id": entry["document_id"],
        "client_name": entry["client_name"],
        "saved_at": entry["saved_at"],
        "status": "unknown",
        "out_of_band": 0,
        "max_abs_drift_pp": None,
        "note": None,
    }
    if entry["error"] is not None:
        item["note"] = entry["error"]
        return item

    holdings = entry["holdings"]
    saved_date = entry["saved_date"]
    if prices is not None and saved_date is not None:
        cutoff = pd.Timestamp(saved_date)
        period_returns: dict[str, Optional[float]] = {}
        for t in sorted({h["ticker"] for h in holdings if h["ticker"]}):
            if t not in prices.columns:
                entry["notes"].append(_t("no_price_data", locale, ticker=t))
                period_returns[t] = None
                continue
            ret, n_obs = _period_return_from_series(prices[t], cutoff)
            if ret is None:
                entry["notes"].append(
                    _t(
                        "window_too_short",
                        locale,
                        ticker=t,
                        since=saved_date.isoformat(),
                        n_obs=n_obs,
                    )
                )
            period_returns[t] = ret
        _apply_drift(holdings, period_returns, entry["notes"], locale)
        _apply_bands(holdings)

        item["out_of_band"] = sum(
            1 for h in holdings if h["band_status"] in ("above", "below")
        )
        known_drifts = [h["drift_pp"] for h in holdings if h["drift_pp"] is not None]
        if known_drifts:
            item["max_abs_drift_pp"] = float(max(abs(d) for d in known_drifts))

        if item["out_of_band"]:
            item["status"] = "breach"
        elif any(h["band_status"] == "within" for h in holdings):
            item["status"] = "ok"

    if item["status"] == "unknown":
        if fetch_note is not None:
            item["note"] = fetch_note
        elif entry["notes"]:
            item["note"] = (
                "；".join(entry["notes"])
                if locale == "zh"
                else "; ".join(entry["notes"])
            )
        else:
            item["note"] = _t("fleet_insufficient_data", locale)
    return item


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
        trades.append(
            {
                "key": h["key"],
                "name": h["name"],
                "action": "buy" if weight_pp > 0 else "sell",
                "weight_pp": float(weight_pp),
            }
        )
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
