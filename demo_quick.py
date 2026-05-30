"""
AI WealthPilot - Quick Demo Script
AI WealthPilot - 快速演示脚本

A simplified demo script for interview presentation.
用于面试演示的简化脚本。

This script demonstrates the three core quantitative modules:
本脚本演示三个核心量化模块：

    1. Mean-Variance Optimization (MVO) - Efficient Frontier
       均值-方差优化（MVO）- 有效前沿
    2. Black-Litterman Model - Incorporating Investor Views
       Black-Litterman模型 - 纳入投资者观点
    3. Monte Carlo Simulation - Retirement Planning
       蒙特卡洛模拟 - 退休规划

Usage / 使用方法:
    python demo_quick.py

Key Outputs / 关键输出:
    - Efficient frontier curve (risk-return relationship)
      有效前沿曲线（风险-收益关系）
    - Optimal portfolio allocation with and without views
      有无观点的最优组合配置
    - Retirement planning success probability
      退休规划成功概率
"""

import numpy as np
import pandas as pd
from src.portfolio.optimizer import PortfolioOptimizer, BlackLittermanOptimizer
from src.portfolio.simulator import MonteCarloSimulator
from src.portfolio.views import ViewInput


def main():
    """
    Main demo function - showcases all three core modules.
    主演示函数 - 展示所有三个核心模块。
    """
    print("=" * 60)
    print("AI WEALTHPILOT - PORTFOLIO ENGINE DEMO")
    print("AI WEALTHPILOT - 投资组合引擎演示")
    print("=" * 60)

    # Set random seed for reproducibility
    # 设置随机种子以保证结果可复现
    np.random.seed(42)

    # ============================================================
    # 1. Create Sample Market Data
    # 1. 创建示例市场数据
    # ============================================================
    print("\n[1/4] Creating sample market data...")
    print("[1/4] 创建示例市场数据...")

    n_days = 252 * 5  # 5 years of daily data
    assets = ["US_Equity", "Intl_Equity", "US_Bonds", "Gold"]

    # Generate correlated returns
    # 生成相关收益率
    returns = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )

    print(f"  Generated {n_days} daily returns for {len(assets)} assets")
    print(f"  生成了{n_days}天的日收益率，涵盖{len(assets)}个资产")

    # ============================================================
    # 2. Mean-Variance Optimization (MVO)
    # 2. 均值-方差优化（MVO）
    # ============================================================
    print("\n" + "=" * 60)
    print("[2/4] MEAN-VARIANCE OPTIMIZATION (MVO)")
    print("[2/4] 均值-方差优化（MVO）")
    print("=" * 60)

    # Create optimizer
    # 创建优化器
    optimizer = PortfolioOptimizer(returns)

    # Compute efficient frontier
    # 计算有效前沿
    print("\nComputing efficient frontier (30 points)...")
    print("计算有效前沿（30个点）...")
    frontier = optimizer.efficient_frontier(n_points=30)

    # Find optimal portfolios
    # 寻找最优组合
    max_sharpe = optimizer.maximize_sharpe()
    min_vol = optimizer.minimize_volatility()

    # Print results
    # 打印结果
    print("\n" + "-" * 40)
    print("Maximum Sharpe Portfolio / 最大夏普组合:")
    print("-" * 40)
    print(f"  Return / 收益率: {max_sharpe['return']:.2%}")
    print(f"  Volatility / 波动率: {max_sharpe['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {max_sharpe['sharpe']:.2f}")
    print("  Weights / 权重:")
    for asset, weight in max_sharpe['weights'].items():
        print(f"    {asset}: {weight:.1%}")

    print("\n" + "-" * 40)
    print("Global Minimum Variance / 全局最小方差:")
    print("-" * 40)
    print(f"  Return / 收益率: {min_vol['return']:.2%}")
    print(f"  Volatility / 波动率: {min_vol['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {min_vol['sharpe']:.2f}")

    # ============================================================
    # 3. Black-Litterman Model
    # 3. Black-Litterman模型
    # ============================================================
    print("\n" + "=" * 60)
    print("[3/4] BLACK-LITTERMAN MODEL")
    print("[3/4] BLACK-LITTERMAN 模型")
    print("=" * 60)

    # Market cap weights
    # 市值权重
    market_cap_weights = np.array([0.45, 0.25, 0.25, 0.05])

    # Create BL optimizer
    # 创建BL优化器
    bl_optimizer = BlackLittermanOptimizer(
        returns,
        market_cap_weights=market_cap_weights,
    )

    # Print equilibrium returns
    # 打印均衡收益
    print("\nMarket-Implied Equilibrium Returns / 市场隐含均衡收益:")
    for i, asset in enumerate(bl_optimizer.asset_names):
        print(f"  {asset}: {bl_optimizer.Pi[i]:.2%}")

    # Define investor views (more conservative estimates)
    # 定义投资者观点（更保守的估计）
    views = [
        ViewInput('absolute', 'US_Equity', 0.10, 60.0),  # US Equity: 10%
        ViewInput('relative', 'US_Equity', 'Intl_Equity', 0.02, 50.0),  # US > Intl by 2%
        ViewInput('absolute', 'Gold', 0.06, 40.0),  # Gold: 6%
    ]

    print("\nInvestor Views / 投资者观点:")
    print("  1. US Equity will return 10% (confidence: 60%)")
    print("     美股预期收益10%（置信度：60%）")
    print("  2. US Equity > Intl Equity by 2% (confidence: 50%)")
    print("     美股将比国际股票高出2%（置信度：50%）")
    print("  3. Gold will return 6% (confidence: 40%)")
    print("     黄金预期收益6%（置信度：40%）")

    # Apply views
    # 应用观点
    print("\nApplying views and computing BL posterior...")
    print("应用观点并计算BL后验...")
    bl_optimizer.apply_views(views)

    # Find BL optimal portfolio
    # 寻找BL最优组合
    bl_result = bl_optimizer.bl_maximize_sharpe()

    print("\n" + "-" * 40)
    print("BL Optimal Portfolio / BL最优组合:")
    print("-" * 40)
    print(f"  Return / 收益率: {bl_result['return']:.2%}")
    print(f"  Volatility / 波动率: {bl_result['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {bl_result['sharpe']:.2f}")
    print("  Weights / 权重:")
    for asset, weight in bl_result['weights'].items():
        print(f"    {asset}: {weight:.1%}")

    # Compare MVO vs BL
    # 对比MVO vs BL
    print("\n" + "-" * 40)
    print("Comparison: MVO vs BL / 对比：MVO vs BL")
    print("-" * 40)
    print(f"{'Metric':<20} {'MVO':>10} {'BL':>10}")
    print("-" * 40)
    print(f"{'Return':<20} {max_sharpe['return']:>9.2%} {bl_result['return']:>9.2%}")
    print(f"{'Volatility':<20} {max_sharpe['volatility']:>9.2%} {bl_result['volatility']:>9.2%}")
    print(f"{'Sharpe':<20} {max_sharpe['sharpe']:>9.2f} {bl_result['sharpe']:>9.2f}")

    # ============================================================
    # 4. Monte Carlo Simulation
    # 4. 蒙特卡洛模拟
    # ============================================================
    print("\n" + "=" * 60)
    print("[4/4] MONTE CARLO SIMULATION - RETIREMENT PLANNING")
    print("[4/4] 蒙特卡洛模拟 - 退休规划")
    print("=" * 60)

    # Client profile
    # 客户画像
    current_age = 30
    retirement_age = 60
    life_expectancy = 85
    current_savings = 100000
    annual_savings = 50000
    desired_income = 150000

    print(f"\nClient Profile / 客户画像:")
    print(f"  Age: {current_age}, Retire at: {retirement_age}, Live to: {life_expectancy}")
    print(f"  Current Savings: ${current_savings:,.0f}")
    print(f"  Annual Savings: ${annual_savings:,.0f}")
    print(f"  Desired Retirement Income: ${desired_income:,.0f}/year")

    # Use MVO-optimized portfolio characteristics (more realistic for simulation)
    # 使用MVO优化后的组合特征（用于模拟更现实）
    expected_return = max_sharpe['return']
    volatility = max_sharpe['volatility']

    print(f"\nUsing MVO-Optimized Portfolio for Simulation:")
    print(f"  Expected Return: {expected_return:.2%}")
    print(f"  Volatility: {volatility:.2%}")

    # Create simulator
    # 创建模拟器
    simulator = MonteCarloSimulator(
        expected_return=expected_return,
        volatility=volatility,
        n_simulations=10000,
        seed=42,
    )

    # Run retirement planning
    # 运行退休规划
    print("\nRunning 10,000 Monte Carlo simulations...")
    print("运行10,000次蒙特卡洛模拟...")
    result = simulator.retirement_planning(
        current_age=current_age,
        retirement_age=retirement_age,
        life_expectancy=life_expectancy,
        current_savings=current_savings,
        annual_savings=annual_savings,
        desired_annual_income=desired_income,
    )

    # Print results
    # 打印结果
    print("\n" + "-" * 40)
    print("Accumulation Phase (Age {} to {}) / 积累阶段".format(current_age, retirement_age))
    print("-" * 40)
    accum = result['accumulation']
    print(f"  Duration: {result['accumulation_years']} years")
    print(f"  Mean Terminal Value: ${accum.mean_terminal:,.0f}")
    print(f"  Median Terminal Value: ${accum.median_terminal:,.0f}")
    print(f"  5th Percentile: ${accum.percentile_5:,.0f}")
    print(f"  95th Percentile: ${accum.percentile_95:,.0f}")

    print("\n" + "-" * 40)
    print("Distribution Phase (Age {} to {}) / 分配阶段".format(retirement_age, life_expectancy))
    print("-" * 40)
    print(f"  Duration: {result['distribution_years']} years")
    print(f"  Annual Withdrawal: ${desired_income:,.0f}")

    print("\n" + "=" * 60)
    print("PORTFOLIO SURVIVAL RATE / 组合存活率")
    print("=" * 60)
    print(f"  Probability of NOT running out of money:")
    print(f"  退休期间资金不耗尽的概率:")
    print(f"  {result['survival_rate']:.1%}")

    if result['survival_rate'] >= 0.90:
        print("\n  ✓ EXCELLENT: High confidence of retirement success")
        print("    优秀：退休成功的高置信度")
    elif result['survival_rate'] >= 0.75:
        print("\n  ⚠ MODERATE: Consider increasing savings")
        print("    中等：考虑增加储蓄")
    else:
        print("\n  ✗ CAUTION: Significant risk of running out of money")
        print("    警告：资金耗尽风险较大")

    # ============================================================
    # Summary
    # 总结
    # ============================================================
    print("\n" + "=" * 60)
    print("SUMMARY / 总结")
    print("=" * 60)
    print("\n1. Efficient Frontier / 有效前沿:")
    print(f"   - Computed {len(frontier)} points on the frontier")
    print(f"   - 计算了{len(frontier)}个前沿点")
    print(f"   - Shows risk-return tradeoff")
    print(f"   - 展示风险-收益权衡")

    print("\n2. Black-Litterman Model / Black-Litterman模型:")
    print(f"   - Incorporated 3 investor views")
    print(f"   - 纳入了3个投资者观点")
    print(f"   - BL Sharpe: {bl_result['sharpe']:.2f} vs MVO Sharpe: {max_sharpe['sharpe']:.2f}")
    print(f"   - Demonstrates how views affect allocation")
    print(f"   - 展示观点如何影响配置")

    print("\n3. Monte Carlo Simulation / 蒙特卡洛模拟:")
    print(f"   - 10,000 simulation paths")
    print(f"   - 10,000条模拟路径")
    print(f"   - Survival rate: {result['survival_rate']:.1%}")
    print(f"   - 存活率：{result['survival_rate']:.1%}")
    print(f"   - Accounts for uncertainty in returns")
    print(f"   - 考虑了收益的不确定性")

    print("\n" + "=" * 60)
    print("DEMO COMPLETED! / 演示完成！")
    print("=" * 60)
    print("\nKey Talking Points for Interview:")
    print("面试要点：")
    print("  1. MVO constructs efficient frontier using Markowitz theory")
    print("     MVO使用Markowitz理论构建有效前沿")
    print("  2. Black-Litterman combines equilibrium with investor views")
    print("     Black-Litterman结合均衡与投资者观点")
    print("  3. Monte Carlo simulates thousands of scenarios for planning")
    print("     蒙特卡洛模拟数千种情景用于规划")
    print("  4. All implementations follow CFA curriculum standards")
    print("     所有实现遵循CFA课程标准")


if __name__ == "__main__":
    main()
