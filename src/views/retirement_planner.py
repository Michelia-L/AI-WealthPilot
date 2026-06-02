"""
AI WealthPilot - Retirement Planner Page
AI WealthPilot - 退休规划器页面

Interactive Streamlit page for goal-based retirement planning using
Monte Carlo simulation. Users input their financial situation and
retirement goals, and the system simulates thousands of possible
outcomes to estimate the probability of a comfortable retirement.

交互式 Streamlit 页面，使用蒙特卡洛模拟进行基于目标的退休规划。
用户输入财务状况和退休目标，系统模拟数千种可能结果，
估算舒适退休的概率。

CFA Reference / CFA 参考:
    - CFA L3 Private Wealth Management: Goal-Based Planning
      CFA 三级私人财富管理：基于目标的规划
    - CFA L3: Monte Carlo simulation for retirement readiness assessment
      CFA 三级：使用蒙特卡洛模拟评估退休准备充足性
    - CFA L3: Human Capital vs Financial Capital framework
      CFA 三级：人力资本 vs 金融资本框架
"""

import streamlit as st
import pandas as pd
import numpy as np
from typing import Optional

# 导入蒙特卡洛模拟器 / Import Monte Carlo simulator
from src.portfolio.simulator import MonteCarloSimulator

# 导入可视化函数 / Import visualization functions
from src.visualization.charts import plot_monte_carlo_paths

# 导入配置 / Import configuration
from src.config import MONTE_CARLO_SIMULATIONS


def _render_sidebar() -> dict:
    """
    Render sidebar inputs for retirement planning parameters.
    渲染退休规划参数的侧栏输入。

    Groups inputs into three sections:
    将输入分为三组:
        1. Personal Info (个人信息): age, retirement age, life expectancy
        2. Financial Info (财务信息): current savings, annual savings, retirement income
        3. Market Assumptions (市场假设): expected return, volatility

    Returns:
        Dict with all user inputs.
        包含所有用户输入的字典。
    """
    st.sidebar.markdown("### 🎯 Retirement Settings")

    # --- 个人信息 / Personal Info ---
    st.sidebar.markdown("##### Personal / 个人信息")
    current_age = st.sidebar.number_input(
        "Current age / 当前年龄",
        min_value=18, max_value=80, value=30, step=1,
    )
    retirement_age = st.sidebar.number_input(
        "Target retirement age / 目标退休年龄",
        min_value=current_age + 1, max_value=100, value=60, step=1,
    )
    life_expectancy = st.sidebar.number_input(
        "Life expectancy / 预期寿命",
        min_value=retirement_age + 1, max_value=120, value=85, step=1,
        help="Consider family history and health status. / 考虑家族史和健康状况。",
    )

    # --- 财务信息 / Financial Info ---
    st.sidebar.markdown("##### Financial / 财务信息")
    current_savings = st.sidebar.number_input(
        "Current savings ($) / 当前储蓄",
        min_value=0, value=100_000, step=10_000, format="%d",
    )
    annual_savings = st.sidebar.number_input(
        "Annual savings ($) / 年度储蓄",
        min_value=0, value=50_000, step=5_000, format="%d",
        help="How much you save per year during working years. / 工作期间每年储蓄金额。",
    )
    desired_income = st.sidebar.number_input(
        "Desired retirement income ($/yr) / 退休后年收入",
        min_value=0, value=80_000, step=5_000, format="%d",
        help="Annual income needed during retirement (in today's dollars). / "
             "退休后每年需要的收入（以今日美元计）。",
    )

    # --- 市场假设 / Market Assumptions ---
    st.sidebar.markdown("##### Market Assumptions / 市场假设")
    expected_return_pct = st.sidebar.slider(
        "Expected annual return / 预期年收益率",
        min_value=2.0, max_value=15.0, value=7.0, step=0.5,
        format="%.1f%%",
        help="Long-term expected annualized return of your portfolio. "
             "A balanced portfolio typically returns 6-8%. / "
             "投资组合的长期预期年化收益率。平衡型组合通常在 6-8%。",
    )
    expected_return = expected_return_pct / 100.0

    volatility_pct = st.sidebar.slider(
        "Annual volatility / 年化波动率",
        min_value=5.0, max_value=30.0, value=15.0, step=0.5,
        format="%.1f%%",
        help="Annualized standard deviation of returns. "
             "A balanced portfolio typically has 10-15% volatility. / "
             "年化收益率标准差。平衡型组合通常在 10-15%。",
    )
    volatility = volatility_pct / 100.0

    # --- 模拟设置 / Simulation Settings ---
    st.sidebar.markdown("##### Simulation / 模拟设置")
    n_simulations = st.sidebar.select_slider(
        "Number of simulations / 模拟次数",
        options=[1_000, 5_000, 10_000, 50_000],
        value=10_000,
        help="More simulations = more stable estimates, but slower. / "
             "模拟次数越多，估计越稳定，但计算越慢。",
    )

    st.sidebar.divider()
    accum_years = retirement_age - current_age
    dist_years = life_expectancy - retirement_age
    st.sidebar.caption(
        f"📊 Accumulation: {accum_years} years · Distribution: {dist_years} years · "
        f"{n_simulations:,} paths"
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
    }


def _run_simulation(config: dict) -> dict:
    """
    Run the two-phase retirement Monte Carlo simulation.
    运行两阶段退休蒙特卡洛模拟。

    Phase 1 (Accumulation / 积累阶段):
        Client works and saves. Portfolio grows with contributions.
        客户工作并储蓄，组合随缴款增长。

    Phase 2 (Distribution / 分配阶段):
        Client retires and withdraws. Portfolio depletes over time.
        客户退休并提款，组合随时间消耗。

    Args:
        config: Dict with all planning parameters.
                包含所有规划参数的字典。

    Returns:
        Dict with simulation results.
        包含模拟结果的字典。
    """
    sim = MonteCarloSimulator(
        expected_return=config["expected_return"],
        volatility=config["volatility"],
        n_simulations=config["n_simulations"],
        seed=42,  # 固定种子以便复现 / Fixed seed for reproducibility
    )

    result = sim.retirement_planning(
        current_age=config["current_age"],
        retirement_age=config["retirement_age"],
        life_expectancy=config["life_expectancy"],
        current_savings=config["current_savings"],
        annual_savings=config["annual_savings"],
        desired_annual_income=config["desired_income"],
    )

    return result


def _render_summary_metrics(result: dict, config: dict) -> None:
    """
    Render the top-level summary metrics for the retirement plan.
    渲染退休规划的顶层摘要指标。

    Displays:
    展示:
        - Survival rate (存活率): probability portfolio lasts through retirement
        - Median terminal value at retirement (退休时中位终端值)
        - Accumulation / Distribution years (积累/分配年数)

    Args:
        result: Simulation result dict from _run_simulation.
                来自 _run_simulation 的模拟结果字典。
        config: User configuration dict.
                用户配置字典。
    """
    st.markdown("### 📊 Retirement Plan Summary / 退休规划摘要")

    survival_rate = result["survival_rate"]
    accum = result["accumulation"]

    # 四列布局 / Four-column layout
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        # 存活率颜色：>=85% 绿色，>=70% 黄色，<70% 红色
        # Survival rate color: >=85% green, >=70% yellow, <70% red
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

    # 存活率解读 / Survival rate interpretation
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


def _render_accumulation_paths(result: dict) -> None:
    """
    Render the accumulation phase Monte Carlo paths chart.
    渲染积累阶段的蒙特卡洛路径图。

    Shows thousands of simulated portfolio growth paths during
    the working years, with percentile bands and goal line.

    展示工作期间数千条模拟的组合增长路径，包含百分位带和目标线。

    Args:
        result: Simulation result dict.
                模拟结果字典。
    """
    st.markdown("### 📈 Accumulation Phase — Portfolio Growth / 积累阶段")

    accum = result["accumulation"]

    # 使用可视化函数绘制路径图 / Use visualization function for paths chart
    fig = plot_monte_carlo_paths(
        accum.paths,
        n_display=200,
        percentiles=True,
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

    # 百分位数统计表 / Percentile statistics table
    st.markdown("**Terminal Value Distribution at Retirement / 退休时终端值分布**")

    stats_data = {
        "Percentile / 百分位": [
            "5th (Pessimistic / 悲观)", "25th", "Median / 中位数",
            "75th", "95th (Optimistic / 乐观)", "Mean / 均值",
        ],
        "Portfolio Value ($) / 组合价值": [
            f"${accum.percentile_5:,.0f}",
            f"${accum.percentile_25:,.0f}",
            f"${accum.median_terminal:,.0f}",
            f"${accum.percentile_75:,.0f}",
            f"${accum.percentile_95:,.0f}",
            f"${accum.mean_terminal:,.0f}",
        ],
    }

    st.dataframe(
        pd.DataFrame(stats_data),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "💡 The **5th percentile** represents a pessimistic scenario (bad luck with returns). "
        "The **95th percentile** represents an optimistic scenario. "
        "Planning based on the median or 25th percentile is more conservative. / "
        "**第 5 百分位**代表悲观情景（收益较差）。"
        "**第 95 百分位**代表乐观情景。"
        "基于中位数或第 25 百分位做规划更为保守。"
    )

    st.divider()


def _render_distribution_analysis(result: dict, config: dict) -> None:
    """
    Render the distribution (retirement) phase analysis.
    渲染分配（退休）阶段分析。

    Shows the depletion paths during retirement and analyzes
    the risk of running out of money.

    展示退休期间的资金消耗路径，分析资金耗尽的风险。

    Args:
        result: Simulation result dict.
                模拟结果字典。
        config: User configuration dict.
                用户配置字典。
    """
    st.markdown("### 🏖️ Distribution Phase — Retirement Spending / 分配阶段")

    dist_paths = result["distribution_paths"]
    survival_rate = result["survival_rate"]

    # 绘制分配阶段路径 / Plot distribution phase paths
    fig = plot_monte_carlo_paths(
        dist_paths,
        n_display=200,
        percentiles=True,
        goal_amount=0,  # 零线表示资金耗尽 / Zero line = funds depleted
    )
    st.plotly_chart(fig, use_container_width=True, theme=None)

    # 分析资金耗尽的时间分布 / Analyze timing of fund depletion
    n_sims, n_periods = dist_paths.shape
    depletion_years = []

    for i in range(n_sims):
        path = dist_paths[i]
        # 找到第一条路径中资金首次变为 0 的年份
        # Find the first year where funds hit zero
        depleted = np.where(path <= 0)[0]
        if len(depleted) > 0:
            depletion_years.append(depleted[0])
        else:
            depletion_years.append(n_periods)  # Never depleted

    depletion_years = np.array(depletion_years)

    # 展示耗尽统计 / Display depletion statistics
    col1, col2, col3 = st.columns(3)

    with col1:
        never_depleted_pct = np.mean(depletion_years >= n_periods)
        st.metric(
            label="Never Depleted / 永不耗尽",
            value=f"{never_depleted_pct:.1%}",
        )

    with col2:
        # 在退休后 10 年内耗尽的比例
        # Fraction depleted within 10 years of retirement
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


def _render_sensitivity_analysis(config: dict) -> None:
    """
    Render sensitivity analysis — how changing savings rate affects survival.
    渲染敏感性分析 —— 储蓄率变化如何影响存活率。

    Shows a table of survival rates at different savings levels,
    helping the user understand how much they need to save.

    展示不同储蓄水平下的存活率表，帮助用户了解需要储蓄多少。

    Args:
        config: User configuration dict.
                用户配置字典。
    """
    st.markdown("### 🔍 Sensitivity Analysis / 敏感性分析")
    st.markdown(
        "**How does changing your annual savings affect the outcome? / "
        "改变年度储蓄金额如何影响结果？**"
    )

    # 测试不同的储蓄水平 / Test different savings levels
    base_savings = config["annual_savings"]
    savings_multipliers = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]

    results = []
    for mult in savings_multipliers:
        test_savings = int(base_savings * mult)
        sim = MonteCarloSimulator(
            expected_return=config["expected_return"],
            volatility=config["volatility"],
            n_simulations=5_000,  # 较少模拟次数以加快速度 / Fewer sims for speed
            seed=42,
        )
        test_result = sim.retirement_planning(
            current_age=config["current_age"],
            retirement_age=config["retirement_age"],
            life_expectancy=config["life_expectancy"],
            current_savings=config["current_savings"],
            annual_savings=test_savings,
            desired_annual_income=config["desired_income"],
        )

        is_current = " ⬅ Current" if mult == 1.0 else ""
        results.append({
            "Annual Savings / 年度储蓄": f"${test_savings:,}{is_current}",
            "Survival Rate / 存活率": f"{test_result['survival_rate']:.1%}",
            "Median at Retirement / 退休中位值": f"${test_result['accumulation'].median_terminal:,.0f}",
        })

    st.dataframe(
        pd.DataFrame(results),
        use_container_width=True,
        hide_index=True,
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
    退休规划器页面的主渲染函数。

    This function is called by the app router (src/app.py).
    It orchestrates user inputs, simulation, and all visualizations.

    本函数由应用路由（src/app.py）调用。
    它协调用户输入、模拟和所有可视化。

    Page layout / 页面布局:
        1. Sidebar: personal, financial, and market assumptions
           侧栏：个人信息、财务信息、市场假设
        2. Summary Metrics: survival rate, key numbers
           摘要指标：存活率、关键数字
        3. Accumulation Paths: Monte Carlo growth visualization
           积累路径：蒙特卡洛增长可视化
        4. Distribution Analysis: retirement spending simulation
           分配分析：退休支出模拟
        5. Sensitivity Analysis: impact of changing savings
           敏感性分析：储蓄变化的影响
    """
    # 页面标题 / Page title
    st.title("🎯 Retirement Planner")
    st.markdown(
        "Goal-based retirement planning using Monte Carlo simulation. "
        "Find out if your savings are on track for a comfortable retirement. / "
        "使用蒙特卡洛模拟的基于目标的退休规划。"
        "了解你的储蓄是否足以支撑舒适的退休生活。"
    )
    st.divider()

    # ====================================
    # 1. 侧栏输入 / Sidebar Inputs
    # ====================================
    config = _render_sidebar()

    # 基本输入校验 / Basic input validation
    if config["current_savings"] == 0 and config["annual_savings"] == 0:
        st.warning(
            "⚠️ Please enter your current savings or annual savings amount. / "
            "请输入当前储蓄或年度储蓄金额。"
        )
        return

    if config["desired_income"] == 0:
        st.warning(
            "⚠️ Please enter your desired retirement income. / "
            "请输入期望的退休收入。"
        )
        return

    # ====================================
    # 2. 运行模拟 / Run Simulation
    # ====================================
    with st.spinner("Running Monte Carlo simulation... / 正在运行蒙特卡洛模拟..."):
        result = _run_simulation(config)

    # ====================================
    # 3. 摘要指标 / Summary Metrics
    # ====================================
    _render_summary_metrics(result, config)

    # ====================================
    # 4. 积累阶段路径图 / Accumulation Paths
    # ====================================
    _render_accumulation_paths(result)

    # ====================================
    # 5. 分配阶段分析 / Distribution Analysis
    # ====================================
    _render_distribution_analysis(result, config)

    # ====================================
    # 6. 敏感性分析 / Sensitivity Analysis
    # ====================================
    _render_sensitivity_analysis(config)

    # 页脚 / Footer
    st.divider()
    st.caption(
        "💡 Simulation uses Geometric Brownian Motion (GBM) with annual time steps. "
        "Results are probabilistic estimates, not guarantees. "
        "Consult a financial advisor for personalized advice. / "
        "模拟使用几何布朗运动（GBM）和年度时间步长。"
        "结果是概率估计，非保证。请咨询财务顾问获取个性化建议。"
    )
