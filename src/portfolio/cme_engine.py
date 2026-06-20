"""
AI WealthPilot - Capital Market Expectations (CME) Engine

Computes Capital Market Expectations by leveraging existing quantitative
infrastructure (market_data.py, risk_metrics.py). Produces a structured
CMEReport that gets injected into the IPS generator's LLM context.

Pipeline:
    1. Fetch historical prices for IPS asset class proxies (yfinance)
    2. Compute returns, volatility, Sharpe, VaR, CVaR per asset class
    3. Fetch implied volatility indices (VIX, MOVE) for Bayesian blending
    4. Compute Bayesian-blended volatility per asset class
    5. Compute correlation matrix
    6. Fetch dynamic risk-free rate (FRED / yfinance / fallback)
    7. Package into CMEReport (Pydantic)
    8. Format as LLM-readable text for prompt injection

CFA Reference:
    - CFA L3: Setting Capital Market Expectations
    - CFA L3: Asset Allocation with CME inputs
    - CFA L3: Historical approach (backward-looking)
    - CFA L3: Model-based approach (options-implied volatility)
    - CFA L3: Multi-method blending for robust CME
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from src.config import (
    CME_LOOKBACK_YEARS,
    CME_INFLATION_ASSUMPTION,
    CME_DATA_INTERVAL,
    CME_IV_BLENDING_TAU,
    IPS_ASSET_CLASS_TICKERS,
    TRADING_DAYS_PER_YEAR,
)
from src.portfolio.cme_cache import CMECacheManager
from src.data.market_data import (
    fetch_price_history,
    compute_returns,
    compute_correlation_matrix,
    fetch_risk_free_rate,
)
from src.data.implied_volatility import (
    fetch_implied_volatility,
    IV_PROXY_MAP,
)
from src.portfolio.risk_metrics import (
    sharpe_ratio,
    max_drawdown,
    value_at_risk,
    conditional_var,
)
from src.portfolio.cme_models import AssetClassCME, CMEReport

logger = logging.getLogger(__name__)

# Path to static fallback CME document
_FALLBACK_CME_PATH = (
    Path(__file__).parent.parent.parent / "docs" / "ips_reference" / "cme_fallback.json"
)


# Core CME Computation

def compute_cme(
    lookback_years: int = CME_LOOKBACK_YEARS,
    inflation: float = CME_INFLATION_ASSUMPTION,
    asset_tickers: Optional[dict] = None,
    iv_blending_tau: float = CME_IV_BLENDING_TAU,
    force_refresh: bool = False,
    cache_ttl_days: Optional[int] = None,
) -> tuple[CMEReport, str]:
    """
    Compute Capital Market Expectations from historical market data,
    enhanced with forward-looking implied volatility via Bayesian blending.

    This is the main entry point for CME generation. It supports a
    file-based caching layer: cached results are returned instantly
    when valid (within TTL and matching parameters). On cache miss
    or forced refresh, it fetches fresh data from yfinance.

    Three-tier degradation:
        1. Valid cache → instant return (no network I/O)
        2. Stale cache → attempt refresh, fall back to stale on failure
        3. No cache → full computation, fall back to static fallback

    Args:
        lookback_years: Number of years of historical data to use.
        inflation: Long-term inflation rate assumption.
        asset_tickers: Override asset class ticker mapping.
            Defaults to IPS_ASSET_CLASS_TICKERS from config.
        iv_blending_tau: Bayesian blending weight for implied volatility.
            0.0 = pure historical, 1.0 = pure implied.
            Defaults to CME_IV_BLENDING_TAU from config (0.5).
        force_refresh: If True, bypass cache and recompute from scratch.
        cache_ttl_days: Override cache TTL in days.
            Defaults to CME_CACHE_TTL_DAYS from config.

    Returns:
        Tuple of (CMEReport, cache_status) where cache_status is one of:
            'fresh' - newly computed from live data
            'cached' - returned from valid cache
            'stale' - returned from expired cache (refresh failed)
            'fallback' - returned from static fallback file

    Raises:
        RuntimeError: If all data sources fail (no cache, no fallback).
    """
    if asset_tickers is None:
        asset_tickers = IPS_ASSET_CLASS_TICKERS

    # --- Cache layer ---
    cache = CMECacheManager(ttl_days=cache_ttl_days)
    params_hash = CMECacheManager.compute_params_hash(
        lookback_years, inflation, asset_tickers, iv_blending_tau,
    )

    if not force_refresh and cache.is_valid(params_hash):
        cached_data = cache.load()
        if cached_data is not None:
            meta = cache.get_metadata()
            logger.info(
                "Using cached CME (computed_at=%s, hash=%s)",
                meta.get("computed_at", "?") if meta else "?",
                params_hash,
            )
            return CMEReport(**cached_data), "cached"

    # --- Fresh computation ---
    logger.info(
        "Computing CME with %d-year lookback, IV blending τ=%.2f%s",
        lookback_years, iv_blending_tau,
        " (force_refresh)" if force_refresh else "",
    )

    report = _compute_cme_fresh(
        lookback_years=lookback_years,
        inflation=inflation,
        asset_tickers=asset_tickers,
        iv_blending_tau=iv_blending_tau,
    )

    if report is not None:
        # Save to cache
        cache.save(report.model_dump(), params_hash)
        return report, "fresh"

    # --- Stale-while-revalidate fallback ---
    if cache.is_stale():
        stale_data = cache.load()
        if stale_data is not None:
            logger.warning(
                "Fresh CME computation failed, using stale cache"
            )
            return CMEReport(**stale_data), "stale"

    # --- Static fallback ---
    logger.warning("All CME sources failed, using static fallback")
    return _load_fallback_cme(), "fallback"


def _compute_cme_fresh(
    lookback_years: int,
    inflation: float,
    asset_tickers: dict,
    iv_blending_tau: float,
) -> Optional[CMEReport]:
    """
    Perform the actual CME computation from live market data.

    This is the original compute_cme logic extracted into a helper
    so the main function can wrap it with caching.

    Args:
        lookback_years: Number of years of historical data to use.
        inflation: Long-term inflation rate assumption.
        asset_tickers: Asset class ticker mapping.
        iv_blending_tau: Bayesian blending weight for implied volatility.

    Returns:
        CMEReport on success, None on failure.
    """
    # Step 1: Fetch historical prices
    tickers = [info["ticker"] for info in asset_tickers.values()]
    period = f"{lookback_years}y"

    try:
        prices = fetch_price_history(
            tickers=tickers,
            period=period,
            interval=CME_DATA_INTERVAL,
            adjust_currency=False,  # Keep in native currency for CME
        )
    except Exception as e:
        logger.error("Failed to fetch price data: %s", e)
        return None

    if prices.empty or prices.shape[1] == 0:
        logger.warning("Empty price data returned")
        return None

    # Step 2: Compute returns
    returns = compute_returns(prices, method="simple")

    # Step 3: Fetch dynamic risk-free rate
    rf_rate, rf_source = _fetch_risk_free_rate_with_source()

    # Step 3.5: Fetch implied volatility data
    iv_data = fetch_implied_volatility(tickers)
    iv_available = any(v is not None for v in iv_data.values())
    if iv_available:
        logger.info(
            "IV data fetched for %d asset classes",
            sum(1 for v in iv_data.values() if v is not None),
        )
    else:
        logger.info("No IV data available, using pure historical volatility")

    # Step 4: Compute per-asset-class metrics (enhanced with IV blending)
    asset_cme_list = []
    for key, info in asset_tickers.items():
        ticker = info["ticker"]
        name = info["name"]

        if ticker not in returns.columns:
            logger.warning("Ticker %s not found in data, skipping", ticker)
            continue

        asset_returns = returns[ticker].dropna()
        asset_prices = prices[ticker].dropna()

        if len(asset_returns) < 60:  # Need at least ~3 months of daily data
            logger.warning(
                "Insufficient data for %s (%d points), skipping",
                ticker, len(asset_returns),
            )
            continue

        # Annualized metrics
        ann_return = float(asset_returns.mean() * TRADING_DAYS_PER_YEAR)
        ann_vol = float(asset_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        sr = sharpe_ratio(asset_returns, risk_free_rate=rf_rate)
        mdd = max_drawdown(asset_prices)
        var95 = value_at_risk(asset_returns, confidence=0.95)
        cvar95 = conditional_var(asset_returns, confidence=0.95)

        # --- Bayesian blending with implied volatility ---
        ticker_iv = iv_data.get(ticker)
        if ticker_iv is not None:
            implied_vol = ticker_iv.implied_volatility
            blended_vol = (
                iv_blending_tau * implied_vol
                + (1 - iv_blending_tau) * ann_vol
            )
            iv_source_label = (
                f"{ticker_iv.iv_index_name} ({ticker_iv.iv_index_ticker})"
            )
            regime = _classify_vol_regime(implied_vol, ann_vol)
            logger.debug(
                "%s: σ_hist=%.4f, σ_iv=%.4f, σ_blended=%.4f, regime=%s",
                ticker, ann_vol, implied_vol, blended_vol, regime,
            )
        else:
            implied_vol = None
            blended_vol = ann_vol  # Graceful degradation: use historical only
            iv_source_label = None
            regime = None

        asset_cme_list.append(AssetClassCME(
            name=name,
            ticker=ticker,
            expected_return=round(ann_return, 6),
            volatility=round(ann_vol, 6),
            sharpe_ratio=round(sr, 4),
            max_drawdown=round(mdd["max_drawdown"], 4),
            var_95=round(var95, 6),
            cvar_95=round(cvar95, 6),
            data_points=len(asset_returns),
            implied_volatility=round(implied_vol, 6) if implied_vol is not None else None,
            iv_source=iv_source_label,
            blended_volatility=round(blended_vol, 6),
            volatility_regime=regime,
        ))

    if not asset_cme_list:
        logger.warning("No asset classes computed")
        return None

    # Step 5: Compute correlation matrix
    available_tickers = [ac.ticker for ac in asset_cme_list]
    available_names = [ac.name for ac in asset_cme_list]
    corr_df = compute_correlation_matrix(prices[available_tickers])

    # Convert to nested dict with asset names as keys
    corr_dict: dict[str, dict[str, float]] = {}
    for i, name_i in enumerate(available_names):
        corr_dict[name_i] = {}
        for j, name_j in enumerate(available_names):
            ticker_i = available_tickers[i]
            ticker_j = available_tickers[j]
            val = corr_df.loc[ticker_i, ticker_j]
            corr_dict[name_i][name_j] = round(float(val), 4)

    # Step 6: Build methodology notes
    as_of = (
        prices.index[-1].strftime("%Y-%m-%d")
        if hasattr(prices.index[-1], "strftime")
        else str(prices.index[-1])
    )

    iv_note = ""
    if iv_available:
        iv_count = sum(1 for v in iv_data.values() if v is not None)
        iv_note = (
            f"隐含波动率数据已获取（{iv_count} 个资产类别），"
            f"采用贝叶斯混合方法（τ={iv_blending_tau:.1f}）将前瞻性 IV 与历史波动率融合。"
            f"IV 来源：VIX（权益类）/ MOVE（固定收益类）。"
        )
    else:
        iv_note = "未获取到隐含波动率数据，仅使用历史波动率。"

    methodology = (
        f"基于 {lookback_years} 年历史数据（截至 {as_of}）计算。"
        f"预期收益率采用历史算术平均年化收益率。"
        f"波动率采用贝叶斯混合方法：blended_vol = τ·σ_IV + (1-τ)·σ_hist。"
        f"{iv_note}"
        f"相关性矩阵基于简单收益率的 Pearson 相关系数。"
        f"无风险利率来源：{rf_source}。"
        f"通胀率假设：{inflation:.1%}。"
        f"局限性：历史数据不代表未来表现；"
        f"部分资产类别使用 ETF 代理（如 AGG 代理固定收益）；"
        f"隐含波动率仅限可用资产类别（VIX 代理权益，MOVE 代理固收）；"
        f"中国境内资产的 yfinance 数据覆盖可能不完整。"
    )

    report = CMEReport(
        as_of_date=as_of,
        data_lookback_years=lookback_years,
        risk_free_rate=round(rf_rate, 6),
        risk_free_rate_source=rf_source,
        inflation_assumption=inflation,
        asset_classes=asset_cme_list,
        correlation_matrix=corr_dict,
        methodology_notes=methodology,
        iv_blending_tau=iv_blending_tau,
        iv_data_available=iv_available,
    )

    logger.info(
        "CME computed: %d asset classes, rf=%.4f (%s), iv_available=%s, as_of=%s",
        len(asset_cme_list), rf_rate, rf_source, iv_available, as_of,
    )
    return report


# Risk-Free Rate with Source Tracking

def _fetch_risk_free_rate_with_source() -> tuple[float, str]:
    """
    Fetch risk-free rate and track which source provided it.

    Returns:
        Tuple of (rate, source_name).
    """
    import os
    from src.config import FRED_API_KEY, DEFAULT_RISK_FREE_RATE

    api_key = FRED_API_KEY or os.getenv("FRED_API_KEY")

    # Try FRED first
    if api_key:
        try:
            import requests
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                "series_id": "DGS3MO",
                "api_key": api_key,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            }
            response = requests.get(url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                observations = data.get("observations", [])
                if observations:
                    val_str = observations[0].get("value")
                    if val_str and val_str != ".":
                        return float(val_str) / 100.0, "fred_api"
        except Exception:
            pass

    # Try yfinance
    try:
        import yfinance as yf
        ticker = yf.Ticker("^IRX")
        rate_pct = ticker.fast_info.get("lastPrice")
        if rate_pct is not None and rate_pct > 0:
            return float(rate_pct) / 100.0, "yfinance_irx"
    except Exception:
        pass

    # Static fallback
    return DEFAULT_RISK_FREE_RATE, "static_fallback"


# Volatility Regime Classification

def _classify_vol_regime(implied_vol: float, historical_vol: float) -> str:
    """
    Classify the current volatility regime based on IV/HV ratio.

    The ratio of implied-to-historical volatility indicates whether
    the market is pricing in higher or lower future volatility
    compared to recent realized volatility.

    CFA Reference:
        CFA L3 — VIX premium/discount to realized vol as a
        forward-looking risk signal. IV/HV > 1 suggests risk-off
        sentiment; IV/HV < 1 suggests complacency.

    Thresholds (based on empirical VIX research):
        ratio < 0.8  → 'low'       (market complacent)
        0.8 ≤ ratio < 1.2 → 'normal'
        1.2 ≤ ratio < 1.6 → 'elevated' (market cautious)
        ratio ≥ 1.6 → 'high'       (market stressed)

    Args:
        implied_vol: Annualized implied volatility as decimal.
        historical_vol: Annualized historical volatility as decimal.

    Returns:
        Regime label: 'low', 'normal', 'elevated', or 'high'.
    """
    if historical_vol <= 0:
        return "normal"
    ratio = implied_vol / historical_vol
    if ratio < 0.8:
        return "low"
    elif ratio < 1.2:
        return "normal"
    elif ratio < 1.6:
        return "elevated"
    else:
        return "high"


# Fallback CME Loading

def _load_fallback_cme() -> CMEReport:
    """
    Load the static fallback CME document.

    Used when dynamic CME generation fails (network issues, etc.).

    Returns:
        CMEReport parsed from the fallback JSON file.

    Raises:
        RuntimeError: If the fallback file is also unavailable.
    """
    if not _FALLBACK_CME_PATH.exists():
        raise RuntimeError(
            f"CME fallback file not found at {_FALLBACK_CME_PATH}. "
            "Cannot generate CME without market data or fallback."
        )

    logger.warning("Using static fallback CME from %s", _FALLBACK_CME_PATH)
    with open(_FALLBACK_CME_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    return CMEReport(**data)


# LLM Prompt Formatting

def format_cme_for_prompt(report: CMEReport) -> str:
    """
    Format a CMEReport as LLM-readable text for prompt injection.

    Produces a structured, human-readable summary of all CME data
    that the IPS generator agent can reference when constructing
    asset allocations and return feasibility assessments.

    Args:
        report: The CMEReport to format.

    Returns:
        Formatted string ready for prompt injection.
    """
    # IV availability note
    iv_header_note = ""
    if report.iv_data_available:
        iv_header_note = (
            f"贝叶斯混合参数 τ（隐含波动率权重）：{report.iv_blending_tau:.1f}"
        )
    else:
        iv_header_note = "未获取到隐含波动率数据，仅显示历史波动率"

    lines = [
        f"数据截止日期：{report.as_of_date}",
        f"历史回溯期：{report.data_lookback_years} 年",
        f"无风险利率：{report.risk_free_rate:.4f}（{report.risk_free_rate:.2%}）"
        f" [来源: {report.risk_free_rate_source}]",
        f"通胀率假设：{report.inflation_assumption:.4f}（{report.inflation_assumption:.2%}）",
        f"波动率方法论：{iv_header_note}",
        "",
        "## 各资产类别预期",
        "",
    ]

    # Asset class table — now includes IV and blended volatility columns
    has_iv = report.iv_data_available and any(
        ac.implied_volatility is not None for ac in report.asset_classes
    )
    has_regime = any(ac.volatility_regime is not None for ac in report.asset_classes)

    if has_iv:
        lines.append(
            f"{'资产类别':<24} {'预期收益率':>10} {'历史σ':>10} "
            f"{'隐含σ':>10} {'混合σ':>10} {'夏普比率':>10} {'最大回撤':>10}"
        )
    else:
        lines.append(
            f"{'资产类别':<24} {'预期收益率':>10} {'波动率':>10} "
            f"{'夏普比率':>10} {'最大回撤':>10}"
        )
    lines.append("─" * 100)

    for ac in report.asset_classes:
        base_cols = (
            f"{ac.name:<24} {ac.expected_return:>10.2%} "
        )

        if has_iv:
            iv_display = f"{ac.implied_volatility:>10.2%}" if ac.implied_volatility is not None else f"{'N/A':>10}"
            blended_display = f"{ac.blended_volatility:>10.2%}" if ac.blended_volatility is not None else f"{'N/A':>10}"
            regime_tag = f" [{ac.volatility_regime}]" if ac.volatility_regime else ""

            base_cols += (
                f"{ac.volatility:>10.2%} {iv_display} {blended_display}{regime_tag}"
                f"  {ac.sharpe_ratio:>10.4f} {ac.max_drawdown:>10.2%}"
            )
        else:
            base_cols += (
                f"{ac.volatility:>10.2%} "
                f"{ac.sharpe_ratio:>10.4f} {ac.max_drawdown:>10.2%}"
            )

        lines.append(base_cols)

    lines.append("")
    lines.append("## 相关性矩阵")
    lines.append("")

    # Correlation matrix
    names = [ac.name for ac in report.asset_classes]
    short_names = [n[:8] for n in names]

    header = f"{'':>16}" + "".join(f"{sn:>10}" for sn in short_names)
    lines.append(header)

    for name in names:
        row_vals = report.correlation_matrix.get(name, {})
        row_str = f"{name[:16]:<16}"
        for other_name in names:
            val = row_vals.get(other_name, 0.0)
            row_str += f"{val:>10.3f}"
        lines.append(row_str)

    lines.append("")
    lines.append("## 使用说明")
    lines.append("")
    usage = [
        "以上数据供 IPS 资产配置参考。LLM 在制定 SAA 时：\n"
        "1. 各资产类别的预期收益率必须参考上表数值\n"
        "2. 无风险利率和通胀率必须使用上述 CME 数值，不得自行假设\n"
        "3. 组合预期收益率 = Σ(权重_i × 预期收益率_i)，必须基于上表计算\n"
        "4. 优先使用「混合波动率」（blended_volatility）衡量风险，"
        "该指标融合了历史波动率与市场隐含波动率（VIX/MOVE）\n"
        "5. 如果「隐含σ」>「历史σ」，说明市场预期未来风险上升（风险规避情绪），"
        "应在风险披露中明确提示\n"
        "6. 「波动率环境」（volatility_regime）标签含义："
        "low=市场自满, normal=正常, elevated=市场谨慎, high=市场承压\n"
        "7. 历史数据不代表未来表现，需在风险披露中明确说明",
    ]
    lines.extend(usage)

    lines.append("")
    lines.append(f"方法论：{report.methodology_notes}")

    return "\n".join(lines)
