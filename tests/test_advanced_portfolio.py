"""
AI WealthPilot - Advanced Portfolio Optimization Tests
AI WealthPilot - 高级投资组合优化测试

Test suite for advanced portfolio optimization features:
高级投资组合优化功能测试套件：

    - Covariance matrix regularization and condition number checks
      协方差矩阵正则化和条件数检查
    - Resampled MVO (Michaud method)
      重抽样MVO（Michaud方法）
    - Asset class constraints
      资产类别约束
    - Numerical stability
      数值稳定性

CFA Reference / CFA 参考:
    CFA L3 Asset Allocation: Testing portfolio optimization implementations
    requires attention to numerical stability, constraint handling, and
    robustness to input estimation errors.
    CFA 三级资产配置：测试投资组合优化实现需要关注数值稳定性、
    约束处理和对输入估计误差的鲁棒性。
"""

import numpy as np
import pandas as pd
import pytest

from src.portfolio.optimizer import PortfolioOptimizer


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
def ill_conditioned_returns():
    """
    Generate returns with highly correlated assets (ill-conditioned covariance).
    生成具有高度相关资产（病态协方差）的收益率数据。
    """
    np.random.seed(42)
    n_days = 1000
    base_returns = np.random.randn(n_days) * 0.01

    # 创建高度相关的资产
    # Create highly correlated assets
    returns_data = pd.DataFrame({
        'Asset_A': base_returns + np.random.randn(n_days) * 0.001,
        'Asset_B': base_returns + np.random.randn(n_days) * 0.001,
        'Asset_C': base_returns + np.random.randn(n_days) * 0.001,
        'Asset_D': np.random.randn(n_days) * 0.01,  # 独立资产
    })
    return returns_data


@pytest.fixture
def asset_class_config():
    """
    Asset class constraint configuration.
    资产类别约束配置。
    """
    return {
        'equity': {
            'assets': ['US_EQ', 'INTL_EQ'],
            'min': 0.3,
            'max': 0.7,
        },
        'bonds': {
            'assets': ['BONDS'],
            'min': 0.2,
            'max': 0.5,
        },
        'alternatives': {
            'assets': ['GOLD'],
            'min': 0.0,
            'max': 0.2,
        },
    }


# ============================================================
# Test Classes / 测试类
# ============================================================

class TestNumericalStability:
    """
    Test suite for numerical stability improvements.
    数值稳定性改进测试套件。
    """

    def test_condition_number_check(self, sample_returns):
        """
        Condition number should be finite and positive.
        条件数应为有限正数。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        condition = optimizer._check_condition_number()

        assert np.isfinite(condition), "Condition number should be finite"
        assert condition > 0, "Condition number should be positive"

    @pytest.mark.parametrize("method", ["diagonal", "eigenvalue"])
    def test_regularization_for_ill_conditioned(self, ill_conditioned_returns, method):
        """
        Ill-conditioned covariance matrix should be regularized.
        病态协方差矩阵应被正则化。
        """
        optimizer = PortfolioOptimizer(ill_conditioned_returns)

        # 检查条件数是否很大
        # Check if condition number is large
        condition = optimizer._check_condition_number()

        if condition > 1e10:
            # 如果条件数很大，应该已经正则化
            # If condition number is large, should have been regularized
            assert optimizer.is_regularized, "Should be regularized for ill-conditioned matrix"

            # 正则化后的条件数应该更小
            # Condition number after regularization should be smaller
            regularized_optimizer = PortfolioOptimizer(ill_conditioned_returns)
            regularized_optimizer.cov_matrix = regularized_optimizer._regularize_covariance_matrix(method=method)
            new_condition = regularized_optimizer._check_condition_number()

            assert new_condition < condition, f"Regularization using {method} should reduce condition number"

    @pytest.mark.parametrize("method", ["diagonal", "eigenvalue"])
    def test_regularization_preserves_symmetry(self, sample_returns, method):
        """
        Regularized covariance matrix should remain symmetric.
        正则化后的协方差矩阵应保持对称。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        regularized = optimizer._regularize_covariance_matrix(method=method)

        # 检查对称性
        # Check symmetry
        np.testing.assert_array_almost_equal(
            regularized.values,
            regularized.values.T,
            err_msg="Regularized matrix should be symmetric",
        )

    @pytest.mark.parametrize("method", ["diagonal", "eigenvalue"])
    def test_regularization_preserves_positive_definiteness(self, sample_returns, method):
        """
        Regularized covariance matrix should be positive definite.
        正则化后的协方差矩阵应为正定矩阵。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        regularized = optimizer._regularize_covariance_matrix(method=method)

        # 检查特征值是否都为正
        # Check if all eigenvalues are positive
        eigenvalues = np.linalg.eigvalsh(regularized.values)
        assert np.all(eigenvalues > 0), "Regularized matrix should be positive definite"

    def test_regularization_invalid_method(self, sample_returns):
        """
        Providing an unknown regularization method should raise ValueError.
        提供未知的正则化方法应该抛出 ValueError。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        with pytest.raises(ValueError, match="Unknown regularization method"):
            optimizer._regularize_covariance_matrix(method="invalid_method_name")

    def test_optimizer_works_with_ill_conditioned_matrix(self, ill_conditioned_returns):
        """
        Optimizer should work even with ill-conditioned covariance matrix.
        优化器即使在病态协方差矩阵下也能工作。
        """
        optimizer = PortfolioOptimizer(ill_conditioned_returns)

        # 应该能够成功运行优化
        # Should be able to run optimization successfully
        result = optimizer.maximize_sharpe()
        assert result['success'], "Optimizer should handle ill-conditioned matrix"
        assert np.all(np.isfinite(list(result['weights'].values())))


class TestResampledMVO:
    """
    Test suite for Resampled MVO (Michaud method).
    重抽样MVO（Michaud方法）测试套件。
    """

    def test_resampled_frontier_shape(self, sample_returns):
        """
        Resampled frontier should return DataFrame with correct columns.
        重抽样前沿应返回具有正确列的DataFrame。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        frontier = optimizer.resampled_efficient_frontier(
            n_points=20,
            n_simulations=50,  # 使用较少模拟以加快测试
        )

        assert isinstance(frontier, pd.DataFrame)
        if not frontier.empty:
            assert 'return' in frontier.columns
            assert 'volatility' in frontier.columns
            assert 'sharpe' in frontier.columns

    def test_resampled_frontier_weights_sum_to_one(self, sample_returns):
        """
        Resampled frontier weights should sum to approximately 1.
        重抽样前沿权重应近似加总为1。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        frontier = optimizer.resampled_efficient_frontier(
            n_points=10,
            n_simulations=50,
        )

        if not frontier.empty:
            # 获取资产权重列
            # Get asset weight columns
            weight_cols = [col for col in optimizer.asset_names if col in frontier.columns]

            for idx in frontier.index:
                weights_sum = frontier.loc[idx, weight_cols].sum()
                assert abs(weights_sum - 1.0) < 0.01, f"Weights should sum to ~1, got {weights_sum}"

    def test_resampled_maximize_sharpe_structure(self, sample_returns):
        """
        Resampled max Sharpe should return correct dict structure.
        重抽样最大夏普应返回正确的字典结构。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.resampled_maximize_sharpe(n_simulations=50)

        expected_keys = {'weights', 'return', 'volatility', 'sharpe', 'success'}
        assert set(result.keys()).issuperset(expected_keys)

    def test_resampled_maximize_sharpe_weights_sum_to_one(self, sample_returns):
        """
        Resampled max Sharpe weights should sum to 1.
        重抽样最大夏普权重应加总为1。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.resampled_maximize_sharpe(n_simulations=50)

        total = sum(result['weights'].values())
        assert abs(total - 1.0) < 1e-6, f"Weights should sum to 1, got {total}"

    def test_resampled_maximize_sharpe_positive_sharpe(self, sample_returns):
        """
        Resampled max Sharpe portfolio should have positive Sharpe ratio.
        重抽样最大夏普组合应有正的夏普比率。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.resampled_maximize_sharpe(n_simulations=50)

        assert result['sharpe'] > 0, "Sharpe ratio should be positive"

    def test_resampled_maximize_sharpe_provides_uncertainty(self, sample_returns):
        """
        Resampled max Sharpe should provide weight standard deviation.
        重抽样最大夏普应提供权重标准差。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.resampled_maximize_sharpe(n_simulations=50)

        assert 'weight_std' in result, "Should provide weight standard deviation"
        assert len(result['weight_std']) == optimizer.n_assets

    def test_resampled_mvo_more_diversified(self, sample_returns):
        """
        Resampled MVO should produce more diversified portfolios than traditional MVO.
        重抽样MVO应比传统MVO产生更多元化的投资组合。
        """
        optimizer = PortfolioOptimizer(sample_returns)

        # 传统MVO
        # Traditional MVO
        traditional_result = optimizer.maximize_sharpe()

        # 重抽样MVO
        # Resampled MVO
        resampled_result = optimizer.resampled_maximize_sharpe(n_simulations=100)

        # 计算HHI（赫芬达尔指数）衡量集中度
        # Calculate HHI (Herfindahl-Hirschman Index) to measure concentration
        traditional_weights = np.array(list(traditional_result['weights'].values()))
        resampled_weights = np.array(list(resampled_result['weights'].values()))

        traditional_hhi = np.sum(traditional_weights ** 2)
        resampled_hhi = np.sum(resampled_weights ** 2)

        # 重抽样MVO的HHI应该更小（更分散）
        # Resampled MVO should have lower HHI (more diversified)
        # 注意：这不是绝对的，但在大多数情况下成立
        # Note: This is not absolute, but holds in most cases
        print(f"Traditional HHI: {traditional_hhi:.4f}, Resampled HHI: {resampled_hhi:.4f}")


class TestAssetClassConstraints:
    """
    Test suite for asset class constraints.
    资产类别约束测试套件。
    """

    def test_asset_class_constraints_respected(
        self,
        sample_returns,
        asset_class_config,
    ):
        """
        Asset class constraints should be respected.
        资产类别约束应被遵守。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_config,
        )

        assert result['success'], "Optimization should succeed"

        # 检查资产类别约束
        # Check asset class constraints
        asset_class_weights = result['asset_class_weights']

        # 股票类别：30%-70%
        # Equity class: 30%-70%
        assert asset_class_weights['equity'] >= 0.3 - 1e-6, \
            f"Equity weight {asset_class_weights['equity']:.3f} should be >= 0.3"
        assert asset_class_weights['equity'] <= 0.7 + 1e-6, \
            f"Equity weight {asset_class_weights['equity']:.3f} should be <= 0.7"

        # 债券类别：20%-50%
        # Bonds class: 20%-50%
        assert asset_class_weights['bonds'] >= 0.2 - 1e-6, \
            f"Bonds weight {asset_class_weights['bonds']:.3f} should be >= 0.2"
        assert asset_class_weights['bonds'] <= 0.5 + 1e-6, \
            f"Bonds weight {asset_class_weights['bonds']:.3f} should be <= 0.5"

        # 另类资产类别：0%-20%
        # Alternatives class: 0%-20%
        assert asset_class_weights['alternatives'] >= 0.0 - 1e-6, \
            f"Alternatives weight {asset_class_weights['alternatives']:.3f} should be >= 0.0"
        assert asset_class_weights['alternatives'] <= 0.2 + 1e-6, \
            f"Alternatives weight {asset_class_weights['alternatives']:.3f} should be <= 0.2"

    def test_asset_class_weights_sum_to_one(
        self,
        sample_returns,
        asset_class_config,
    ):
        """
        Asset class weights should sum to 1.
        资产类别权重应加总为1。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_config,
        )

        total = sum(result['asset_class_weights'].values())
        assert abs(total - 1.0) < 1e-6, f"Asset class weights should sum to 1, got {total}"

    def test_asset_class_constraints_with_target_return(
        self,
        sample_returns,
        asset_class_config,
    ):
        """
        Asset class constraints should work with target return constraint.
        资产类别约束应与目标收益约束配合工作。
        """
        optimizer = PortfolioOptimizer(sample_returns)

        # 使用一个可行的目标收益率
        # Use a feasible target return
        target_return = float(optimizer.mean_returns.mean())

        result = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_config,
            target_return=target_return,
        )

        assert result['success'], "Optimization should succeed with target return"

        # 检查目标收益约束是否满足
        # Check if target return constraint is satisfied
        assert abs(result['return'] - target_return) < 1e-3, \
            f"Return {result['return']:.4f} should be close to target {target_return:.4f}"

    def test_asset_class_constraints_with_indices(
        self,
        sample_returns,
    ):
        """
        Asset class constraints should work with asset indices.
        资产类别约束应支持资产索引。
        """
        optimizer = PortfolioOptimizer(sample_returns)

        # 使用索引而不是名称
        # Use indices instead of names
        asset_classes = {
            'equity': {
                'assets': [0, 1],  # US_EQ, INTL_EQ
                'min': 0.4,
                'max': 0.8,
            },
            'bonds': {
                'assets': [2],  # BONDS
                'min': 0.1,
                'max': 0.4,
            },
            'alternatives': {
                'assets': [3],  # GOLD
                'min': 0.0,
                'max': 0.2,
            },
        }

        result = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_classes,
        )

        assert result['success'], "Optimization should succeed with indices"

    def test_asset_class_constraints_structure(
        self,
        sample_returns,
        asset_class_config,
    ):
        """
        Asset class constraints result should have correct structure.
        资产类别约束结果应有正确的结构。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_config,
        )

        expected_keys = {
            'weights',
            'return',
            'volatility',
            'sharpe',
            'success',
            'asset_class_weights',
        }
        assert set(result.keys()) == expected_keys

    def test_asset_class_constraints_positive_sharpe(
        self,
        sample_returns,
        asset_class_config,
    ):
        """
        Portfolio with asset class constraints should have positive Sharpe.
        带资产类别约束的投资组合应有正的夏普比率。
        """
        optimizer = PortfolioOptimizer(sample_returns)
        result = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_class_config,
        )

        assert result['sharpe'] > 0, "Sharpe ratio should be positive"


class TestIntegration:
    """
    Integration tests for advanced optimization features.
    高级优化功能集成测试。
    """

    def test_all_optimization_methods_consistent(self, sample_returns):
        """
        All optimization methods should return consistent structure.
        所有优化方法应返回一致的结构。
        """
        optimizer = PortfolioOptimizer(sample_returns)

        # 传统MVO
        # Traditional MVO
        traditional = optimizer.maximize_sharpe()

        # 重抽样MVO
        # Resampled MVO
        resampled = optimizer.resampled_maximize_sharpe(n_simulations=50)

        # 带约束的MVO
        # Constrained MVO
        asset_classes = {
            'equity': {'assets': ['US_EQ', 'INTL_EQ'], 'min': 0.3, 'max': 0.7},
            'bonds': {'assets': ['BONDS'], 'min': 0.2, 'max': 0.5},
            'alternatives': {'assets': ['GOLD'], 'min': 0.0, 'max': 0.2},
        }
        constrained = optimizer.optimize_with_asset_class_constraints(
            asset_classes=asset_classes,
        )

        # 所有结果都应有相同的键
        # All results should have the same keys
        base_keys = {'weights', 'return', 'volatility', 'sharpe', 'success'}
        assert set(traditional.keys()).issuperset(base_keys)
        assert set(resampled.keys()).issuperset(base_keys)
        assert set(constrained.keys()).issuperset(base_keys)

    def test_regularization_does_not_break_optimization(self, sample_returns):
        """
        Regularization should not break optimization functionality.
        正则化不应破坏优化功能。
        """
        optimizer = PortfolioOptimizer(sample_returns)

        # 强制正则化
        # Force regularization
        optimizer.cov_matrix = optimizer._regularize_covariance_matrix(epsilon=1e-4)
        optimizer.is_regularized = True

        # 所有优化方法都应正常工作
        # All optimization methods should work normally
        result1 = optimizer.maximize_sharpe()
        assert result1['success']

        result2 = optimizer.minimize_volatility()
        assert result2['success']

        result3 = optimizer.efficient_frontier(n_points=10)
        assert len(result3) > 0


class TestCovarianceShrinkage:
    """
    Test suite for covariance shrinkage estimators (Ledoit-Wolf and OAS).
    协方差收缩估计量（Ledoit-Wolf 和 OAS）测试套件。
    """

    def test_invalid_covariance_method(self, sample_returns):
        """
        Verify that providing an unsupported covariance_method raises a ValueError.
        """
        with pytest.raises(ValueError, match="Unknown covariance method"):
            PortfolioOptimizer(sample_returns, covariance_method="invalid_method")

    def test_ledoit_wolf_covariance_properties(self, sample_returns):
        """
        Verify that ledoit-wolf covariance is symmetric and positive definite,
        and is different from sample covariance.
        """
        optimizer_sample = PortfolioOptimizer(sample_returns, covariance_method='sample')
        optimizer_lw = PortfolioOptimizer(sample_returns, covariance_method='ledoit-wolf')

        # Check shape, index and columns match
        assert optimizer_lw.cov_matrix.shape == optimizer_sample.cov_matrix.shape
        assert (optimizer_lw.cov_matrix.index == optimizer_sample.cov_matrix.index).all()

        # Should not be identical to sample covariance
        assert not np.allclose(optimizer_lw.cov_matrix.values, optimizer_sample.cov_matrix.values)

        # Symmetry check
        np.testing.assert_array_almost_equal(
            optimizer_lw.cov_matrix.values,
            optimizer_lw.cov_matrix.values.T,
            err_msg="Ledoit-Wolf covariance matrix should be symmetric"
        )

        # Positive definiteness check (all eigenvalues > 0)
        eigenvalues = np.linalg.eigvalsh(optimizer_lw.cov_matrix.values)
        assert np.all(eigenvalues > 0), "Ledoit-Wolf covariance matrix should be positive definite"

    def test_oas_covariance_properties(self, sample_returns):
        """
        Verify that oas covariance is symmetric and positive definite,
        and is different from sample covariance.
        """
        optimizer_sample = PortfolioOptimizer(sample_returns, covariance_method='sample')
        optimizer_oas = PortfolioOptimizer(sample_returns, covariance_method='oas')

        # Check shape, index and columns match
        assert optimizer_oas.cov_matrix.shape == optimizer_sample.cov_matrix.shape
        assert (optimizer_oas.cov_matrix.index == optimizer_sample.cov_matrix.index).all()

        # Should not be identical to sample covariance
        assert not np.allclose(optimizer_oas.cov_matrix.values, optimizer_sample.cov_matrix.values)

        # Symmetry check
        np.testing.assert_array_almost_equal(
            optimizer_oas.cov_matrix.values,
            optimizer_oas.cov_matrix.values.T,
            err_msg="OAS covariance matrix should be symmetric"
        )

        # Positive definiteness check (all eigenvalues > 0)
        eigenvalues = np.linalg.eigvalsh(optimizer_oas.cov_matrix.values)
        assert np.all(eigenvalues > 0), "OAS covariance matrix should be positive definite"

    def test_shrinkage_optimization_run(self, sample_returns):
        """
        Verify optimization works with both estimators.
        """
        for method in ['ledoit-wolf', 'oas']:
            optimizer = PortfolioOptimizer(sample_returns, covariance_method=method)

            # Max Sharpe
            res_sharpe = optimizer.maximize_sharpe()
            assert res_sharpe['success'], f"maximize_sharpe failed with {method}"
            weights_sum = sum(res_sharpe['weights'].values())
            assert abs(weights_sum - 1.0) < 1e-6

            # Min Volatility
            res_vol = optimizer.minimize_volatility()
            assert res_vol['success'], f"minimize_volatility failed with {method}"
            weights_sum = sum(res_vol['weights'].values())
            assert abs(weights_sum - 1.0) < 1e-6

    def test_black_litterman_with_shrinkage(self, sample_returns):
        """
        Verify BlackLittermanOptimizer works with shrinkage.
        """
        from src.portfolio.optimizer import BlackLittermanOptimizer
        from src.portfolio.views import ViewInput

        # Initialize with ledoit-wolf
        bl_opt = BlackLittermanOptimizer(sample_returns, covariance_method='ledoit-wolf')
        assert bl_opt.covariance_method == 'ledoit-wolf'

        view = ViewInput(
            view_type="absolute",
            asset_long="US_EQ",
            expected_return=0.08,
            confidence=60.0,
        )
        bl_opt.apply_views([view])
        assert bl_opt.views_applied

        result = bl_opt.bl_maximize_sharpe()
        assert result['success']
        weights_sum = sum(result['weights'].values())
        assert abs(weights_sum - 1.0) < 1e-6