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
    - CFA L3: Black-Litterman Model — Bayesian combination of equilibrium and views
      CFA 三级：Black-Litterman 模型 —— 均衡收益与观点的贝叶斯结合
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional
import plotly.graph_objects as go

# 导入数据获取模块 / Import data fetching module
from src.data.market_data import fetch_price_history, compute_returns

# 导入投资组合优化器 / Import portfolio optimizer
from src.portfolio.optimizer import PortfolioOptimizer, BlackLittermanOptimizer

# 导入观点处理模块 / Import view processor
from src.portfolio.views import ViewInput, ViewProcessor

# 导入可视化函数 / Import visualization functions
from src.visualization.charts import (
    plot_efficient_frontier,
    plot_allocation_pie,
)

# 导入配置 / Import configuration
from src.config import (
    DEFAULT_ASSET_CLASSES,
    RISK_FREE_RATE,
    BL_DEFAULT_TAU,
    BL_DEFAULT_DELTA,
    BL_DEFAULT_CONFIDENCE,
)


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
    st.sidebar.markdown("### ⌬ Optimizer Settings")

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

    # --- 优化方法 / Optimization method ---
    st.sidebar.markdown("##### Optimization Method / 优化方法")
    opt_method = st.sidebar.selectbox(
        "Select optimization method",
        options=[
            "Traditional MVO",
            "Resampled MVO (Michaud)",
            "Black-Litterman",
        ],
        index=0,
        label_visibility="collapsed",
        help="Traditional MVO: classic Markowitz optimization. "
             "Resampled MVO: Monte Carlo simulation to reduce estimation error. "
             "Black-Litterman: combine equilibrium with your views. / "
             "传统MVO：经典Markowitz优化。"
             "重抽样MVO：蒙特卡洛模拟以减少估计误差。"
             "Black-Litterman：结合均衡收益和您的观点。",
    )

    # --- 优化目标 / Optimization objective ---
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

    # --- 重抽样MVO参数 / Resampled MVO parameters ---
    resampled_config = {}
    if opt_method == "Resampled MVO (Michaud)":
        st.sidebar.markdown("##### Resampled MVO Parameters / 重抽样MVO参数")

        resampled_config["n_simulations"] = st.sidebar.slider(
            "Number of simulations / 模拟次数",
            min_value=100,
            max_value=5000,
            value=1000,
            step=100,
            help="More simulations = more stable results but slower. / "
                 "更多模拟 = 更稳定的结果但更慢。",
        )

    # --- 资产类别约束 / Asset class constraints ---
    asset_class_constraints = {}
    st.sidebar.markdown("##### Asset Class Constraints / 资产类别约束")
    use_asset_class_constraints = st.sidebar.checkbox(
        "Enable asset class constraints / 启用资产类别约束",
        value=False,
        help="Add minimum and maximum weight constraints for asset classes. / "
             "为资产类别添加最小和最大权重约束。",
    )

    if use_asset_class_constraints and len(selected_keys) >= 2:
        st.sidebar.caption(
            "Set min/max weights for each asset class / "
            "为每个资产类别设置最小/最大权重"
        )

        # 根据所选资产动态创建约束
        # Dynamically create constraints based on selected assets
        # 简单分类：股票类、债券类、其他
        # Simple classification: equity, bonds, other
        equity_keys = [k for k in selected_keys if 'EQUITY' in k]
        bond_keys = [k for k in selected_keys if 'BOND' in k]
        other_keys = [k for k in selected_keys if k not in equity_keys and k not in bond_keys]

        if equity_keys:
            col1, col2 = st.sidebar.columns(2)
            with col1:
                equity_min = st.number_input(
                    "Equity Min %",
                    min_value=0,
                    max_value=100,
                    value=20,
                    step=5,
                    key="equity_min",
                ) / 100
            with col2:
                equity_max = st.number_input(
                    "Equity Max %",
                    min_value=0,
                    max_value=100,
                    value=80,
                    step=5,
                    key="equity_max",
                ) / 100
            asset_class_constraints['equity'] = {
                'assets': [DEFAULT_ASSET_CLASSES[k]["name"] for k in equity_keys],
                'min': equity_min,
                'max': equity_max,
            }

        if bond_keys:
            col1, col2 = st.sidebar.columns(2)
            with col1:
                bond_min = st.number_input(
                    "Bond Min %",
                    min_value=0,
                    max_value=100,
                    value=10,
                    step=5,
                    key="bond_min",
                ) / 100
            with col2:
                bond_max = st.number_input(
                    "Bond Max %",
                    min_value=0,
                    max_value=100,
                    value=50,
                    step=5,
                    key="bond_max",
                ) / 100
            asset_class_constraints['bonds'] = {
                'assets': [DEFAULT_ASSET_CLASSES[k]["name"] for k in bond_keys],
                'min': bond_min,
                'max': bond_max,
            }

        if other_keys:
            col1, col2 = st.sidebar.columns(2)
            with col1:
                other_min = st.number_input(
                    "Other Min %",
                    min_value=0,
                    max_value=100,
                    value=0,
                    step=5,
                    key="other_min",
                ) / 100
            with col2:
                other_max = st.number_input(
                    "Other Max %",
                    min_value=0,
                    max_value=100,
                    value=30,
                    step=5,
                    key="other_max",
                ) / 100
            asset_class_constraints['other'] = {
                'assets': [DEFAULT_ASSET_CLASSES[k]["name"] for k in other_keys],
                'min': other_min,
                'max': other_max,
            }

    # --- Black-Litterman 专用参数 / BL-specific parameters ---
    bl_config = {}
    if opt_mode == "Black-Litterman":
        st.sidebar.markdown("##### BL Parameters / BL 参数")

        bl_config["tau"] = st.sidebar.slider(
            "Uncertainty scale (τ)",
            min_value=0.01,
            max_value=0.10,
            value=BL_DEFAULT_TAU,
            step=0.005,
            format="%.3f",
            help="Higher τ = less trust in equilibrium. / "
                 "更高的τ = 对均衡信任度更低。",
        )

        bl_config["delta"] = st.sidebar.number_input(
            "Risk aversion (δ)",
            min_value=1.0,
            max_value=10.0,
            value=BL_DEFAULT_DELTA,
            step=0.5,
            help="Higher δ = more risk averse. / "
                 "更高的δ = 更厌恶风险。",
        )

        # Market cap weights input
        # 市值权重输入
        st.sidebar.markdown("##### Market Cap Weights / 市值权重")
        st.sidebar.caption(
            "Enter market cap weights (must sum to 1.0) / "
            "输入市值权重（必须加总为1.0）"
        )

        # Dynamic input based on selected assets
        # 根据所选资产动态输入
        market_weights = {}
        total_weight = 0.0
        for key in selected_keys:
            asset_name = DEFAULT_ASSET_CLASSES[key]["name"]
            default_weight = 1.0 / len(selected_keys)
            market_weights[key] = st.sidebar.number_input(
                f"{asset_name}",
                min_value=0.0,
                max_value=1.0,
                value=default_weight,
                step=0.05,
                format="%.2f",
                key=f"mw_{key}",
            )
            total_weight += market_weights[key]

        # Show total weight warning if not summing to 1
        # 如果权重不加总为1，显示警告
        if abs(total_weight - 1.0) > 0.01:
            st.sidebar.warning(
                f"⚠️ Weights sum to {total_weight:.2f}, should be 1.0 / "
                f"权重加总为{total_weight:.2f}，应为1.0"
            )

        bl_config["market_weights"] = market_weights

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
        "opt_method": opt_method,
        "opt_mode": opt_mode,
        "bl_config": bl_config if opt_method == "Black-Litterman" else None,
        "resampled_config": resampled_config if opt_method == "Resampled MVO (Michaud)" else None,
        "asset_class_constraints": asset_class_constraints if use_asset_class_constraints else None,
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
    opt_method: str = "Traditional MVO",
    resampled_config: dict = None,
    asset_class_constraints: dict = None,
) -> dict:
    """
    Run the portfolio optimization and return all results.
    运行投资组合优化并返回所有结果。

    Supports multiple optimization methods:
    支持多种优化方法:
        1. Traditional MVO (传统MVO)
        2. Resampled MVO - Michaud method (重抽样MVO - Michaud方法)
        3. MVO with asset class constraints (带资产类别约束的MVO)

    Args:
        returns: DataFrame of daily asset returns.
                 资产日收益率 DataFrame。
        risk_free_rate: Annual risk-free rate.
                        年化无风险利率。
        allow_short: Whether to allow short selling.
                     是否允许做空。
        opt_mode: 'Maximum Sharpe' or 'Minimum Volatility'.
                  'Maximum Sharpe' 或 'Minimum Volatility'。
        opt_method: Optimization method name.
                    优化方法名称。
        resampled_config: Configuration for resampled MVO.
                          重抽样MVO配置。
        asset_class_constraints: Asset class constraint configuration.
                                 资产类别约束配置。

    Returns:
        Dict with optimizer results, efficient frontier, and random portfolios.
        包含优化器结果、有效前沿和随机组合的字典。
    """
    # 创建优化器实例 / Create optimizer instance
    optimizer = PortfolioOptimizer(returns, risk_free_rate=risk_free_rate)

    # 根据优化方法运行优化
    # Run optimization based on method
    if opt_method == "Resampled MVO (Michaud)":
        # 重抽样MVO
        # Resampled MVO
        n_simulations = resampled_config.get("n_simulations", 1000) if resampled_config else 1000

        if opt_mode == "Maximum Sharpe":
            selected = optimizer.resampled_maximize_sharpe(
                n_simulations=n_simulations,
                allow_short=allow_short,
            )
        else:
            # 对于最小波动率，使用传统MVO（重抽样主要用于最大夏普）
            # For minimum volatility, use traditional MVO (resampling mainly for max Sharpe)
            selected = optimizer.minimize_volatility(allow_short=allow_short)

        # 重抽样有效前沿
        # Resampled efficient frontier
        frontier = optimizer.resampled_efficient_frontier(
            n_points=50,
            n_simulations=n_simulations,
            allow_short=allow_short,
        )

        # 也计算传统前沿用于对比
        # Also calculate traditional frontier for comparison
        traditional_frontier = optimizer.efficient_frontier(
            n_points=50, allow_short=allow_short
        )

        # 运行传统MVO用于对比
        # Run traditional MVO for comparison
        max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
        min_vol = optimizer.minimize_volatility(allow_short=allow_short)

    elif asset_class_constraints:
        # 带资产类别约束的MVO
        # MVO with asset class constraints
        selected = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_constraints,
            allow_short=allow_short,
        )

        # 传统有效前沿（无约束）
        # Traditional efficient frontier (unconstrained)
        frontier = optimizer.efficient_frontier(
            n_points=50, allow_short=allow_short
        )

        # 运行传统MVO用于对比
        # Run traditional MVO for comparison
        max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
        min_vol = optimizer.minimize_volatility(allow_short=allow_short)

    else:
        # 传统MVO
        # Traditional MVO
        max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
        min_vol = optimizer.minimize_volatility(allow_short=allow_short)

        # 构建有效前沿
        # Build efficient frontier
        frontier = optimizer.efficient_frontier(
            n_points=50, allow_short=allow_short
        )

        # 根据用户选择的优化模式确定"选中的组合"
        # Determine the "selected portfolio" based on user's optimization mode
        if opt_mode == "Maximum Sharpe":
            selected = max_sharpe
        else:
            selected = min_vol

    # 生成随机组合云（用于可视化对比）
    # Generate random portfolio cloud (for visual comparison)
    random_ports = optimizer.random_portfolios(n_portfolios=1000)

    return {
        "optimizer": optimizer,
        "max_sharpe": max_sharpe,
        "min_vol": min_vol,
        "frontier": frontier,
        "random_portfolios": random_ports,
        "selected": selected,
        "opt_method": opt_method,
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
    st.markdown("### ↗ Efficient Frontier / 有效前沿")

    fig = plot_efficient_frontier(
        frontier=results["frontier"],
        random_portfolios=results["random_portfolios"],
        max_sharpe=results["max_sharpe"],
        min_vol=results["min_vol"],
    )

    st.plotly_chart(fig, use_container_width=True, theme=None)

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

    st.markdown(f"### ✦ Optimal Portfolio: {opt_mode} / 最优组合")

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
        st.plotly_chart(fig, use_container_width=True, theme=None)

    with table_col:
        # 权重详情表 / Detailed weights table
        st.markdown("**Asset Weights / 资产权重**")

        weights_df = pd.DataFrame([
            {
                "Asset / 资产": asset,
                "Weight / 权重": weight * 100,
                "Allocation / 配置": "Long / 多" if weight >= 0 else "Short / 空",
            }
            for asset, weight in selected["weights"].items()
        ])
        st.dataframe(
            weights_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Weight / 权重": st.column_config.NumberColumn(
                    format="%.2f%%"
                )
            }
        )

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


def _render_asset_class_weights(results: dict) -> None:
    """
    Render asset class weights if available.
    渲染资产类别权重（如果可用）。

    Args:
        results: Dict from _run_optimization.
                 来自 _run_optimization 的结果字典。
    """
    selected = results["selected"]

    # 检查是否有资产类别权重信息
    # Check if asset class weights information is available
    if "asset_class_weights" not in selected:
        return

    st.markdown("### ⌬ Asset Class Weights / 资产类别权重")

    asset_class_weights = selected["asset_class_weights"]

    # 创建资产类别权重表
    # Create asset class weights table
    weights_data = []
    for class_name, weight in asset_class_weights.items():
        weights_data.append({
            "Asset Class / 资产类别": class_name.capitalize(),
            "Weight / 权重": weight * 100,
        })

    st.dataframe(
        pd.DataFrame(weights_data),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Weight / 权重": st.column_config.NumberColumn(
                format="%.2f%%"
            )
        }
    )

    st.caption(
        "💡 Asset class constraints help maintain diversification and "
        "prevent over-concentration in any single asset class. / "
        "资产类别约束有助于保持多元化，防止过度集中于任何单一资产类别。"
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
    st.markdown("### ⧉ Portfolio Comparison / 组合对比")

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
    st.markdown("### ⧉ Asset Universe Summary / 资产池摘要")

    summary_data = []
    for name in optimizer.asset_names:
        ann_ret = optimizer.mean_returns[name]
        ann_vol = np.sqrt(optimizer.cov_matrix.loc[name, name])
        summary_data.append({
            "Asset / 资产": name,
            "Ann. Return / 年化收益率": ann_ret * 100,
            "Ann. Volatility / 年化波动率": ann_vol * 100,
        })

    st.dataframe(
        pd.DataFrame(summary_data),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ann. Return / 年化收益率": st.column_config.NumberColumn(
                format="%.2f%%"
            ),
            "Ann. Volatility / 年化波动率": st.column_config.NumberColumn(
                format="%.2f%%"
            ),
        }
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
    st.title("⧉ Portfolio Optimizer")

    # 根据优化模式显示不同的描述
    # Show different description based on optimization mode
    config = _render_sidebar()

    if config["opt_mode"] == "Black-Litterman":
        st.markdown(
            "Black-Litterman Model: Combine market equilibrium with your investment views. "
            "Add your views below, then see how they affect optimal allocation. / "
            "Black-Litterman 模型：将市场均衡与您的投资观点相结合。"
            "在下方添加您的观点，然后查看它们如何影响最优配置。"
        )
    else:
        st.markdown(
            "Mean-Variance Optimization based on Markowitz's Modern Portfolio Theory. "
            "Select assets, configure parameters, and find the optimal allocation. / "
            "基于 Markowitz 现代投资组合理论的均值-方差优化。"
            "选择资产、配置参数，寻找最优配置。"
        )
    st.divider()

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
    if config["opt_mode"] == "Black-Litterman":
        # Black-Litterman 模式：需要观点输入
        # BL mode: requires view input
        views = _render_bl_views_input(returns.columns.tolist())

        if not views:
            st.warning(
                "⚠️ Please add at least one view for Black-Litterman optimization. / "
                "请添加至少一个观点以运行 Black-Litterman 优化。"
            )
            return

        with st.spinner("Running Black-Litterman optimization... / 正在运行 Black-Litterman 优化..."):
            results = _run_bl_optimization(
                returns,
                config["risk_free_rate"],
                config["allow_short"],
                config["bl_config"],
                views,
            )

        # 检查优化是否成功 / Check optimization success
        if not results["selected"]["success"]:
            st.error(
                "❌ BL Optimization failed to converge. Try adjusting views "
                "or parameters. / "
                "BL 优化未能收敛，请尝试调整观点或参数。"
            )
            return

        # BL 可视化 / BL Visualizations
        _render_bl_returns_comparison(results["bl_optimizer"])
        _render_bl_efficient_frontier_comparison(
            results["mvo_frontier"],
            results["bl_frontier"],
            results["mvo_max_sharpe"],
            results["bl_max_sharpe"],
            results["mvo_random"],
        )
        _render_bl_impact_analysis(results["bl_optimizer"])

        # 复用现有组件展示选中的组合
        # Reuse existing component to show selected portfolio
        st.markdown("### ✦ Optimal Portfolio (BL Max Sharpe) / 最优组合（BL 最大夏普）")

        selected = results["selected"]
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

        # 权重详情表 / Detailed weights table
        st.markdown("**Asset Weights / 资产权重**")
        weights_df = pd.DataFrame([
            {
                "Asset / 资产": asset,
                "Weight / 权重": weight * 100,
                "Allocation / 配置": "Long / 多" if weight >= 0 else "Short / 空",
            }
            for asset, weight in selected["weights"].items()
        ])
        st.dataframe(
            weights_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Weight / 权重": st.column_config.NumberColumn(
                    format="%.2f%%"
                )
            }
        )

    else:
        # MVO 模式：支持传统MVO、重抽样MVO、资产类别约束
        # MVO mode: support traditional MVO, resampled MVO, asset class constraints
        opt_method = config["opt_method"]

        # 显示优化方法描述
        # Show optimization method description
        if opt_method == "Resampled MVO (Michaud)":
            st.info(
                "🔄 **Resampled MVO (Michaud Method)**: Uses Monte Carlo simulation to "
                "reduce estimation error and produce more diversified portfolios. / "
                "**重抽样MVO（Michaud方法）**：使用蒙特卡洛模拟来减少估计误差，"
                "产生更多元化的投资组合。"
            )
        elif config.get("asset_class_constraints"):
            st.info(
                "📊 **Asset Class Constraints**: Portfolio weights are constrained "
                "to stay within specified ranges for each asset class. / "
                "**资产类别约束**：投资组合权重被约束在每个资产类别的指定范围内。"
            )

        with st.spinner("Running portfolio optimization... / 正在运行投资组合优化..."):
            results = _run_optimization(
                returns,
                config["risk_free_rate"],
                config["allow_short"],
                config["opt_mode"],
                opt_method=opt_method,
                resampled_config=config.get("resampled_config"),
                asset_class_constraints=config.get("asset_class_constraints"),
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
        # 5.5 资产类别权重 / Asset Class Weights
        # ====================================
        _render_asset_class_weights(results)

        # ====================================
        # 6. 组合对比表 / Portfolio Comparison
        # ====================================
        _render_comparison_table(results)

    # ====================================
    # 7. 资产池摘要 / Asset Universe Summary
    # ====================================
    if config["opt_mode"] == "Black-Litterman":
        _render_asset_universe(results["mvo_optimizer"])
    else:
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


def _render_bl_views_input(
    asset_names: list[str],
) -> list:
    """
    Render investor views input interface for Black-Litterman model.
    为 Black-Litterman 模型渲染投资者观点输入界面。

    Allows users to add multiple views:
    允许用户添加多个观点：

        1. Absolute views: "Asset X will return Y%"
           绝对观点："资产X将获得Y%收益"
        2. Relative views: "Asset X will outperform Asset Y by Z%"
           相对观点："资产X将比资产Y高出Z%"

    CFA Reference / CFA 参考:
        CFA L3: Investor views represent subjective return expectations.
        These views are combined with market equilibrium returns using
        Bayesian inference in the Black-Litterman model.
        CFA 三级：投资者观点代表主观收益预期。
        在 Black-Litterman 模型中，这些观点通过贝叶斯推断与市场均衡收益相结合。

    Args:
        asset_names: List of available asset names.
                     可用资产名称列表。

    Returns:
        List of ViewInput objects.
        ViewInput 对象列表。
    """
    st.markdown("### ⌬ Investor Views / 投资者观点")
    st.caption(
        "Add your investment views. The Black-Litterman model will blend these "
        "views with market equilibrium returns. / "
        "添加您的投资观点。Black-Litterman 模型将把这些观点与市场均衡收益相结合。"
    )

    # Initialize session state for views if not exists
    # 如果不存在，初始化观点的 session state
    if "bl_views" not in st.session_state:
        st.session_state.bl_views = []

    # Add new view section
    # 添加新观点区域
    with st.expander("➕ Add New View / 添加新观点", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            view_type = st.radio(
                "View Type / 观点类型",
                options=["Absolute / 绝对", "Relative / 相对"],
                index=0,
                horizontal=True,
            )

        with col2:
            confidence = st.slider(
                "Confidence / 置信度",
                min_value=10,
                max_value=100,
                value=BL_DEFAULT_CONFIDENCE,
                step=5,
                format="%d%%",
                help="Higher confidence = more weight on this view. / "
                     "更高置信度 = 观点权重更大。",
            )

        if "Absolute" in view_type:
            # Absolute view input
            # 绝对观点输入
            col3, col4 = st.columns(2)
            with col3:
                asset = st.selectbox(
                    "Asset / 资产",
                    options=asset_names,
                    key="abs_asset",
                )
            with col4:
                expected_return = st.number_input(
                    "Expected Return / 预期收益",
                    min_value=-1.0,
                    max_value=5.0,
                    value=0.15,
                    step=0.01,
                    format="%.2f",
                    key="abs_return",
                    help="Annualized return (e.g., 0.15 = 15%). / "
                         "年化收益率（如 0.15 = 15%）。",
                )

            if st.button("Add View / 添加观点", key="add_abs"):
                st.session_state.bl_views.append(
                    ViewInput(
                        view_type='absolute',
                        asset_long=asset,
                        expected_return=expected_return,
                        confidence=float(confidence),
                    )
                )
                st.success(f"✅ Added: {asset} → {expected_return:.1%}")
                st.rerun()

        else:
            # Relative view input
            # 相对观点输入
            col5, col6, col7 = st.columns(3)
            with col5:
                asset_long = st.selectbox(
                    "Outperforms / 优于",
                    options=asset_names,
                    key="rel_long",
                )
            with col6:
                # Filter out the selected long asset from short options
                # 从空头选项中过滤掉已选的多头资产
                short_options = [a for a in asset_names if a != asset_long]
                asset_short = st.selectbox(
                    "Underperforms / 劣于",
                    options=short_options,
                    key="rel_short",
                )
            with col7:
                return_diff = st.number_input(
                    "Return Difference / 收益差",
                    min_value=-1.0,
                    max_value=1.0,
                    value=0.03,
                    step=0.01,
                    format="%.2f",
                    key="rel_diff",
                    help="How much outperforms (e.g., 0.03 = 3%). / "
                         "高出多少（如 0.03 = 3%）。",
                )

            if st.button("Add View / 添加观点", key="add_rel"):
                st.session_state.bl_views.append(
                    ViewInput(
                        view_type='relative',
                        asset_long=asset_long,
                        asset_short=asset_short,
                        expected_return=return_diff,
                        confidence=float(confidence),
                    )
                )
                st.success(f"✅ Added: {asset_long} > {asset_short} by {return_diff:.1%}")
                st.rerun()

    # Display existing views
    # 显示已添加的观点
    if st.session_state.bl_views:
        st.markdown("#### Current Views / 当前观点")

        for i, view in enumerate(st.session_state.bl_views):
            if view.view_type == 'absolute':
                desc = (
                    f"**{view.asset_long}** → {view.expected_return:.1%} "
                    f"(confidence: {view.confidence:.0f}%)"
                )
            else:
                desc = (
                    f"**{view.asset_long}** > **{view.asset_short}** "
                    f"by {view.expected_return:.1%} "
                    f"(confidence: {view.confidence:.0f}%)"
                )

            col_desc, col_del = st.columns([4, 1])
            with col_desc:
                st.markdown(f"{i+1}. {desc}")
            with col_del:
                if st.button("🗑️", key=f"del_{i}"):
                    st.session_state.bl_views.pop(i)
                    st.rerun()

        # Clear all views button
        # 清除所有观点按钮
        if st.button("Clear All Views / 清除所有观点"):
            st.session_state.bl_views = []
            st.rerun()
    else:
        st.info(
            "ℹ️ No views added yet. Add at least one view to run Black-Litterman optimization. / "
            "尚未添加观点。请添加至少一个观点以运行 Black-Litterman 优化。"
        )

    return st.session_state.bl_views


def _run_bl_optimization(
    returns: pd.DataFrame,
    risk_free_rate: float,
    allow_short: bool,
    bl_config: dict,
    views: list,
) -> dict:
    """
    Run Black-Litterman optimization with user views.
    运行带有用户观点的 Black-Litterman 优化。

    Args:
        returns: DataFrame of daily asset returns.
                 资产日收益率 DataFrame。
        risk_free_rate: Annual risk-free rate.
                        年化无风险利率。
        allow_short: Whether to allow short selling.
                     是否允许做空。
        bl_config: Black-Litterman configuration dict with tau, delta, market_weights.
                   Black-Litterman 配置字典，包含 tau、delta、market_weights。
        views: List of ViewInput objects.
               ViewInput 对象列表。

    Returns:
        Dict with BL optimizer results, MVO results for comparison, and frontiers.
        包含 BL 优化结果、MVO 对比结果和有效前沿的字典。
    """
    # Extract market weights from config
    # 从配置中提取市场权重
    market_weights_dict = bl_config["market_weights"]
    market_weights = np.array([
        market_weights_dict.get(name, 1.0 / len(returns.columns))
        for name in returns.columns
    ])
    # Normalize to sum to 1
    # 归一化使其加总为1
    market_weights = market_weights / market_weights.sum()

    # Create BL optimizer
    # 创建 BL 优化器
    bl_opt = BlackLittermanOptimizer(
        returns,
        risk_free_rate=risk_free_rate,
        market_cap_weights=market_weights,
        delta=bl_config["delta"],
        tau=bl_config["tau"],
    )

    # Apply views
    # 应用观点
    bl_opt.apply_views(views)

    # Run BL optimization
    # 运行 BL 优化
    bl_max_sharpe = bl_opt.bl_maximize_sharpe(allow_short=allow_short)
    bl_min_vol = bl_opt.bl_minimize_volatility(allow_short=allow_short)
    bl_frontier = bl_opt.bl_efficient_frontier(n_points=50, allow_short=allow_short)

    # Also run MVO for comparison
    # 同时运行 MVO 用于对比
    mvo_opt = PortfolioOptimizer(returns, risk_free_rate=risk_free_rate)
    mvo_max_sharpe = mvo_opt.maximize_sharpe(allow_short=allow_short)
    mvo_min_vol = mvo_opt.minimize_volatility(allow_short=allow_short)
    mvo_frontier = mvo_opt.efficient_frontier(n_points=50, allow_short=allow_short)
    mvo_random = mvo_opt.random_portfolios(n_portfolios=1000)

    # Select portfolio based on mode (default to max Sharpe)
    # 根据模式选择组合（默认为最大夏普）
    selected = bl_max_sharpe

    return {
        "bl_optimizer": bl_opt,
        "bl_max_sharpe": bl_max_sharpe,
        "bl_min_vol": bl_min_vol,
        "bl_frontier": bl_frontier,
        "mvo_optimizer": mvo_opt,
        "mvo_max_sharpe": mvo_max_sharpe,
        "mvo_min_vol": mvo_min_vol,
        "mvo_frontier": mvo_frontier,
        "mvo_random": mvo_random,
        "selected": selected,
    }


def _render_bl_returns_comparison(bl_optimizer: BlackLittermanOptimizer) -> None:
    """
    Render comparison table: Equilibrium vs BL Posterior.
    渲染对比表：均衡收益 vs BL 后验。

    CFA Reference / CFA 参考:
        CFA L3: The BL posterior is a weighted average of equilibrium
        returns and investor views. The weight depends on relative confidence.
        CFA 三级：BL 后验是均衡收益和投资者观点的加权平均。
        权重取决于相对置信度。

    Args:
        bl_optimizer: BlackLittermanOptimizer instance with views applied.
                      已应用观点的 BlackLittermanOptimizer 实例。
    """
    st.markdown("### ⧉ Returns Comparison / 收益率对比")

    data = []
    for i, name in enumerate(bl_optimizer.asset_names):
        eq_ret = bl_optimizer.Pi[i]
        bl_ret = bl_optimizer.mu_bl[i]
        adj = bl_ret - eq_ret

        data.append({
            "Asset / 资产": name,
            "Equilibrium / 均衡": f"{eq_ret:.2%}",
            "BL Posterior / BL后验": f"{bl_ret:.2%}",
            "Adjustment / 调整": f"{adj:+.2%}",
            "Direction / 方向": "↑" if adj > 0 else ("↓" if adj < 0 else "→"),
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "💡 The BL posterior blends equilibrium returns with your views. "
        "Positive adjustment means the model increased the expected return "
        "relative to equilibrium. / "
        "BL后验将均衡收益与您的观点相结合。"
        "正向调整意味着模型相对于均衡提高了预期收益。"
    )


def _render_bl_efficient_frontier_comparison(
    mvo_frontier: pd.DataFrame,
    bl_frontier: pd.DataFrame,
    mvo_max_sharpe: dict,
    bl_max_sharpe: dict,
    mvo_random: pd.DataFrame,
) -> None:
    """
    Render side-by-side MVO vs BL efficient frontiers.
    渲染并排的 MVO vs BL 有效前沿对比图。

    Args:
        mvo_frontier: MVO efficient frontier DataFrame.
                      MVO 有效前沿 DataFrame。
        bl_frontier: BL efficient frontier DataFrame.
                     BL 有效前沿 DataFrame。
        mvo_max_sharpe: MVO max Sharpe portfolio dict.
                        MVO 最大夏普组合字典。
        bl_max_sharpe: BL max Sharpe portfolio dict.
                       BL 最大夏普组合字典。
        mvo_random: Random portfolios for scatter cloud.
                    随机组合用于散点云。
    """
    st.markdown("### ↗ Efficient Frontier Comparison / 有效前沿对比")

    fig = go.Figure()

    # Random portfolio cloud (subtle background)
    # 随机组合散点云（淡色背景）
    fig.add_trace(go.Scatter(
        x=mvo_random["volatility"] * 100,
        y=mvo_random["return"] * 100,
        mode="markers",
        marker=dict(
            size=3,
            color=mvo_random["sharpe"],
            colorscale="Viridis",
            opacity=0.3,
            showscale=False,
        ),
        name="Random Portfolios / 随机组合",
        hovertemplate="Vol: %{x:.1f}%<br>Return: %{y:.1f}%<extra></extra>",
    ))

    # MVO frontier
    # MVO 有效前沿
    fig.add_trace(go.Scatter(
        x=mvo_frontier["volatility"] * 100,
        y=mvo_frontier["return"] * 100,
        mode="lines",
        line=dict(color="#3B82F6", width=3),
        name="MVO Frontier / MVO前沿",
    ))

    # BL frontier
    # BL 有效前沿
    fig.add_trace(go.Scatter(
        x=bl_frontier["volatility"] * 100,
        y=bl_frontier["return"] * 100,
        mode="lines",
        line=dict(color="#F59E0B", width=3, dash="dash"),
        name="BL Frontier / BL前沿",
    ))

    # MVO max Sharpe
    # MVO 最大夏普
    fig.add_trace(go.Scatter(
        x=[mvo_max_sharpe["volatility"] * 100],
        y=[mvo_max_sharpe["return"] * 100],
        mode="markers",
        marker=dict(size=16, color="#3B82F6", symbol="star"),
        name=f"MVO Max Sharpe ({mvo_max_sharpe['sharpe']:.2f})",
    ))

    # BL max Sharpe
    # BL 最大夏普
    fig.add_trace(go.Scatter(
        x=[bl_max_sharpe["volatility"] * 100],
        y=[bl_max_sharpe["return"] * 100],
        mode="markers",
        marker=dict(size=16, color="#F59E0B", symbol="star"),
        name=f"BL Max Sharpe ({bl_max_sharpe['sharpe']:.2f})",
    ))

    fig.update_layout(
        title="MVO vs Black-Litterman Efficient Frontiers",
        xaxis_title="Annualized Volatility / 年化波动率 (%)",
        yaxis_title="Annualized Return / 年化收益率 (%)",
        height=500,
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.8)",
        plot_bgcolor="rgba(15, 23, 42, 0.8)",
        font=dict(color="#E2E8F0"),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        hovermode="closest",
    )

    st.plotly_chart(fig, use_container_width=True, theme=None)

    st.caption(
        "💡 The BL frontier shifts based on your views. If views are bullish, "
        "the frontier moves upward (higher expected returns). "
        "The **blue curve** is MVO, the **yellow dashed curve** is BL. / "
        "BL前沿根据您的观点移动。如果观点是看多的，前沿向上移动（更高预期收益）。"
        "**蓝色曲线**是MVO，**黄色虚线曲线**是BL。"
    )


def _render_bl_impact_analysis(bl_optimizer: BlackLittermanOptimizer) -> None:
    """
    Render bar chart showing BL adjustment magnitude for each asset.
    渲染柱状图展示每个资产的 BL 调整幅度。

    Args:
        bl_optimizer: BlackLittermanOptimizer instance with views applied.
                      已应用观点的 BlackLittermanOptimizer 实例。
    """
    st.markdown("### ↘ View Impact Analysis / 观点影响分析")

    adjustments = []
    for i, name in enumerate(bl_optimizer.asset_names):
        adj = bl_optimizer.mu_bl[i] - bl_optimizer.Pi[i]
        adjustments.append({
            "Asset / 资产": name,
            "Adjustment / 调整": adj,
            "Abs Adjustment / 绝对调整": abs(adj),
        })

    df = pd.DataFrame(adjustments)
    df = df.sort_values("Abs Adjustment / 绝对调整", ascending=True)

    # Create bar chart
    # 创建柱状图
    colors = [
        "#10B981" if adj > 0 else "#EF4444"
        for adj in df["Adjustment / 调整"]
    ]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["Asset / 资产"],
        y=df["Adjustment / 调整"] * 100,
        marker_color=colors,
        text=[f"{adj:+.2%}" for adj in df["Adjustment / 调整"]],
        textposition="outside",
        textfont=dict(color="#E2E8F0"),
    ))

    fig.update_layout(
        title="BL Adjustment by Asset (Posterior - Equilibrium)",
        xaxis_title="Asset / 资产",
        yaxis_title="Return Adjustment / 收益调整 (%)",
        height=400,
        template="plotly_dark",
        paper_bgcolor="rgba(15, 23, 42, 0.8)",
        plot_bgcolor="rgba(15, 23, 42, 0.8)",
        font=dict(color="#E2E8F0"),
        showlegend=False,
    )

    # Add zero line
    # 添加零线
    fig.add_hline(y=0, line_dash="dash", line_color="#64748B")

    st.plotly_chart(fig, use_container_width=True, theme=None)

    st.caption(
        "💡 Green bars = BL increased expected return vs equilibrium. "
        "Red bars = BL decreased expected return. "
        "Larger bars = stronger view impact. / "
        "绿色柱 = BL相对于均衡提高了预期收益。"
        "红色柱 = BL降低了预期收益。"
        "柱子越大 = 观点影响越强。"
    )
