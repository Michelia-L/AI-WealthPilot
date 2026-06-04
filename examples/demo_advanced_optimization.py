"""
AI WealthPilot - Advanced Portfolio Optimization Demo
AI WealthPilot - 高级投资组合优化演示

Demonstrates the new advanced optimization features:
演示新增的高级优化功能：

    1. Covariance matrix regularization (协方差矩阵正则化)
    2. Resampled MVO - Michaud method (重抽样MVO - Michaud方法)
    3. Asset class constraints (资产类别约束)

Usage / 使用方法:
    python demo_advanced_optimization.py
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from src.portfolio.optimizer import PortfolioOptimizer



def create_sample_data():
    """
    Create sample return data for demonstration.
    创建示例收益率数据用于演示。
    """
    np.random.seed(42)
    n_days = 252 * 5  # 5 years of daily data

    assets = ["US_Equity", "Intl_Equity", "US_Bonds", "Gold"]

    # Generate correlated returns
    # 生成相关收益率
    returns_data = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )

    return returns_data


def demo_numerical_stability():
    """
    Demonstrate numerical stability improvements.
    演示数值稳定性改进。
    """
    print("=" * 60)
    print("1. Numerical Stability / 数值稳定性")
    print("=" * 60)

    returns = create_sample_data()
    optimizer = PortfolioOptimizer(returns)

    print(f"\nCondition number: {optimizer.condition_number:.2e}")
    print(f"Is regularized: {optimizer.is_regularized}")

    if optimizer.is_regularized:
        print("✓ Covariance matrix was regularized for numerical stability")
        print("  协方差矩阵已正则化以提高数值稳定性")
    else:
        print("✓ Covariance matrix is well-conditioned, no regularization needed")
        print("  协方差矩阵条件良好，无需正则化")


def demo_resampled_mvo():
    """
    Demonstrate Resampled MVO (Michaud method).
    演示重抽样MVO（Michaud方法）。
    """
    print("\n" + "=" * 60)
    print("2. Resampled MVO (Michaud Method) / 重抽样MVO（Michaud方法）")
    print("=" * 60)

    returns = create_sample_data()
    optimizer = PortfolioOptimizer(returns)

    # Traditional MVO
    # 传统MVO
    traditional_result = optimizer.maximize_sharpe()

    # Resampled MVO
    # 重抽样MVO
    resampled_result = optimizer.resampled_maximize_sharpe(n_simulations=500)

    print("\nTraditional MVO (Maximum Sharpe):")
    print("传统MVO（最大夏普）:")
    print(f"  Return / 收益率: {traditional_result['return']:.2%}")
    print(f"  Volatility / 波动率: {traditional_result['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {traditional_result['sharpe']:.2f}")
    print("  Weights / 权重:")
    for asset, weight in traditional_result['weights'].items():
        print(f"    {asset}: {weight:.2%}")

    print("\nResampled MVO (Maximum Sharpe):")
    print("重抽样MVO（最大夏普）:")
    print(f"  Return / 收益率: {resampled_result['return']:.2%}")
    print(f"  Volatility / 波动率: {resampled_result['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {resampled_result['sharpe']:.2f}")
    print(f"  Simulations / 模拟次数: {resampled_result['n_simulations']}")
    print("  Weights / 权重:")
    for asset, weight in resampled_result['weights'].items():
        print(f"    {asset}: {weight:.2%}")

    # Compare diversification
    # 比较多元化程度
    traditional_weights = np.array(list(traditional_result['weights'].values()))
    resampled_weights = np.array(list(resampled_result['weights'].values()))

    traditional_hhi = np.sum(traditional_weights ** 2)
    resampled_hhi = np.sum(resampled_weights ** 2)

    print(f"\nDiversification Comparison / 多元化比较:")
    print(f"  Traditional HHI / 传统HHI: {traditional_hhi:.4f}")
    print(f"  Resampled HHI / 重抽样HHI: {resampled_hhi:.4f}")

    if resampled_hhi < traditional_hhi:
        print("  ✓ Resampled MVO is more diversified / 重抽样MVO更加多元化")
    else:
        print("  ✓ Similar diversification levels / 多元化程度相似")


def demo_asset_class_constraints():
    """
    Demonstrate asset class constraints.
    演示资产类别约束。
    """
    print("\n" + "=" * 60)
    print("3. Asset Class Constraints / 资产类别约束")
    print("=" * 60)

    returns = create_sample_data()
    optimizer = PortfolioOptimizer(returns)

    # Define asset class constraints
    # 定义资产类别约束
    asset_classes = {
        'equity': {
            'assets': ['US_Equity', 'Intl_Equity'],
            'min': 0.40,  # At least 40% in equities
            'max': 0.80,  # At most 80% in equities
        },
        'bonds': {
            'assets': ['US_Bonds'],
            'min': 0.15,  # At least 15% in bonds
            'max': 0.40,  # At most 40% in bonds
        },
        'alternatives': {
            'assets': ['Gold'],
            'min': 0.05,  # At least 5% in alternatives
            'max': 0.25,  # At most 25% in alternatives
        },
    }

    # Run optimization with constraints
    # 运行带约束的优化
    result = optimizer.optimize_with_asset_class_constraints(
        asset_classes=asset_classes,
    )

    print("\nOptimization with Asset Class Constraints:")
    print("带资产类别约束的优化:")
    print(f"  Success / 成功: {result['success']}")
    print(f"  Return / 收益率: {result['return']:.2%}")
    print(f"  Volatility / 波动率: {result['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {result['sharpe']:.2f}")

    print("\nAsset Class Weights / 资产类别权重:")
    for class_name, weight in result['asset_class_weights'].items():
        constraint = asset_classes[class_name]
        min_w = constraint['min']
        max_w = constraint['max']
        status = "✓" if min_w <= weight <= max_w else "✗"
        print(f"  {class_name}: {weight:.2%} (constraint: {min_w:.0%}-{max_w:.0%}) {status}")

    print("\nIndividual Asset Weights / 单个资产权重:")
    for asset, weight in result['weights'].items():
        print(f"  {asset}: {weight:.2%}")


def demo_resampled_frontier():
    """
    Demonstrate resampled efficient frontier.
    演示重抽样有效前沿。
    """
    print("\n" + "=" * 60)
    print("4. Resampled Efficient Frontier / 重抽样有效前沿")
    print("=" * 60)

    returns = create_sample_data()
    optimizer = PortfolioOptimizer(returns)

    # Compute resampled frontier
    # 计算重抽样前沿
    frontier = optimizer.resampled_efficient_frontier(
        n_points=10,
        n_simulations=200,
    )

    if not frontier.empty:
        print("\nResampled Efficient Frontier Points:")
        print("重抽样有效前沿点:")
        print(f"{'Return':>10} {'Volatility':>12} {'Sharpe':>8}")
        print("-" * 32)

        for idx in frontier.index[:5]:  # Show first 5 points
            ret = frontier.loc[idx, 'return']
            vol = frontier.loc[idx, 'volatility']
            sharpe = frontier.loc[idx, 'sharpe']
            print(f"{ret:>10.2%} {vol:>12.2%} {sharpe:>8.2f}")

        if len(frontier) > 5:
            print(f"... and {len(frontier) - 5} more points")
    else:
        print("Failed to compute resampled frontier")


if __name__ == "__main__":
    print("AI WealthPilot - Advanced Portfolio Optimization Demo")
    print("AI WealthPilot - 高级投资组合优化演示")
    print("=" * 60)

    # Run demos
    # 运行演示
    demo_numerical_stability()
    demo_resampled_mvo()
    demo_asset_class_constraints()
    demo_resampled_frontier()

    print("\n" + "=" * 60)
    print("Demo completed! / 演示完成！")
    print("=" * 60)