"""
AI WealthPilot - Retirement Planner Page

Interactive Streamlit page for goal-based retirement planning using
Monte Carlo simulation. Users input their financial situation and
retirement goals, and the system simulates thousands of possible
outcomes to estimate the probability of a comfortable retirement.

CFA References:
- CFA L3 Private Wealth Management: Goal-Based Planning.
- CFA L3: Monte Carlo simulation for retirement readiness assessment.
- CFA L3: Human Capital vs Financial Capital framework.
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

# Import Monte Carlo simulator
from src.portfolio.simulator import MonteCarloSimulator

# Import visualization functions
from src.visualization.charts import plot_monte_carlo_paths

# Import configuration
from src.config import MONTE_CARLO_SIMULATIONS
from src.views.compliance import render_suitability_disclaimer


def _render_top_controls() -> Dict[str, Any]:
    """
    Render retirement planning controls in the main page body using a premium expander.
    
    Returns:
        Dict with all retirement parameters.
    """
    # Note: .premium-console CSS is now injected globally via styles.py
    
    with st.expander("🛠️ Adjust Retirement Parameters / 调整退休规划参数", expanded=True):
        col1, col2, col3 = st.columns([1, 1, 1])
        
        with col1:
            st.markdown("##### 👤 Personal Info / 个人信息")
            current_age = st.number_input(
                "Current age / 当前年龄",
                min_value=18, max_value=80, value=30, step=1,
                key="ret_current_age"
            )
            retirement_age = st.number_input(
                "Target retirement age / 目标退休年龄",
                min_value=current_age + 1, max_value=100, value=60, step=1,
                key="ret_retirement_age"
            )
            life_expectancy = st.number_input(
                "Life expectancy / 预期寿命",
                min_value=retirement_age + 1, max_value=120, value=85, step=1,
                help="Consider family history and health status. / 考虑家族史和健康状况。",
                key="ret_life_expectancy"
            )
            
        with col2:
            st.markdown("##### 💰 Financial Info / 财务及储蓄")
            current_savings = st.number_input(
                "Current savings ($) / 当前储蓄",
                min_value=0, value=100_000, step=10_000, format="%d",
                key="ret_current_savings"
            )
            annual_savings = st.number_input(
                "Annual savings ($) / 年度储蓄",
                min_value=0, value=50_000, step=5_000, format="%d",
                help="How much you save per year during working years. / 工作期间每年储蓄金额。",
                key="ret_annual_savings"
            )
            desired_income = st.number_input(
                "Desired retirement income ($/yr) / 退休后年收入",
                min_value=0, value=80_000, step=5_000, format="%d",
                help="Annual income needed during retirement (in today's dollars). / 退休后每年需要的收入（以今日美元计）。",
                key="ret_desired_income"
            )
            inflation_rate_pct = st.number_input(
                "Expected annual inflation (%) / 预期年通胀率",
                min_value=0.0, max_value=10.0, value=2.5, step=0.1,
                help="Annual inflation rate to adjust retirement withdrawals (e.g., 2.5%). / 年度通货膨胀率，用于调整退休提取名义金额。",
                key="ret_inflation_rate"
            )
            inflation_rate = inflation_rate_pct / 100.0
            
        with col3:
            st.markdown("##### 📈 Assumptions & Sim / 假设与模拟")
            expected_return_pct = st.slider(
                "Expected annual return / 预期年收益率",
                min_value=2.0, max_value=15.0, value=7.0, step=0.5,
                format="%.1f%%",
                help="Long-term expected annualized return of your portfolio. A balanced portfolio typically returns 6-8%. / 投资组合的长期预期年化收益率。平衡型组合通常在 6-8%。",
                key="ret_expected_return"
            )
            expected_return = expected_return_pct / 100.0

            volatility_pct = st.slider(
                "Annual volatility / 年化波动率",
                min_value=5.0, max_value=30.0, value=15.0, step=0.5,
                format="%.1f%%",
                help="Annualized standard deviation of returns. A balanced portfolio typically has 10-15% volatility. / 年化收益率标准差。平衡型组合通常在 10-15%。",
                key="ret_volatility"
            )
            volatility = volatility_pct / 100.0

            n_simulations = st.select_slider(
                "Number of simulations / 模拟次数",
                options=[1_000, 5_000, 10_000, 50_000],
                value=10_000,
                help="More simulations = more stable estimates, but slower. / 模拟次数越多，估计越稳定，但计算越慢。",
                key="ret_n_simulations"
            )
            
        accum_years = retirement_age - current_age
        dist_years = life_expectancy - retirement_age
        
        st.markdown(
            f'<div style="text-align: right; color: #94A3B8; font-size: 0.85rem; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.05);">'
            f'🎯 <b>Accumulation:</b> {accum_years} years &nbsp;|&nbsp; <b>Distribution:</b> {dist_years} years &nbsp;|&nbsp; <b>Paths:</b> {n_simulations:,}'
            f'</div>',
            unsafe_allow_html=True
        )

    return {
        "current_age": current_age,
        "retirement_age": retirement_age,
        "life_expectancy": life_expectancy,
        "current_savings": current_savings,
        "annual_savings": annual_savings,
        "desired_income": desired_income,
        "expected_return": expected_return,
        "volatility": volatility,
        "n_simulations": n_simulations,
        "inflation_rate": inflation_rate,
    }


def _run_simulation(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the two-phase retirement Monte Carlo simulation.

    Phase 1 (Accumulation):
        Client works and saves. Portfolio grows with contributions and market returns.
        Formula: V_t = V_{t-1} * (1 + R_t) + Contribution
    
    Phase 2 (Distribution):
        Client retires and withdraws. Portfolio depletes with withdrawals and market returns.
        Formula: V_t = (V_{t-1} - Withdrawal) * (1 + R_t)

    Args:
        config: Dict with all planning parameters.

    Returns:
        Dict with simulation results.
    """
    sim = MonteCarloSimulator(
        expected_return=config["expected_return"],
        volatility=config["volatility"],
        n_simulations=config["n_simulations"],
        seed=42,  # Fixed seed for reproducibility
    )

    result = sim.retirement_planning(
        current_age=config["current_age"],
        retirement_age=config["retirement_age"],
        life_expectancy=config["life_expectancy"],
        current_savings=config["current_savings"],
        annual_savings=config["annual_savings"],
        desired_annual_income=config["desired_income"],
        inflation_rate=config["inflation_rate"],
    )

    return result


def _render_summary_metrics(result: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    Render the top-level summary metrics for the retirement plan.

    Args:
        result: Simulation result dict from _run_simulation.
        config: User configuration dict.
    """
    st.markdown("### Retirement Plan Summary / 退休规划摘要")

    survival_rate = result["survival_rate"]
    accum = result["accumulation"]

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # Survival rate bounds: >=85% green, >=70% yellow, <70% red
        if survival_rate >= 0.85:
            delta_color = "normal"
            status = "On Track / 状态良好"
        elif survival_rate >= 0.70:
            delta_color = "normal"
            status = "Caution / 需注意"
        else:
            delta_color = "inverse"
            status = "At Risk / 有风险"

        st.metric(
            label="Survival Rate / 存活率",
            value=f"{survival_rate:.1%}",
            delta=status,
            delta_color=delta_color,
        )

    with col2:
        st.metric(
            label="Median at Retirement / 退休时中位值",
            value=f"${accum.median_terminal:,.0f}",
        )

    with col3:
        st.metric(
            label="Accumulation Phase / 积累阶段",
            value=f"{result['accumulation_years']} years / 年",
        )

    with col4:
        st.metric(
            label="Distribution Phase / 分配阶段",
            value=f"{result['distribution_years']} years / 年",
        )

    # Detailed survival rate text
    if survival_rate >= 0.90:
        st.success(
            f"✅ Your portfolio has a **{survival_rate:.1%}** probability of lasting "
            f"through retirement. This is considered a strong plan. / "
            f"你的组合有 **{survival_rate:.1%}** 的概率支撑整个退休期。这是一个稳健的计划。"
        )
    elif survival_rate >= 0.75:
        st.warning(
            f"⚠️ Your portfolio has a **{survival_rate:.1%}** survival rate. "
            f"Consider increasing savings or adjusting retirement expectations. / "
            f"你的组合存活率为 **{survival_rate:.1%}**。"
            f"建议增加储蓄或调整退休预期。"
        )
    else:
        st.error(
            f"🚨 Your portfolio has only a **{survival_rate:.1%}** survival rate. "
            f"Significant changes are needed — consider saving more, retiring later, "
            f"or reducing retirement income needs. / "
            f"你的组合存活率仅 **{survival_rate:.1%}**。需要重大调整——"
            f"考虑增加储蓄、延迟退休或降低退休收入需求。"
        )

    st.divider()


def _render_accumulation_paths(result: Dict[str, Any]) -> None:
    """
    Render the accumulation phase Monte Carlo paths chart.

    Args:
        result: Simulation result dict.
    """
    st.markdown("### ↗ Accumulation Phase — Portfolio Growth / 积累阶段")

    accum = result["accumulation"]

    # Generate paths chart
    fig = plot_monte_carlo_paths(
        accum.paths,
        n_display=200,
        percentiles=True,
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

    st.markdown("**Terminal Value Distribution at Retirement / 退休时终端值分布**")

    stats_data = {
        "Percentile / 百分位": [
            "5th (Pessimistic / 悲观)", "25th", "Median / 中位数",
            "75th", "95th (Optimistic / 乐观)", "Mean / 均值",
        ],
        "Portfolio Value ($) / 组合价值": [
            accum.percentile_5,
            accum.percentile_25,
            accum.median_terminal,
            accum.percentile_75,
            accum.percentile_95,
            accum.mean_terminal,
        ],
    }

    st.dataframe(
        pd.DataFrame(stats_data),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Portfolio Value ($) / 组合价值": st.column_config.NumberColumn(
                format="$%,.0f"
            )
        }
    )

    st.caption(
        "💡 The 5th percentile represents a pessimistic scenario (bad luck with returns). "
        "The 95th percentile represents an optimistic scenario. "
        "Planning based on the median or 25th percentile is more conservative. / "
        "第 5 百分位代表悲观情景（收益较差）。"
        "第 95 百分位代表乐观情景。"
        "基于中位数或第 25 百分位做规划更为保守。"
    )

    st.divider()


def _render_distribution_analysis(result: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    Render the distribution (retirement) phase analysis.

    Args:
        result: Simulation result dict.
        config: User configuration dict.
    """
    st.markdown("### Distribution Phase — Retirement Spending / 分配阶段")

    dist_paths = result["distribution_paths"]

    # Plot distribution phase paths
    fig = plot_monte_carlo_paths(
        dist_paths,
        n_display=200,
        percentiles=True,
        goal_amount=0,  # Zero represents running out of money
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

    # Analyze timing of fund depletion
    n_sims, n_periods = dist_paths.shape
    depletion_years = []

    for i in range(n_sims):
        path = dist_paths[i]
        depleted = np.where(path <= 0)[0]
        if len(depleted) > 0:
            depletion_years.append(depleted[0])
        else:
            depletion_years.append(n_periods)  # Never depleted

    depletion_years = np.array(depletion_years)

    col1, col2, col3 = st.columns(3)

    with col1:
        never_depleted_pct = np.mean(depletion_years >= n_periods)
        st.metric(
            label="Never Depleted / 永不耗尽",
            value=f"{never_depleted_pct:.1%}",
        )

    with col2:
        early_depletion = np.mean(depletion_years <= 10)
        st.metric(
            label="Depleted in ≤10 years / 10年内耗尽",
            value=f"{early_depletion:.1%}",
        )

    with col3:
        median_depletion = np.median(depletion_years[depletion_years < n_periods])
        if len(depletion_years[depletion_years < n_periods]) > 0:
            st.metric(
                label="Median depletion year / 中位耗尽年份",
                value=f"Year {median_depletion:.0f}",
            )
        else:
            st.metric(
                label="Median depletion year / 中位耗尽年份",
                value="N/A (all survived)",
            )

    st.divider()


def _render_sensitivity_analysis(config: Dict[str, Any]) -> None:
    """
    Render sensitivity analysis showing how changing savings rate affects survival rate.

    Args:
        config: User configuration dict.
    """
    st.markdown("### Sensitivity Analysis / 敏感性分析")
    st.markdown(
        "**How does changing your annual savings affect the outcome? / "
        "改变年度储蓄金额如何影响结果？**"
    )

    # Evaluate multiple savings scenarios
    base_savings = config["annual_savings"]
    savings_multipliers = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

    results = []
    for mult in savings_multipliers:
        test_savings = int(base_savings * mult)
        sim = MonteCarloSimulator(
            expected_return=config["expected_return"],
            volatility=config["volatility"],
            n_simulations=5_000,  # Fewer simulations for speed
            seed=42,
        )
        test_result = sim.retirement_planning(
            current_age=config["current_age"],
            retirement_age=config["retirement_age"],
            life_expectancy=config["life_expectancy"],
            current_savings=config["current_savings"],
            annual_savings=test_savings,
            desired_annual_income=config["desired_income"],
            inflation_rate=config["inflation_rate"],
        )

        is_current = " ⬅ Current" if mult == 1.0 else ""
        results.append({
            "Annual Savings / 年度储蓄": f"${test_savings:,}{is_current}",
            "Survival Rate / 存活率": test_result['survival_rate'] * 100.0,
            "Median at Retirement / 退休中位值": test_result['accumulation'].median_terminal,
        })

    st.dataframe(
        pd.DataFrame(results),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Survival Rate / 存活率": st.column_config.NumberColumn(
                format="%.1f%%"
            ),
            "Median at Retirement / 退休中位值": st.column_config.NumberColumn(
                format="$%,.0f"
            ),
        }
    )

    st.caption(
        "💡 This analysis shows how your survival rate changes with different savings levels. "
        "A common rule of thumb is to save at least 15-20% of gross income. / "
        "此分析展示不同储蓄水平下存活率的变化。"
        "一个常见经验法则是至少储蓄税前收入的 15-20%。"
    )


def render() -> None:
    """
    Main render function for the Retirement Planner page.
    Orchestrates user inputs, simulation, and all visualizations.
    """
    st.title("Retirement Planner")
    st.markdown(
        "Goal-based retirement planning using Monte Carlo simulation. "
        "Find out if your savings are on track for a comfortable retirement. / "
        "使用蒙特卡洛模拟的基于目标的退休规划。"
        "了解你的储蓄是否足以支撑舒适的退休生活。"
    )
    st.divider()

    acknowledged = render_suitability_disclaimer("retirement")

    if not acknowledged:
        st.info(
            "👆 **Please acknowledge the Suitability Disclaimer above to access "
            "the retirement simulation tools.** / "
            "**请先确认上方的适配性免责声明以使用退休模拟工具。**"
        )
        return

    # 1. Controls Console in Main Page Body
    config = _render_top_controls()

    # Basic input validation
    if config["current_savings"] == 0 and config["annual_savings"] == 0:
        st.warning(
            "Please enter your current savings or annual savings amount. / "
            "请输入当前储蓄或年度储蓄金额。"
        )
        return

    if config["desired_income"] == 0:
        st.warning(
            "Please enter your desired retirement income. / "
            "请输入期望的退休收入。"
        )
        return

    # 2. Run Simulation
    with st.spinner("Running Monte Carlo simulation... / 正在运行蒙特卡洛模拟..."):
        result = _run_simulation(config)

    # 3. Summary Metrics
    _render_summary_metrics(result, config)

    # 4. Accumulation Paths Chart
    _render_accumulation_paths(result)

    # 5. Distribution Analysis
    _render_distribution_analysis(result, config)

    # 6. Sensitivity Analysis
    _render_sensitivity_analysis(config)

    # Footer
    st.divider()
    st.caption(
        "💡 Simulation uses Geometric Brownian Motion (GBM) with annual time steps. "
        "Results are probabilistic estimates, not guarantees. "
        "Consult a financial advisor for personalized advice. / "
        "模拟使用几何布朗运动（GBM）和年度时间步长。"
        "结果是概率估计，非保证。请咨询财务顾问获取个性化建议。"
    )
