"""
AI WealthPilot - Market Dashboard Page
AI WealthPilot - 市场仪表板页面

This module implements the interactive Market Dashboard for the Streamlit app.
It displays real-time market quotes, historical price charts, correlation
heatmaps, and risk/return statistics for the user's asset universe.

本模块实现 Streamlit 应用的交互式市场仪表板。
展示实时市场行情、历史价格走势图、相关性热力图，
以及用户资产池的风险/收益统计数据。

CFA Reference / CFA 参考:
    - CFA L3: Capital Market Expectations — Monitoring market conditions
      is essential for forming forward-looking return assumptions.
      CFA 三级：资本市场预期 —— 监控市场状况对形成前瞻性收益假设至关重要。
    - CFA L1: Quantitative Methods — Correlation analysis for diversification.
      CFA 一级：定量方法 —— 用于分散化分析的相关性分析。
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional

# 导入数据获取函数 / Import data fetching functions
from src.data.market_data import (
    fetch_price_history,
    compute_returns,
    compute_correlation_matrix,
    get_latest_quotes,
)

# 导入可视化函数 / Import visualization functions
from src.visualization.charts import (
    plot_price_history,
    plot_correlation_heatmap,
)

# 导入风险指标函数 / Import risk metrics functions
from src.portfolio.risk_metrics import (
    sharpe_ratio,
    max_drawdown,
    value_at_risk,
    conditional_var,
)

# 导入配置 / Import configuration
from src.config import ASSET_UNIVERSE, TRADING_DAYS_PER_YEAR


# ============================================================
# 时间范围映射表：UI 显示文本 → yfinance 的 period 参数
# Time period mapping: UI display text → yfinance period parameter
# ============================================================
PERIOD_OPTIONS = {
    "1 Month": "1mo",
    "3 Months": "3mo",
    "6 Months": "6mo",
    "1 Year": "1y",
    "3 Years": "3y",
    "5 Years": "5y",
}

# ============================================================
# 资产类别列表（从 ASSET_UNIVERSE 中自动提取不重复的类别）
# Asset categories (automatically extracted from ASSET_UNIVERSE)
# ============================================================
ALL_CATEGORIES = sorted(set(
    info["category"] for info in ASSET_UNIVERSE.values()
))


# ============================================================
# 数据缓存函数（使用 Streamlit 缓存，避免频繁请求 API）
# Cached data functions (using Streamlit cache to avoid frequent API calls)
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def _cached_fetch_prices(tickers: tuple, period: str) -> Optional[pd.DataFrame]:
    """
    Cached wrapper for fetch_price_history.
    fetch_price_history 的缓存包装函数。

    Uses tuple for tickers (instead of list) because Streamlit's cache
    requires hashable arguments.
    tickers 使用 tuple（而非 list），因为 Streamlit 的缓存要求参数可哈希。

    TTL = 300 seconds (5 minutes): balances freshness vs API rate limits.
    TTL = 300 秒（5 分钟）：在数据新鲜度和 API 请求限制之间取平衡。

    Args:
        tickers: Tuple of Yahoo Finance ticker symbols.
                 Yahoo Finance 股票代码元组。
        period: Data period string (e.g., '1y', '5y').
                数据时间范围字符串（如 '1y'、'5y'）。

    Returns:
        DataFrame of adjusted close prices, or None if fetch fails.
        调整后收盘价 DataFrame，获取失败时返回 None。
    """
    try:
        return fetch_price_history(list(tickers), period=period)
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _cached_get_quotes(tickers: tuple) -> Optional[pd.DataFrame]:
    """
    Cached wrapper for get_latest_quotes.
    get_latest_quotes 的缓存包装函数。

    Args:
        tickers: Tuple of ticker symbols.
                 股票代码元组。

    Returns:
        DataFrame of latest quotes, or None if fetch fails.
        最新行情 DataFrame，获取失败时返回 None。
    """
    try:
        return get_latest_quotes(list(tickers))
    except Exception:
        return None


def _render_sidebar() -> tuple[list[str], str]:
    """
    Render the sidebar controls and return user selections.
    渲染侧栏控件并返回用户选择。

    Provides two controls / 提供两个控件:
    1. Asset category multi-select (资产类别多选)
    2. Time period selector (时间范围选择)

    Returns:
        Tuple of (selected_tickers, yfinance_period_string).
        返回元组：(选中的 ticker 列表, yfinance 时间范围字符串)。
    """
    st.sidebar.markdown("### 🎛️ Dashboard Settings")
    st.sidebar.markdown("##### Asset Categories / 资产类别")

    # 让用户选择要展示的资产类别
    # Let the user choose which asset categories to display
    selected_categories = st.sidebar.multiselect(
        "Select categories",
        options=ALL_CATEGORIES,
        default=ALL_CATEGORIES,
        label_visibility="collapsed",
    )

    # 根据选中的类别筛选 tickers
    # Filter tickers based on selected categories
    selected_tickers = [
        ticker for ticker, info in ASSET_UNIVERSE.items()
        if info["category"] in selected_categories
    ]

    st.sidebar.markdown("##### Time Period / 时间范围")

    # 时间范围选择器
    # Time period selector
    period_label = st.sidebar.select_slider(
        "Select period",
        options=list(PERIOD_OPTIONS.keys()),
        value="1 Year",
        label_visibility="collapsed",
    )
    period = PERIOD_OPTIONS[period_label]

    # 显示当前选中的资产数量
    # Show how many assets are currently selected
    st.sidebar.divider()
    st.sidebar.caption(f"📊 Showing {len(selected_tickers)} assets · {period_label}")

    return selected_tickers, period


def _render_market_overview(quotes_df: pd.DataFrame) -> None:
    """
    Render the real-time market overview section with metric cards.
    渲染实时市场概览区域，以指标卡片形式展示。

    Uses Streamlit's st.metric component to display:
    使用 Streamlit 的 st.metric 组件展示：
    - Asset name (资产名称)
    - Latest price (最新价格)
    - Daily change amount and percentage (日涨跌额和涨跌幅)

    The cards are arranged in rows of 4 columns for a clean layout.
    卡片按每行 4 列排列，保持整洁的布局。

    Args:
        quotes_df: DataFrame from get_latest_quotes with columns:
                   ticker, name, category, price, previous_close, change, change_pct.
                   来自 get_latest_quotes 的 DataFrame。
    """
    st.markdown("### 📊 Market Overview / 市场概览")

    if quotes_df is None or quotes_df.empty:
        st.warning("⚠️ Unable to fetch live quotes. Please try again later.")
        st.warning("⚠️ 无法获取实时行情，请稍后重试。")
        return

    # 按资产类别分组展示 / Group by asset category for display
    categories_in_data = quotes_df["category"].unique()

    for category in categories_in_data:
        cat_data = quotes_df[quotes_df["category"] == category]
        if cat_data.empty:
            continue

        # 类别标题 / Category header
        st.markdown(f"**{category}**")

        # 每行最多 4 个指标卡片 / Up to 4 metric cards per row
        cols = st.columns(min(len(cat_data), 4))
        for i, (_, row) in enumerate(cat_data.iterrows()):
            col = cols[i % 4]
            with col:
                # 格式化价格和涨跌幅
                # Format price and change values
                price = row.get("price")
                change = row.get("change")
                change_pct = row.get("change_pct")

                if pd.notna(price):
                    # 获取资产的货币符号 / Get asset's currency symbol
                    ticker = row.get("ticker", "")
                    asset_info = ASSET_UNIVERSE.get(ticker, {})
                    currency_symbol = asset_info.get("symbol", "$")
                    currency = asset_info.get("currency", "USD")

                    # 根据货币类型和价格大小选择合适的格式
                    # Choose format based on currency type and price magnitude
                    if currency in ["Rate", "Index"]:
                        # 汇率和指数不加货币符号 / Exchange rates and indices: no currency symbol
                        if price > 1000:
                            price_str = f"{price:,.0f}"
                        elif price > 1:
                            price_str = f"{price:,.2f}"
                        else:
                            price_str = f"{price:,.4f}"
                    elif currency == "JPY":
                        # 日元没有小数位 / JPY has no decimal places
                        price_str = f"{currency_symbol}{price:,.0f}"
                    elif price > 1000:
                        price_str = f"{currency_symbol}{price:,.0f}"
                    elif price > 1:
                        price_str = f"{currency_symbol}{price:,.2f}"
                    else:
                        price_str = f"{currency_symbol}{price:,.4f}"

                    # delta 参数控制涨跌颜色：正数绿色，负数红色
                    # delta parameter controls color: positive=green, negative=red
                    delta_str = (
                        f"{change_pct:+.2f}%" if pd.notna(change_pct) else None
                    )
                    st.metric(
                        label=row["name"],
                        value=price_str,
                        delta=delta_str,
                    )
                else:
                    st.metric(label=row["name"], value="N/A")

    st.divider()


def _render_price_chart(prices_df: pd.DataFrame, period_label: str) -> None:
    """
    Render the historical price chart section.
    渲染历史价格走势图区域。

    Uses normalized prices (base=100) to allow meaningful comparison
    across assets with very different price scales (e.g., BTC ~$60,000
    vs Silver ~$30). This is a standard technique in financial analysis.

    使用归一化价格（基准=100）以便在价格差异很大的资产之间
    进行有意义的比较（如 BTC ~$60,000 vs 白银 ~$30）。
    这是金融分析中的标准方法。

    Args:
        prices_df: DataFrame of adjusted close prices with DatetimeIndex.
                   调整后收盘价 DataFrame，日期索引。
        period_label: Human-readable period label for the chart title.
                      用于图表标题的可读时间范围标签。
    """
    st.markdown("### 📈 Price History / 价格走势")

    if prices_df is None or prices_df.empty:
        st.warning("⚠️ Unable to fetch price history. Please try again later.")
        st.warning("⚠️ 无法获取价格历史数据，请稍后重试。")
        return

    # 让用户选择是否归一化（默认开启）
    # Let user toggle normalization (default: on)
    normalize = st.checkbox(
        "Normalize prices (base=100) / 归一化价格（基准=100）",
        value=True,
        help="Normalizing rebases all assets to 100 at the start date, "
             "making it easy to compare percentage performance across assets "
             "with different price scales. / "
             "归一化将所有资产在起始日期设为100，"
             "方便比较不同价格量级的资产的百分比表现。",
    )

    # 使用已有的可视化函数生成 Plotly 图表
    # Use the existing visualization function to generate the Plotly chart
    fig = plot_price_history(
        prices_df,
        normalize=normalize,
        title=f"Asset Price History — {period_label}",
    )

    # 使用 Streamlit 渲染 Plotly 图表，占满容器宽度
    # Render the Plotly chart in Streamlit, using full container width
    st.plotly_chart(fig, use_container_width=True)

    st.divider()


def _render_correlation_heatmap(prices_df: pd.DataFrame) -> None:
    """
    Render the correlation heatmap section.
    渲染相关性热力图区域。

    Correlation between asset returns is a key input for portfolio
    diversification. Low or negative correlation between assets means
    combining them can reduce overall portfolio risk.

    资产收益率之间的相关性是投资组合分散化的关键输入。
    资产间低相关或负相关意味着组合它们可以降低整体组合风险。

    CFA Reference / CFA 参考:
        CFA L1/L2: The correlation matrix feeds directly into the
        covariance matrix used in Mean-Variance Optimization (MVO).
        CFA 一级/二级：相关性矩阵直接用于计算均值-方差优化（MVO）中的协方差矩阵。

    Args:
        prices_df: DataFrame of adjusted close prices.
                   调整后收盘价 DataFrame。
    """
    st.markdown("### 🔗 Correlation Matrix / 相关性矩阵")

    if prices_df is None or prices_df.empty or prices_df.shape[1] < 2:
        st.info("ℹ️ Select at least 2 assets to view correlation. / "
                "请至少选择 2 个资产以查看相关性。")
        return

    # 计算相关性矩阵 / Compute correlation matrix
    corr_matrix = compute_correlation_matrix(prices_df)

    # 使用已有的可视化函数生成热力图
    # Use existing visualization function to generate the heatmap
    fig = plot_correlation_heatmap(corr_matrix)

    st.plotly_chart(fig, use_container_width=True)

    # 添加解读提示 / Add interpretation tips
    st.caption(
        "💡 **How to read / 如何解读**: "
        "Values close to **+1.0** (red) indicate strong positive correlation — "
        "assets tend to move together. "
        "Values close to **-1.0** (blue) indicate strong negative correlation — "
        "good for diversification. / "
        "接近 **+1.0**（红色）表示强正相关——资产倾向于同涨同跌。"
        "接近 **-1.0**（蓝色）表示强负相关——有利于分散化。"
    )

    st.divider()


def _render_risk_statistics(prices_df: pd.DataFrame) -> None:
    """
    Render the risk/return statistics table.
    渲染风险/收益统计表。

    Computes key performance metrics for each asset:
    为每个资产计算关键绩效指标：
    - Annualized Return (年化收益率)
    - Annualized Volatility (年化波动率)
    - Sharpe Ratio (夏普比率)
    - Max Drawdown (最大回撤)
    - 95% VaR (95% 在险价值)

    CFA Reference / CFA 参考:
        CFA L1/L3: These are the standard metrics used to evaluate
        and compare investment performance. Sharpe ratio is the most
        common risk-adjusted return measure.
        CFA 一级/三级：这些是评估和比较投资绩效的标准指标。
        夏普比率是最常用的风险调整收益衡量标准。

    Args:
        prices_df: DataFrame of adjusted close prices.
                   调整后收盘价 DataFrame。
    """
    st.markdown("### 📋 Risk & Return Statistics / 风险收益统计")

    if prices_df is None or prices_df.empty:
        st.warning("⚠️ No data available for statistics. / 无数据可用于统计。")
        return

    # 计算日收益率 / Compute daily returns
    returns_df = compute_returns(prices_df, method="simple")

    # 为每个资产计算统计指标 / Compute statistics for each asset
    stats_records = []
    for col in returns_df.columns:
        ret_series = returns_df[col].dropna()
        price_series = prices_df[col].dropna()

        if len(ret_series) < 20:
            # 数据太少，跳过 / Too little data, skip
            continue

        # 查找资产的显示名称 / Look up the asset's display name
        asset_info = ASSET_UNIVERSE.get(col, {})
        display_name = asset_info.get("name", col)

        # 年化收益率 = 日均收益率 × 252
        # Annualized return = daily mean × 252
        ann_return = float(ret_series.mean() * TRADING_DAYS_PER_YEAR)

        # 年化波动率 = 日标准差 × √252
        # Annualized volatility = daily std × √252
        ann_vol = float(ret_series.std() * np.sqrt(TRADING_DAYS_PER_YEAR))

        # 夏普比率 / Sharpe ratio
        sr = sharpe_ratio(ret_series)

        # 最大回撤 / Maximum drawdown
        dd = max_drawdown(price_series)

        # 95% VaR / 95% Value at Risk
        var_95 = value_at_risk(ret_series, confidence=0.95)

        stats_records.append({
            "Asset / 资产": display_name,
            "Ann. Return / 年化收益": f"{ann_return:.2%}",
            "Ann. Volatility / 年化波动率": f"{ann_vol:.2%}",
            "Sharpe / 夏普": f"{sr:.2f}",
            "Max Drawdown / 最大回撤": f"{dd['max_drawdown']:.2%}",
            "VaR 95%": f"{var_95:.2%}",
        })

    if stats_records:
        stats_df = pd.DataFrame(stats_records)
        # 使用 Streamlit 的交互式数据表格展示
        # Display using Streamlit's interactive data table
        st.dataframe(
            stats_df,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("ℹ️ Not enough data to compute statistics. / 数据不足，无法计算统计指标。")


def render() -> None:
    """
    Main render function for the Market Dashboard page.
    市场仪表板页面的主渲染函数。

    This function is the entry point called by the app router (src/app.py).
    It orchestrates the sidebar controls and all dashboard sections.

    本函数是应用路由（src/app.py）调用的入口点。
    它协调侧栏控件和所有仪表板区域的渲染。

    Page layout / 页面布局:
        1. Sidebar: asset category filter + time period selector
           侧栏：资产类别筛选 + 时间范围选择
        2. Market Overview: real-time quote cards
           市场概览：实时行情卡片
        3. Price History: interactive line chart
           价格走势：交互式折线图
        4. Correlation Heatmap: asset return correlations
           相关性热力图：资产收益率相关性
        5. Risk Statistics: performance metrics table
           风险统计：绩效指标表格
    """
    # 页面标题和说明 / Page title and description
    st.title("📈 Global Market Dashboard")
    st.markdown(
        "Real-time market data and analytics for your asset universe. / "
        "资产池的实时市场数据和分析。"
    )
    st.divider()

    # ====================================
    # 1. 侧栏控件 / Sidebar Controls
    # ====================================
    selected_tickers, period = _render_sidebar()

    if not selected_tickers:
        st.warning("⚠️ Please select at least one asset category from the sidebar. / "
                   "请从侧栏至少选择一个资产类别。")
        return

    # ====================================
    # 2. 市场概览 — 实时行情 / Market Overview — Live Quotes
    # ====================================
    with st.spinner("Fetching live market data... / 正在获取实时行情数据..."):
        quotes_df = _cached_get_quotes(tuple(selected_tickers))
    _render_market_overview(quotes_df)

    # ====================================
    # 3. 价格走势图 / Price History Chart
    # ====================================
    # 将 period 映射回显示标签用于图表标题
    # Map period back to display label for chart title
    period_label = next(
        (k for k, v in PERIOD_OPTIONS.items() if v == period), period
    )

    with st.spinner("Fetching historical prices... / 正在获取历史价格..."):
        prices_df = _cached_fetch_prices(tuple(selected_tickers), period)
    _render_price_chart(prices_df, period_label)

    # ====================================
    # 4. 相关性热力图 / Correlation Heatmap
    # ====================================
    _render_correlation_heatmap(prices_df)

    # ====================================
    # 5. 风险统计表 / Risk & Return Statistics
    # ====================================
    _render_risk_statistics(prices_df)

    # 页脚 / Footer
    st.divider()
    st.caption(
        "💡 Data sourced from Yahoo Finance via yfinance. "
        "Cached for 5 minutes to reduce API calls. / "
        "数据来自 Yahoo Finance（通过 yfinance），缓存 5 分钟以减少 API 调用。"
    )
