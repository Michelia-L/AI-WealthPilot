"""
AI WealthPilot - Portfolio Optimizer Page
AI WealthPilot - 投资组合优化器页面

Interactive Streamlit page for Mean-Variance Portfolio Optimization.
Users can select asset classes, configure parameters, and visualize
the efficient frontier, optimal portfolios, and risk-return metrics.

交互式 Streamlit 页面，用于均值-方差投资组合优化。
用户可以选择资产类别、配置参数，并可视化有效前沿、最优组合和风险收益指标。

CFA Reference / CFA 参考:
    - CFA L1: Modern Portfolio Theory (MPT), Efficient Frontier, Capital Allocation Line
      CFA 一级：现代投资组合理论（MPT）、有效前沿、资本配置线
    - CFA L3: Asset Allocation — Strategic asset allocation using mean-variance framework
      CFA 三级：资产配置 —— 使用均值-方差框架的战略资产配置
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional

# 导入数据获取模块 / Import data fetching module
from src.data.market_data import fetch_price_history, compute_returns

# 导入投资组合优化器 / Import portfolio optimizer
from src.portfolio.optimizer import PortfolioOptimizer

# 导入可视化函数 / Import visualization functions
from src.visualization.charts import (
    plot_efficient_frontier,
    plot_allocation_pie,
)

# 导入配置 / Import configuration
from src.config import DEFAULT_ASSET_CLASSES, RISK_FREE_RATE


# ============================================================
# 默认资产类别列表（用于 UI 多选控件）
# Default asset class list (for UI multi-select widget)
# ============================================================
ASSET_OPTIONS = {
    key: f"{val['name']} ({val['ticker']})"
    for key, val in DEFAULT_ASSET_CLASSES.items()
}


def _render_sidebar() -> dict:
    """
    Render sidebar controls and return user configuration.
    渲染侧栏控件并返回用户配置。

    Controls / 控件:
        1. Asset class multi-select (资产类别多选)
        2. Data period selector (数据时间范围)
        3. Risk-free rate input (无风险利率)
        4. Short-selling toggle (做空开关)
        5. Optimization mode (优化模式)

    Returns:
        Dict with all user selections.
        包含所有用户选择的字典。
    """
    st.sidebar.markdown("### ⚙️ Optimizer Settings")

    # --- 资产类别选择 / Asset class selection ---
    st.sidebar.markdown("##### Asset Classes / 资产类别")
    selected_keys = st.sidebar.multiselect(
        "Select asset classes for optimization",
        options=list(ASSET_OPTIONS.keys()),
        default=["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"],
        format_func=lambda k: ASSET_OPTIONS[k],
        label_visibility="collapsed",
    )

    # --- 数据时间范围 / Data period ---
    st.sidebar.markdown("##### Data Period / 数据时间范围")
    period = st.sidebar.select_slider(
        "Historical data window",
        options=["1y", "2y", "3y", "5y", "10y"],
        value="5y",
        label_visibility="collapsed",
    )

    # --- 无风险利率 / Risk-free rate ---
    st.sidebar.markdown("##### Risk-Free Rate / 无风险利率")
    risk_free_rate = st.sidebar.number_input(
        "Annual risk-free rate",
        min_value=0.0,
        max_value=0.20,
        value=RISK_FREE_RATE,
        step=0.005,
        format="%.3f",
        help="Typically the yield on 10-year government bonds. / "
             "通常使用十年期国债收益率。",
    )

    # --- 做空开关 / Short-selling toggle ---
    st.sidebar.markdown("##### Constraints / 约束条件")
    allow_short = st.sidebar.checkbox(
        "Allow short selling / 允许做空",
        value=False,
        help="If unchecked, all weights are constrained to [0, 1] (long-only). / "
             "不勾选时，所有权重约束在 [0, 1] 范围内（只做多）。",
    )

    # --- 优化模式 / Optimization mode ---
    st.sidebar.markdown("##### Optimization Goal / 优化目标")
    opt_mode = st.sidebar.radio(
        "Select optimization objective",
        options=["Maximum Sharpe", "Minimum Volatility"],
        index=0,
        label_visibility="collapsed",
        help="Maximum Sharpe: best risk-adjusted return. "
             "Minimum Volatility: lowest possible risk. / "
             "最大夏普比率：最优风险调整收益。最小波动率：最低风险。",
    )

    # 侧栏底部信息 / Sidebar footer info
    st.sidebar.divider()
    st.sidebar.caption(
        f"📊 {len(selected_keys)} assets · {period} history · "
        f"Rf = {risk_free_rate:.1%}"
    )

    return {
        "selected_keys": selected_keys,
        "period": period,
        "risk_free_rate": risk_free_rate,
        "allow_short": allow_short,
        "opt_mode": opt_mode,
    }


def _fetch_and_prepare_data(
    selected_keys: list[str],
    period: str,
) -> Optional[pd.DataFrame]:
    """
    Fetch price data for selected asset classes and compute returns.
    获取所选资产类别的价格数据并计算收益率。

    Maps asset class keys (e.g., 'US_EQUITY') to their ticker symbols
    (e.g., 'SPY') and downloads historical data from Yahoo Finance.

    将资产类别键（如 'US_EQUITY'）映射到其 ticker 代码（如 'SPY'），
    并从 Yahoo Finance 下载历史数据。

    Args:
        selected_keys: List of asset class keys from DEFAULT_ASSET_CLASSES.
                       来自 DEFAULT_ASSET_CLASSES 的资产类别键列表。
        period: yfinance period string (e.g., '5y').
                yfinance 时间范围字符串（如 '5y'）。

    Returns:
        DataFrame of daily simple returns, or None if data fetch fails.
        日简单收益率 DataFrame，获取失败时返回 None。
    """
    # 将资产类别键映射为 ticker 代码
    # Map asset class keys to ticker symbols
    tickers = [DEFAULT_ASSET_CLASSES[key]["ticker"] for key in selected_keys]
    names = [DEFAULT_ASSET_CLASSES[key]["name"] for key in selected_keys]

    # 下载价格数据 / Download price data
    prices = fetch_price_history(tickers, period=period)

    if prices is None or prices.empty:
        return None

    # 将列名从 ticker 代码改为可读的资产名称
    # Rename columns from ticker symbols to readable asset names
    prices.columns = names

    # 计算简单收益率（MVO 使用简单收益率更直观）
    # Compute simple returns (MVO uses simple returns for cross-sectional additivity)
    returns = compute_returns(prices, method="simple")

    return returns


def _run_optimization(
    returns: pd.DataFrame,
    risk_free_rate: float,
    allow_short: bool,
    opt_mode: str,
) -> dict:
    """
    Run the portfolio optimization and return all results.
    运行投资组合优化并返回所有结果。

    Performs three types of optimization:
    执行三种优化:
        1. Maximum Sharpe ratio portfolio (最大夏普比率组合)
        2. Minimum volatility portfolio (最小波动率组合)
        3. Efficient frontier (有效前沿)

    Plus generates random portfolios for visualization.
    同时生成随机组合用于可视化。

    Args:
        returns: DataFrame of daily asset returns.
                 资产日收益率 DataFrame。
        risk_free_rate: Annual risk-free rate.
                        年化无风险利率。
        allow_short: Whether to allow short selling.
                     是否允许做空。
        opt_mode: 'Maximum Sharpe' or 'Minimum Volatility'.
                  'Maximum Sharpe' 或 'Minimum Volatility'。

    Returns:
        Dict with optimizer results, efficient frontier, and random portfolios.
        包含优化器结果、有效前沿和随机组合的字典。
    """
    # 创建优化器实例 / Create optimizer instance
    optimizer = PortfolioOptimizer(returns, risk_free_rate=risk_free_rate)

    # 运行两种优化 / Run both optimizations
    max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
    min_vol = optimizer.minimize_volatility(allow_short=allow_short)

    # 构建有效前沿（使用较少的点以加快速度）
    # Build efficient frontier (use fewer points for speed)
    frontier = optimizer.efficient_frontier(
        n_points=50, allow_short=allow_short
    )

    # 生成随机组合云（用于可视化对比）
    # Generate random portfolio cloud (for visual comparison)
    random_ports = optimizer.random_portfolios(n_portfolios=3000)

    # 根据用户选择的优化模式确定"选中的组合"
    # Determine the "selected portfolio" based on user's optimization mode
    if opt_mode == "Maximum Sharpe":
        selected = max_sharpe
    else:
        selected = min_vol

    return {
        "optimizer": optimizer,
        "max_sharpe": max_sharpe,
        "min_vol": min_vol,
        "frontier": frontier,
        "random_portfolios": random_ports,
        "selected": selected,
    }


def _render_efficient_frontier(results: dict) -> None:
    """
    Render the efficient frontier chart with highlighted optimal portfolios.
    渲染有效前沿图，高亮显示最优组合。

    The chart shows:
    图表展示:
        - Random portfolio cloud (散点云): shows the universe of possible allocations
          展示所有可能配置的空间
        - Efficient frontier curve (有效前沿曲线): the optimal boundary
          最优边界
        - Max Sharpe portfolio (最大夏普组合): the best risk-adjusted portfolio
          最优风险调整组合
        - Min Volatility portfolio (最小波动率组合): the lowest-risk portfolio
          最低风险组合

    Args:
        results: Dict from _run_optimization.
                 来自 _run_optimization 的结果字典。
    """
    st.markdown("### 📈 Efficient Frontier / 有效前沿")

    fig = plot_efficient_frontier(
        frontier=results["frontier"],
        random_portfolios=results["random_portfolios"],
        max_sharpe=results["max_sharpe"],
        min_vol=results["min_vol"],
    )

    st.plotly_chart(fig, use_container_width=True)

    # 添加解读说明 / Add interpretation caption
    st.caption(
        "💡 Each dot is a random portfolio. The **blue curve** is the efficient frontier — "
        "portfolios on this curve offer the highest return for each risk level. "
        "The **star** (Max Sharpe) and **diamond** (Min Vol) mark the two key optimal portfolios. / "
        "每个散点代表一个随机组合。**蓝色曲线**是有效前沿——"
        "该曲线上的组合在每个风险水平下提供最高收益。"
        "**星形**（最大夏普）和**菱形**（最小波动率）标记了两个关键最优组合。"
    )

    st.divider()


def _render_selected_portfolio(results: dict) -> None:
    """
    Render the selected optimal portfolio's details: pie chart + metrics.
    渲染所选最优组合的详情：饼图 + 指标。

    Displays:
    展示:
        - Portfolio allocation pie chart (配置饼图)
        - Key metrics: return, volatility, Sharpe ratio (关键指标)
        - Interpretation of what the metrics mean (指标含义解读)

    Args:
        results: Dict from _run_optimization.
                 来自 _run_optimization 的结果字典。
    """
    selected = results["selected"]
    opt_mode = "Maximum Sharpe" if selected is results["max_sharpe"] else "Minimum Volatility"

    st.markdown(f"### 🎯 Optimal Portfolio: {opt_mode} / 最优组合")

    # 三列布局展示关键指标 / Three-column layout for key metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            label="Annualized Return / 年化收益率",
            value=f"{selected['return']:.2%}",
        )

    with col2:
        st.metric(
            label="Annualized Volatility / 年化波动率",
            value=f"{selected['volatility']:.2%}",
        )

    with col3:
        st.metric(
            label="Sharpe Ratio / 夏普比率",
            value=f"{selected['sharpe']:.2f}",
        )

    st.markdown("")

    # 两列布局：饼图 + 权重表 / Two-column layout: pie chart + weights table
    chart_col, table_col = st.columns([1, 1])

    with chart_col:
        # 资产配置饼图 / Allocation pie chart
        fig = plot_allocation_pie(
            selected["weights"],
            title=f"Asset Allocation — {opt_mode}",
        )
        st.plotly_chart(fig, use_container_width=True)

    with table_col:
        # 权重详情表 / Detailed weights table
        st.markdown("**Asset Weights / 资产权重**")

        weights_df = pd.DataFrame([
            {
                "Asset / 资产": asset,
                "Weight / 权重": f"{weight:.2%}",
                "Allocation / 配置": "Long / 多" if weight >= 0 else "Short / 空",
            }
            for asset, weight in selected["weights"].items()
        ])
        st.dataframe(weights_df, use_container_width=True, hide_index=True)

        # 收益率解读 / Return interpretation
        sharpe = selected["sharpe"]
        if sharpe > 1.0:
            quality = "Good / 良好"
        elif sharpe > 0.5:
            quality = "Moderate / 中等"
        else:
            quality = "Below average / 偏低"

        st.caption(
            f"📊 Sharpe ratio = {sharpe:.2f} ({quality}). "
            f"This means for each unit of risk taken, the portfolio earns "
            f"{sharpe:.2f} units of excess return above the risk-free rate. / "
            f"夏普比率 = {sharpe:.2f}（{quality}）。"
            f"这意味着每承担一单位风险，组合获得 {sharpe:.2f} 单位的超额收益。"
        )

    st.divider()


def _render_comparison_table(results: dict) -> None:
    """
    Render a comparison table of all key portfolios.
    渲染所有关键组合的对比表。

    Compares / 对比:
        - Maximum Sharpe portfolio (最大夏普组合)
        - Minimum Volatility portfolio (最小波动率组合)

    Args:
        results: Dict from _run_optimization.
                 来自 _run_optimization 的结果字典。
    """
    st.markdown("### 📊 Portfolio Comparison / 组合对比")

    max_sharpe = results["max_sharpe"]
    min_vol = results["min_vol"]

    comparison_data = {
        "Metric / 指标": [
            "Annualized Return / 年化收益率",
            "Annualized Volatility / 年化波动率",
            "Sharpe Ratio / 夏普比率",
        ],
        "Max Sharpe / 最大夏普": [
            f"{max_sharpe['return']:.2%}",
            f"{max_sharpe['volatility']:.2%}",
            f"{max_sharpe['sharpe']:.2f}",
        ],
        "Min Volatility / 最小波动率": [
            f"{min_vol['return']:.2%}",
            f"{min_vol['volatility']:.2%}",
            f"{min_vol['sharpe']:.2f}",
        ],
    }

    st.dataframe(
        pd.DataFrame(comparison_data),
        use_container_width=True,
        hide_index=True,
    )

    # 解读两种组合的权衡 / Interpret the tradeoff
    st.caption(
        "💡 **Tradeoff / 权衡**: The Max Sharpe portfolio optimizes risk-adjusted returns "
        "but may have higher volatility. The Min Volatility portfolio has the lowest risk "
        "but may sacrifice returns. Choose based on your risk tolerance. / "
        "**最大夏普组合**优化风险调整收益但波动率可能更高。"
        "**最小波动率组合**风险最低但可能牺牲收益。根据你的风险承受能力选择。"
    )

    st.divider()


def _render_asset_universe(optimizer: PortfolioOptimizer) -> None:
    """
    Render the asset universe summary — expected returns and volatilities.
    渲染资产池摘要 —— 预期收益率和波动率。

    Shows the input data that feeds into the optimizer, helping users
    understand what the optimization is based on.

    展示输入优化器的数据，帮助用户理解优化的基础。

    Args:
        optimizer: PortfolioOptimizer instance.
                   PortfolioOptimizer 实例。
    """
    st.markdown("### 📋 Asset Universe Summary / 资产池摘要")

    summary_data = []
    for name in optimizer.asset_names:
        ann_ret = optimizer.mean_returns[name]
        ann_vol = np.sqrt(optimizer.cov_matrix.loc[name, name])
        summary_data.append({
            "Asset / 资产": name,
            "Ann. Return / 年化收益率": f"{ann_ret:.2%}",
            "Ann. Volatility / 年化波动率": f"{ann_vol:.2%}",
        })

    st.dataframe(
        pd.DataFrame(summary_data),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "💡 These are annualized statistics computed from historical daily returns. "
        "Past performance does not guarantee future results. / "
        "这些是从历史日收益率计算的年化统计数据。过往表现不保证未来收益。"
    )


def render() -> None:
    """
    Main render function for the Portfolio Optimizer page.
    投资组合优化器页面的主渲染函数。

    This function is called by the app router (src/app.py).
    It orchestrates the sidebar controls, data fetching, optimization,
    and all visualization sections.

    本函数由应用路由（src/app.py）调用。
    它协调侧栏控件、数据获取、优化和所有可视化区域的渲染。

    Page layout / 页面布局:
        1. Sidebar: asset selection, period, risk-free rate, constraints
           侧栏：资产选择、时间范围、无风险利率、约束条件
        2. Efficient Frontier: interactive scatter + frontier curve
           有效前沿：交互式散点 + 前沿曲线
        3. Selected Portfolio: pie chart + metrics + weights table
           所选组合：饼图 + 指标 + 权重表
        4. Comparison Table: Max Sharpe vs Min Volatility
           对比表：最大夏普 vs 最小波动率
        5. Asset Universe: input data summary
           资产池：输入数据摘要
    """
    # 页面标题 / Page title
    st.title("📊 Portfolio Optimizer")
    st.markdown(
        "Mean-Variance Optimization based on Markowitz's Modern Portfolio Theory. "
        "Select assets, configure parameters, and find the optimal allocation. / "
        "基于 Markowitz 现代投资组合理论的均值-方差优化。"
        "选择资产、配置参数，寻找最优配置。"
    )
    st.divider()

    # ====================================
    # 1. 侧栏控件 / Sidebar Controls
    # ====================================
    config = _render_sidebar()

    # 检查是否至少选择了 2 个资产 / Check at least 2 assets selected
    if len(config["selected_keys"]) < 2:
        st.warning(
            "⚠️ Please select at least 2 asset classes for optimization. / "
            "请至少选择 2 个资产类别进行优化。"
        )
        return

    # ====================================
    # 2. 获取数据 / Fetch Data
    # ====================================
    with st.spinner("Fetching historical data... / 正在获取历史数据..."):
        returns = _fetch_and_prepare_data(
            config["selected_keys"],
            config["period"],
        )

    if returns is None or returns.empty:
        st.error(
            "❌ Failed to fetch market data. Please check your internet connection "
            "and try again. / 获取市场数据失败，请检查网络连接后重试。"
        )
        return

    # 检查数据量是否足够 / Check if enough data
    if len(returns) < 60:
        st.warning(
            f"⚠️ Only {len(returns)} trading days of data available. "
            f"Results may be unreliable with insufficient data. / "
            f"仅有 {len(returns)} 个交易日的数据，数据不足可能导致结果不可靠。"
        )

    # ====================================
    # 3. 运行优化 / Run Optimization
    # ====================================
    with st.spinner("Running portfolio optimization... / 正在运行投资组合优化..."):
        results = _run_optimization(
            returns,
            config["risk_free_rate"],
            config["allow_short"],
            config["opt_mode"],
        )

    # 检查优化是否成功 / Check optimization success
    if not results["selected"]["success"]:
        st.error(
            "❌ Optimization failed to converge. Try adjusting constraints "
            "or selecting different assets. / "
            "优化未能收敛，请尝试调整约束条件或选择不同的资产。"
        )
        return

    # ====================================
    # 4. 有效前沿图 / Efficient Frontier Chart
    # ====================================
    _render_efficient_frontier(results)

    # ====================================
    # 5. 所选最优组合详情 / Selected Portfolio Details
    # ====================================
    _render_selected_portfolio(results)

    # ====================================
    # 6. 组合对比表 / Portfolio Comparison
    # ====================================
    _render_comparison_table(results)

    # ====================================
    # 7. 资产池摘要 / Asset Universe Summary
    # ====================================
    _render_asset_universe(results["optimizer"])

    # 页脚 / Footer
    st.caption(
        "💡 Data sourced from Yahoo Finance via yfinance. "
        "Optimization uses SciPy's SLSQP solver. "
        "Results are based on historical data and do not guarantee future performance. / "
        "数据来自 Yahoo Finance（通过 yfinance）。"
        "优化使用 SciPy 的 SLSQP 求解器。"
        "结果基于历史数据，不保证未来表现。"
    )
