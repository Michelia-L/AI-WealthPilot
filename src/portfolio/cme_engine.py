"""
AI WealthPilot - Capital Market Expectations (CME) Engine

Computes Capital Market Expectations by leveraging existing quantitative
infrastructure (market_data.py, risk_metrics.py). Produces a structured
CMEReport that gets injected into the IPS generator's LLM context.

Pipeline:
    1. Fetch historical prices for IPS asset class proxies (yfinance)
    2. Compute returns, volatility, Sharpe, VaR, CVaR per asset class
    3. Compute correlation matrix
    4. Fetch dynamic risk-free rate (FRED / yfinance / fallback)
    5. Package into CMEReport (Pydantic)
    6. Format as LLM-readable text for prompt injection

CFA Reference:
    - CFA L3: Setting Capital Market Expectations
    - CFA L3: Asset Allocation with CME inputs
    - CFA L3: Historical approach to forecasting (with known limitations)
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
    IPS_ASSET_CLASS_TICKERS,
    TRADING_DAYS_PER_YEAR,
)
from src.data.market_data import (
    fetch_price_history,
    compute_returns,
    compute_correlation_matrix,
    fetch_risk_free_rate,
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


# ============================================================
# Core CME Computation
# ============================================================

def compute_cme(
    lookback_years: int = CME_LOOKBACK_YEARS,
    inflation: float = CME_INFLATION_ASSUMPTION,
    asset_tickers: Optional[dict] = None,
) -> CMEReport:
    """
    Compute Capital Market Expectations from historical market data.

    This is the main entry point for CME generation. It fetches
    historical prices, computes per-asset risk/return metrics,
    builds the correlation matrix, and packages everything into
    a structured CMEReport.

    Args:
        lookback_years: Number of years of historical data to use.
        inflation: Long-term inflation rate assumption.
        asset_tickers: Override asset class ticker mapping.
            Defaults to IPS_ASSET_CLASS_TICKERS from config.

    Returns:
        CMEReport with all asset class expectations.

    Raises:
        RuntimeError: If data fetching fails entirely.
    """
    logger.info("Computing CME with %d-year lookback", lookback_years)

    if asset_tickers is None:
        asset_tickers = IPS_ASSET_CLASS_TICKERS

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
        return _load_fallback_cme()

    if prices.empty or prices.shape[1] == 0:
        logger.warning("Empty price data, falling back to static CME")
        return _load_fallback_cme()

    # Step 2: Compute returns
    returns = compute_returns(prices, method="simple")

    # Step 3: Fetch dynamic risk-free rate
    rf_rate, rf_source = _fetch_risk_free_rate_with_source()

    # Step 4: Compute per-asset-class metrics
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
        ))

    if not asset_cme_list:
        logger.warning("No asset classes computed, falling back to static CME")
        return _load_fallback_cme()

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
    as_of = prices.index[-1].strftime("%Y-%m-%d") if hasattr(prices.index[-1], "strftime") else str(prices.index[-1])
    methodology = (
        f"基于 {lookback_years} 年历史数据（截至 {as_of}）计算。"
        f"预期收益率采用历史算术平均年化收益率。"
        f"波动率采用历史标准差年化（×√252）。"
        f"相关性矩阵基于简单收益率的 Pearson 相关系数。"
        f"无风险利率来源：{rf_source}。"
        f"通胀率假设：{inflation:.1%}。"
        f"局限性：历史数据不代表未来表现；"
        f"部分资产类别使用 ETF 代理（如 AGG 代理固定收益）；"
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
    )

    logger.info(
        "CME computed: %d asset classes, rf=%.4f (%s), as_of=%s",
        len(asset_cme_list), rf_rate, rf_source, as_of,
    )
    return report


# ============================================================
# Risk-Free Rate with Source Tracking
# ============================================================

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


# ============================================================
# Fallback CME Loading
# ============================================================

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


# ============================================================
# LLM Prompt Formatting
# ============================================================

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
    lines = [
        f"数据截止日期：{report.as_of_date}",
        f"历史回溯期：{report.data_lookback_years} 年",
        f"无风险利率：{report.risk_free_rate:.4f}（{report.risk_free_rate:.2%}）"
        f" [来源: {report.risk_free_rate_source}]",
        f"通胀率假设：{report.inflation_assumption:.4f}（{report.inflation_assumption:.2%}）",
        "",
        "## 各资产类别预期（基于历史数据）",
        "",
    ]

    # Asset class table
    lines.append(
        f"{'资产类别':<24} {'预期收益率':>10} {'波动率':>10} "
        f"{'夏普比率':>10} {'最大回撤':>10} {'95%VaR':>10} {'95%CVaR':>10}"
    )
    lines.append("─" * 100)

    for ac in report.asset_classes:
        lines.append(
            f"{ac.name:<24} {ac.expected_return:>10.2%} {ac.volatility:>10.2%} "
            f"{ac.sharpe_ratio:>10.4f} {ac.max_drawdown:>10.2%} "
            f"{ac.var_95:>10.4f} {ac.cvar_95:>10.4f}"
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
    lines.append(
        "以上数据基于历史表现计算，供 IPS 资产配置参考。"
        "LLM 在制定 SAA 时：\n"
        "1. 各资产类别的预期收益率和波动率必须参考上表数值\n"
        "2. 无风险利率和通胀率必须使用上述 CME 数值，不得自行假设\n"
        "3. 组合预期收益率 = Σ(权重_i × 预期收益率_i)，必须基于上表计算\n"
        "4. 历史数据不代表未来表现，需在风险披露中明确说明"
    )

    lines.append("")
    lines.append(f"方法论：{report.methodology_notes}")

    return "\n".join(lines)
