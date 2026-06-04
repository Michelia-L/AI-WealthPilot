"""
AI WealthPilot - Market Data Acquisition Module
AI WealthPilot - 市场数据获取模块

This module is the foundational data layer of the AI WealthPilot system.
It fetches historical and real-time market data for the defined asset universe
using the yfinance library, and provides clean pandas DataFrames for
downstream portfolio analysis, optimization, and risk assessment.

本模块是 AI WealthPilot 系统的基础数据层。
通过 yfinance 库获取预定义资产池的历史和实时市场数据，
并提供清洗后的 pandas DataFrame，供下游的投资组合分析、优化和风险评估使用。

CFA Reference / CFA 参考:
    - CFA L1: Quantitative Methods - Time-Series Analysis
      CFA 一级：定量方法 - 时间序列分析
    - CFA L3: Asset Allocation - Capital Market Expectations
      CFA 三级：资产配置 - 资本市场预期
    - Data quality and consistency are critical for any quantitative
      investment process (GIPS standards).
      数据质量和一致性对任何量化投资流程至关重要（GIPS 标准）。
"""

import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# 从项目配置中导入资产池、年交易日数和基准货币
# Import the asset universe definition, trading days constant, and base currency from project config
from src.config import ASSET_UNIVERSE, TRADING_DAYS_PER_YEAR, BASE_CURRENCY


def fetch_price_history(
    tickers: Optional[list[str]] = None,
    period: str = "5y",
    interval: str = "1d",
    base_currency: Optional[str] = None,
    adjust_currency: bool = True,
) -> pd.DataFrame:
    """
    Fetch adjusted close prices for a list of tickers, with optional currency translation.
    获取一组股票/资产的调整后收盘价，支持可选的汇率折算。

    This function downloads historical price data from Yahoo Finance.
    It uses "adjusted close" prices (auto_adjust=True), which account for
    stock splits and dividends. If adjust_currency is True, it automatically
    downloads required exchange rates and converts all asset price series to
    the specified base currency to prevent exchange rate distortion.

    本函数从 Yahoo Finance 下载历史价格数据。
    使用"调整后收盘价"（auto_adjust=True），已经考虑了股票拆分和分红。
    如果 adjust_currency 为 True，系统会自动下载所需的汇率，并将所有资产的价格
    序列折算为指定的基准货币计价，以防止汇率波动扭曲投资组合的统计特征。

    CFA Reference / CFA 参考:
        - CFA L3: Asset Allocation - Currency Management & Asset Allocation
          Asset returns and covariances must be computed in a consistent base/reporting
          currency. Unadjusted local returns ignore exchange rate volatility and the
          covariance between asset returns and currency movements, leading to distorted
          Mean-Variance Optimization (MVO) frontiers.
          资产收益率和协方差必须在统一的基准/报告货币下计算。未调整的本币收益率忽略了
          汇率波动率以及资产收益率与汇率变动之间的协方差，从而导致均值-方差优化（MVO）前沿失真。

    Args:
        tickers: List of Yahoo Finance ticker symbols.
                 Defaults to all tickers in ASSET_UNIVERSE.
                 Yahoo Finance 股票代码列表。
                 默认使用 ASSET_UNIVERSE 中的所有代码。
        period: Data period to download (e.g., '1y', '5y', '10y', 'max').
                下载数据的时间跨度（如 '1y'、'5y'、'10y'、'max'）。
        interval: Data interval / frequency (e.g., '1d', '1wk', '1mo').
                  数据频率（如 '1d' 日频、'1wk' 周频、'1mo' 月频）。
        base_currency: The target reporting currency (e.g., 'USD', 'CNY').
                       Defaults to BASE_CURRENCY from config.py.
                       目标报告货币（如 'USD'、'CNY'）。
                       默认使用 config.py 中的 BASE_CURRENCY。
        adjust_currency: If True, convert all assets' prices to base_currency.
                         如果为 True，将所有资产的价格折算为 base_currency 计价。

    Returns:
        DataFrame with DatetimeIndex and one column per ticker (adjusted close in base currency).
        返回以日期为索引、每个资产为一列的 DataFrame（基准货币计价的调整后收盘价）。
    """
    # 如果没有指定 tickers，则使用配置文件中定义的完整资产池
    # If no tickers specified, use the full asset universe from config
    if tickers is None:
        tickers = list(ASSET_UNIVERSE.keys())

    if base_currency is None:
        base_currency = BASE_CURRENCY

    # 确定需要下载的汇率 Tickers
    # Determine the exchange rate tickers to download
    fx_tickers_to_download = []
    if adjust_currency:
        for t in tickers:
            asset_info = ASSET_UNIVERSE.get(t, {})
            curr = asset_info.get("currency", "USD")
            # 如果资产结算货币不是 base_currency，且不是 Index/Rate，需要该货币相对于 USD 的汇率
            # If asset currency is different from base_currency, and not Index/Rate, fetch its rate to USD
            if curr not in ["Index", "Rate", base_currency]:
                if curr != "USD":
                    fx_tickers_to_download.append(f"{curr}=X")
        # 如果 base_currency 不是 USD，且不是 Index/Rate，我们也需要 base_currency 相对于 USD 的汇率来进行二次折算
        # If base_currency is not USD, we also need its rate to USD for secondary conversion
        if base_currency not in ["Index", "Rate", "USD"]:
            fx_tickers_to_download.append(f"{base_currency}=X")

        # 去重
        # Deduplicate
        fx_tickers_to_download = list(set(fx_tickers_to_download))

    # 合并下载列表（保持原请求的 tickers 顺序）
    # Combine download list (preserving original tickers order)
    all_download_tickers = []
    for t in (tickers + fx_tickers_to_download):
        if t not in all_download_tickers:
            all_download_tickers.append(t)

    # 使用 yfinance 批量下载数据
    # auto_adjust=True: 自动将收盘价调整为考虑分红 and 拆分后的价格
    # Download data in batch using yfinance
    data = yf.download(all_download_tickers, period=period, interval=interval, auto_adjust=True)

    # 提取收盘价，统一转换为以 Ticker 为列名的 DataFrame
    # Extract Close prices, unify to a DataFrame with tickers as columns
    if isinstance(data.columns, pd.MultiIndex):
        prices = data["Close"].copy()
    else:
        prices = data[["Close"]].copy()
        prices.columns = all_download_tickers

    # 填充因为跨市场节假日不一致导致的缺失值（仅针对下载的汇率列，保留资产原有的 NaN 特征）
    # Forward/backward fill only the exchange rate columns to handle trading days mismatch
    fx_cols = [c for c in prices.columns if c.endswith("=X")]
    if fx_cols:
        prices[fx_cols] = prices[fx_cols].ffill().bfill()

    # 进行汇率折算
    # Perform currency translation
    if adjust_currency:
        for t in tickers:
            asset_info = ASSET_UNIVERSE.get(t, {})
            curr = asset_info.get("currency", "USD")

            # 1. 第一步：将非美元资产的价格折算为美元计价的价格
            # Step 1: convert non-USD prices to USD-denominated prices
            if curr not in ["Index", "Rate", "USD"]:
                fx_t = f"{curr}=X"
                if fx_t in prices.columns:
                    prices[t] = prices[t] / prices[fx_t]

            # 2. 第二步：若基准货币不是美元，则将美元价格折算为基准货币价格
            # Step 2: if base_currency is not USD, convert USD-denominated prices to base currency
            if base_currency != "USD" and curr not in ["Index", "Rate"]:
                base_fx_t = f"{base_currency}=X"
                if base_fx_t in prices.columns:
                    prices[t] = prices[t] * prices[base_fx_t]

    # 仅保留用户请求的资产代码，过滤掉汇率序列
    # Keep only the requested tickers, filtering out temporary exchange rates
    prices = prices[tickers]

    # 删除所有值都为 NaN 的行
    # Drop rows where ALL values are NaN
    prices = prices.dropna(how="all")

    return prices


def compute_returns(prices: pd.DataFrame, method: str = "log") -> pd.DataFrame:
    """
    Compute returns from price series.
    从价格序列计算收益率。

    Supports two return calculation methods:
    支持两种收益率计算方式：

    1. Log returns (对数收益率):
       r_t = ln(P_t / P_{t-1})
       - Preferred for statistical modeling because they are time-additive:
         the sum of daily log returns = the log return over the full period.
       - 在统计建模中更受青睐，因为对数收益率具有时间可加性：
         日对数收益率之和 = 整个期间的对数收益率。

    2. Simple / Arithmetic returns (简单/算术收益率):
       r_t = (P_t - P_{t-1}) / P_{t-1}
       - More intuitive; represents the actual percentage gain/loss.
       - Cross-sectionally additive: portfolio return = weighted sum of asset returns.
       - 更直观，表示实际的百分比盈亏。
       - 横截面可加性：组合收益率 = 各资产收益率的加权和。

    CFA Reference / CFA 参考:
        CFA L1 Quantitative Methods: Distinguish between arithmetic and
        geometric (≈ log) returns; arithmetic returns are used for
        expected return estimation, geometric for compounding analysis.
        CFA 一级定量方法：区分算术收益率和几何收益率（≈ 对数收益率）；
        算术收益率用于预期收益率估计，几何收益率用于复利分析。

    Args:
        prices: DataFrame of adjusted close prices.
                调整后收盘价的 DataFrame。
        method: 'log' for log returns, 'simple' for arithmetic returns.
                'log' 表示对数收益率，'simple' 表示算术收益率。

    Returns:
        DataFrame of returns (first row dropped due to NaN from differencing).
        收益率 DataFrame（第一行因差分产生 NaN 而被删除）。
    """
    if method == "log":
        # 对数收益率公式: r_t = ln(P_t / P_{t-1})
        # Log return formula: r_t = ln(P_t / P_{t-1})
        returns = np.log(prices / prices.shift(1))
    else:
        # 简单收益率: r_t = (P_t - P_{t-1}) / P_{t-1}
        # pct_change() 等价于 (P_t / P_{t-1}) - 1
        # Simple return: r_t = (P_t - P_{t-1}) / P_{t-1}
        # pct_change() is equivalent to (P_t / P_{t-1}) - 1
        returns = prices.pct_change()

    # 删除第一行的 NaN（因为 t=0 时没有前一天的价格来计算收益率）
    # Drop the first row NaN (no previous price at t=0 to compute return)
    return returns.dropna()


def compute_correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Compute correlation matrix from price series.
    从价格序列计算相关性矩阵。

    Correlation measures the linear relationship between asset returns,
    ranging from -1 (perfect negative) to +1 (perfect positive).
    Low or negative correlation between assets is key for portfolio
    diversification — the foundation of Modern Portfolio Theory (MPT).

    相关性衡量资产收益率之间的线性关系，
    取值范围从 -1（完全负相关）到 +1（完全正相关）。
    资产之间低相关或负相关是投资组合分散化的关键——
    这是现代投资组合理论（MPT）的基础。

    CFA Reference / CFA 参考:
        CFA L1/L2 Portfolio Management: Correlation is a critical input
        to the covariance matrix used in Mean-Variance Optimization.
        Diversification benefit increases as correlation decreases.
        CFA 一级/二级投资组合管理：相关性是均值-方差优化中
        协方差矩阵的关键输入。相关性越低，分散化收益越大。

    Args:
        prices: DataFrame of adjusted close prices.
                调整后收盘价的 DataFrame。

    Returns:
        Correlation matrix DataFrame (symmetric, diagonal = 1.0).
        相关性矩阵 DataFrame（对称矩阵，对角线为 1.0）。
    """
    # 先计算简单收益率，再求 Pearson 相关系数矩阵
    # 注意：使用简单收益率而非对数收益率，因为简单收益率在横截面上更直观
    # First compute simple returns, then calculate Pearson correlation matrix
    # Note: using simple returns (not log) as they are more intuitive cross-sectionally
    returns = compute_returns(prices, method="simple")
    return returns.corr()


def get_latest_quotes(tickers: Optional[list[str]] = None) -> pd.DataFrame:
    """
    Get the latest quote data for a list of tickers.
    获取一组资产的最新行情数据。

    Fetches real-time (or near real-time) price information including
    the last traded price and the previous close. Computes the daily
    price change and percentage change for quick market overview.

    获取实时（或近实时）价格信息，包括最新成交价和前收盘价。
    计算日涨跌额和涨跌幅，用于快速的市场概览。

    Args:
        tickers: List of ticker symbols. Defaults to ASSET_UNIVERSE.
                 股票代码列表。默认使用 ASSET_UNIVERSE。

    Returns:
        DataFrame with columns: ticker, name, category, price,
        previous_close, change, change_pct.
        返回包含以下列的 DataFrame：ticker（代码）、name（名称）、
        category（类别）、price（最新价）、previous_close（前收盘价）、
        change（涨跌额）、change_pct（涨跌幅%）。
    """
    # 如果没有指定 tickers，使用默认资产池
    # If no tickers specified, use the default asset universe
    if tickers is None:
        tickers = list(ASSET_UNIVERSE.keys())

    records = []
    for ticker in tickers:
        try:
            # fast_info 提供轻量级的实时行情数据，比 info 属性更快
            # fast_info provides lightweight real-time quote data, faster than the info property
            info = yf.Ticker(ticker).fast_info
            # 从 ASSET_UNIVERSE 配置中获取资产的名称和分类信息
            # Get the asset's display name and category from the ASSET_UNIVERSE config
            asset_info = ASSET_UNIVERSE.get(ticker, {})
            records.append({
                "ticker": ticker,
                "name": asset_info.get("name", ticker),
                "category": asset_info.get("category", "Unknown"),
                "price": info.get("lastPrice", None),
                "previous_close": info.get("previousClose", None),
            })
        except Exception:
            # 如果某个 ticker 获取失败（如网络问题、代码无效），跳过并继续
            # If a ticker fails to fetch (e.g., network issue, invalid symbol), skip it
            continue

    df = pd.DataFrame(records)

    # 计算涨跌额和涨跌幅（仅在数据存在时计算）
    # Calculate price change and percentage change (only when data is available)
    # change = 最新价 - 前收盘价 / change = last price - previous close
    # change_pct = (涨跌额 / 前收盘价) × 100 / change_pct = (change / previous_close) × 100
    if not df.empty and "price" in df.columns and "previous_close" in df.columns:
        df["change"] = df["price"] - df["previous_close"]
        df["change_pct"] = (df["change"] / df["previous_close"]) * 100

    return df


# ==========================================
# 主程序入口 - 用于快速测试和验证
# Main entry point - for quick testing and validation
# ==========================================
if __name__ == "__main__":
    # 快速测试：下载 SPY（标普500 ETF）、GLD（黄金 ETF）、BTC-USD（比特币）的一年数据
    # Quick test: download 1 year of data for SPY (S&P 500 ETF), GLD (Gold ETF), BTC-USD (Bitcoin)
    print("Fetching sample data...")
    prices = fetch_price_history(["SPY", "GLD", "BTC-USD"], period="1y")
    print(f"Fetched {len(prices)} trading days of data")
    print(prices.tail())

    # 打印相关性矩阵，观察资产之间的相关性（分散化分析的基础）
    # Print correlation matrix to observe inter-asset correlation (basis for diversification analysis)
    print("\nCorrelation matrix:")
    print(compute_correlation_matrix(prices))
