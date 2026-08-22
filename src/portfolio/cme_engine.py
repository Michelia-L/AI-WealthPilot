"""
AI WealthPilot - Capital Market Expectations (CME) Engine

Computes Capital Market Expectations by leveraging existing quantitative
infrastructure (market_data.py, risk_metrics.py). Produces a structured
CMEReport that gets injected into the IPS generator's LLM context.

Pipeline:
    1. Fetch historical prices for IPS asset class proxies (yfinance)
    2. Compute returns, volatility, Sharpe, VaR, CVaR per asset class
    3. Fetch implied volatility indices (VIX, MOVE) for weighted blending
    4. Compute blended volatility per asset class
    5. Compute correlation matrix
    6. Fetch dynamic risk-free rate (base-currency cascade)
    7. Package into CMEReport (Pydantic)
    8. Format as LLM-readable text for prompt injection


"""

import json
import logging
from pathlib import Path
from typing import Optional

import numpy as np

from src.config import (
    BASE_CURRENCY,
    CME_DATA_INTERVAL,
    CME_FORWARD_BLENDING_OMEGA,
    CME_INFLATION_ASSUMPTION,
    CME_IV_BLENDING_TAU,
    CME_LOOKBACK_YEARS,
    CME_REFERENCE_ALLOCATION,
    IPS_ASSET_CLASS_TICKERS,
    TRADING_DAYS_PER_YEAR,
)
from src.data.implied_volatility import (
    fetch_implied_volatility,
)
from src.data.market_data import (
    compute_correlation_matrix,
    compute_returns,
    fetch_price_history,
    fetch_risk_free_rate_detailed,
)
from src.portfolio.cme_cache import CMECacheManager
from src.portfolio.cme_models import AssetClassCME, CMEReport
from src.portfolio.forward_returns import fetch_forward_returns
from src.portfolio.risk_metrics import (
    conditional_var,
    max_drawdown,
    sharpe_ratio,
    value_at_risk,
)

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
    forward_blending_omega: float = CME_FORWARD_BLENDING_OMEGA,
    force_refresh: bool = False,
    cache_ttl_days: Optional[int] = None,
) -> tuple[CMEReport, str]:
    """
    Compute Capital Market Expectations from historical market data,
    enhanced with forward-looking implied volatility via weighted blending
    and forward-looking building-blocks expected returns.

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
        iv_blending_tau: Blending weight for implied volatility.
            0.0 = pure historical, 1.0 = pure implied.
            Defaults to CME_IV_BLENDING_TAU from config (0.5).
        forward_blending_omega: Blending weight for forward-looking
            building-blocks expected returns. 0.0 = pure historical,
            1.0 = pure forward. Defaults to CME_FORWARD_BLENDING_OMEGA
            from config (0.5).
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
        lookback_years,
        inflation,
        asset_tickers,
        iv_blending_tau,
        forward_blending_omega=forward_blending_omega,
        base_currency=BASE_CURRENCY,
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
        lookback_years,
        iv_blending_tau,
        " (force_refresh)" if force_refresh else "",
    )

    report = _compute_cme_fresh(
        lookback_years=lookback_years,
        inflation=inflation,
        asset_tickers=asset_tickers,
        iv_blending_tau=iv_blending_tau,
        forward_blending_omega=forward_blending_omega,
    )

    if report is not None:
        # Save to cache
        cache.save(report.model_dump(), params_hash)
        return report, "fresh"

    # --- Stale-while-revalidate fallback ---
    if cache.is_stale():
        stale_data = cache.load()
        if stale_data is not None:
            logger.warning("Fresh CME computation failed, using stale cache")
            return CMEReport(**stale_data), "stale"

    # --- Static fallback ---
    logger.warning("All CME sources failed, using static fallback")
    return _load_fallback_cme(), "fallback"


def _compute_cme_fresh(
    lookback_years: int,
    inflation: float,
    asset_tickers: dict,
    iv_blending_tau: float,
    forward_blending_omega: float,
) -> Optional[CMEReport]:
    """
    Perform the actual CME computation from live market data.

    This is the original compute_cme logic extracted into a helper
    so the main function can wrap it with caching.

    Args:
        lookback_years: Number of years of historical data to use.
        inflation: Long-term inflation rate assumption.
        asset_tickers: Asset class ticker mapping.
        iv_blending_tau: Blending weight for implied volatility.
        forward_blending_omega: Blending weight for forward-looking
            building-blocks expected returns.

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
            base_currency=BASE_CURRENCY,
            # FX-translate all asset classes to the CNY base currency so the
            # CME table is single-currency (unhedged FX exposure included).
            adjust_currency=True,
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

    # Step 3.6: Compute forward-looking expected returns (building blocks)
    forward_data = fetch_forward_returns(tickers, inflation, rf_rate)
    forward_available = any(v is not None for v in forward_data.values())
    if forward_available:
        logger.info(
            "Forward returns computed for %d asset classes",
            sum(1 for v in forward_data.values() if v is not None),
        )
    else:
        logger.info("No forward returns available, using pure historical means")

    # Step 4: Compute per-asset-class metrics (enhanced with IV blending)
    asset_cme_list = []
    for info in asset_tickers.values():
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
                ticker,
                len(asset_returns),
            )
            continue

        # Annualized metrics
        ann_return = float(asset_returns.mean() * TRADING_DAYS_PER_YEAR)
        ann_vol = float(asset_returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        sr = sharpe_ratio(asset_returns, risk_free_rate=rf_rate)
        mdd = max_drawdown(asset_prices)
        var95 = value_at_risk(asset_returns, confidence=0.95)
        cvar95 = conditional_var(asset_returns, confidence=0.95)

        # --- forward-looking expected return blending ---
        ticker_fwd = forward_data.get(ticker)
        if ticker_fwd is not None:
            expected_return = (
                forward_blending_omega * ticker_fwd.forward_return
                + (1 - forward_blending_omega) * ann_return
            )
            fwd_return = ticker_fwd.forward_return
            fwd_basis = ticker_fwd.basis
        else:
            expected_return = ann_return  # Graceful degradation
            fwd_return = None
            fwd_basis = None

        # --- weighted blending with implied volatility ---
        ticker_iv = iv_data.get(ticker)
        if ticker_iv is not None:
            implied_vol = ticker_iv.implied_volatility
            blended_vol = (
                iv_blending_tau * implied_vol + (1 - iv_blending_tau) * ann_vol
            )
            iv_source_label = f"{ticker_iv.iv_index_name} ({ticker_iv.iv_index_ticker})"
            regime = _classify_vol_regime(implied_vol, ann_vol)
            logger.debug(
                "%s: σ_hist=%.4f, σ_iv=%.4f, σ_blended=%.4f, regime=%s",
                ticker,
                ann_vol,
                implied_vol,
                blended_vol,
                regime,
            )
        else:
            implied_vol = None
            blended_vol = ann_vol  # Graceful degradation: use historical only
            iv_source_label = None
            regime = None

        asset_cme_list.append(
            AssetClassCME(
                name=name,
                ticker=ticker,
                expected_return=round(expected_return, 6),
                volatility=round(ann_vol, 6),
                sharpe_ratio=round(sr, 4),
                max_drawdown=round(mdd["max_drawdown"], 4),
                var_95=round(var95, 6),
                cvar_95=round(cvar95, 6),
                data_points=len(asset_returns),
                implied_volatility=round(implied_vol, 6)
                if implied_vol is not None
                else None,
                iv_source=iv_source_label,
                blended_volatility=round(blended_vol, 6),
                volatility_regime=regime,
                historical_return=round(ann_return, 6),
                forward_return=round(fwd_return, 6) if fwd_return is not None else None,
                forward_basis=fwd_basis,
            )
        )

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
            f"采用加权混合方法（τ={iv_blending_tau:.1f}）将前瞻性 IV 与历史波动率融合。"
            f"IV 来源：VIX（权益类）/ MOVE（固定收益类）。"
        )
    else:
        iv_note = "未获取到隐含波动率数据，仅使用历史波动率。"

    if forward_available:
        fwd_count = sum(1 for v in forward_data.values() if v is not None)
        fwd_note = (
            f"预期收益率采用 building-blocks 前视法与历史均值混合"
            f"（{fwd_count} 个资产类别有前视输入，ω={forward_blending_omega:.1f}）："
            f"权益=股息率+长期增长假设，固收=到期收益率代理，"
            f"黄金=通胀假设，现金=无风险利率；"
            f"前视输入不可用的资产类别回退为历史均值。"
            f"前视收益按资产本地货币计算，汇率预期变动假设为零。"
        )
    else:
        fwd_note = "预期收益率采用历史算术平均年化收益率（前视输入均不可用）。"

    methodology = (
        f"基于 {lookback_years} 年历史数据（截至 {as_of}）计算。"
        f"{fwd_note}"
        f"波动率采用加权混合方法：blended_vol = τ·σ_IV + (1-τ)·σ_hist。"
        f"{iv_note}"
        f"相关性矩阵基于简单收益率的 Pearson 相关系数。"
        f"无风险利率来源：{rf_source}。"
        f"所有资产类别收益已换算为人民币（CNY）口径；未对冲汇率风险。"
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
        forward_blending_omega=forward_blending_omega,
    )

    logger.info(
        "CME computed: %d asset classes, rf=%.4f (%s), iv_available=%s, as_of=%s",
        len(asset_cme_list),
        rf_rate,
        rf_source,
        iv_available,
        as_of,
    )
    return report


# Risk-Free Rate with Source Tracking


def _fetch_risk_free_rate_with_source() -> tuple[float, str]:
    """
    Fetch the base-currency risk-free rate and track which source provided it.

    Delegates to ``market_data.fetch_risk_free_rate_detailed`` on
    ``BASE_CURRENCY`` (CNY), so CME Sharpe ratios stay consistent with the
    CNY-denominated return basis.

    Returns:
        Tuple of (rate, source_name).
    """
    return fetch_risk_free_rate_detailed(currency=BASE_CURRENCY)


# Volatility Regime Classification


def _classify_vol_regime(implied_vol: float, historical_vol: float) -> str:
    """
    Classify the current volatility regime based on IV/HV ratio.

    The ratio of implied-to-historical volatility indicates whether
    the market is pricing in higher or lower future volatility
    compared to recent realized volatility.

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
            f"加权混合参数 τ（隐含波动率权重）：{report.iv_blending_tau:.1f}"
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
    has_fwd = any(ac.forward_return is not None for ac in report.asset_classes)
    fwd_header = f" {'前视收益':>10}" if has_fwd else ""

    if has_iv:
        lines.append(
            f"{'资产类别':<24} {'预期收益率':>10}{fwd_header} {'历史σ':>10} "
            f"{'隐含σ':>10} {'混合σ':>10} {'夏普比率':>10} {'最大回撤':>10}"
        )
    else:
        lines.append(
            f"{'资产类别':<24} {'预期收益率':>10}{fwd_header} {'波动率':>10} "
            f"{'夏普比率':>10} {'最大回撤':>10}"
        )
    lines.append("─" * 100)

    for ac in report.asset_classes:
        fwd_display = (
            f"{ac.forward_return:>10.2%}"
            if ac.forward_return is not None
            else f"{'N/A':>10}"
        )
        base_cols = f"{ac.name:<24} {ac.expected_return:>10.2%} "
        if has_fwd:
            base_cols += f"{fwd_display} "

        if has_iv:
            iv_display = (
                f"{ac.implied_volatility:>10.2%}"
                if ac.implied_volatility is not None
                else f"{'N/A':>10}"
            )
            blended_display = (
                f"{ac.blended_volatility:>10.2%}"
                if ac.blended_volatility is not None
                else f"{'N/A':>10}"
            )
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

    if has_fwd:
        lines.append("")
        lines.append("## 前视收益构成（building blocks）")
        lines.append("")
        for ac in report.asset_classes:
            if ac.forward_return is not None and ac.forward_basis:
                lines.append(f"- {ac.name}：{ac.forward_basis}")
        lines.append(
            "预期收益率 = ω × 前视 + (1-ω) × 历史均值"
            f"（ω={report.forward_blending_omega:.1f}）"
        )

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
        "1. 各资产类别的预期收益率必须参考上表数值（该值为前视 building-blocks "
        "与历史均值的混合，前视构成见「前视收益构成」一节；无前视输入的资产类别"
        "为纯历史均值）\n"
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


# Reference-Portfolio Suggestion (retirement planning)


def reference_portfolio_suggestion(
    report: CMEReport,
    allocation: Optional[dict[str, float]] = None,
) -> Optional[dict]:
    """Portfolio-level forward μ/σ for a reference allocation.

    Combines the report's blended expected returns, blended volatilities
    and correlation matrix into a single suggestion for the retirement
    planner's GBM inputs:

        μ_p = Σᵢ wᵢ·E(Rᵢ)
        σ_p = √( Σᵢⱼ wᵢwⱼ σᵢσⱼ ρᵢⱼ )

    Correlation edges missing from the matrix are treated as 0
    (uncorrelated) — conservative and honest about coverage gaps.

    Args:
        report: The CME report (cached or fresh).
        allocation: {IPS asset-class key: weight}; defaults to
            CME_REFERENCE_ALLOCATION. Classes absent from the report are
            dropped and the remaining weights renormalized.

    Returns:
        {"expected_return", "volatility", "allocation": {name: weight}}
        with the actual (renormalized) weights, or None when fewer than
        two asset classes are available.
    """
    if allocation is None:
        allocation = CME_REFERENCE_ALLOCATION

    by_name = {ac.name: ac for ac in report.asset_classes}
    entries = []  # (name, weight, mu, sigma)
    for key, w in allocation.items():
        info = IPS_ASSET_CLASS_TICKERS.get(key)
        if not info or float(w) <= 0:
            continue
        ac = by_name.get(info["name"])
        if ac is None:
            continue
        sigma = (
            ac.blended_volatility
            if ac.blended_volatility is not None
            else ac.volatility
        )
        entries.append((ac.name, float(w), ac.expected_return, float(sigma)))

    if len(entries) < 2:
        return None

    total = sum(w for _, w, _, _ in entries)
    weights = [w / total for _, w, _, _ in entries]
    names = [e[0] for e in entries]

    mu = sum(w * e[2] for w, e in zip(weights, entries, strict=False))
    var = 0.0
    for i in range(len(entries)):
        for j in range(len(entries)):
            rho = (
                1.0
                if i == j
                else report.correlation_matrix.get(names[i], {}).get(names[j], 0.0)
            )
            var += weights[i] * weights[j] * entries[i][3] * entries[j][3] * rho
    sigma = float(np.sqrt(max(var, 0.0)))

    return {
        "expected_return": round(mu, 6),
        "volatility": round(sigma, 6),
        "allocation": {names[i]: round(weights[i], 4) for i in range(len(entries))},
    }


# Risk-Level-Keyed Reference Allocation

# Intra-group splits for the risk-level reference allocation (documented
# assumptions): the equity budget is split across the three CME equity
# classes, the alternative budget across gold/REITs, and the remainder
# across fixed income + cash.
_LEVEL_EQUITY_SPLIT = {
    "domestic_equity": 0.5,
    "international_equity_dm": 0.4,
    "international_equity_hk": 0.1,
}
_LEVEL_ALT_SPLIT = {
    "alternative_gold": 0.75,
    "alternative_reit": 0.25,
}
_LEVEL_DEFENSIVE_SPLIT = {
    "fixed_income": 0.85,
    "cash": 0.15,
}


def reference_allocation_for_level(
    tolerance_level: str,
) -> Optional[dict[str, float]]:
    """Risk-level-keyed reference allocation derived from RISK_LEVEL_CAPS.

    The equity/alternative groups share a risk budget derived from their
    per-level caps (capped at 95% combined — caps are maxima and can
    exceed 100%, so aggressive levels are scaled proportionally); the
    remainder goes to fixed income + cash. Conservative levels whose
    caps sum to ≤ 95% sit exactly at their caps.

    Args:
        tolerance_level: Bilingual label, e.g. "Moderate / 平衡型".

    Returns:
        {IPS asset-class key: weight} summing to 1, or None when the
        label is unknown — callers then fall back to the static
        CME_REFERENCE_ALLOCATION.
    """
    from src.portfolio.risk_constraints import caps_for_tolerance

    try:
        caps = caps_for_tolerance(tolerance_level)
    except ValueError:
        return None

    # Caps are per-group *maxima* and can exceed 100% combined (进取型:
    # equity .90 + alternative .30 = 1.20), so they cannot be targets
    # directly. The risk budget is capped at 95% (some defensive ballast
    # is always kept) and split between the two groups proportionally to
    # their caps; conservative levels (E+A ≤ 0.95) sit at their caps.
    equity_cap = caps.get("equity", 0.0)
    alt_cap = caps.get("alternative", 0.0)
    risky_budget = min(equity_cap + alt_cap, 0.95)
    risky_cap_total = equity_cap + alt_cap
    if risky_cap_total > 0:
        equity = risky_budget * equity_cap / risky_cap_total
        alternative = risky_budget * alt_cap / risky_cap_total
    else:
        equity = alternative = 0.0
    defensive = 1.0 - equity - alternative

    allocation: dict[str, float] = {}
    for key, share in _LEVEL_EQUITY_SPLIT.items():
        allocation[key] = equity * share
    for key, share in _LEVEL_ALT_SPLIT.items():
        allocation[key] = alternative * share
    for key, share in _LEVEL_DEFENSIVE_SPLIT.items():
        allocation[key] = defensive * share
    return allocation
