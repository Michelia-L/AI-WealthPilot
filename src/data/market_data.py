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
from datetime import datetime, timedelta
from typing import Optional

# 从项目配置中导入资产池和年交易日数
# Import the asset universe definition and trading days constant from project config
from src.config import ASSET_UNIVERSE, TRADING_DAYS_PER_YEAR


def fetch_price_history(
    tickers: Optional[list[str]] = None,
    period: str = "5y",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Fetch adjusted close prices for a list of tickers.
    获取一组股票/资产的调整后收盘价。

    This function downloads historical price data from Yahoo Finance.
    It uses "adjusted close" prices (auto_adjust=True), which account for
    stock splits and dividends, ensuring the price series accurately
    reflects the true total return an investor would have received.

    本函数从 Yahoo Finance 下载历史价格数据。
    使用"调整后收盘价"（auto_adjust=True），已经考虑了股票拆分和分红，
    确保价格序列准确反映投资者实际获得的总回报。

    CFA Reference / CFA 参考:
        Adjusted close prices are essential for computing accurate historical
        returns, which form the basis of Mean-Variance Optimization (MVO).
        调整后收盘价对于计算准确的历史收益率至关重要，
        而历史收益率是均值-方差优化（MVO）的基础输入。

    Args:
        tickers: List of Yahoo Finance ticker symbols.
                 Defaults to all tickers in ASSET_UNIVERSE.
                 Yahoo Finance 股票代码列表。
                 默认使用 ASSET_UNIVERSE 中的所有代码。
        period: Data period to download (e.g., '1y', '5y', '10y', 'max').
                A longer period provides more data for statistical analysis,
                but may include regime changes.
                下载数据的时间跨度（如 '1y'、'5y'、'10y'、'max'）。
                更长的时间跨度提供更多统计分析数据，但可能包含市场制度变化。
        interval: Data interval / frequency (e.g., '1d', '1wk', '1mo').
                  Daily data ('1d') is the most common for portfolio analysis.
                  数据频率（如 '1d' 日频、'1wk' 周频、'1mo' 月频）。
                  日频数据（'1d'）是投资组合分析中最常用的。

    Returns:
        DataFrame with DatetimeIndex and one column per ticker (adjusted close).
        返回以日期为索引、每个资产为一列的 DataFrame（调整后收盘价）。
    """
    # 如果没有指定 tickers，则使用配置文件中定义的完整资产池
    # If no tickers specified, use the full asset universe from config
    if tickers is None:
        tickers = list(ASSET_UNIVERSE.keys())

    # 使用 yfinance 批量下载数据
    # auto_adjust=True: 自动将收盘价调整为考虑分红和拆分后的价格
    # Download data in batch using yfinance
    # auto_adjust=True: automatically adjusts prices for dividends and splits
    data = yf.download(tickers, period=period, interval=interval, auto_adjust=True)

    # yfinance 在下载多个 ticker 时返回多层列索引 (MultiIndex)
    # 单个 ticker 时返回普通列索引，需要分别处理
    # yfinance returns MultiIndex columns for multiple tickers,
    # but single-level columns for a single ticker — handle both cases
    if isinstance(data.columns, pd.MultiIndex):
        # 多个 ticker：从多层索引中提取 "Close" 层
        # Multiple tickers: extract the "Close" level from MultiIndex
        prices = data["Close"]
    else:
        # 单个 ticker：选取 Close 列并重命名为 ticker 名称
        # Single ticker: select Close column and rename to ticker symbol
        prices = data[["Close"]]
        prices.columns = tickers

    # 删除所有值都为 NaN 的行（例如不同资产上市时间不同导致的缺失）
    # Drop rows where ALL values are NaN (e.g., due to different listing dates)
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
        import numpy as np
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
