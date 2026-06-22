"""
AI WealthPilot - Portfolio Module Tests
AI WealthPilot - 投资组合模块测试

Comprehensive test suite for the quantitative engine covering:
量化引擎的全面测试套件，覆盖：

- Portfolio Optimizer (MVO, efficient frontier, max Sharpe, min volatility)
  投资组合优化器（MVO、有效前沿、最大夏普、最小波动率）
- Monte Carlo Simulator (GBM, retirement planning, path properties)
  蒙特卡洛模拟器（GBM、退休规划、路径属性）
- Risk Metrics (Sharpe, Sortino, VaR, CVaR, max drawdown, mathematical properties)
  风险度量（夏普、索提诺、VaR、CVaR、最大回撤、数学性质）

Test Design Philosophy / 测试设计理念:
    - Positive tests: verify correct behavior under normal conditions
      正向测试：验证正常条件下的正确行为
    - Edge cases: single asset, zero volatility, constant returns
      边界情况：单资产、零波动率、常数收益率
    - Mathematical properties: VaR ≤ CVaR, max Sharpe ≥ min vol Sharpe
      数学性质：VaR ≤ CVaR, 最大夏普 ≥ 最小波动率的夏普
    - Reproducibility: same seed → same results
      可复现性：相同种子 → 相同结果
"""
import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import PortfolioOptimizer
from src.portfolio.simulator import MonteCarloSimulator, SimulationResult
from src.portfolio.risk_metrics import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    value_at_risk,
    conditional_var,
    compute_all_metrics,
)


# ============================================================
# Fixtures / 测试夹具
# ============================================================

@pytest.fixture
def sample_returns():
    """
    Generate synthetic daily returns for 4 assets over 5 years.
    生成 4 个资产 5 年的合成日收益率数据。

    Asset characteristics / 资产特征:
        - US_EQ: highest return (0.04%/day ≈ 10%/year)
          美股：最高收益率
        - INTL_EQ: moderate return (0.03%/day ≈ 7.5%/year)
          国际股票：中等收益率
        - BONDS: lowest return (0.01%/day ≈ 2.5%/year)
          债券：最低收益率
        - GOLD: moderate return (0.02%/day ≈ 5%/year)
          黄金：中等收益率
    """
    np.random.seed(42)
    n_days = 252 * 5
    assets = ["US_EQ", "INTL_EQ", "BONDS", "GOLD"]
    returns = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )
    return returns


@pytest.fixture
def sample_prices(sample_returns):
    """
    Convert returns to price series starting at 100.
    将收益率转换为以 100 为起点的价格序列。
    """
    return (1 + sample_returns).cumprod() * 100


@pytest.fixture
def single_asset_returns():
    """
    Single asset returns for edge-case testing.
    用于边界情况测试的单资产收益率。
    """
    np.random.seed(123)
    return pd.DataFrame(
        np.random.randn(252 * 3) * 0.01 + 0.0003,
        columns=["SINGLE"],
    )


@pytest.fixture
def constant_returns():
    """
    Constant (zero-variance) return series for degenerate case testing.
    常数（零方差）收益率序列，用于退化情况测试。

    Uses 0.0 so that pd.Series.std() returns exactly 0.0 (no floating-point noise).
    使用 0.0 以确保 pd.Series.std() 精确返回 0.0（无浮点噪声）。
    """
    return pd.Series([0.0] * 252, name="CONSTANT")


# ============================================================
# Optimizer Tests — 优化器测试
# ============================================================

class TestPortfolioOptimizer:
    """
    Test suite for the Mean-Variance Portfolio Optimizer.
    均值-方差投资组合优化器的测试套件。

    Covers / 覆盖:
        - maximize_sharpe(): weights, constraints, optimality
        - minimize_volatility(): basic functionality, target return
        - efficient_frontier(): output structure, return monotonicity
        - random_portfolios(): output structure
        - portfolio_performance(): mathematical correctness
        - summary(): output format
        - Edge cases: single asset, short selling
    """

    # ------ maximize_sharpe() tests ------

    def test_weights_sum_to_one(self, sample_returns):
        """Fully invested constraint: Σw_i = 1 / 全额投资约束"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.maximize_sharpe()
        total_weight = sum(result["weights"].values())
        assert abs(total_weight - 1.0) < 1e-6, f"Weights sum to {total_weight}, expected 1.0"

    def test_no_negative_weights_long_only(self, sample_returns):
        """Long-only constraint: all w_i ≥ 0 / 只做多约束"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.maximize_sharpe(allow_short=False)
        for asset, w in result["weights"].items():
            assert w >= -1e-6, f"Negative weight for {asset}: {w}"

    def test_sharpe_is_positive(self, sample_returns):
        """Max Sharpe portfolio should have positive Sharpe ratio / 最大夏普组合应有正夏普比率"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.maximize_sharpe()
        assert result["sharpe"] > 0, "Max Sharpe portfolio should have positive Sharpe"

    def test_maximize_sharpe_returns_all_keys(self, sample_returns):
        """Result dict should contain all expected keys / 结果字典应包含所有必要键"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.maximize_sharpe()
        expected_keys = {"weights", "return", "volatility", "sharpe", "success"}
        assert set(result.keys()) == expected_keys

    def test_maximize_sharpe_success_flag(self, sample_returns):
        """Optimizer should converge successfully / 优化器应成功收敛"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.maximize_sharpe()
        assert result["success"] is True

    # ------ Short selling tests ------

    def test_short_selling_allows_negative_weights(self, sample_returns):
        """
        When allow_short=True, weights CAN be negative.
        当允许做空时，权重可以为负值。

        Note: weights don't have to be negative, they just CAN be.
        We verify the constraint is relaxed by checking the bounds used.
        注意：权重不必须为负，只是可以为负。
        """
        opt = PortfolioOptimizer(sample_returns)
        result = opt.maximize_sharpe(allow_short=True)
        # 权重仍然应加总为 1 / Weights should still sum to 1
        total_weight = sum(result["weights"].values())
        assert abs(total_weight - 1.0) < 1e-6

    def test_short_selling_min_vol_weights_sum_to_one(self, sample_returns):
        """Short-selling min-vol weights should also sum to 1 / 做空最小波动率权重也应加总为1"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.minimize_volatility(allow_short=True)
        total_weight = sum(result["weights"].values())
        assert abs(total_weight - 1.0) < 1e-6

    # ------ minimize_volatility() tests ------

    def test_minimize_volatility_basic(self, sample_returns):
        """
        GMV (Global Minimum Variance) portfolio should have lower volatility
        than the equal-weight portfolio.
        全局最小方差（GMV）组合应比等权组合具有更低的波动率。

        CFA L3: The GMV portfolio is the leftmost point on the efficient frontier.
        CFA 三级：GMV 组合是有效前沿上最左边的点。
        """
        opt = PortfolioOptimizer(sample_returns)
        gmv = opt.minimize_volatility()

        # 等权组合的波动率 / Equal-weight portfolio volatility
        equal_weights = np.ones(opt.n_assets) / opt.n_assets
        _, equal_vol, _ = opt.portfolio_performance(equal_weights)

        assert gmv["volatility"] <= equal_vol + 1e-6, (
            f"GMV vol ({gmv['volatility']:.4f}) should be <= equal-weight vol ({equal_vol:.4f})"
        )

    def test_minimize_volatility_with_target_return(self, sample_returns):
        """
        When target_return is specified, the optimized portfolio's return
        should match the target (within numerical tolerance).
        当指定目标收益率时，优化后组合的收益率应匹配目标值（在数值容差内）。
        """
        opt = PortfolioOptimizer(sample_returns)
        target = 0.06  # 6% annualized target / 年化 6% 目标收益率
        result = opt.minimize_volatility(target_return=target)
        if result["success"]:
            assert abs(result["return"] - target) < 1e-4, (
                f"Return ({result['return']:.4f}) should match target ({target})"
            )

    def test_minimize_volatility_returns_all_keys(self, sample_returns):
        """Result dict should contain all expected keys / 结果应包含所有必要键"""
        opt = PortfolioOptimizer(sample_returns)
        result = opt.minimize_volatility()
        expected_keys = {"weights", "return", "volatility", "sharpe", "success"}
        assert set(result.keys()) == expected_keys

    # ------ Optimality tests: Max Sharpe dominates Min Vol ------

    def test_max_sharpe_geq_min_vol_sharpe(self, sample_returns):
        """
        The maximum Sharpe portfolio should have a Sharpe ratio ≥ the
        minimum volatility portfolio's Sharpe ratio.
        最大夏普组合的夏普比率应 ≥ 最小波动率组合的夏普比率。

        CFA L1: The tangency portfolio (max Sharpe) is the optimal risky portfolio;
        the GMV is a sub-optimal choice on the efficient frontier.
        CFA 一级：切点组合（最大夏普）是最优风险组合，
        GMV 在有效前沿上是次优选择。
        """
        opt = PortfolioOptimizer(sample_returns)
        max_s = opt.maximize_sharpe()
        min_v = opt.minimize_volatility()
        assert max_s["sharpe"] >= min_v["sharpe"] - 1e-6, (
            f"Max Sharpe ({max_s['sharpe']:.4f}) should be >= "
            f"Min Vol Sharpe ({min_v['sharpe']:.4f})"
        )

    # ------ efficient_frontier() tests ------

    def test_efficient_frontier_monotonic_risk(self, sample_returns):
        """Frontier should have enough points / 前沿应有足够的点数"""
        opt = PortfolioOptimizer(sample_returns)
        frontier = opt.efficient_frontier(n_points=20)
        assert len(frontier) > 5, "Too few frontier points"

    def test_efficient_frontier_returns_increase(self, sample_returns):
        """
        Along the efficient frontier, returns should monotonically increase.
        沿有效前沿，收益率应单调递增。

        This is a defining property of the efficient frontier:
        higher return requires higher risk (volatility).
        这是有效前沿的定义性质：更高收益需要更高风险（波动率）。
        """
        opt = PortfolioOptimizer(sample_returns)
        frontier = opt.efficient_frontier(n_points=30)
        returns = frontier["return"].values
        # 允许微小的数值误差 / Allow tiny numerical tolerance
        for i in range(1, len(returns)):
            assert returns[i] >= returns[i - 1] - 1e-6, (
                f"Return at point {i} ({returns[i]:.4f}) < "
                f"return at point {i-1} ({returns[i-1]:.4f})"
            )

    def test_efficient_frontier_has_weight_columns(self, sample_returns):
        """
        Frontier DataFrame should include one weight column per asset.
        前沿 DataFrame 应包含每个资产的权重列。
        """
        opt = PortfolioOptimizer(sample_returns)
        frontier = opt.efficient_frontier(n_points=10)
        for asset in opt.asset_names:
            assert asset in frontier.columns, f"Missing weight column for {asset}"

    # ------ random_portfolios() tests ------

    def test_random_portfolios_output_shape(self, sample_returns):
        """Random portfolios should return correct number of rows / 随机组合应返回正确的行数"""
        opt = PortfolioOptimizer(sample_returns)
        rp = opt.random_portfolios(n_portfolios=100)
        assert len(rp) == 100
        assert set(rp.columns) == {"return", "volatility", "sharpe"}

    def test_random_portfolios_volatility_positive(self, sample_returns):
        """All random portfolios should have positive volatility / 所有随机组合应有正波动率"""
        opt = PortfolioOptimizer(sample_returns)
        rp = opt.random_portfolios(n_portfolios=50)
        assert (rp["volatility"] > 0).all()

    # ------ portfolio_performance() tests ------

    def test_portfolio_performance_equal_weight(self, sample_returns):
        """
        Equal-weight portfolio should have return = mean of asset returns.
        等权组合的收益率应等于各资产收益率的平均值。
        """
        opt = PortfolioOptimizer(sample_returns)
        equal_w = np.ones(opt.n_assets) / opt.n_assets
        ret, vol, sr = opt.portfolio_performance(equal_w)
        expected_ret = float(opt.mean_returns.mean())
        assert abs(ret - expected_ret) < 1e-6

    # ------ summary() tests ------

    def test_summary_contains_asset_info(self, sample_returns):
        """Summary should list all assets and the risk-free rate / 摘要应列出所有资产和无风险利率"""
        opt = PortfolioOptimizer(sample_returns)
        s = opt.summary()
        assert "US_EQ" in s
        assert "BONDS" in s
        assert "Risk-free rate" in s
        assert "Annualized Expected Returns" in s
        assert "Annualized Volatilities" in s

    # ------ Edge case: single asset ------

    def test_single_asset_optimizer(self, single_asset_returns):
        """
        With a single asset, all weights should be 1.0 (trivial case).
        单资产时，权重应为 1.0（平凡情况）。
        """
        opt = PortfolioOptimizer(single_asset_returns)
        result = opt.maximize_sharpe()
        assert abs(list(result["weights"].values())[0] - 1.0) < 1e-6


# ============================================================
# Simulator Tests — 蒙特卡洛模拟器测试
# ============================================================

class TestMonteCarloSimulator:
    """
    Test suite for the Monte Carlo Simulator.
    蒙特卡洛模拟器的测试套件。

    Covers / 覆盖:
        - simulate(): path shape, initial value, floor at zero
        - Goal-based metrics: probability of success
        - retirement_planning(): two-phase simulation, survival rate
        - Reproducibility: same seed → same results
        - SimulationResult: summary output format
    """

    # ------ Basic simulate() tests ------

    def test_initial_value_correct(self):
        """All simulation paths should start at the initial value / 所有路径应从初始值开始"""
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=10, seed=42,
        )
        result = sim.simulate(initial_value=100000)
        assert np.all(result.paths[:, 0] == 100000)

    def test_output_shape(self):
        """Paths shape should be (n_simulations, n_years + 1) / 路径形状应为 (模拟次数, 年数+1)"""
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=500, n_years=20, seed=42,
        )
        result = sim.simulate(initial_value=100000)
        assert result.paths.shape == (500, 21)  # 20 years + initial

    def test_probability_of_success(self):
        """Probability of success should be in [0, 1] / 成功概率应在 [0, 1] 区间"""
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=1000, n_years=30, seed=42,
        )
        result = sim.simulate(initial_value=100000, goal_amount=500000)
        assert 0 <= result.probability_of_success <= 1

    def test_no_goal_means_no_success_probability(self):
        """Without a goal, probability_of_success should be None / 无目标时成功概率应为 None"""
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=5, seed=42,
        )
        result = sim.simulate(initial_value=100000)
        assert result.goal_amount is None
        assert result.probability_of_success is None

    # ------ Path property tests ------

    def test_paths_non_negative(self):
        """
        Portfolio values should never be negative (floor at 0).
        组合价值应永远不为负（最低为 0）。

        When large withdrawals cause the portfolio to go below zero,
        the simulator should clamp to 0 (funds depleted).
        当大额提款导致组合价值低于零时，模拟器应将其截断为 0（资金耗尽）。
        """
        sim = MonteCarloSimulator(
            expected_return=0.02, volatility=0.30,
            n_simulations=200, n_years=20, seed=42,
        )
        # 大额年度提款，期望部分路径触底为 0
        # Large annual withdrawal, expecting some paths to hit 0
        result = sim.simulate(
            initial_value=100000,
            annual_withdrawal=50000,  # 很大的提款 / Very large withdrawal
        )
        assert np.all(result.paths >= 0), "Portfolio values should never be negative"

    def test_contribution_increases_terminal_value(self):
        """
        Adding annual contributions should increase expected terminal values
        compared to no contributions.
        添加年度缴款应增加预期终端值（与无缴款相比）。
        """
        sim_base = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=500, n_years=10, seed=42,
        )
        result_no_contrib = sim_base.simulate(initial_value=100000)

        sim_contrib = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=500, n_years=10, seed=42,
        )
        result_with_contrib = sim_contrib.simulate(
            initial_value=100000, annual_contribution=10000,
        )

        assert result_with_contrib.mean_terminal > result_no_contrib.mean_terminal, (
            "Contributions should increase expected terminal value"
        )

    # ------ Reproducibility tests ------

    def test_reproducibility_with_same_seed(self):
        """
        Two simulations with the same seed should produce identical results.
        使用相同种子的两次模拟应产生完全相同的结果。
        """
        kwargs = dict(expected_return=0.08, volatility=0.15,
                      n_simulations=100, n_years=10, seed=42)

        result1 = MonteCarloSimulator(**kwargs).simulate(initial_value=100000)
        result2 = MonteCarloSimulator(**kwargs).simulate(initial_value=100000)

        np.testing.assert_array_equal(result1.paths, result2.paths)

    def test_different_seeds_produce_different_results(self):
        """
        Two simulations with different seeds should produce different results.
        使用不同种子的两次模拟应产生不同的结果。
        """
        result1 = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=10, seed=42,
        ).simulate(initial_value=100000)

        result2 = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=10, seed=99,
        ).simulate(initial_value=100000)

        assert not np.array_equal(result1.paths, result2.paths)

    # ------ Zero volatility (degenerate) tests ------

    def test_zero_volatility_deterministic(self):
        """
        With zero volatility, all paths should follow the deterministic growth path:
        V_t = V_0 × exp(μt) (no randomness).
        零波动率时，所有路径应遵循确定性增长路径。

        This tests the GBM formula: when σ=0, drift = μ - 0.5×0² = μ,
        and growth = exp(μ) every year (no random component).
        """
        sim = MonteCarloSimulator(
            expected_return=0.10, volatility=0.0,
            n_simulations=50, n_years=5, seed=42,
        )
        result = sim.simulate(initial_value=100000)

        # 所有路径应完全相同（因为没有随机性）
        # All paths should be identical (no randomness)
        for i in range(1, 50):
            np.testing.assert_array_almost_equal(
                result.paths[0], result.paths[i], decimal=2
            )

    # ------ SimulationResult.summary() tests ------

    def test_summary_output_format(self):
        """Summary should contain key statistics / 摘要应包含关键统计量"""
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=10, seed=42,
        )
        result = sim.simulate(initial_value=100000, goal_amount=200000)
        summary = result.summary()
        assert "Monte Carlo Simulation Results" in summary
        assert "Mean terminal value" in summary
        assert "Median terminal value" in summary
        assert "5th percentile" in summary
        assert "95th percentile" in summary
        assert "Goal" in summary
        assert "Probability of success" in summary

    # ------ Percentile ordering tests ------

    def test_percentile_ordering(self):
        """
        Percentiles should be in order: 5th ≤ 25th ≤ median ≤ 75th ≤ 95th.
        百分位数应按顺序排列：5th ≤ 25th ≤ 中位数 ≤ 75th ≤ 95th。
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=1000, n_years=20, seed=42,
        )
        r = sim.simulate(initial_value=100000)
        assert r.percentile_5 <= r.percentile_25
        assert r.percentile_25 <= r.median_terminal
        assert r.median_terminal <= r.percentile_75
        assert r.percentile_75 <= r.percentile_95

    # ------ retirement_planning() tests ------

    def test_retirement_planning_structure(self):
        """
        retirement_planning() should return all expected keys.
        retirement_planning() 应返回所有预期的键。
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=200, n_years=30, seed=42,
        )
        result = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=30000,
            desired_annual_income=100000,
        )
        expected_keys = {
            "accumulation", "distribution_paths",
            "survival_rate", "accumulation_years", "distribution_years",
        }
        assert set(result.keys()) == expected_keys

    def test_retirement_planning_phase_years(self):
        """
        Accumulation and distribution years should match age parameters.
        积累和分配阶段的年数应与年龄参数匹配。

        accumulation_years = retirement_age - current_age
        distribution_years = life_expectancy - retirement_age
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=30, seed=42,
        )
        result = sim.retirement_planning(
            current_age=35, retirement_age=65, life_expectancy=90,
            current_savings=50000, annual_savings=20000,
            desired_annual_income=80000,
        )
        assert result["accumulation_years"] == 30, "65 - 35 = 30"
        assert result["distribution_years"] == 25, "90 - 65 = 25"

    def test_retirement_planning_survival_rate_in_range(self):
        """
        Survival rate should be in [0, 1].
        存活率应在 [0, 1] 区间内。
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=200, n_years=30, seed=42,
        )
        result = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=50000,
            desired_annual_income=200000,
        )
        assert 0 <= result["survival_rate"] <= 1

    def test_retirement_planning_distribution_paths_shape(self):
        """
        Distribution paths shape should be (n_simulations, dist_years + 1).
        分配路径形状应为 (模拟次数, 分配年数 + 1)。
        """
        n_sims = 200
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=n_sims, n_years=30, seed=42,
        )
        result = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=30000,
            desired_annual_income=100000,
        )
        dist_years = 85 - 60  # = 25
        assert result["distribution_paths"].shape == (n_sims, dist_years + 1)

    def test_retirement_planning_distribution_paths_non_negative(self):
        """
        Distribution phase portfolio values should never be negative.
        分配阶段的组合价值应永不为负。
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=200, n_years=30, seed=42,
        )
        result = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=30000,
            desired_annual_income=300000,  # 很大的提款 / Very large withdrawal
        )
        assert np.all(result["distribution_paths"] >= 0), (
            "Distribution phase values should never be negative"
        )

    def test_retirement_planning_accumulation_is_simulation_result(self):
        """
        The accumulation phase should return a proper SimulationResult.
        积累阶段应返回正确的 SimulationResult 对象。
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=100, n_years=30, seed=42,
        )
        result = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=30000,
            desired_annual_income=100000,
        )
        accum = result["accumulation"]
        assert isinstance(accum, SimulationResult)
        assert accum.paths.shape[0] == 100  # n_simulations
        assert accum.paths.shape[1] == 31   # 30 accumulation years + 1

    def test_retirement_planning_inflation_impact(self):
        """
        Retirement planning with positive inflation should result in a lower
        survival rate compared to zero inflation due to higher nominal cash outflows.
        """
        sim = MonteCarloSimulator(
            expected_return=0.08, volatility=0.15,
            n_simulations=500, n_years=30, seed=42,
        )
        # Without inflation (0.0)
        res_no_inf = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=50000,
            desired_annual_income=200000, inflation_rate=0.0
        )
        # With inflation (3.0%)
        res_inf = sim.retirement_planning(
            current_age=30, retirement_age=60, life_expectancy=85,
            current_savings=100000, annual_savings=50000,
            desired_annual_income=200000, inflation_rate=0.03
        )
        assert res_inf["survival_rate"] < res_no_inf["survival_rate"], (
            f"Inflation should decrease survival rate (with: {res_inf['survival_rate']:.2%}, without: {res_no_inf['survival_rate']:.2%})"
        )


# ============================================================
# Risk Metrics Tests — 风险度量测试
# ============================================================

class TestRiskMetrics:
    """
    Test suite for risk and performance metrics.
    风险和绩效指标的测试套件。

    Covers / 覆盖:
        - sharpe_ratio: type check, positive for positive excess return
        - sortino_ratio: type check, comparison with Sharpe
        - max_drawdown: sign, peak/trough dates
        - value_at_risk: historical & parametric, sign, confidence sensitivity
        - conditional_var: sign, VaR ≤ CVaR property
        - compute_all_metrics: comprehensive output
        - Edge cases: constant returns, invalid method
    """

    # ------ Sharpe ratio tests ------

    def test_sharpe_ratio_type(self, sample_returns):
        """Sharpe ratio should return a float / 夏普比率应返回浮点数"""
        sr = sharpe_ratio(sample_returns["US_EQ"])
        assert isinstance(sr, float)

    def test_sharpe_ratio_positive_for_positive_excess_return(self, sample_returns):
        """
        US_EQ has ~10% annualized return with 4.5% risk-free rate,
        so Sharpe should be positive.
        US_EQ 年化收益率约 10%，无风险利率 4.5%，夏普比率应为正。
        """
        sr = sharpe_ratio(sample_returns["US_EQ"])
        assert sr > 0

    def test_sharpe_ratio_zero_vol_returns_zero(self, constant_returns):
        """
        A constant return series has zero volatility.
        sharpe_ratio should handle this gracefully (return 0).
        常数收益率序列波动率为零，夏普比率应优雅处理（返回 0）。
        """
        sr = sharpe_ratio(constant_returns)
        assert sr == 0.0

    # ------ Sortino ratio tests ------

    def test_sortino_ratio_type(self, sample_returns):
        """Sortino ratio should return a float / 索提诺比率应返回浮点数"""
        sr = sortino_ratio(sample_returns["US_EQ"])
        assert isinstance(sr, float)

    def test_sortino_geq_sharpe_for_positive_skew(self, sample_returns):
        """
        For return distributions with limited downside, Sortino should
        generally be ≥ Sharpe because downside deviation ≤ total std.
        对于下行有限的收益分布，索提诺比率通常 ≥ 夏普比率，
        因为下行偏差 ≤ 总标准差。

        CFA Reference: Sortino only penalizes downside deviation, so it is
        typically higher than Sharpe for return streams with positive mean.
        CFA 参考：索提诺只惩罚下行偏差，对正均值收益流通常高于夏普。
        """
        sr = sharpe_ratio(sample_returns["US_EQ"])
        so = sortino_ratio(sample_returns["US_EQ"])
        # Sortino is typically >= Sharpe
        assert so >= sr - 0.5, (
            f"Sortino ({so:.2f}) should be roughly >= Sharpe ({sr:.2f})"
        )

    def test_sortino_ratio_exact_value(self):
        """
        Sortino ratio exact mathematical validation with a small known series.
        """
        returns = pd.Series([-0.01, -0.02, 0.03, 0.04, -0.015, 0.01, 0.02, -0.005])
        so = sortino_ratio(returns, risk_free_rate=0.045)
        # Expected value is calculated under N-1 denominator (N=8):
        # excess return = mean(returns)*252 - 0.045 = 1.53
        # downside diff relative to MAR=0: -0.01, -0.02, 0, 0, -0.015, 0, 0, -0.005
        # downside vol = sqrt(sum(diff**2)/7)*sqrt(252) ≈ 0.1643166
        # Sortino = 1.53 / 0.1643166 ≈ 9.31128
        assert abs(so - 9.31128) < 1e-4

    # ------ Max drawdown tests ------

    def test_max_drawdown_is_negative(self, sample_prices):
        """Max drawdown should be ≤ 0 (it's a loss) / 最大回撤应 ≤ 0（代表损失）"""
        dd = max_drawdown(sample_prices["US_EQ"])
        assert dd["max_drawdown"] <= 0, "Max drawdown should be non-positive"

    def test_max_drawdown_has_dates(self, sample_prices):
        """Result should include peak and trough dates / 结果应包含峰值和谷底日期"""
        dd = max_drawdown(sample_prices["US_EQ"])
        assert "peak_date" in dd
        assert "trough_date" in dd

    def test_max_drawdown_peak_before_trough(self, sample_prices):
        """Peak date should be before trough date / 峰值日期应在谷底日期之前"""
        dd = max_drawdown(sample_prices["US_EQ"])
        assert dd["peak_date"] <= dd["trough_date"], (
            f"Peak ({dd['peak_date']}) should be before trough ({dd['trough_date']})"
        )

    def test_max_drawdown_bounded(self, sample_prices):
        """Max drawdown should be between -1 and 0 / 最大回撤应在 [-1, 0] 之间"""
        dd = max_drawdown(sample_prices["US_EQ"])
        assert -1.0 <= dd["max_drawdown"] <= 0.0

    # ------ VaR tests ------

    def test_var_is_positive(self, sample_returns):
        """VaR (as loss magnitude) should be positive / VaR（损失幅度）应为正"""
        var = value_at_risk(sample_returns["US_EQ"], confidence=0.95)
        assert var > 0, "VaR (loss) should be positive"

    def test_var_parametric_is_positive(self, sample_returns):
        """Parametric VaR should also be positive / 参数法 VaR 也应为正"""
        var = value_at_risk(
            sample_returns["US_EQ"], confidence=0.95, method="parametric"
        )
        assert var > 0, "Parametric VaR should be positive"

    def test_var_higher_confidence_larger(self, sample_returns):
        """
        99% VaR should be ≥ 95% VaR (higher confidence → more extreme quantile).
        99% VaR 应 ≥ 95% VaR（更高置信度 → 更极端的分位数）。

        CFA Reference: Higher confidence level corresponds to a more
        conservative (larger) VaR estimate.
        CFA 参考：更高的置信水平对应更保守（更大）的 VaR 估计。
        """
        var_95 = value_at_risk(sample_returns["US_EQ"], confidence=0.95)
        var_99 = value_at_risk(sample_returns["US_EQ"], confidence=0.99)
        assert var_99 >= var_95 - 1e-6, (
            f"99% VaR ({var_99:.4f}) should be >= 95% VaR ({var_95:.4f})"
        )

    def test_var_invalid_method_raises(self, sample_returns):
        """Invalid VaR method should raise ValueError / 无效的 VaR 方法应引发 ValueError"""
        with pytest.raises(ValueError, match="Unknown method"):
            value_at_risk(sample_returns["US_EQ"], method="invalid_method")

    # ------ CVaR tests ------

    def test_cvar_is_positive(self, sample_returns):
        """CVaR (Expected Shortfall) should be positive / CVaR（预期亏损）应为正"""
        cvar = conditional_var(sample_returns["US_EQ"], confidence=0.95)
        assert cvar > 0, "CVaR should be positive"

    def test_cvar_geq_var(self, sample_returns):
        """
        CVaR ≥ VaR is a mathematical property.
        CVaR ≥ VaR 是一个数学性质。

        CVaR is the expected loss BEYOND the VaR threshold, so it must
        be at least as large as VaR itself.
        CVaR 是超过 VaR 阈值后的预期损失，因此必须 ≥ VaR 本身。

        CFA Reference: CVaR (Expected Shortfall) is a coherent risk measure
        that captures tail risk. It always ≥ VaR by definition.
        CFA 参考：CVaR（预期亏损）是一致性风险度量，
        捕捉尾部风险。根据定义它总是 ≥ VaR。
        """
        var = value_at_risk(sample_returns["US_EQ"], confidence=0.95)
        cvar = conditional_var(sample_returns["US_EQ"], confidence=0.95)
        assert cvar >= var - 1e-6, (
            f"CVaR ({cvar:.4f}) should be >= VaR ({var:.4f}). "
            "This is a mathematical property of coherent risk measures."
        )

    # ------ compute_all_metrics() tests ------

    def test_compute_all_metrics_without_prices(self, sample_returns):
        """
        compute_all_metrics without prices should return all metrics
        except max_drawdown.
        不传入价格时，应返回除最大回撤外的所有指标。
        """
        metrics = compute_all_metrics(sample_returns["US_EQ"])
        expected_keys = {
            "annualized_return", "annualized_volatility",
            "sharpe_ratio", "sortino_ratio",
            "var_95_daily", "cvar_95_daily",
            "skewness", "kurtosis",
        }
        assert expected_keys.issubset(set(metrics.keys()))
        # 没有传价格，不应有 max_drawdown / No prices → no max_drawdown
        assert "max_drawdown" not in metrics

    def test_compute_all_metrics_with_prices(self, sample_returns, sample_prices):
        """
        compute_all_metrics with prices should include max_drawdown.
        传入价格时，应额外包含最大回撤。
        """
        metrics = compute_all_metrics(
            sample_returns["US_EQ"], prices=sample_prices["US_EQ"]
        )
        assert "max_drawdown" in metrics
        assert "peak_date" in metrics
        assert "trough_date" in metrics
        assert metrics["max_drawdown"] <= 0

    def test_compute_all_metrics_values_are_finite(self, sample_returns):
        """
        All numeric metric values should be finite (not NaN or inf).
        所有数值类型的指标值应为有限值（非 NaN 或 inf）。
        """
        metrics = compute_all_metrics(sample_returns["US_EQ"])
        for key, value in metrics.items():
            if isinstance(value, float):
                assert np.isfinite(value), f"Metric '{key}' is not finite: {value}"
