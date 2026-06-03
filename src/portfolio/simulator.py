"""
AI WealthPilot - Monte Carlo Simulator
AI WealthPilot - 蒙特卡洛模拟器

Simulates portfolio value paths using Geometric Brownian Motion (GBM)
to estimate goal-based planning outcomes, such as retirement readiness.
This is a core module for the "probability of success" approach to
financial planning — answering questions like "How likely am I to
have enough money to retire comfortably?"

使用几何布朗运动（GBM）模拟投资组合的未来价值路径，
用于估算基于目标的财务规划结果，例如退休准备充足性。
这是"成功概率"方法在财务规划中的核心模块——
回答诸如"我有多大概率拥有足够的钱舒适地退休？"等问题。

Key Concepts / 核心概念:
    Geometric Brownian Motion (GBM) / 几何布朗运动:
        dS = μS dt + σS dW
        Where / 其中:
        - S = portfolio value (组合价值)
        - μ = expected return / drift (预期收益率 / 漂移项)
        - σ = volatility (波动率)
        - W = Wiener process / Brownian motion (维纳过程 / 布朗运动)

    The discrete-time approximation used here / 离散时间近似:
        S_{t+1} = S_t × exp(μ - 0.5σ² + σZ)
        Where Z ~ N(0,1) / 其中 Z 服从标准正态分布

References / 参考文献:
    - CFA® Program Curriculum, Level III — Private Wealth Management
      CFA® 课程教材，三级 —— 私人财富管理
    - Monte Carlo Methods in Financial Engineering (Glasserman, 2003)
      金融工程中的蒙特卡洛方法（Glasserman, 2003）
    - CFA® Level III — Goal-Based Planning & Probability of Success
      CFA® 三级 —— 基于目标的规划与成功概率
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional

# 从项目配置中导入蒙特卡洛参数和年交易日数
# Import Monte Carlo parameters and trading days from project config
from src.config import MONTE_CARLO_SIMULATIONS, MONTE_CARLO_YEARS, TRADING_DAYS_PER_YEAR


@dataclass
class SimulationResult:
    """
    Container for Monte Carlo simulation results.
    蒙特卡洛模拟结果的数据容器。

    Uses Python's @dataclass for clean, immutable-style data storage.
    This makes it easy to pass simulation results between modules
    (e.g., from simulator to visualization, or to the AI advisor).

    使用 Python 的 @dataclass 实现简洁的数据存储。
    方便在模块间传递模拟结果（如从模拟器到可视化模块，或到 AI 顾问）。

    CFA Reference / CFA 参考:
        CFA L3 Private Wealth: Monte Carlo output is typically presented as
        a distribution of terminal wealth values, with key percentiles
        (5th, 25th, median, 75th, 95th) to help clients understand the
        range of possible outcomes.
        CFA 三级私人财富管理：蒙特卡洛的输出通常以终端财富值的分布呈现，
        包含关键百分位数（5th、25th、中位数、75th、95th），
        帮助客户理解可能结果的范围。
    """

    # 原始模拟路径：形状为 (模拟次数, 时间步数)
    # 每一行是一条独立的模拟路径，每一列是一个时间点
    # Raw simulation paths: shape (n_simulations, n_periods)
    # Each row is one independent simulation path, each column is a time step
    paths: np.ndarray

    # ====================================
    # 终端价值的汇总统计量
    # Summary statistics at the terminal period
    # ====================================

    # 所有模拟路径的终端值数组 / Array of terminal values from all simulation paths
    terminal_values: np.ndarray

    # 终端值的均值（受极端值影响较大）
    # Mean of terminal values (more sensitive to extreme outliers)
    mean_terminal: float

    # 终端值的中位数（更稳健，不受极端值影响）
    # Median of terminal values (more robust, not affected by outliers)
    median_terminal: float

    # 第 5 百分位数：悲观情景下的结果（95% 的情况优于此值）
    # 5th percentile: pessimistic scenario outcome (95% of cases are better)
    percentile_5: float

    # 第 25 百分位数：较差情景 / 25th percentile: below-average scenario
    percentile_25: float

    # 第 75 百分位数：较好情景 / 75th percentile: above-average scenario
    percentile_75: float

    # 第 95 百分位数：乐观情景下的结果（仅 5% 的情况优于此值）
    # 95th percentile: optimistic scenario outcome (only 5% of cases are better)
    percentile_95: float

    # ====================================
    # 基于目标的指标（Goal-Based Metrics）
    # ====================================

    # 目标金额（如退休储蓄目标）/ Goal amount (e.g., retirement savings target)
    goal_amount: Optional[float] = None

    # 成功概率 = 终端值 >= 目标金额的模拟路径占比
    # Probability of success = fraction of simulations where terminal value >= goal
    # CFA L3: This is the key output of goal-based planning
    # CFA 三级：这是基于目标的财务规划的核心输出指标
    probability_of_success: Optional[float] = None

    def summary(self) -> str:
        """
        Generate a human-readable summary of simulation results.
        生成模拟结果的可读性摘要。

        Returns:
            Formatted string with key statistics and goal metrics.
            包含关键统计量和目标指标的格式化字符串。
        """
        lines = [
            "Monte Carlo Simulation Results",
            f"  Simulations: {len(self.terminal_values):,}",
            f"  Mean terminal value: ${self.mean_terminal:,.0f}",
            f"  Median terminal value: ${self.median_terminal:,.0f}",
            f"  5th percentile: ${self.percentile_5:,.0f}",
            f"  95th percentile: ${self.percentile_95:,.0f}",
        ]
        # 如果设置了目标金额，显示目标和成功概率
        # If a goal amount was set, display the goal and probability of success
        if self.goal_amount is not None:
            lines.append(f"  Goal: ${self.goal_amount:,.0f}")
            lines.append(
                f"  Probability of success: {self.probability_of_success:.1%}"
            )
        return "\n".join(lines)


class MonteCarloSimulator:
    """
    Monte Carlo simulator for portfolio planning.
    用于投资组合规划的蒙特卡洛模拟器。

    Simulates future portfolio value paths using Geometric Brownian Motion (GBM),
    with optional periodic contributions (accumulation phase) and
    withdrawals (distribution/retirement phase).

    使用几何布朗运动（GBM）模拟未来的投资组合价值路径，
    支持可选的定期缴款（积累阶段）和提款（分配/退休阶段）。

    Why Monte Carlo? / 为什么使用蒙特卡洛？
        Deterministic projections (e.g., "assume 8% annual return") give a
        single, often misleading estimate. Monte Carlo generates thousands
        of possible scenarios based on the assumed return distribution,
        providing a probability-weighted range of outcomes.

        确定性预测（如"假设年收益率 8%"）只给出一个结果，往往具有误导性。
        蒙特卡洛基于假设的收益率分布生成数千种可能的情景，
        提供概率加权的结果范围。

    CFA Reference / CFA 参考:
        CFA L3 Private Wealth Management: Monte Carlo simulation is the
        standard tool for goal-based financial planning. It accounts for
        the uncertainty and path-dependency of investment returns,
        producing a "probability of success" metric that helps advisors
        set realistic expectations with clients.
        CFA 三级私人财富管理：蒙特卡洛模拟是基于目标的财务规划的标准工具。
        它考虑了投资收益的不确定性和路径依赖性，
        产生"成功概率"指标，帮助顾问与客户设定合理预期。
    """

    def __init__(
        self,
        expected_return: float,
        volatility: float,
        n_simulations: int = MONTE_CARLO_SIMULATIONS,
        n_years: int = MONTE_CARLO_YEARS,
        seed: Optional[int] = None,
    ):
        """
        Initialize the Monte Carlo simulator.
        初始化蒙特卡洛模拟器。

        Args:
            expected_return: Annualized expected return of the portfolio (e.g., 0.08 for 8%).
                             This is the drift parameter μ in the GBM model.
                             投资组合的年化预期收益率（如 0.08 表示 8%）。
                             这是 GBM 模型中的漂移参数 μ。
            volatility: Annualized volatility (standard deviation) of the portfolio
                        (e.g., 0.15 for 15%). This is the diffusion parameter σ in GBM.
                        投资组合的年化波动率（标准差）（如 0.15 表示 15%）。
                        这是 GBM 中的扩散参数 σ。
            n_simulations: Number of simulation paths to generate.
                           More paths = more stable probability estimates, but slower.
                           Typically 1,000 ~ 100,000 paths.
                           要生成的模拟路径数量。
                           路径越多概率估计越稳定，但计算越慢。通常 1,000 ~ 100,000 条。
            n_years: Number of years to simulate into the future.
                     模拟的未来年数。
            seed: Random seed for reproducibility. Set this to get the same
                  results every time (important for testing and debugging).
                  随机种子，用于结果可复现。设置后每次运行结果一致
                  （对测试和调试很重要）。
        """
        self.expected_return = expected_return
        self.volatility = volatility
        self.n_simulations = n_simulations
        self.n_years = n_years

        # 使用 numpy 的新式随机数生成器（比旧版 np.random 更高质量）
        # Use numpy's modern random number generator (higher quality than legacy np.random)
        self.rng = np.random.default_rng(seed)

    def simulate(
        self,
        initial_value: float,
        annual_contribution: float = 0,
        annual_withdrawal: float = 0,
        goal_amount: Optional[float] = None,
    ) -> SimulationResult:
        """
        Run the Monte Carlo simulation.
        运行蒙特卡洛模拟。

        Uses annual time steps with GBM for portfolio growth,
        plus deterministic cash flows (contributions/withdrawals).

        使用年度时间步长的 GBM 模拟投资组合增长，
        加上确定性现金流（缴款/提款）。

        The simulation formula at each time step / 每个时间步的模拟公式:
            V_{t+1} = V_t × exp(drift + σ × Z) + C - W

            Where / 其中:
            - V_t = portfolio value at time t (t 时刻的组合价值)
            - drift = μ - 0.5σ² (risk-adjusted drift, 风险调整后的漂移项)
            - σ = volatility (波动率)
            - Z ~ N(0,1) (standard normal random variable, 标准正态随机变量)
            - C = annual contribution (年度缴款)
            - W = annual withdrawal (年度提款)

        Why drift = μ - 0.5σ²? / 为什么漂移项 = μ - 0.5σ²？
            This is the "volatility drag" or "Jensen's inequality" adjustment.
            When you take the exponential of a normal random variable, the
            expected value of exp(X) ≠ exp(E[X]). The -0.5σ² correction ensures
            that E[exp(drift + σZ)] = exp(μ), i.e., the expected growth rate
            matches the assumed expected return.

            这是"波动率拖累"或"Jensen 不等式"调整。
            当对正态随机变量取指数时，exp(X) 的期望 ≠ exp(E[X])。
            -0.5σ² 的修正确保 E[exp(drift + σZ)] = exp(μ)，
            即预期增长率与假设的预期收益率一致。

        CFA Reference / CFA 参考:
            CFA L3: Monte Carlo simulations should use the geometric mean
            (compound) return, not the arithmetic mean, for multi-period
            projections. The -0.5σ² adjustment achieves this.
            CFA 三级：蒙特卡洛模拟在多期预测中应使用几何平均（复合）收益率，
            而非算术平均。-0.5σ² 的调整实现了这一点。

        Args:
            initial_value: Starting portfolio value (e.g., current savings).
                           初始投资组合价值（如当前储蓄金额）。
            annual_contribution: Annual addition to portfolio (e.g., savings during
                                 working years). Applied at the END of each year.
                                 每年新增缴款（如工作期间的年度储蓄）。在每年末计入。
            annual_withdrawal: Annual withdrawal from portfolio (e.g., retirement income).
                               Applied at the END of each year.
                               每年提款（如退休收入）。在每年末扣除。
            goal_amount: Target portfolio value for computing "probability of success".
                         If set, the result will include the percentage of simulations
                         that reach or exceed this goal.
                         目标组合价值，用于计算"成功概率"。
                         如果设置了，结果将包含达到或超过此目标的模拟比例。

        Returns:
            SimulationResult with all paths, terminal statistics, and goal metrics.
            包含所有路径、终端统计量和目标指标的 SimulationResult 对象。
        """
        n_periods = self.n_years

        # 初始化路径矩阵：形状 (模拟次数, 年数+1)
        # 第 0 列为初始值，后续列为每年末的组合价值
        # Initialize path matrix: shape (n_simulations, n_years + 1)
        # Column 0 = initial value, subsequent columns = portfolio value at each year-end
        paths = np.zeros((self.n_simulations, n_periods + 1))
        paths[:, 0] = initial_value

        # GBM 漂移项，已调整波动率拖累（Jensen 不等式修正）
        # drift = μ - 0.5σ²
        # GBM drift term, adjusted for volatility drag (Jensen's inequality correction)
        # Without this adjustment, the simulated mean return would OVERESTIMATE
        # the true compound return by approximately 0.5σ²
        # 如果不做此调整，模拟的平均收益率会高估真实复合收益率约 0.5σ²
        drift = self.expected_return - 0.5 * self.volatility**2

        for t in range(1, n_periods + 1):
            # 生成标准正态随机数（每条路径一个独立随机数）
            # Generate standard normal random numbers (one per simulation path)
            z = self.rng.standard_normal(self.n_simulations)

            # GBM 增长因子：exp(drift + σ × Z)
            # 这是对数正态分布的核心：收益率取对数后服从正态分布
            # GBM growth factor: exp(drift + σ × Z)
            # This is the heart of log-normal modeling: log-returns are normally distributed
            growth = np.exp(drift + self.volatility * z)

            # 更新组合价值：上期价值 × 增长因子 + 缴款 - 提款
            # Update portfolio value: previous value × growth + contributions - withdrawals
            paths[:, t] = paths[:, t - 1] * growth + annual_contribution - annual_withdrawal

            # 组合价值不能为负（最低为零，表示资金耗尽）
            # Portfolio value cannot be negative (floor at zero = funds depleted)
            paths[:, t] = np.maximum(paths[:, t], 0)

        # 提取所有模拟路径的终端值（最后一年的组合价值）
        # Extract terminal values from all simulation paths (portfolio value at final year)
        terminal = paths[:, -1]

        # 汇总统计量并构建结果对象
        # Aggregate statistics and build the result object
        result = SimulationResult(
            paths=paths,
            terminal_values=terminal,
            mean_terminal=float(np.mean(terminal)),
            median_terminal=float(np.median(terminal)),
            # 百分位数用于描述结果的分布范围
            # Percentiles describe the range of outcome distribution
            percentile_5=float(np.percentile(terminal, 5)),     # 悲观 / pessimistic
            percentile_25=float(np.percentile(terminal, 25)),   # 较差 / below average
            percentile_75=float(np.percentile(terminal, 75)),   # 较好 / above average
            percentile_95=float(np.percentile(terminal, 95)),   # 乐观 / optimistic
            goal_amount=goal_amount,
            # 成功概率 = 终端值 >= 目标的路径比例
            # Probability of success = fraction of paths where terminal >= goal
            probability_of_success=(
                float(np.mean(terminal >= goal_amount))
                if goal_amount is not None
                else None
            ),
        )

        return result

    def retirement_planning(
        self,
        current_age: int,
        retirement_age: int,
        life_expectancy: int,
        current_savings: float,
        annual_savings: float,
        desired_annual_income: float,
        inflation_rate: float = 0.025,
    ) -> dict:
        """
        Two-phase retirement simulation — the cornerstone of wealth management planning.
        两阶段退休模拟 —— 财富管理规划的基石。

        Phase 1 — Accumulation (积累阶段):
            From current age to retirement age.
            During this phase, the client is working and contributing to the portfolio.
            从当前年龄到退休年龄。
            在此阶段，客户工作并持续向组合缴款。

        Phase 2 — Distribution (分配阶段):
            From retirement age to life expectancy.
            During this phase, the client withdraws from the portfolio for living expenses.
            从退休年龄到预期寿命。
            在此阶段，客户从组合中提款用于生活开支。

        The key output is the "survival rate" — the probability that the
        portfolio never runs out of money during retirement.

        核心输出是"存活率"—— 退休期间组合资金永不耗尽的概率。

        CFA Reference / CFA 参考:
            CFA L3 Private Wealth — Retirement Planning:
            - Human Capital vs Financial Capital: During accumulation, human capital
              (future earning ability) is high and financial capital is growing.
              In distribution, human capital is zero and financial capital is
              being consumed.
            - 人力资本 vs 金融资本：积累阶段，人力资本（未来赚钱能力）高，
              金融资本在增长。分配阶段，人力资本为零，金融资本被消耗。
            - Mortality Risk: The risk of outliving one's assets ("longevity risk")
              is a key concern. Monte Carlo simulation is the standard tool
              to quantify this risk.
            - 长寿风险：资产先于人耗尽的风险是核心关注点。
              蒙特卡洛模拟是量化这一风险的标准工具。

        Args:
            current_age: Client's current age (e.g., 30).
                         客户当前年龄（如 30 岁）。
            retirement_age: Target retirement age (e.g., 60).
                            目标退休年龄（如 60 岁）。
            life_expectancy: Expected lifespan (e.g., 85).
                             This should account for family history and health.
                             预期寿命（如 85 岁）。应考虑家族史和健康状况。
            current_savings: Current portfolio value in dollars.
                             当前投资组合价值（美元）。
            annual_savings: Annual savings amount during accumulation phase.
                            积累阶段的年度储蓄金额。
            desired_annual_income: Annual income needed during retirement (in today's dollars).
                                   退休期间每年需要的收入（以今日美元计）。
            inflation_rate: Annual inflation rate to adjust retirement withdrawals (e.g., 0.025).
                            年度通货膨胀率，用于调整退休后的年度提款名义值。

        Returns:
            Dict with / 返回字典，包含:
            - 'accumulation': SimulationResult for the accumulation phase
              积累阶段的模拟结果
            - 'distribution_paths': numpy array of distribution phase paths
              分配阶段的路径数组
            - 'survival_rate': probability of portfolio never depleting
              组合永不耗尽的概率
            - 'accumulation_years': number of years in accumulation
              积累阶段年数
            - 'distribution_years': number of years in distribution
              分配阶段年数
        """
        # ============================================================
        # Phase 1: Accumulation (积累阶段)
        # 客户工作并持续储蓄，组合以原始预期收益率增长
        # Client works and saves, portfolio grows at original expected return
        # ============================================================
        accum_years = retirement_age - current_age
        accum_sim = MonteCarloSimulator(
            expected_return=self.expected_return,
            volatility=self.volatility,
            n_simulations=self.n_simulations,
            n_years=accum_years,
            # 使用当前 rng 生成新种子，确保可复现性
            # Generate a new seed from current rng to maintain reproducibility
            seed=self.rng.integers(0, 2**31),
        )
        accum_result = accum_sim.simulate(
            initial_value=current_savings,
            annual_contribution=annual_savings,
        )

        # ============================================================
        # Phase 2: Distribution (分配阶段)
        # 退休后，采用更保守的投资策略（降低预期收益和波动率各 30%）
        # After retirement, adopt a more conservative strategy
        # (reduce expected return and volatility by 30% each)
        # ============================================================
        # CFA L3 理由：退休后风险承受能力下降（人力资本为零），
        # 应转向更保守的资产配置（更多债券、更少股票）
        # CFA L3 rationale: Risk tolerance decreases after retirement
        # (human capital = 0), should shift to more conservative allocation
        # (more bonds, fewer equities)
        dist_years = life_expectancy - retirement_age
        dist_sim = MonteCarloSimulator(
            expected_return=self.expected_return * 0.7,  # 更保守 / More conservative
            volatility=self.volatility * 0.7,
            n_simulations=self.n_simulations,
            n_years=dist_years,
            seed=self.rng.integers(0, 2**31),
        )

        # 分配阶段的初始值 = 积累阶段每条路径 of terminal values
        dist_paths = np.zeros((self.n_simulations, dist_years + 1))
        dist_paths[:, 0] = accum_result.terminal_values

        # 分配阶段的 GBM 漂移项（使用保守化后的参数）
        # Distribution phase GBM drift (using conservative parameters)
        drift = (self.expected_return * 0.7) - 0.5 * (self.volatility * 0.7) ** 2
        rng = np.random.default_rng(self.rng.integers(0, 2**31))

        for t in range(1, dist_years + 1):
            z = rng.standard_normal(self.n_simulations)
            growth = np.exp(drift + self.volatility * 0.7 * z)
            
            # Adjust the desired annual income (today's dollars) for inflation.
            # The number of inflation years is: accumulation years + current retirement year (t)
            # Formula: Nominal Withdrawal = Real Income * (1 + inflation_rate) ^ (T_accum + t)
            # 公式：名义提取额 = 实际收入 * (1 + 通胀率) ^ (积累期 + 当前退休期t)
            inflation_factor = (1.0 + inflation_rate) ** (accum_years + t)
            nominal_withdrawal = desired_annual_income * inflation_factor

            # 每年：组合增长后减去名义年度提款
            # Each year: portfolio grows then subtract inflation-adjusted annual withdrawal
            dist_paths[:, t] = dist_paths[:, t - 1] * growth - nominal_withdrawal
            # 组合价值不能为负 / Portfolio value cannot be negative
            dist_paths[:, t] = np.maximum(dist_paths[:, t], 0)

        # ============================================================
        # 计算存活率：退休期间组合价值始终 > 0 的路径占比
        # Calculate survival rate: fraction of paths where portfolio stays > 0
        # throughout the entire distribution phase
        # ============================================================
        # np.all(..., axis=1): 检查每条路径的所有时间点是否都 > 0
        # np.all(..., axis=1): check if ALL time points in each path are > 0
        never_depleted = np.all(dist_paths > 0, axis=1)

        # 存活率 = 永不耗尽的路径数 / 总路径数
        # Survival rate = number of never-depleted paths / total paths
        # CFA L3: 一般建议存活率 >= 85%-90% 才是可接受的退休计划
        # CFA L3: Generally, a survival rate >= 85%-90% is considered acceptable
        survival_rate = float(np.mean(never_depleted))

        return {
            "accumulation": accum_result,
            "distribution_paths": dist_paths,
            "survival_rate": survival_rate,
            "accumulation_years": accum_years,
            "distribution_years": dist_years,
        }


# ==========================================
# 主程序入口 - 退休规划模拟演示
# Main entry point - Retirement planning simulation demo
# ==========================================
if __name__ == "__main__":
    # 演示场景：一位 30 岁的投资者规划退休
    # Demo scenario: A 30-year-old investor planning for retirement
    # - 预期年收益率 8%（中等风险股债混合组合）
    # - Expected annual return 8% (moderate risk stock-bond portfolio)
    # - 年化波动率 15%
    # - Annualized volatility 15%
    # - 模拟 10,000 条路径以获得稳定的概率估计
    # - 10,000 simulation paths for stable probability estimates
    sim = MonteCarloSimulator(
        expected_return=0.08,
        volatility=0.15,
        n_simulations=10000,
        seed=42,  # 固定种子以便复现结果 / Fixed seed for reproducibility
    )

    # 退休规划参数 / Retirement planning parameters:
    # - 当前 30 岁，计划 60 岁退休，预期活到 85 岁
    # - Age 30, plan to retire at 60, expect to live to 85
    # - 当前储蓄 10 万美元，每年新增储蓄 5 万美元
    # - Current savings $100,000, annual savings $50,000
    # - 退休后每年需要 20 万美元生活费
    # - Need $200,000/year in retirement income
    result = sim.retirement_planning(
        current_age=30,
        retirement_age=60,
        life_expectancy=85,
        current_savings=100000,
        annual_savings=50000,
        desired_annual_income=200000,
    )

    print("=== Retirement Planning Simulation ===")
    print(f"Accumulation phase: {result['accumulation_years']} years")
    print(result["accumulation"].summary())
    print(f"\nDistribution phase: {result['distribution_years']} years")
    # 存活率是最关键的输出：退休期间资金不耗尽的概率
    # Survival rate is the most critical output: probability of not running out of money
    print(f"Portfolio survival rate: {result['survival_rate']:.1%}")
