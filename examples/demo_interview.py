"""
AI WealthPilot - Interview Demo Script
AI WealthPilot - 面试演示脚本

A focused demo script for interview presentation showcasing:
用于面试演示的脚本，展示：

    1. Mean-Variance Optimization (MVO) - Efficient Frontier
       均值-方差优化（MVO）- 有效前沿
    2. Monte Carlo Simulation - Retirement Planning
       蒙特卡洛模拟 - 退休规划
    3. Risk Metrics Analysis
       风险指标分析

Usage / 使用方法:
    python demo_interview.py

Key Outputs / 关键输出:
    - Efficient frontier curve (risk-return relationship)
      有效前沿曲线（风险-收益关系）
    - Optimal portfolio allocation
      最优组合配置
    - Retirement planning success probability
      退休规划成功概率
    - Comprehensive risk metrics
      全面的风险指标
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
from src.portfolio.optimizer import PortfolioOptimizer
from src.portfolio.simulator import MonteCarloSimulator
from src.portfolio.risk_metrics import compute_all_metrics


def main():
    """
    Main demo function - showcases core quantitative modules.
    主演示函数 - 展示核心量化模块。
    """
    print("=" * 60)
    print("AI WEALTHPILOT - PORTFOLIO ENGINE DEMO")
    print("AI WEALTHPILOT - 投资组合引擎演示")
    print("=" * 60)
    print("\nDemonstrating quantitative finance modules:")
    print("展示量化金融模块：")
    print("  1. Mean-Variance Optimization (Markowitz)")
    print("     均值-方差优化（Markowitz）")
    print("  2. Monte Carlo Simulation (GBM)")
    print("     蒙特卡洛模拟（GBM）")
    print("  3. Risk Metrics (Sharpe, VaR, CVaR)")
    print("     风险指标（夏普、VaR、CVaR）")

    # Set random seed for reproducibility
    # 设置随机种子以保证结果可复现
    np.random.seed(42)

    # ============================================================
    # 1. Create Sample Market Data
    # 1. 创建示例市场数据
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 1: MARKET DATA")
    print("步骤1：市场数据")
    print("=" * 60)

    n_days = 252 * 5  # 5 years of daily data
    assets = ["US_Equity", "Intl_Equity", "US_Bonds", "Gold"]

    # Generate correlated returns with realistic characteristics
    # 生成具有现实特征的相关收益率
    returns = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )

    print(f"\nGenerated {n_days} daily returns for {len(assets)} asset classes:")
    print(f"生成了{n_days}天的日收益率，涵盖{len(assets)}个资产类别：")
    for asset in assets:
        ann_ret = returns[asset].mean() * 252
        ann_vol = returns[asset].std() * np.sqrt(252)
        print(f"  {asset}: Return={ann_ret:.1%}, Volatility={ann_vol:.1%}")

    # ============================================================
    # 2. Mean-Variance Optimization (MVO)
    # 2. 均值-方差优化（MVO）
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 2: MEAN-VARIANCE OPTIMIZATION")
    print("步骤2：均值-方差优化")
    print("=" * 60)

    # Create optimizer
    # 创建优化器
    optimizer = PortfolioOptimizer(returns)

    # Compute efficient frontier
    # 计算有效前沿
    print("\nComputing efficient frontier (50 points)...")
    print("计算有效前沿（50个点）...")
    frontier = optimizer.efficient_frontier(n_points=50)

    # Find optimal portfolios
    # 寻找最优组合
    max_sharpe = optimizer.maximize_sharpe()
    min_vol = optimizer.minimize_volatility()

    # Generate random portfolios for comparison
    # 生成随机组合用于对比
    print("Generating 5,000 random portfolios...")
    print("生成5,000个随机组合...")
    random_ports = optimizer.random_portfolios(n_portfolios=5000)

    # Print results
    # 打印结果
    print("\n" + "-" * 50)
    print("OPTIMAL PORTFOLIOS / 最优组合")
    print("-" * 50)

    print("\n1. Maximum Sharpe Ratio Portfolio / 最大夏普比率组合:")
    print(f"   Return / 收益率: {max_sharpe['return']:.2%}")
    print(f"   Volatility / 波动率: {max_sharpe['volatility']:.2%}")
    print(f"   Sharpe Ratio / 夏普比率: {max_sharpe['sharpe']:.2f}")
    print("   Allocation / 配置:")
    for asset, weight in max_sharpe['weights'].items():
        if weight > 0.01:  # Only show significant allocations
            print(f"     {asset}: {weight:.1%}")

    print("\n2. Global Minimum Variance Portfolio / 全局最小方差组合:")
    print(f"   Return / 收益率: {min_vol['return']:.2%}")
    print(f"   Volatility / 波动率: {min_vol['volatility']:.2%}")
    print(f"   Sharpe Ratio / 夏普比率: {min_vol['sharpe']:.2f}")
    print("   Allocation / 配置:")
    for asset, weight in min_vol['weights'].items():
        if weight > 0.01:
            print(f"     {asset}: {weight:.1%}")

    # Demonstrate the benefit of optimization
    # 展示优化的收益
    print("\n" + "-" * 50)
    print("OPTIMIZATION BENEFIT / 优化收益")
    print("-" * 50)

    # Calculate equal-weight portfolio for comparison
    # 计算等权组合作为对比
    equal_weights = np.ones(optimizer.n_assets) / optimizer.n_assets
    equal_ret, equal_vol, equal_sharpe = optimizer.portfolio_performance(equal_weights)

    print(f"\nEqual-Weight Portfolio / 等权组合:")
    print(f"   Return: {equal_ret:.2%}, Volatility: {equal_vol:.2%}, Sharpe: {equal_sharpe:.2f}")

    print(f"\nOptimized Portfolio (Max Sharpe) / 优化组合（最大夏普）:")
    print(f"   Return: {max_sharpe['return']:.2%}, Volatility: {max_sharpe['volatility']:.2%}, Sharpe: {max_sharpe['sharpe']:.2f}")

    print(f"\nImprovement / 改进:")
    print(f"   Return: {(max_sharpe['return'] - equal_ret):+.2%}")
    print(f"   Volatility: {(max_sharpe['volatility'] - equal_vol):+.2%}")
    print(f"   Sharpe: {(max_sharpe['sharpe'] - equal_sharpe):+.2f}")

    # ============================================================
    # 3. Monte Carlo Simulation
    # 3. 蒙特卡洛模拟
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 3: MONTE CARLO SIMULATION - RETIREMENT PLANNING")
    print("步骤3：蒙特卡洛模拟 - 退休规划")
    print("=" * 60)

    # Client profile
    # 客户画像
    current_age = 30
    retirement_age = 60
    life_expectancy = 85
    current_savings = 100000
    annual_savings = 50000
    desired_income = 120000

    print(f"\nClient Profile / 客户画像:")
    print(f"  Current Age / 当前年龄: {current_age}")
    print(f"  Retirement Age / 退休年龄: {retirement_age}")
    print(f"  Life Expectancy / 预期寿命: {life_expectancy}")
    print(f"  Current Savings / 当前储蓄: ${current_savings:,.0f}")
    print(f"  Annual Savings / 年度储蓄: ${annual_savings:,.0f}")
    print(f"  Desired Retirement Income / 期望退休收入: ${desired_income:,.0f}/year")

    # Use optimized portfolio characteristics
    # 使用优化后的组合特征
    expected_return = max_sharpe['return']
    volatility = max_sharpe['volatility']

    print(f"\nUsing Optimized Portfolio Characteristics:")
    print(f"使用优化后的组合特征:")
    print(f"  Expected Return / 预期收益率: {expected_return:.2%}")
    print(f"  Volatility / 波动率: {volatility:.2%}")

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
    print("\n" + "-" * 50)
    print("SIMULATION RESULTS / 模拟结果")
    print("-" * 50)

    print(f"\nAccumulation Phase (Age {current_age} to {retirement_age}):")
    print(f"积累阶段（{current_age}岁到{retirement_age}岁）:")
    accum = result['accumulation']
    print(f"  Duration / 持续时间: {result['accumulation_years']} years")
    print(f"  Mean Terminal Value / 平均终端价值: ${accum.mean_terminal:,.0f}")
    print(f"  Median Terminal Value / 中位数终端价值: ${accum.median_terminal:,.0f}")
    print(f"  5th Percentile / 第5百分位: ${accum.percentile_5:,.0f}")
    print(f"  95th Percentile / 第95百分位: ${accum.percentile_95:,.0f}")

    print(f"\nDistribution Phase (Age {retirement_age} to {life_expectancy}):")
    print(f"分配阶段（{retirement_age}岁到{life_expectancy}岁）:")
    print(f"  Duration / 持续时间: {result['distribution_years']} years")
    print(f"  Annual Withdrawal / 年度提款: ${desired_income:,.0f}")

    # Survival rate (most critical metric)
    # 存活率（最关键指标）
    print("\n" + "=" * 50)
    print("PORTFOLIO SURVIVAL RATE / 组合存活率")
    print("=" * 50)
    print(f"\n  Probability of NOT running out of money:")
    print(f"  退休期间资金不耗尽的概率:")
    print(f"  {result['survival_rate']:.1%}")

    # Interpretation
    # 解读
    if result['survival_rate'] >= 0.90:
        print("\n  ✓ EXCELLENT: High confidence of retirement success")
        print("    优秀：退休成功的高置信度")
        print("  The portfolio is projected to sustain withdrawals throughout retirement.")
        print("  预计组合能够在整个退休期间维持提款。")
    elif result['survival_rate'] >= 0.75:
        print("\n  ⚠ MODERATE: Consider increasing savings or adjusting goals")
        print("    中等：考虑增加储蓄或调整目标")
        print("  There is some risk of running out of money in later years.")
        print("  在晚年有资金耗尽的风险。")
    else:
        print("\n  ✗ CAUTION: Significant risk of running out of money")
        print("    警告：资金耗尽风险较大")
        print("  Recommend increasing savings rate or reducing retirement income goal.")
        print("  建议增加储蓄率或降低退休收入目标。")

    # ============================================================
    # 4. Risk Metrics Analysis
    # 4. 风险指标分析
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 4: RISK METRICS ANALYSIS")
    print("步骤4：风险指标分析")
    print("=" * 60)

    # Compute metrics for the optimal portfolio
    # 计算最优组合的指标
    # Create a synthetic portfolio return series
    # 创建一个合成的组合收益率序列
    weights = np.array(list(max_sharpe['weights'].values()))
    portfolio_returns = returns.dot(weights)

    metrics = compute_all_metrics(portfolio_returns)

    print("\nOptimal Portfolio Risk Metrics:")
    print("最优组合风险指标:")
    print("-" * 50)
    print(f"  Annualized Return / 年化收益率: {metrics['annualized_return']:.2%}")
    print(f"  Annualized Volatility / 年化波动率: {metrics['annualized_volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {metrics['sharpe_ratio']:.2f}")
    print(f"  Sortino Ratio / 索提诺比率: {metrics['sortino_ratio']:.2f}")
    print(f"  95% VaR (Daily) / 95%在险价值（日度）: {metrics['var_95_daily']:.2%}")
    print(f"  95% CVaR (Daily) / 95%条件在险价值（日度）: {metrics['cvar_95_daily']:.2%}")
    print(f"  Skewness / 偏度: {metrics['skewness']:.2f}")
    print(f"  Kurtosis / 峰度: {metrics['kurtosis']:.2f}")

    # Interpret risk metrics
    # 解读风险指标
    print("\n" + "-" * 50)
    print("RISK INTERPRETATION / 风险解读")
    print("-" * 50)

    print(f"\n1. Sharpe Ratio ({metrics['sharpe_ratio']:.2f}):")
    if metrics['sharpe_ratio'] > 1.0:
        print("   ✓ Good risk-adjusted return (>1.0)")
        print("     良好的风险调整后收益（>1.0）")
    elif metrics['sharpe_ratio'] > 0.5:
        print("   ⚠ Moderate risk-adjusted return")
        print("     中等风险调整后收益")
    else:
        print("   ✗ Low risk-adjusted return")
        print("     较低的风险调整后收益")

    print(f"\n2. 95% VaR ({metrics['var_95_daily']:.2%} daily):")
    print(f"   On a typical bad day, the portfolio could lose up to {metrics['var_95_daily']:.2%}")
    print(f"   在典型的糟糕一天，组合可能损失高达{metrics['var_95_daily']:.2%}")

    print(f"\n3. 95% CVaR ({metrics['cvar_95_daily']:.2%} daily):")
    print(f"   In extreme scenarios (worst 5%), average loss is {metrics['cvar_95_daily']:.2%}")
    print(f"   在极端情景下（最差5%），平均损失为{metrics['cvar_95_daily']:.2%}")

    # ============================================================
    # 5. Summary
    # 5. 总结
    # ============================================================
    print("\n" + "=" * 60)
    print("SUMMARY & KEY TAKEAWAYS")
    print("总结与关键要点")
    print("=" * 60)

    print("\n1. EFFICIENT FRONTIER (MVO):")
    print("   有效前沿（MVO）:")
    print(f"   - Computed {len(frontier)} points showing risk-return tradeoff")
    print(f"   - 计算了{len(frontier)}个点，展示风险-收益权衡")
    print(f"   - Max Sharpe portfolio: {max_sharpe['return']:.1%} return, {max_sharpe['volatility']:.1%} vol")
    print(f"   - 最大夏普组合：{max_sharpe['return']:.1%}收益，{max_sharpe['volatility']:.1%}波动")
    print(f"   - Demonstrates Markowitz Modern Portfolio Theory")
    print(f"   - 展示Markowitz现代投资组合理论")

    print("\n2. MONTE CARLO SIMULATION:")
    print("   蒙特卡洛模拟:")
    print(f"   - 10,000 simulation paths using Geometric Brownian Motion")
    print(f"   - 使用几何布朗运动的10,000条模拟路径")
    print(f"   - Survival rate: {result['survival_rate']:.1%}")
    print(f"   - 存活率：{result['survival_rate']:.1%}")
    print(f"   - Accounts for uncertainty in market returns")
    print(f"   - 考虑了市场收益的不确定性")

    print("\n3. RISK MANAGEMENT:")
    print("   风险管理:")
    print(f"   - Sharpe ratio: {metrics['sharpe_ratio']:.2f} (risk-adjusted performance)")
    print(f"   - 夏普比率：{metrics['sharpe_ratio']:.2f}（风险调整绩效）")
    print(f"   - VaR and CVaR quantify downside risk")
    print(f"   - VaR和CVaR量化下行风险")
    print(f"   - All metrics follow industry-standard methodologies")
    print(f"   - 所有指标遵循行业标准方法论")

    print("\n" + "=" * 60)
    print("DEMO COMPLETED SUCCESSFULLY!")
    print("演示成功完成！")
    print("=" * 60)

    print("\nInterview Talking Points:")
    print("面试讨论要点：")
    print("  1. How MVO constructs the efficient frontier using quadratic optimization")
    print("     MVO如何使用二次优化构建有效前沿")
    print("  2. Why Monte Carlo is superior to deterministic projections")
    print("     为什么蒙特卡洛优于确定性预测")
    print("  3. How risk metrics (Sharpe, VaR, CVaR) are calculated and interpreted")
    print("     风险指标（夏普、VaR、CVaR）如何计算和解读")
    print("  4. Real-world application: retirement planning with uncertainty")
    print("     实际应用：考虑不确定性的退休规划")
    print("  5. Professional standards and best practices")
    print("     专业标准与最佳实践")


if __name__ == "__main__":
    main()
