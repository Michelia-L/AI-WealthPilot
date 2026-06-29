"""
AI WealthPilot - Portfolio Optimizer Page

Interactive Streamlit page for Mean-Variance Portfolio Optimization.
Users can select asset classes, configure parameters, and visualize
the efficient frontier, optimal portfolios, and risk-return metrics.

"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
import plotly.graph_objects as go

# Import data fetching and processing functions
from src.data.market_data import fetch_price_history, compute_returns, fetch_risk_free_rate

# Import portfolio optimizers
from src.portfolio.optimizer import PortfolioOptimizer, BlackLittermanOptimizer

# Import view input objects
from src.portfolio.views import ViewInput, ViewProcessor

# Import chart visualization components
from src.visualization.charts import (
    plot_efficient_frontier,
    plot_allocation_pie,
)

# Import global configurations
from src.config import (
    DEFAULT_ASSET_CLASSES,
    RISK_FREE_RATE,
    BL_DEFAULT_TAU,
    BL_DEFAULT_DELTA,
    BL_DEFAULT_CONFIDENCE,
    FRED_API_KEY,
)

from src.views.compliance import render_suitability_disclaimer

# Default asset class mapping for UI multi-select
ASSET_OPTIONS: Dict[str, str] = {
    key: f"{val['name']} ({val['ticker']})"
    for key, val in DEFAULT_ASSET_CLASSES.items()
}


@st.cache_data(ttl=86400, show_spinner="Fetching latest risk-free rate...")
def get_dynamic_risk_free_rate() -> float:
    """
    Fetch the risk-free rate dynamically and cache it for 24 hours.
    获取动态无风险利率并缓存24小时。
    """
    try:
        return fetch_risk_free_rate(fred_api_key=FRED_API_KEY, default_rate=RISK_FREE_RATE)
    except Exception:
        return RISK_FREE_RATE


def _render_top_controls() -> Dict[str, Any]:
    """
    Render portfolio optimization controls in the main page body using a premium expander.
    
    Returns:
        Dict with all optimizer parameters.
    """
    # Note: .premium-console CSS is now injected globally via styles.py
    
    with st.expander("🛠️ Adjust Optimization Parameters / 调整投资组合优化参数", expanded=True):
        col1, col2, col3 = st.columns([1.2, 1, 1.2])
        
        with col1:
            st.markdown("##### 📁 Assets & Horizon / 资产与时间")
            selected_keys = st.multiselect(
                "Select asset classes for optimization / 选择资产类别",
                options=list(ASSET_OPTIONS.keys()),
                default=["US_EQUITY", "INTL_EQUITY", "US_BOND", "GOLD"],
                format_func=lambda k: ASSET_OPTIONS[k],
                key="opt_selected_keys"
            )
            
            period = st.select_slider(
                "Historical data window / 历史数据时间范围",
                options=["1y", "2y", "3y", "5y", "10y"],
                value="5y",
                key="opt_period"
            )
            
            # Fetch dynamic risk-free rate
            dynamic_rf = get_dynamic_risk_free_rate()
            
            risk_free_rate = st.number_input(
                "Annual risk-free rate / 无风险利率",
                min_value=0.0,
                max_value=0.20,
                value=dynamic_rf,
                step=0.005,
                format="%.3f",
                help="Typically the yield on 10-year government bonds. / 通常使用十年期国债收益率。",
                key="opt_rf"
            )
            
        with col2:
            st.markdown("##### ⚙️ Method & Goal / 优化设置")
            opt_method = st.selectbox(
                "Select optimization method / 优化方法",
                options=[
                    "Traditional MVO",
                    "Resampled MVO (Michaud)",
                    "Black-Litterman",
                ],
                index=0,
                help="Traditional MVO: classic Markowitz optimization. Resampled MVO: Monte Carlo simulation. Black-Litterman: combine equilibrium with your views. / 传统MVO：Markowitz优化。重抽样MVO：蒙特卡洛模拟。Black-Litterman：结合均衡收益与您的观点。",
                key="opt_method_select"
            )
            
            opt_mode = st.radio(
                "Select optimization objective / 优化目标",
                options=["Maximum Sharpe", "Minimum Volatility"],
                index=0,
                help="Maximum Sharpe: best risk-adjusted return. Minimum Volatility: lowest possible risk. / 最大夏普比率：最优风险调整收益。最小波动率：最低风险。",
                key="opt_mode_select"
            )
            
            allow_short = st.checkbox(
                "Allow short selling / 允许做空",
                value=False,
                help="If unchecked, all weights are constrained to [0, 1] (long-only). / 不做空时，所有权重限制在 [0, 1] 之间。",
                key="opt_allow_short"
            )
            
        with col3:
            st.markdown("##### 🔒 Constraints & Model / 约束与模型参数")
            
            # Resampled MVO parameters
            resampled_config = {}
            if opt_method == "Resampled MVO (Michaud)":
                resampled_config["n_simulations"] = st.slider(
                    "Number of simulations / 模拟次数",
                    min_value=100,
                    max_value=5000,
                    value=200,
                    step=100,
                    key="opt_n_simulations"
                )
            
            # Asset class constraints
            asset_class_constraints = {}
            use_asset_class_constraints = st.checkbox(
                "Enable asset class constraints / 启用资产类别约束",
                value=False,
                help="Add minimum and maximum weight constraints for asset classes. / 为资产类别添加最小和最大权重约束。",
                key="opt_use_constraints"
            )
            
            if use_asset_class_constraints and len(selected_keys) >= 2:
                # Classify assets
                equity_keys = [k for k in selected_keys if 'EQUITY' in k]
                bond_keys = [k for k in selected_keys if 'BOND' in k]
                other_keys = [k for k in selected_keys if k not in equity_keys and k not in bond_keys]
                
                if equity_keys:
                    c_eq1, c_eq2 = st.columns(2)
                    with c_eq1:
                        equity_min = st.number_input("Equity Min %", min_value=0, max_value=100, value=20, step=5, key="opt_eq_min") / 100.0
                    with c_eq2:
                        equity_max = st.number_input("Equity Max %", min_value=0, max_value=100, value=80, step=5, key="opt_eq_max") / 100.0
                    asset_class_constraints['equity'] = {
                        'assets': [DEFAULT_ASSET_CLASSES[k]["name"] for k in equity_keys],
                        'min': equity_min,
                        'max': equity_max,
                    }
                    
                if bond_keys:
                    c_bd1, c_bd2 = st.columns(2)
                    with c_bd1:
                        bond_min = st.number_input("Bond Min %", min_value=0, max_value=100, value=10, step=5, key="opt_bond_min") / 100.0
                    with c_bd2:
                        bond_max = st.number_input("Bond Max %", min_value=0, max_value=100, value=50, step=5, key="opt_bond_max") / 100.0
                    asset_class_constraints['bonds'] = {
                        'assets': [DEFAULT_ASSET_CLASSES[k]["name"] for k in bond_keys],
                        'min': bond_min,
                        'max': bond_max,
                    }
                    
                if other_keys:
                    c_ot1, c_ot2 = st.columns(2)
                    with c_ot1:
                        other_min = st.number_input("Other Min %", min_value=0, max_value=100, value=0, step=5, key="opt_other_min") / 100.0
                    with c_ot2:
                        other_max = st.number_input("Other Max %", min_value=0, max_value=100, value=30, step=5, key="opt_other_max") / 100.0
                    asset_class_constraints['other'] = {
                        'assets': [DEFAULT_ASSET_CLASSES[k]["name"] for k in other_keys],
                        'min': other_min,
                        'max': other_max,
                    }
            
            # Black-Litterman specific parameters
            bl_config = {}
            if opt_method == "Black-Litterman":
                bl_config["tau"] = st.slider(
                    "Uncertainty scale (τ) / 不确定性比例",
                    min_value=0.01,
                    max_value=0.10,
                    value=BL_DEFAULT_TAU,
                    step=0.005,
                    format="%.3f",
                    help="Higher τ = less trust in equilibrium. / 更高的 τ = 对均衡的信任度更低。",
                    key="opt_bl_tau"
                )
                
                bl_config["delta"] = st.number_input(
                    "Risk aversion (δ) / 风险厌恶系数",
                    min_value=1.0,
                    max_value=10.0,
                    value=BL_DEFAULT_DELTA,
                    step=0.5,
                    help="Higher δ = more risk averse. / 更高的 δ = 更厌恶风险。",
                    key="opt_bl_delta"
                )
                
                with st.expander("📊 Market Cap Weights / 市值权重配置", expanded=False):
                    st.caption("Enter market cap weights (must sum to 1.0) / 输入市值权重（必须加总为 1.0）")
                    market_weights = {}
                    total_weight = 0.0
                    for key in selected_keys:
                        asset_name = DEFAULT_ASSET_CLASSES[key]["name"]
                        default_weight = 1.0 / len(selected_keys)
                        market_weights[key] = st.number_input(
                            f"{asset_name}",
                            min_value=0.0,
                            max_value=1.0,
                            value=default_weight,
                            step=0.05,
                            format="%.2f",
                            key=f"opt_mw_{key}"
                        )
                        total_weight += market_weights[key]
                        
                    if abs(total_weight - 1.0) > 0.01:
                        st.warning(f"Weights sum to {total_weight:.2f}, should be 1.0 / 权重和为 {total_weight:.2f}，应为 1.0")
                    bl_config["market_weights"] = market_weights

        st.markdown(
            f'<div style="text-align: right; color: #94A3B8; font-size: 0.85rem; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.05);">'
            f'🎯 <b>Assets:</b> {len(selected_keys)} &nbsp;|&nbsp; <b>Horizon:</b> {period} &nbsp;|&nbsp; <b>Rf:</b> {risk_free_rate:.2%} &nbsp;|&nbsp; <b>Method:</b> {opt_method}'
            f'</div>',
            unsafe_allow_html=True
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


@st.cache_data(ttl=300, show_spinner="Fetching historical prices... / 正在拉取历史价格数据...")
def _cached_fetch_price_history(tickers: Tuple[str, ...], period: str) -> Optional[pd.DataFrame]:
    """
    Cached wrapper for fetch_price_history.
    获取历史收盘价数据的缓存包装函数，缓存 5 分钟。
    """
    try:
        return fetch_price_history(list(tickers), period=period)
    except Exception:
        return None


def _fetch_and_prepare_data(
    selected_keys: List[str],
    period: str,
) -> Optional[pd.DataFrame]:
    """
    Fetch price data for selected asset classes and compute returns.

    Args:
        selected_keys: List of asset class keys.
        period: yfinance period string.

    Returns:
        DataFrame of daily simple returns, or None if the data fetch fails.
    """
    tickers = [DEFAULT_ASSET_CLASSES[key]["ticker"] for key in selected_keys]
    names = [DEFAULT_ASSET_CLASSES[key]["name"] for key in selected_keys]

    prices = _cached_fetch_price_history(tuple(tickers), period)

    if prices is None or prices.empty:
        return None

    prices.columns = names

    # Compute daily simple returns: R_t = (P_t - P_{t-1}) / P_{t-1}
    returns = compute_returns(prices, method="simple")

    return returns



@st.cache_data
def _run_optimization(
    returns: pd.DataFrame,
    risk_free_rate: float,
    allow_short: bool,
    opt_mode: str,
    opt_method: str = "Traditional MVO",
    resampled_config: Optional[Dict[str, Any]] = None,
    asset_class_constraints: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run the portfolio optimization and return all results.

    Financial Formulas Explained:
    1. Expected Return: E(R_p) = w^T * Mean(Returns)
    2. Portfolio Volatility: Vol_p = sqrt(w^T * Covariance * w)
    3. Sharpe Ratio: SR = (E(R_p) - R_f) / Vol_p
       Represents excess return per unit of total risk.

    Args:
        returns: DataFrame of daily asset returns.
        risk_free_rate: Annual risk-free rate.
        allow_short: Whether to allow short selling.
        opt_mode: 'Maximum Sharpe' or 'Minimum Volatility'.
        opt_method: Optimization method name.
        resampled_config: Configuration for resampled MVO.
        asset_class_constraints: Asset class constraint configuration.

    Returns:
        Dict with optimizer results, efficient frontier, and random portfolios.
    """
    optimizer = PortfolioOptimizer(returns, risk_free_rate=risk_free_rate)

    if opt_method == "Resampled MVO (Michaud)":
        n_simulations = resampled_config.get("n_simulations", 1000) if resampled_config else 1000

        if opt_mode == "Maximum Sharpe":
            selected = optimizer.resampled_maximize_sharpe(
                n_simulations=n_simulations,
                allow_short=allow_short,
            )
        else:
            selected = optimizer.resampled_minimize_volatility(
                n_simulations=n_simulations,
                allow_short=allow_short,
            )

        frontier = optimizer.resampled_efficient_frontier(
            n_points=25,
            n_simulations=n_simulations,
            allow_short=allow_short,
        )
        max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
        min_vol = optimizer.minimize_volatility(allow_short=allow_short)

    elif asset_class_constraints:
        selected = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_constraints,
            allow_short=allow_short,
        )
        frontier = optimizer.efficient_frontier(
            n_points=50, allow_short=allow_short
        )
        max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
        min_vol = optimizer.minimize_volatility(allow_short=allow_short)

    else:
        max_sharpe = optimizer.maximize_sharpe(allow_short=allow_short)
        min_vol = optimizer.minimize_volatility(allow_short=allow_short)
        frontier = optimizer.efficient_frontier(
            n_points=50, allow_short=allow_short
        )

        if opt_mode == "Maximum Sharpe":
            selected = max_sharpe
        else:
            selected = min_vol

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


def _render_efficient_frontier(results: Dict[str, Any]) -> None:
    """
    Render the efficient frontier chart with highlighted optimal portfolios.

    Args:
        results: Dict from _run_optimization.
    """
    st.markdown("### ↗ Efficient Frontier / 有效前沿")

    # Extract risk-free rate from optimizer for CAL computation
    optimizer = results.get("optimizer")
    risk_free_rate = optimizer.risk_free_rate if optimizer else None

    fig = plot_efficient_frontier(
        frontier=results["frontier"],
        random_portfolios=results["random_portfolios"],
        max_sharpe=results["max_sharpe"],
        min_vol=results["min_vol"],
        risk_free_rate=risk_free_rate,
    )

    st.plotly_chart(fig, use_container_width=True, theme=None)

    st.caption(
        "💡 Each dot is a random portfolio. The blue curve is the efficient frontier — "
        "portfolios on this curve offer the highest return for each risk level. "
        "The star (Max Sharpe) and diamond (Min Vol) mark the two key optimal portfolios. "
        "The dashed gold line is the **Capital Allocation Line (CAL)** — it shows the best "
        "possible combinations of the risk-free asset and the tangency portfolio. "
        "Points below the star represent lending (partial risk-free allocation); "
        "points above represent borrowing (leveraged positions). / "
        "每个散点代表一个随机组合。蓝色曲线是有效前沿——该曲线上的组合在每个风险水平下提供最高收益。"
        "星形（最大夏普）和菱形（最小波动率）标记了两个关键最优组合。"
        "金色虚线是**资本配置线（CAL）**——它展示了无风险资产与切点组合的最优混合。"
        "星形下方代表放贷（部分配置无风险资产）；上方代表借贷（杠杆头寸）。"
    )

    st.divider()


def _render_selected_portfolio(
    selected: Dict[str, Any],
    title: str = "Optimal Portfolio / 最优组合",
    show_pie: bool = True,
    show_sharpe_quality: bool = True,
) -> None:
    """
    Render an optimal portfolio's details: metrics + optional pie chart + weights table.

    Reusable for both MVO and Black-Litterman results.

    Args:
        selected: Portfolio dict with 'return', 'volatility', 'sharpe', 'weights' keys.
        title: Heading text for the section.
        show_pie: Whether to render the allocation pie chart.
        show_sharpe_quality: Whether to render the Sharpe ratio quality caption.
    """
    st.markdown(f"### {title}")

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

    if show_pie:
        chart_col, table_col = st.columns([1, 1])
        with chart_col:
            fig = plot_allocation_pie(
                selected["weights"],
                title=f"Asset Allocation — {title.split(' / ')[0]}",
            )
            st.plotly_chart(fig, use_container_width=True, theme=None)
    else:
        table_col = st.container()

    with table_col:
        st.markdown("**Asset Weights / 资产权重**")

        weights_df = pd.DataFrame([
            {
                "Asset / 资产": asset,
                "Weight / 权重": weight * 100.0,
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

        if show_sharpe_quality:
            sharpe = selected["sharpe"]
            quality = "Good / 良好" if sharpe > 1.0 else ("Moderate / 中等" if sharpe > 0.5 else "Below average / 偏低")

            st.caption(
                f"📊 Sharpe ratio = {sharpe:.2f} ({quality}). "
                f"This means for each unit of risk taken, the portfolio earns "
                f"{sharpe:.2f} units of excess return above the risk-free rate. / "
                f"夏普比率 = {sharpe:.2f}（{quality}）。这意味着每承担一单位风险，组合获得 {sharpe:.2f} 单位的超额收益。"
            )

    st.divider()


def _render_asset_class_weights(results: Dict[str, Any]) -> None:
    """
    Render asset class weights if available.

    Args:
        results: Dict from _run_optimization.
    """
    selected = results["selected"]

    if "asset_class_weights" not in selected:
        return

    st.markdown("### Asset Class Weights / 资产类别权重")

    asset_class_weights = selected["asset_class_weights"]

    weights_data = []
    for class_name, weight in asset_class_weights.items():
        weights_data.append({
            "Asset Class / 资产类别": class_name.capitalize(),
            "Weight / 权重": weight * 100.0,
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


def _render_comparison_table(results: Dict[str, Any]) -> None:
    """
    Render a comparison table of Max Sharpe and Min Volatility portfolios.

    Args:
        results: Dict from _run_optimization.
    """
    st.markdown("### Portfolio Comparison / 组合对比")

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

    st.caption(
        "💡 Tradeoff: The Max Sharpe portfolio optimizes risk-adjusted returns but may have higher volatility. "
        "The Min Volatility portfolio has the lowest risk but may sacrifice returns. Choose based on your risk tolerance. / "
        "权衡：最大夏普组合优化风险调整收益，但波动率可能更高。最小波动率组合风险最低，但可能牺牲收益。根据您的风险承受能力选择。"
    )

    st.divider()


def _render_asset_universe(optimizer: PortfolioOptimizer) -> None:
    """
    Render the asset universe summary - expected returns and volatilities.

    Args:
        optimizer: PortfolioOptimizer instance.
    """
    st.markdown("### Asset Universe Summary / 资产池摘要")

    summary_data = []
    for name in optimizer.asset_names:
        ann_ret = optimizer.mean_returns[name]
        ann_vol = np.sqrt(optimizer.cov_matrix.loc[name, name])
        summary_data.append({
            "Asset / 资产": name,
            "Ann. Return / 年化收益率": ann_ret * 100.0,
            "Ann. Volatility / 年化波动率": ann_vol * 100.0,
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


def _render_bl_views_input(
    asset_names: List[str],
) -> List[ViewInput]:
    """
    Render investor views input interface for Black-Litterman model.

    Args:
        asset_names: List of available asset names.

    Returns:
        List of ViewInput objects.
    """
    st.markdown("### Investor Views / 投资者观点")
    st.caption(
        "Add your investment views. The Black-Litterman model will blend these "
        "views with market equilibrium returns. / "
        "添加您的投资观点。Black-Litterman 模型将把这些观点与市场均衡收益相结合。"
    )

    if "bl_views" not in st.session_state:
        st.session_state.bl_views = []

    with st.expander("➕ Add New View / 添加新观点", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            view_type = st.radio(
                "View Type / 观点类型",
                options=["Absolute / 绝对", "Relative / 相对"],
                index=0,
                horizontal=True,
                key="bl_view_type_input"
            )

        with col2:
            confidence = st.slider(
                "Confidence / 置信度",
                min_value=10,
                max_value=100,
                value=BL_DEFAULT_CONFIDENCE,
                step=5,
                format="%d%%",
                help="Higher confidence = more weight on this view. / 更高置信度 = 观点权重更大。",
                key="bl_confidence_input"
            )

        if "Absolute" in view_type:
            col3, col4 = st.columns(2)
            with col3:
                asset = st.selectbox(
                    "Asset / 资产",
                    options=asset_names,
                    key="abs_asset_select",
                )
            with col4:
                expected_return = st.number_input(
                    "Expected Return / 预期收益",
                    min_value=-1.0,
                    max_value=5.0,
                    value=0.15,
                    step=0.01,
                    format="%.2f",
                    key="abs_return_val",
                    help="Annualized return (e.g., 0.15 = 15%). / 年化收益率（如 0.15 = 15%）。",
                )

            if st.button("Add View / 添加观点", key="add_abs_btn"):
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
            col5, col6, col7 = st.columns(3)
            with col5:
                asset_long = st.selectbox(
                    "Outperforms / 优于",
                    options=asset_names,
                    key="rel_long_select",
                )
            with col6:
                short_options = [a for a in asset_names if a != asset_long]
                asset_short = st.selectbox(
                    "Underperforms / 劣于",
                    options=short_options,
                    key="rel_short_select",
                )
            with col7:
                return_diff = st.number_input(
                    "Return Difference / 收益差",
                    min_value=-1.0,
                    max_value=1.0,
                    value=0.03,
                    step=0.01,
                    format="%.2f",
                    key="rel_diff_val",
                    help="How much outperforms (e.g., 0.03 = 3%). / 高出多少（如 0.03 = 3%）。",
                )

            if st.button("Add View / 添加观点", key="add_rel_btn"):
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
                if st.button("🗑️", key=f"del_view_{i}"):
                    st.session_state.bl_views.pop(i)
                    st.rerun()

        if st.button("Clear All Views / 清除所有观点", key="clear_all_views_btn"):
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
    bl_config: Dict[str, Any],
    views: List[ViewInput],
) -> Dict[str, Any]:
    """
    Run Black-Litterman optimization with investor views.

    Black-Litterman Formulas:
    1. Market Implied Equilibrium Returns: Pi = delta * Sigma * w_market
    2. Posterior Expected Return: mu_BL = [(tau*Sigma)^-1 + P^T * Omega^-1 * P]^-1 * [(tau*Sigma)^-1 * Pi + P^T * Omega^-1 * Q]
    3. Posterior Covariance: Sigma_BL = Sigma + [(tau*Sigma)^-1 + P^T * Omega^-1 * P]^-1

    Args:
        returns: DataFrame of daily asset returns.
        risk_free_rate: Annual risk-free rate.
        allow_short: Whether to allow short selling.
        bl_config: Black-Litterman configurations.
        views: List of ViewInput objects.

    Returns:
        Dict with BL optimizer results, MVO results for comparison, and frontiers.
    """
    market_weights_dict = bl_config["market_weights"]
    market_weights = np.array([
        market_weights_dict.get(name, 1.0 / len(returns.columns))
        for name in returns.columns
    ])
    market_weights = market_weights / market_weights.sum()

    bl_opt = BlackLittermanOptimizer(
        returns,
        risk_free_rate=risk_free_rate,
        market_cap_weights=market_weights,
        delta=bl_config["delta"],
        tau=bl_config["tau"],
    )

    bl_opt.apply_views(views)

    bl_max_sharpe = bl_opt.bl_maximize_sharpe(allow_short=allow_short)
    bl_min_vol = bl_opt.bl_minimize_volatility(allow_short=allow_short)
    bl_frontier = bl_opt.bl_efficient_frontier(n_points=50, allow_short=allow_short)

    mvo_opt = PortfolioOptimizer(returns, risk_free_rate=risk_free_rate)
    mvo_max_sharpe = mvo_opt.maximize_sharpe(allow_short=allow_short)
    mvo_min_vol = mvo_opt.minimize_volatility(allow_short=allow_short)
    mvo_frontier = mvo_opt.efficient_frontier(n_points=50, allow_short=allow_short)
    mvo_random = mvo_opt.random_portfolios(n_portfolios=1000)

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
    Render returns comparison table between Equilibrium and BL Posterior.

    Args:
        bl_optimizer: BlackLittermanOptimizer instance.
    """
    st.markdown("### Returns Comparison / 收益率对比")

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
        "Positive adjustment means the model increased the expected return relative to equilibrium. / "
        "BL后验将均衡收益与您的观点相结合。正向调整意味着模型相对于均衡提高了预期收益。"
    )


def _render_bl_efficient_frontier_comparison(
    mvo_frontier: pd.DataFrame,
    bl_frontier: pd.DataFrame,
    mvo_max_sharpe: Dict[str, Any],
    bl_max_sharpe: Dict[str, Any],
    mvo_random: pd.DataFrame,
    risk_free_rate: float = None,
) -> None:
    """
    Render side-by-side MVO vs BL efficient frontiers comparison chart.

    Args:
        mvo_frontier: MVO efficient frontier DataFrame.
        bl_frontier: BL efficient frontier DataFrame.
        mvo_max_sharpe: MVO max Sharpe portfolio.
        bl_max_sharpe: BL max Sharpe portfolio.
        mvo_random: Random portfolios.
        risk_free_rate: Annual risk-free rate for CAL computation (decimal).
    """
    st.markdown("### ↗ Efficient Frontier Comparison / 有效前沿对比")

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=mvo_random["volatility"] * 100.0,
        y=mvo_random["return"] * 100.0,
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

    fig.add_trace(go.Scatter(
        x=mvo_frontier["volatility"] * 100.0,
        y=mvo_frontier["return"] * 100.0,
        mode="lines",
        line=dict(color="#3B82F6", width=3),
        name="MVO Frontier / MVO前沿",
    ))

    fig.add_trace(go.Scatter(
        x=bl_frontier["volatility"] * 100.0,
        y=bl_frontier["return"] * 100.0,
        mode="lines",
        line=dict(color="#F59E0B", width=3, dash="dash"),
        name="BL Frontier / BL前沿",
    ))

    fig.add_trace(go.Scatter(
        x=[mvo_max_sharpe["volatility"] * 100.0],
        y=[mvo_max_sharpe["return"] * 100.0],
        mode="markers",
        marker=dict(size=16, color="#3B82F6", symbol="star"),
        name=f"MVO Max Sharpe ({mvo_max_sharpe['sharpe']:.2f})",
    ))

    fig.add_trace(go.Scatter(
        x=[bl_max_sharpe["volatility"] * 100.0],
        y=[bl_max_sharpe["return"] * 100.0],
        mode="markers",
        marker=dict(size=16, color="#F59E0B", symbol="star"),
        name=f"BL Max Sharpe ({bl_max_sharpe['sharpe']:.2f})",
    ))

    # Capital Allocation Lines for both MVO and BL tangency portfolios
    if risk_free_rate is not None:
        rf_pct = risk_free_rate * 100.0

        # Determine a common x-max for CAL extension
        all_vols = [
            mvo_frontier["volatility"].max() * 100.0,
            bl_frontier["volatility"].max() * 100.0,
            mvo_max_sharpe["volatility"] * 100.0,
            bl_max_sharpe["volatility"] * 100.0,
        ]
        cal_max_vol = max(all_vols) * 1.5

        # MVO CAL
        if mvo_max_sharpe.get("success", True):
            cal_rets_mvo = [rf_pct, rf_pct + mvo_max_sharpe["sharpe"] * cal_max_vol]
            fig.add_trace(go.Scatter(
                x=[0, cal_max_vol],
                y=cal_rets_mvo,
                mode="lines",
                line=dict(color="#3B82F6", width=1.5, dash="dot"),
                name=f"MVO CAL (Sharpe={mvo_max_sharpe['sharpe']:.2f})",
                hovertemplate="MVO CAL<br>Vol: %{x:.1f}%<br>Ret: %{y:.1f}%<extra></extra>",
            ))

        # BL CAL
        if bl_max_sharpe.get("success", True):
            cal_rets_bl = [rf_pct, rf_pct + bl_max_sharpe["sharpe"] * cal_max_vol]
            fig.add_trace(go.Scatter(
                x=[0, cal_max_vol],
                y=cal_rets_bl,
                mode="lines",
                line=dict(color="#F59E0B", width=1.5, dash="dot"),
                name=f"BL CAL (Sharpe={bl_max_sharpe['sharpe']:.2f})",
                hovertemplate="BL CAL<br>Vol: %{x:.1f}%<br>Ret: %{y:.1f}%<extra></extra>",
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
        "💡 The BL frontier shifts based on your views. If views are bullish, the frontier moves upward. "
        "The blue curve is MVO, the yellow dashed curve is BL. "
        "The dotted lines are **CALs** — the best possible risk-return tradeoffs using each tangency portfolio. / "
        "BL前沿根据您的观点移动。如果观点是看多的，前沿向上移动。蓝色曲线是 MVO，黄色虚线是 BL。"
        "点虚线是**资本配置线（CAL）**——使用各自切点组合的最优风险收益权衡。"
    )


def _render_bl_impact_analysis(bl_optimizer: BlackLittermanOptimizer) -> None:
    """
    Render bar chart showing return adjustment for each asset under BL.

    Args:
        bl_optimizer: BlackLittermanOptimizer instance.
    """
    st.markdown("### View Impact Analysis / 观点影响分析")

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

    colors = [
        "#10B981" if adj > 0 else "#EF4444"
        for adj in df["Adjustment / 调整"]
    ]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=df["Asset / 资产"],
        y=df["Adjustment / 调整"] * 100.0,
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

    fig.add_hline(y=0, line_dash="dash", line_color="#64748B")

    st.plotly_chart(fig, use_container_width=True, theme=None)

    st.caption(
        "💡 Green bars = BL increased expected return vs equilibrium. Red bars = BL decreased expected return. "
        "Larger bars = stronger view impact. / "
        "绿色柱 = BL相对于均衡提高了预期收益。红色柱 = BL降低了预期收益。柱子越大 = 观点影响越强。"
    )


def render() -> None:
    """
    Main render function for the Portfolio Optimizer page.
    Orchestrates the top-bar control console, optimization, and all visualizations.
    """
    st.title("Portfolio Optimizer")

    acknowledged = render_suitability_disclaimer("optimizer")

    if not acknowledged:
        st.info(
            "👆 **Please acknowledge the Suitability Disclaimer above to access "
            "the portfolio optimization tools.** / "
            "**请先确认上方的适配性免责声明以使用投资组合优化工具。**"
        )
        return

    # Render main-body controls console
    config = _render_top_controls()

    # Fixed bug: check config["opt_method"] instead of config["opt_mode"] to determine BL mode
    if config["opt_method"] == "Black-Litterman":
        st.markdown(
            "Black-Litterman Model: Combine market equilibrium with your investment views. "
            "Add your views below, then see how they affect optimal allocation. / "
            "Black-Litterman 模型：将市场均衡与您的投资观点相结合。在下方添加您的观点，然后查看它们如何影响最优配置。"
        )
    else:
        st.markdown(
            "Mean-Variance Optimization based on Markowitz's Modern Portfolio Theory. "
            "Select assets, configure parameters, and find the optimal allocation. / "
            "基于 Markowitz 现代投资组合理论的均值-方差优化。选择资产、配置参数，寻找最优配置。"
        )
    st.divider()

    if len(config["selected_keys"]) < 2:
        st.warning(
            "Please select at least 2 asset classes for optimization. / 请至少选择 2 个资产类别进行优化。"
        )
        return

    # Fetch data
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

    if len(returns) < 60:
        st.warning(
            f"Only {len(returns)} trading days of data available. "
            f"Results may be unreliable with insufficient data. / "
            f"仅有 {len(returns)} 个交易日的数据，数据不足可能导致结果不可靠。"
        )

    # Run optimization
    if config["opt_method"] == "Black-Litterman":
        views = _render_bl_views_input(returns.columns.tolist())

        if not views:
            st.warning(
                "Please add at least one view for Black-Litterman optimization. / 请添加至少一个观点以运行 Black-Litterman 优化。"
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

        if not results["selected"]["success"]:
            st.error(
                "❌ BL Optimization failed to converge. Try adjusting views or parameters. / BL 优化未能收敛，请尝试调整观点或参数。"
            )
            return

        _render_bl_returns_comparison(results["bl_optimizer"])
        _render_bl_efficient_frontier_comparison(
            results["mvo_frontier"],
            results["bl_frontier"],
            results["mvo_max_sharpe"],
            results["bl_max_sharpe"],
            results["mvo_random"],
            config["risk_free_rate"],
        )
        _render_bl_impact_analysis(results["bl_optimizer"])

        _render_selected_portfolio(
            results["selected"],
            title="Optimal Portfolio (BL Max Sharpe) / 最优组合（BL 最大夏普）",
            show_pie=False,
            show_sharpe_quality=False,
        )

    else:
        opt_method = config["opt_method"]

        if opt_method == "Resampled MVO (Michaud)":
            st.info(
                "🔄 **Resampled MVO (Michaud Method)**: Uses Monte Carlo simulation to "
                "reduce estimation error and produce more diversified portfolios. / "
                "**重抽样MVO（Michaud方法）**：使用蒙特卡洛模拟来减少估计误差，产生更多元化的投资组合。"
            )
        elif config.get("asset_class_constraints"):
            st.info(
                "📊 **Asset Class Constraints**: Portfolio weights are constrained to stay within specified ranges for each asset class. / "
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

        if not results["selected"]["success"]:
            st.error(
                "❌ Optimization failed to converge. Try adjusting constraints or selecting different assets. / 优化未能收敛，请尝试调整约束条件或选择不同的资产。"
            )
            return

        _render_efficient_frontier(results)
        selected = results["selected"]
        opt_mode = config["opt_mode"]
        _render_selected_portfolio(
            selected,
            title=f"Optimal Portfolio: {opt_mode} / 最优组合：{opt_mode}",
        )
        _render_asset_class_weights(results)
        _render_comparison_table(results)

    if config["opt_method"] == "Black-Litterman":
        _render_asset_universe(results["mvo_optimizer"])
    else:
        _render_asset_universe(results["optimizer"])

    st.caption(
        "💡 Data sourced from Yahoo Finance via yfinance. "
        "Optimization uses SciPy's SLSQP solver. / "
        "数据来自 Yahoo Finance（通过 yfinance）。优化使用 SciPy 的 SLSQP 求解器。"
    )
