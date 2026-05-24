"""
AI WealthPilot - Black-Litterman Model Tests
AI WealthPilot - Black-Litterman 模型测试

Comprehensive test suite for the Black-Litterman model implementation.
Black-Litterman 模型实现的全面测试套件。

Covers / 覆盖:
    - Market-implied equilibrium returns calculation
      市场隐含均衡收益计算
    - BL posterior returns and covariance properties
      BL后验收益和协方差性质
    - Absolute and relative view processing
      绝对和相对观点处理
    - Edge cases: no views, single asset, high/low confidence
      边界情况：无观点、单资产、高/低置信度
    - Mathematical properties and invariants
      数学性质和不变量

CFA Reference / CFA 参考:
    CFA L3 Asset Allocation: Black-Litterman Model
    CFA 三级资产配置：Black-Litterman 模型
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import PortfolioOptimizer, BlackLittermanOptimizer
from src.portfolio.views import ViewInput, ViewProcessor


# ============================================================
# Fixtures / 测试夹具
# ============================================================

@pytest.fixture
def sample_returns():
    """
    Generate synthetic returns for 4 assets over 5 years.
    为4种资产生成5年的合成收益率数据。
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
def market_cap_weights():
    """
    Market cap weights for 4 assets (sums to 1).
    4种资产的市值权重（加总为1）。
    """
    return np.array([0.40, 0.25, 0.20, 0.15])


@pytest.fixture
def absolute_view():
    """
    Sample absolute view: US_EQ will return 15%.
    示例绝对观点：US_EQ 预期收益 15%。
    """
    return ViewInput(
        view_type='absolute',
        asset_long='US_EQ',
        expected_return=0.15,
        confidence=70.0,
    )


@pytest.fixture
def relative_view():
    """
    Sample relative view: US_EQ will outperform INTL_EQ by 3%.
    示例相对观点：US_EQ 将比 INTL_EQ 高出 3%。
    """
    return ViewInput(
        view_type='relative',
        asset_long='US_EQ',
        asset_short='INTL_EQ',
        expected_return=0.03,
        confidence=60.0,
    )


@pytest.fixture
def bl_optimizer(sample_returns, market_cap_weights):
    """
    BlackLittermanOptimizer instance.
    BlackLittermanOptimizer 实例。
    """
    return BlackLittermanOptimizer(
        sample_returns,
        market_cap_weights=market_cap_weights,
    )


@pytest.fixture
def view_processor():
    """
    ViewProcessor instance for 4 assets.
    4种资产的 ViewProcessor 实例。
    """
    return ViewProcessor(["US_EQ", "INTL_EQ", "BONDS", "GOLD"])


# ============================================================
# Test Classes / 测试类
# ============================================================

class TestImpliedEquilibriumReturns:
    """
    Test suite for market-implied equilibrium returns.
    市场隐含均衡收益测试套件。
    """

    def test_Pi_shape(self, bl_optimizer):
        """
        Pi should have shape (n_assets,).
        Pi 的形状应为 (n_assets,)。
        """
        assert bl_optimizer.Pi.shape == (bl_optimizer.n_assets,)

    def test_Pi_formula_correctness(self, bl_optimizer, market_cap_weights):
        """
        Pi should equal δ × Σ × w_mkt.
        Pi 应等于 δ × Σ × w_mkt。
        """
        expected_Pi = (
            bl_optimizer.delta
            * bl_optimizer.cov_matrix.values
            @ market_cap_weights
        )
        np.testing.assert_array_almost_equal(
            bl_optimizer.Pi, expected_Pi, decimal=10
        )

    def test_Pi_linear_in_delta(self, sample_returns):
        """
        Doubling delta should double Pi (linearity property).
        使 delta 翻倍应该使 Pi 翻倍（线性性质）。
        """
        weights = np.array([0.40, 0.25, 0.20, 0.15])
        opt1 = BlackLittermanOptimizer(
            sample_returns, market_cap_weights=weights, delta=2.0
        )
        opt2 = BlackLittermanOptimizer(
            sample_returns, market_cap_weights=weights, delta=4.0
        )
        # Doubling delta should double Pi
        np.testing.assert_array_almost_equal(opt2.Pi, 2.0 * opt1.Pi)

    def test_Pi_finite_values(self, bl_optimizer):
        """
        All Pi values should be finite.
        所有 Pi 值应该是有限的。
        """
        assert np.all(np.isfinite(bl_optimizer.Pi))


class TestViewProcessor:
    """
    Test suite for ViewProcessor class.
    ViewProcessor 类测试套件。
    """

    def test_absolute_view_P_matrix(self, view_processor, absolute_view):
        """
        Absolute view should set P[0, asset_idx] = 1.
        绝对观点应设置 P[0, 资产索引] = 1。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [absolute_view], cov
        )
        # US_EQ is index 0
        assert P[0, 0] == 1.0
        assert P[0, 1:] == pytest.approx(0.0, abs=1e-10)

    def test_absolute_view_Q_vector(self, view_processor, absolute_view):
        """
        Q should contain the expected return for absolute view.
        Q 应包含绝对观点的预期收益。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [absolute_view], cov
        )
        assert Q[0] == 0.15

    def test_relative_view_P_matrix(self, view_processor, relative_view):
        """
        Relative view: P[k, long] = 1, P[k, short] = -1.
        相对观点：P[k, 多头] = 1, P[k, 空头] = -1。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [relative_view], cov
        )
        # US_EQ (index 0) = 1, INTL_EQ (index 1) = -1
        assert P[0, 0] == 1.0
        assert P[0, 1] == -1.0
        assert P[0, 2:] == pytest.approx(0.0, abs=1e-10)

    def test_relative_view_Q_vector(self, view_processor, relative_view):
        """
        Q should contain the return difference for relative view.
        Q 应包含相对观点的收益差。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [relative_view], cov
        )
        assert Q[0] == 0.03

    def test_multiple_views(self, view_processor, absolute_view, relative_view):
        """
        Multiple views should produce K x N P matrix.
        多个观点应生成 K x N 的 P 矩阵。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [absolute_view, relative_view], cov
        )
        assert P.shape == (2, 4)
        assert Q.shape == (2,)

    def test_omega_diagonal(self, view_processor, absolute_view):
        """
        Omega should be diagonal (independent views).
        Omega 应为对角矩阵（观点独立）。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [absolute_view], cov
        )
        # Off-diagonal elements should be zero
        np.testing.assert_array_almost_equal(Omega, np.diag(np.diag(Omega)))

    def test_high_confidence_low_omega(self, view_processor):
        """
        High confidence should produce small omega.
        高置信度应产生小的 omega。
        """
        view_high = ViewInput(
            view_type='absolute', asset_long='US_EQ',
            expected_return=0.15, confidence=95.0
        )
        view_low = ViewInput(
            view_type='absolute', asset_long='US_EQ',
            expected_return=0.15, confidence=20.0
        )

        cov = pd.DataFrame(np.eye(4) * 0.04)
        _, _, Omega_high = view_processor.generate_P_Q_omega([view_high], cov)
        _, _, Omega_low = view_processor.generate_P_Q_omega([view_low], cov)

        # High confidence → smaller omega
        assert Omega_high[0, 0] < Omega_low[0, 0]

    def test_omega_positive_diagonal(self, view_processor, absolute_view):
        """
        Omega diagonal elements should be positive.
        Omega 对角元素应为正数。
        """
        cov = pd.DataFrame(np.eye(4) * 0.04)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            [absolute_view], cov
        )
        assert np.all(np.diag(Omega) > 0)

    def test_validate_views_valid(self, view_processor, absolute_view):
        """
        Valid views should produce no warnings.
        有效观点不应产生警告。
        """
        warnings = view_processor.validate_views([absolute_view])
        assert len(warnings) == 0

    def test_validate_views_invalid_asset(self, view_processor):
        """
        Invalid asset name should produce warning.
        无效资产名称应产生警告。
        """
        view = ViewInput(
            view_type='absolute', asset_long='INVALID',
            expected_return=0.15, confidence=70.0
        )
        warnings = view_processor.validate_views([view])
        assert len(warnings) > 0
        assert "Unknown asset" in warnings[0]


class TestBlackLittermanPosterior:
    """
    Test suite for BL posterior returns and covariance.
    BL 后验收益和协方差测试套件。
    """

    def test_no_views_returns_equilibrium(self, bl_optimizer):
        """
        With very low confidence, BL posterior should be close to equilibrium.
        置信度非常低时，BL 后验应接近均衡收益。
        """
        view = ViewInput(
            view_type='absolute', asset_long='US_EQ',
            expected_return=0.50, confidence=0.1  # Very low confidence
        )
        bl_optimizer.apply_views([view])

        # With near-zero confidence, posterior should be close to equilibrium
        np.testing.assert_array_almost_equal(
            bl_optimizer.mu_bl, bl_optimizer.Pi, decimal=2
        )

    def test_high_confidence_view_pulls_toward_view(self, bl_optimizer):
        """
        High confidence view should pull posterior toward the view.
        高置信度观点应将后验拉向观点方向。
        """
        view = ViewInput(
            view_type='absolute', asset_long='US_EQ',
            expected_return=0.30, confidence=99.0  # Very high confidence
        )
        bl_optimizer.apply_views([view])

        # BL posterior for US_EQ should be closer to 0.30 than to Pi
        pi_us = bl_optimizer.Pi[0]
        bl_us = bl_optimizer.mu_bl[0]

        # Distance from view should be small
        assert abs(bl_us - 0.30) < abs(pi_us - 0.30)

    def test_posterior_covariance_shape(self, bl_optimizer, absolute_view):
        """
        Posterior covariance should have shape (N, N).
        后验协方差矩阵形状应为 (N, N)。
        """
        bl_optimizer.apply_views([absolute_view])
        assert bl_optimizer.Sigma_bl.shape == (
            bl_optimizer.n_assets, bl_optimizer.n_assets
        )

    def test_posterior_covariance_symmetric(self, bl_optimizer, absolute_view):
        """
        Posterior covariance should be symmetric.
        后验协方差矩阵应为对称矩阵。
        """
        bl_optimizer.apply_views([absolute_view])
        np.testing.assert_array_almost_equal(
            bl_optimizer.Sigma_bl, bl_optimizer.Sigma_bl.T
        )

    def test_posterior_covariance_positive_semidefinite(self, bl_optimizer, absolute_view):
        """
        Posterior covariance should be positive semi-definite.
        后验协方差矩阵应为半正定矩阵。
        """
        bl_optimizer.apply_views([absolute_view])
        eigenvalues = np.linalg.eigvalsh(bl_optimizer.Sigma_bl)
        assert np.all(eigenvalues >= -1e-10), (
            "Posterior covariance should be positive semi-definite"
        )

    def test_posterior_covariance_increases_with_tau(self, sample_returns, market_cap_weights):
        """
        Larger tau should increase posterior covariance.
        更大的 tau 应增加后验协方差。
        """
        views = [ViewInput('absolute', 'US_EQ', 0.15, 70.0)]

        opt1 = BlackLittermanOptimizer(
            sample_returns, market_cap_weights=market_cap_weights, tau=0.01
        )
        opt2 = BlackLittermanOptimizer(
            sample_returns, market_cap_weights=market_cap_weights, tau=0.10
        )

        opt1.apply_views(views)
        opt2.apply_views(views)

        # Larger tau → larger posterior covariance
        assert np.trace(opt2.Sigma_bl) > np.trace(opt1.Sigma_bl)

    def test_posterior_returns_finite(self, bl_optimizer, absolute_view):
        """
        Posterior returns should be finite.
        后验收益应为有限值。
        """
        bl_optimizer.apply_views([absolute_view])
        assert np.all(np.isfinite(bl_optimizer.mu_bl))
        assert np.all(np.isfinite(bl_optimizer.Sigma_bl))

    def test_relative_view_effect(self, bl_optimizer):
        """
        Relative view "A > B" should increase A's return relative to B.
        相对观点"A > B"应增加 A 相对于 B 的收益。
        """
        view = ViewInput(
            view_type='relative', asset_long='US_EQ',
            asset_short='INTL_EQ', expected_return=0.05, confidence=80.0
        )
        bl_optimizer.apply_views([view])

        # US_EQ should have higher posterior return than INTL_EQ
        assert bl_optimizer.mu_bl[0] > bl_optimizer.mu_bl[1]


class TestBlackLittermanOptimization:
    """
    Test suite for BL optimization methods.
    BL 优化方法测试套件。
    """

    def test_bl_maximize_sharpe_shape(self, bl_optimizer, absolute_view):
        """
        BL max Sharpe should return correct dict structure.
        BL 最大夏普应返回正确的字典结构。
        """
        bl_optimizer.apply_views([absolute_view])
        result = bl_optimizer.bl_maximize_sharpe()

        expected_keys = {"weights", "return", "volatility", "sharpe", "success"}
        assert set(result.keys()) == expected_keys

    def test_bl_weights_sum_to_one(self, bl_optimizer, absolute_view):
        """
        BL optimized weights should sum to 1.
        BL 优化后的权重应加总为 1。
        """
        bl_optimizer.apply_views([absolute_view])
        result = bl_optimizer.bl_maximize_sharpe()
        total = sum(result["weights"].values())
        assert abs(total - 1.0) < 1e-6

    def test_bl_long_only_no_negative_weights(self, bl_optimizer, absolute_view):
        """
        BL long-only should have no negative weights.
        BL 只做多不应有负权重。
        """
        bl_optimizer.apply_views([absolute_view])
        result = bl_optimizer.bl_maximize_sharpe(allow_short=False)
        for asset, w in result["weights"].items():
            assert w >= -1e-6, f"Negative weight for {asset}: {w}"

    def test_bl_sharpe_is_positive(self, bl_optimizer, absolute_view):
        """
        BL max Sharpe portfolio should have positive Sharpe.
        BL 最大夏普组合应有正的夏普比率。
        """
        bl_optimizer.apply_views([absolute_view])
        result = bl_optimizer.bl_maximize_sharpe()
        assert result["sharpe"] > 0

    def test_bl_optimize_without_views_raises(self, bl_optimizer):
        """
        Calling bl_optimize without views should raise ValueError.
        未调用 apply_views 就调用 bl_optimize 应抛出 ValueError。
        """
        with pytest.raises(ValueError, match="Must call apply_views"):
            bl_optimizer.bl_maximize_sharpe()

    def test_bl_minimize_volatility_shape(self, bl_optimizer, absolute_view):
        """
        BL min volatility should return correct dict structure.
        BL 最小波动率应返回正确的字典结构。
        """
        bl_optimizer.apply_views([absolute_view])
        result = bl_optimizer.bl_minimize_volatility()

        expected_keys = {"weights", "return", "volatility", "sharpe", "success"}
        assert set(result.keys()) == expected_keys

    def test_bl_minimize_volatility_with_target(self, bl_optimizer, absolute_view):
        """
        BL min volatility with target return should satisfy constraint.
        带目标收益的 BL 最小波动率应满足约束。
        """
        bl_optimizer.apply_views([absolute_view])
        target = float(bl_optimizer.mu_bl.mean())
        result = bl_optimizer.bl_minimize_volatility(target_return=target)

        # Return should be close to target (within tolerance)
        assert abs(result["return"] - target) < 1e-3

    def test_bl_efficient_frontier_shape(self, bl_optimizer, absolute_view):
        """
        BL efficient frontier should return DataFrame with correct columns.
        BL 有效前沿应返回具有正确列的 DataFrame。
        """
        bl_optimizer.apply_views([absolute_view])
        frontier = bl_optimizer.bl_efficient_frontier(n_points=20)

        assert isinstance(frontier, pd.DataFrame)
        assert "return" in frontier.columns
        assert "volatility" in frontier.columns
        assert "sharpe" in frontier.columns
        # Should have asset weight columns
        for asset in bl_optimizer.asset_names:
            assert asset in frontier.columns

    def test_bl_vs_mvo_difference(self, bl_optimizer, absolute_view):
        """
        BL and MVO should produce different results (unless views = equilibrium).
        BL 和 MVO 应产生不同结果（除非观点 = 均衡）。
        """
        bl_optimizer.apply_views([absolute_view])

        bl_result = bl_optimizer.bl_maximize_sharpe()

        # Compare with base MVO
        mvo_optimizer = PortfolioOptimizer(bl_optimizer.returns)
        mvo_result = mvo_optimizer.maximize_sharpe()

        # They should be different (views are not equilibrium)
        assert bl_result["return"] != mvo_result["return"], (
            "BL and MVO should produce different returns"
        )

    def test_bl_summary_after_views(self, bl_optimizer, absolute_view):
        """
        BL summary should work after views are applied.
        应用观点后 BL 摘要应能工作。
        """
        bl_optimizer.apply_views([absolute_view])
        summary = bl_optimizer.bl_summary()

        assert "Black-Litterman Model Summary" in summary
        assert "Equilibrium" in summary
        assert "BL Posterior" in summary

    def test_bl_summary_without_views(self, bl_optimizer):
        """
        BL summary without views should return message.
        未应用观点时 BL 摘要应返回提示信息。
        """
        summary = bl_optimizer.bl_summary()
        assert "No views applied" in summary


class TestEdgeCases:
    """
    Test suite for edge cases and boundary conditions.
    边界情况和边界条件测试套件。
    """

    def test_single_asset(self):
        """
        BL should work with single asset.
        BL 应能处理单资产情况。
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            np.random.randn(1000) * 0.01 + 0.0004,
            columns=["SINGLE"]
        )

        opt = BlackLittermanOptimizer(
            returns, market_cap_weights=np.array([1.0])
        )

        view = ViewInput('absolute', 'SINGLE', 0.20, 80.0)
        opt.apply_views([view])

        result = opt.bl_maximize_sharpe()
        assert abs(list(result["weights"].values())[0] - 1.0) < 1e-6

    def test_two_assets_one_relative_view(self):
        """
        Two assets with one relative view.
        两种资产和一个相对观点。
        """
        np.random.seed(42)
        returns = pd.DataFrame(
            np.random.randn(1000, 2) * 0.01 + np.array([0.0004, 0.0003]),
            columns=["A", "B"]
        )

        opt = BlackLittermanOptimizer(
            returns, market_cap_weights=np.array([0.5, 0.5])
        )

        view = ViewInput('relative', 'A', 'B', 0.05, 70.0)
        opt.apply_views([view])

        # A should have higher weight than B (view is A outperforms B)
        result = opt.bl_maximize_sharpe()
        assert result["weights"]["A"] > result["weights"]["B"]

    def test_extreme_confidence_values(self, bl_optimizer):
        """
        Should handle extreme confidence values gracefully.
        应能优雅处理极端置信度值。
        """
        # Very high confidence
        view_high = ViewInput('absolute', 'US_EQ', 0.50, 99.9)
        bl_optimizer.apply_views([view_high])
        assert np.all(np.isfinite(bl_optimizer.mu_bl))

        # Very low confidence
        opt2 = BlackLittermanOptimizer(
            bl_optimizer.returns,
            market_cap_weights=bl_optimizer.market_cap_weights,
        )
        view_low = ViewInput('absolute', 'US_EQ', 0.50, 0.1)
        opt2.apply_views([view_low])
        assert np.all(np.isfinite(opt2.mu_bl))

    def test_all_views_same_asset(self, bl_optimizer):
        """
        Multiple views on the same asset should be handled.
        应能处理对同一资产的多个观点。
        """
        views = [
            ViewInput('absolute', 'US_EQ', 0.10, 50.0),
            ViewInput('absolute', 'US_EQ', 0.20, 80.0),
        ]
        bl_optimizer.apply_views(views)

        # Should not crash, and result should be finite
        assert np.all(np.isfinite(bl_optimizer.mu_bl))
        assert np.all(np.isfinite(bl_optimizer.Sigma_bl))

    def test_equal_market_weights(self, sample_returns):
        """
        Default equal weights should work.
        默认等权重应能工作。
        """
        opt = BlackLittermanOptimizer(sample_returns)  # No market_cap_weights

        expected_weights = np.ones(4) / 4
        np.testing.assert_array_almost_equal(
            opt.market_cap_weights, expected_weights
        )

    def test_custom_tau(self, sample_returns, market_cap_weights):
        """
        Custom tau value should be used.
        自定义 tau 值应被使用。
        """
        opt = BlackLittermanOptimizer(
            sample_returns,
            market_cap_weights=market_cap_weights,
            tau=0.05
        )
        assert opt.tau == 0.05

    def test_custom_delta(self, sample_returns, market_cap_weights):
        """
        Custom delta value should be used.
        自定义 delta 值应被使用。
        """
        opt = BlackLittermanOptimizer(
            sample_returns,
            market_cap_weights=market_cap_weights,
            delta=3.0
        )
        assert opt.delta == 3.0

    def test_invalid_market_weights_length(self, sample_returns):
        """
        Invalid market weights length should raise ValueError.
        无效的市值权重长度应抛出 ValueError。
        """
        with pytest.raises(ValueError, match="must match number of assets"):
            BlackLittermanOptimizer(
                sample_returns,
                market_cap_weights=np.array([0.5, 0.5])  # Wrong length
            )

    def test_invalid_market_weights_sum(self, sample_returns):
        """
        Market weights not summing to 1 should raise ValueError.
        市值权重不加总为1应抛出 ValueError。
        """
        with pytest.raises(ValueError, match="must sum to 1.0"):
            BlackLittermanOptimizer(
                sample_returns,
                market_cap_weights=np.array([0.5, 0.5, 0.5, 0.5])  # Sums to 2.0
            )
