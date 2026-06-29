"""
AI WealthPilot - Comprehensive Portfolio Engine Demo
AI WealthPilot - 综合投资组合引擎演示

This demo showcases all three core quantitative modules:
本演示展示三个核心量化模块：

    1. Mean-Variance Optimization (MVO) — Markowitz framework
       均值-方差优化（MVO）—— Markowitz 框架
    2. Black-Litterman Model — Bayesian combination of equilibrium and views
       Black-Litterman 模型 —— 均衡收益与投资者观点的贝叶斯结合
    3. Monte Carlo Simulation — Goal-based financial planning
       蒙特卡洛模拟 —— 基于目标的财务规划

Usage / 使用方法:
    python demo_comprehensive.py

Output / 输出:
    - Console output with detailed analysis
      控制台输出详细分析
    - Interactive Plotly charts (opened in browser)
      交互式 Plotly 图表（在浏览器中打开）
    - Portfolio allocation recommendations
      投资组合配置建议

"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import webbrowser
import tempfile

# Import core modules
# 导入核心模块
from src.portfolio.optimizer import PortfolioOptimizer, BlackLittermanOptimizer
from src.portfolio.simulator import MonteCarloSimulator
from src.portfolio.risk_metrics import compute_all_metrics
from src.portfolio.views import ViewInput, ViewProcessor
from src.visualization.charts import (
    plot_efficient_frontier,
    plot_allocation_pie,
    plot_monte_carlo_paths,
    plot_correlation_heatmap,
)

# Set random seed for reproducibility
# 设置随机种子以保证结果可复现
np.random.seed(42)


def create_sample_market_data():
    """
    Create realistic sample market data for demonstration.
    创建真实的示例市场数据用于演示。

    Asset characteristics based on historical patterns:
    基于历史模式的资产特征：
    - US Equity: High return, high volatility
      美股：高收益，高波动
    - International Equity: Moderate return, moderate volatility
      国际股票：中等收益，中等波动
    - US Bonds: Low return, low volatility
      美国债券：低收益，低波动
    - Gold: Moderate return, moderate volatility, low correlation with equities
      黄金：中等收益，中等波动，与股票低相关
    """
    n_days = 252 * 5  # 5 years of daily data

    # Asset names
    assets = ["US_Equity", "Intl_Equity", "US_Bonds", "Gold"]

    # Generate correlated returns using Cholesky decomposition
    # 使用Cholesky分解生成相关收益率
    # Correlation matrix (realistic estimates)
    # 相关性矩阵（现实估计）
    corr_matrix = np.array([
        [1.00, 0.75, 0.10, 0.05],  # US_Equity
        [0.75, 1.00, 0.15, 0.10],  # Intl_Equity
        [0.10, 0.15, 1.00, 0.20],  # US_Bonds
        [0.05, 0.10, 0.20, 1.00],  # Gold
    ])

    # Volatilities (annualized)
    # 波动率（年化）
    volatilities = np.array([0.18, 0.20, 0.05, 0.15])

    # Expected returns (annualized)
    # 预期收益率（年化）
    expected_returns = np.array([0.10, 0.08, 0.04, 0.06])

    # Convert to daily
    # 转换为日度
    daily_vols = volatilities / np.sqrt(252)
    daily_returns = expected_returns / 252

    # Create covariance matrix
    # 创建协方差矩阵
    cov_matrix = np.outer(daily_vols, daily_vols) * corr_matrix

    # Generate random returns
    # 生成随机收益率
    returns = np.random.multivariate_normal(
        daily_returns, cov_matrix, size=n_days
    )

    # Create DataFrame
    # 创建DataFrame
    returns_df = pd.DataFrame(returns, columns=assets)

    return returns_df


def demo_mean_variance_optimization(returns):
    """
    Demonstrate Mean-Variance Optimization (MVO).
    演示均值-方差优化（MVO）。

    This section shows:
    本节展示：
    1. Efficient frontier construction
       有效前沿构建
    2. Maximum Sharpe ratio portfolio (tangency portfolio)
       最大夏普比率组合（切点组合）
    3. Global minimum variance portfolio
       全局最小方差组合
    4. Random portfolio cloud for comparison
       随机组合云用于对比
    """
    print("\n" + "=" * 70)
    print("1. MEAN-VARIANCE OPTIMIZATION (MVO)")
    print("1. 均值-方差优化（MVO）")
    print("=" * 70)

    # Create optimizer
    # 创建优化器
    optimizer = PortfolioOptimizer(returns)

    # Print asset universe summary
    # 打印资产池摘要
    print("\nAsset Universe Summary / 资产池摘要:")
    print(optimizer.summary())

    # Compute efficient frontier
    # 计算有效前沿
    print("\nComputing efficient frontier (50 points)...")
    print("计算有效前沿（50个点）...")
    frontier = optimizer.efficient_frontier(n_points=50)

    # Find optimal portfolios
    # 寻找最优组合
    max_sharpe = optimizer.maximize_sharpe()
    min_vol = optimizer.minimize_volatility()

    # Generate random portfolios for visualization
    # 生成随机组合用于可视化
    print("Generating 2,000 random portfolios for comparison...")
    print("生成2,000个随机组合用于对比...")
    random_ports = optimizer.random_portfolios(n_portfolios=2000)

    # Print results
    # 打印结果
    print("\n" + "-" * 50)
    print("Maximum Sharpe Ratio Portfolio / 最大夏普比率组合:")
    print("-" * 50)
    print(f"  Expected Return / 预期收益率: {max_sharpe['return']:.2%}")
    print(f"  Volatility / 波动率: {max_sharpe['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {max_sharpe['sharpe']:.2f}")
    print("  Weights / 权重:")
    for asset, weight in max_sharpe['weights'].items():
        print(f"    {asset}: {weight:.1%}")

    print("\n" + "-" * 50)
    print("Global Minimum Variance Portfolio / 全局最小方差组合:")
    print("-" * 50)
    print(f"  Expected Return / 预期收益率: {min_vol['return']:.2%}")
    print(f"  Volatility / 波动率: {min_vol['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {min_vol['sharpe']:.2f}")
    print("  Weights / 权重:")
    for asset, weight in min_vol['weights'].items():
        print(f"    {asset}: {weight:.1%}")

    # Create visualization
    # 创建可视化
    fig = plot_efficient_frontier(
        frontier=frontier,
        random_portfolios=random_ports,
        max_sharpe=max_sharpe,
        min_vol=min_vol,
    )

    return fig, max_sharpe, min_vol, frontier


def demo_black_litterman(returns, max_sharpe_mvo):
    """
    Demonstrate Black-Litterman Model.
    演示Black-Litterman模型。

    This section shows:
    本节展示：
    1. Market-implied equilibrium returns
       市场隐含均衡收益
    2. Incorporating investor views (absolute and relative)
       纳入投资者观点（绝对和相对）
    3. BL posterior returns vs. MVO
       BL后验收益 vs. MVO
    4. How views affect optimal allocation
       观点如何影响最优配置
    """
    print("\n" + "=" * 70)
    print("2. BLACK-LITTERMAN MODEL")
    print("2. BLACK-LITTERMAN 模型")
    print("=" * 70)

    # Market capitalization weights (realistic estimates)
    # 市值权重（现实估计）
    market_cap_weights = np.array([0.45, 0.25, 0.25, 0.05])

    # Create BL optimizer
    # 创建BL优化器
    bl_optimizer = BlackLittermanOptimizer(
        returns,
        market_cap_weights=market_cap_weights,
        tau=0.025,  # Uncertainty scaling factor
    )

    # Print market-implied equilibrium returns
    # 打印市场隐含均衡收益
    print("\nMarket-Implied Equilibrium Returns / 市场隐含均衡收益:")
    print("-" * 50)
    for i, asset in enumerate(bl_optimizer.asset_names):
        print(f"  {asset}: {bl_optimizer.Pi[i]:.2%}")

    # Define investor views
    # 定义投资者观点
    print("\nInvestor Views / 投资者观点:")
    print("-" * 50)

    views = [
        # Absolute view: US Equity will return 12%
        # 绝对观点：美股预期收益12%
        ViewInput(
            view_type='absolute',
            asset_long='US_Equity',
            expected_return=0.12,
            confidence=70.0,
        ),
        # Relative view: US Equity will outperform International by 3%
        # 相对观点：美股将比国际股票高出3%
        ViewInput(
            view_type='relative',
            asset_long='US_Equity',
            asset_short='Intl_Equity',
            expected_return=0.03,
            confidence=60.0,
        ),
        # Absolute view: Gold will return 8%
        # 绝对观点：黄金预期收益8%
        ViewInput(
            view_type='absolute',
            asset_long='Gold',
            expected_return=0.08,
            confidence=50.0,
        ),
    ]

    for view in views:
        if view.view_type == 'absolute':
            print(f"  Absolute: {view.asset_long} → {view.expected_return:.1%} "
                  f"(confidence: {view.confidence:.0f}%)")
        else:
            print(f"  Relative: {view.asset_long} > {view.asset_short} by "
                  f"{view.expected_return:.1%} (confidence: {view.confidence:.0f}%)")

    # Apply views and compute BL posterior
    # 应用观点并计算BL后验
    print("\nApplying views and computing BL posterior...")
    print("应用观点并计算BL后验...")
    bl_optimizer.apply_views(views)

    # Print BL summary
    # 打印BL摘要
    print("\n" + bl_optimizer.bl_summary())

    # Find BL optimal portfolio
    # 寻找BL最优组合
    bl_max_sharpe = bl_optimizer.bl_maximize_sharpe()

    print("\n" + "-" * 50)
    print("BL Maximum Sharpe Portfolio / BL最大夏普组合:")
    print("-" * 50)
    print(f"  Expected Return / 预期收益率: {bl_max_sharpe['return']:.2%}")
    print(f"  Volatility / 波动率: {bl_max_sharpe['volatility']:.2%}")
    print(f"  Sharpe Ratio / 夏普比率: {bl_max_sharpe['sharpe']:.2f}")
    print("  Weights / 权重:")
    for asset, weight in bl_max_sharpe['weights'].items():
        print(f"    {asset}: {weight:.1%}")

    # Compare with MVO
    # 与MVO对比
    print("\n" + "-" * 50)
    print("Comparison: MVO vs Black-Litterman / 对比：MVO vs Black-Litterman")
    print("-" * 50)
    print(f"{'Metric / 指标':<25} {'MVO':>12} {'BL':>12} {'Difference':>12}")
    print("-" * 60)
    print(f"{'Return / 收益率':<25} {max_sharpe_mvo['return']:>11.2%} "
          f"{bl_max_sharpe['return']:>11.2%} "
          f"{bl_max_sharpe['return'] - max_sharpe_mvo['return']:>+11.2%}")
    print(f"{'Volatility / 波动率':<25} {max_sharpe_mvo['volatility']:>11.2%} "
          f"{bl_max_sharpe['volatility']:>11.2%} "
          f"{bl_max_sharpe['volatility'] - max_sharpe_mvo['volatility']:>+11.2%}")
    print(f"{'Sharpe / 夏普比率':<25} {max_sharpe_mvo['sharpe']:>11.2f} "
          f"{bl_max_sharpe['sharpe']:>11.2f} "
          f"{bl_max_sharpe['sharpe'] - max_sharpe_mvo['sharpe']:>+11.2f}")

    # Create comparison pie charts
    # 创建对比饼图
    fig_mvo = plot_allocation_pie(
        max_sharpe_mvo['weights'],
        title="MVO Optimal Allocation / MVO最优配置"
    )
    fig_bl = plot_allocation_pie(
        bl_max_sharpe['weights'],
        title="BL Optimal Allocation (with Views) / BL最优配置（含观点）"
    )

    return fig_mvo, fig_bl, bl_max_sharpe


def demo_monte_carlo_simulation(bl_result):
    """
    Demonstrate Monte Carlo Simulation for retirement planning.
    演示蒙特卡洛模拟进行退休规划。

    This section shows:
    本节展示：
    1. Two-phase retirement simulation (accumulation + distribution)
       两阶段退休模拟（积累 + 分配）
    2. Probability of success analysis
       成功概率分析
    3. Portfolio survival rate
       组合存活率
    4. Percentile distribution of outcomes
       结果的百分位数分布
    """
    print("\n" + "=" * 70)
    print("3. MONTE CARLO SIMULATION — RETIREMENT PLANNING")
    print("3. 蒙特卡洛模拟 —— 退休规划")
    print("=" * 70)

    # Client profile
    # 客户画像
    current_age = 30
    retirement_age = 60
    life_expectancy = 85
    current_savings = 100000  # $100,000
    annual_savings = 50000    # $50,000/year
    desired_retirement_income = 150000  # $150,000/year

    print("\nClient Profile / 客户画像:")
    print("-" * 50)
    print(f"  Current Age / 当前年龄: {current_age}")
    print(f"  Retirement Age / 退休年龄: {retirement_age}")
    print(f"  Life Expectancy / 预期寿命: {life_expectancy}")
    print(f"  Current Savings / 当前储蓄: ${current_savings:,.0f}")
    print(f"  Annual Savings / 年度储蓄: ${annual_savings:,.0f}")
    print(f"  Desired Retirement Income / 期望退休收入: ${desired_retirement_income:,.0f}/year")

    # Use BL-optimized portfolio characteristics
    # 使用BL优化后的组合特征
    expected_return = bl_result['return']
    volatility = bl_result['volatility']

    print(f"\nUsing BL-Optimized Portfolio Characteristics:")
    print(f"使用BL优化后的组合特征:")
    print(f"  Expected Return / 预期收益率: {expected_return:.2%}")
    print(f"  Volatility / 波动率: {volatility:.2%}")

    # Create Monte Carlo simulator
    # 创建蒙特卡洛模拟器
    simulator = MonteCarloSimulator(
        expected_return=expected_return,
        volatility=volatility,
        n_simulations=10000,  # 10,000 simulation paths
        seed=42,
    )

    # Run retirement planning simulation
    # 运行退休规划模拟
    print("\nRunning 10,000 Monte Carlo simulations...")
    print("运行10,000次蒙特卡洛模拟...")
    result = simulator.retirement_planning(
        current_age=current_age,
        retirement_age=retirement_age,
        life_expectancy=life_expectancy,
        current_savings=current_savings,
        annual_savings=annual_savings,
        desired_annual_income=desired_retirement_income,
    )

    # Print accumulation phase results
    # 打印积累阶段结果
    print("\n" + "-" * 50)
    print("ACCUMULATION PHASE (Age {} to {}) / 积累阶段（{}岁到{}岁）".format(
        current_age, retirement_age, current_age, retirement_age
    ))
    print("-" * 50)
    accum = result['accumulation']
    print(f"  Duration / 持续时间: {result['accumulation_years']} years / 年")
    print(f"  Mean Terminal Value / 平均终端价值: ${accum.mean_terminal:,.0f}")
    print(f"  Median Terminal Value / 中位数终端价值: ${accum.median_terminal:,.0f}")
    print(f"  5th Percentile / 第5百分位: ${accum.percentile_5:,.0f}")
    print(f"  95th Percentile / 第95百分位: ${accum.percentile_95:,.0f}")

    # Print distribution phase results
    # 打印分配阶段结果
    print("\n" + "-" * 50)
    print("DISTRIBUTION PHASE (Age {} to {}) / 分配阶段（{}岁到{}岁）".format(
        retirement_age, life_expectancy, retirement_age, life_expectancy
    ))
    print("-" * 50)
    print(f"  Duration / 持续时间: {result['distribution_years']} years / 年")
    print(f"  Annual Withdrawal / 年度提款: ${desired_retirement_income:,.0f}")

    # Print survival rate (most critical metric)
    # 打印存活率（最关键指标）
    print("\n" + "=" * 50)
    print("PORTFOLIO SURVIVAL RATE / 组合存活率")
    print("=" * 50)
    print(f"  Probability of NOT running out of money:")
    print(f"  退休期间资金不耗尽的概率:")
    print(f"  {result['survival_rate']:.1%}")

    # Interpretation
    # 解读
    if result['survival_rate'] >= 0.90:
        print("\n  ✓ EXCELLENT: High confidence of retirement success")
        print("    优秀：退休成功的高置信度")
    elif result['survival_rate'] >= 0.75:
        print("\n  ⚠ MODERATE: Consider increasing savings or adjusting goals")
        print("    中等：考虑增加储蓄或调整目标")
    else:
        print("\n  ✗ CAUTION: Significant risk of running out of money")
        print("    警告：资金耗尽风险较大")

    # Create visualization
    # 创建可视化
    # Plot accumulation phase paths
    # 绘制积累阶段路径
    fig_accum = plot_monte_carlo_paths(
        accum.paths,
        n_display=200,
        goal_amount=current_savings + annual_savings * result['accumulation_years'],
    )

    # Plot distribution phase paths
    # 绘制分配阶段路径
    fig_dist = plot_monte_carlo_paths(
        result['distribution_paths'],
        n_display=200,
        goal_amount=0,  # Goal is to never reach zero
    )

    return fig_accum, fig_dist, result


def demo_risk_metrics(returns):
    """
    Demonstrate comprehensive risk metrics analysis.
    演示全面的风险指标分析。

    This section shows:
    本节展示：
    1. Risk-adjusted performance metrics (Sharpe, Sortino)
       风险调整绩效指标（夏普、索提诺）
    2. Tail risk metrics (VaR, CVaR)
       尾部风险指标（VaR、CVaR）
    3. Distribution characteristics (skewness, kurtosis)
       分布特征（偏度、峰度）
    4. Maximum drawdown analysis
       最大回撤分析
    """
    print("\n" + "=" * 70)
    print("4. RISK METRICS ANALYSIS")
    print("4. 风险指标分析")
    print("=" * 70)

    # Compute metrics for each asset
    # 计算每个资产的指标
    print("\nRisk Metrics by Asset / 各资产风险指标:")
    print("-" * 70)

    metrics_list = []
    for asset in returns.columns:
        metrics = compute_all_metrics(returns[asset])
        metrics_list.append(metrics)

        print(f"\n{asset}:")
        print(f"  Annualized Return / 年化收益率: {metrics['annualized_return']:.2%}")
        print(f"  Annualized Volatility / 年化波动率: {metrics['annualized_volatility']:.2%}")
        print(f"  Sharpe Ratio / 夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"  Sortino Ratio / 索提诺比率: {metrics['sortino_ratio']:.2f}")
        print(f"  95% VaR (daily) / 95%在险价值（日度）: {metrics['var_95_daily']:.2%}")
        print(f"  95% CVaR (daily) / 95%条件在险价值（日度）: {metrics['cvar_95_daily']:.2%}")
        print(f"  Skewness / 偏度: {metrics['skewness']:.2f}")
        print(f"  Kurtosis / 峰度: {metrics['kurtosis']:.2f}")

    # Create correlation heatmap
    # 创建相关性热力图
    corr_matrix = returns.corr()
    fig_corr = plot_correlation_heatmap(corr_matrix)

    print("\n" + "-" * 50)
    print("Correlation Matrix / 相关性矩阵:")
    print("-" * 50)
    print(corr_matrix.round(2).to_string())

    return fig_corr, metrics_list


def save_and_open_figures(figures, filenames):
    """
    Save figures to HTML files and open in browser.
    将图表保存为HTML文件并在浏览器中打开。
    """
    print("\n" + "=" * 70)
    print("Saving charts...")
    print("保存图表...")

    for fig, filename in zip(figures, filenames):
        filepath = os.path.join(tempfile.gettempdir(), filename)
        fig.write_html(filepath)
        print(f"  Saved: {filepath}")
        webbrowser.open('file://' + filepath)

    print("\nCharts opened in browser / 图表已在浏览器中打开")


def main():
    """
    Main demo function.
    主演示函数。
    """
    print("=" * 70)
    print("AI WEALTHPILOT - COMPREHENSIVE PORTFOLIO ENGINE DEMO")
    print("AI WEALTHPILOT - 综合投资组合引擎演示")
    print("=" * 70)
    print("\nThis demo showcases three core quantitative modules:")
    print("本演示展示三个核心量化模块：")
    print("  1. Mean-Variance Optimization (MVO) / 均值-方差优化")
    print("  2. Black-Litterman Model / Black-Litterman 模型")
    print("  3. Monte Carlo Simulation / 蒙特卡洛模拟")
    print("\n" + "=" * 70)

    # Step 1: Create sample market data
    # 步骤1：创建示例市场数据
    print("\nStep 1: Creating sample market data (5 assets, 5 years)...")
    print("步骤1：创建示例市场数据（5个资产，5年）...")
    returns = create_sample_market_data()
    print(f"  Generated {len(returns)} daily returns for {len(returns.columns)} assets")
    print(f"  生成了{len(returns)}天的日收益率，涵盖{len(returns.columns)}个资产")

    # Step 2: Mean-Variance Optimization
    # 步骤2：均值-方差优化
    fig_frontier, max_sharpe, min_vol, frontier = demo_mean_variance_optimization(returns)

    # Step 3: Black-Litterman Model
    # 步骤3：Black-Litterman模型
    fig_mvo, fig_bl, bl_result = demo_black_litterman(returns, max_sharpe)

    # Step 4: Monte Carlo Simulation
    # 步骤4：蒙特卡洛模拟
    fig_accum, fig_dist, mc_result = demo_monte_carlo_simulation(bl_result)

    # Step 5: Risk Metrics Analysis
    # 步骤5：风险指标分析
    fig_corr, metrics = demo_risk_metrics(returns)

    # Step 6: Summary and Recommendations
    # 步骤6：总结和建议
    print("\n" + "=" * 70)
    print("SUMMARY & RECOMMENDATIONS")
    print("总结与建议")
    print("=" * 70)

    print("\nBased on the analysis:")
    print("基于分析：")
    print(f"\n1. Optimal Portfolio (BL with Views) / 最优组合（含观点的BL）:")
    print(f"   - Expected Return / 预期收益率: {bl_result['return']:.2%}")
    print(f"   - Volatility / 波动率: {bl_result['volatility']:.2%}")
    print(f"   - Sharpe Ratio / 夏普比率: {bl_result['sharpe']:.2f}")

    print(f"\n2. Retirement Planning / 退休规划:")
    print(f"   - Survival Rate / 存活率: {mc_result['survival_rate']:.1%}")
    if mc_result['survival_rate'] >= 0.85:
        print("   - Status: ON TRACK / 状态：正常")
    else:
        print("   - Status: NEEDS ADJUSTMENT / 状态：需调整")

    print(f"\n3. Key Risk Metrics (US Equity) / 关键风险指标（美股）:")
    us_metrics = metrics[0]
    print(f"   - Sharpe Ratio / 夏普比率: {us_metrics['sharpe_ratio']:.2f}")
    print(f"   - 95% VaR (daily) / 95%在险价值（日度）: {us_metrics['var_95_daily']:.2%}")
    print(f"   - Max Drawdown / 最大回撤: {us_metrics.get('max_drawdown', 'N/A')}")

    # Save and open charts
    # 保存并打开图表
    figures = [fig_frontier, fig_mvo, fig_bl, fig_accum, fig_dist, fig_corr]
    filenames = [
        "01_efficient_frontier.html",
        "02_mvo_allocation.html",
        "03_bl_allocation.html",
        "04_accumulation_phase.html",
        "05_distribution_phase.html",
        "06_correlation_heatmap.html",
    ]

    save_and_open_figures(figures, filenames)

    print("\n" + "=" * 70)
    print("DEMO COMPLETED SUCCESSFULLY!")
    print("演示成功完成！")
    print("=" * 70)
    print("\nAll charts have been opened in your browser.")
    print("所有图表已在浏览器中打开。")
    print("\nFor interview preparation, you can discuss:")
    print("面试准备时，您可以讨论：")
    print("  1. How MVO constructs the efficient frontier")
    print("     MVO如何构建有效前沿")
    print("  2. How Black-Litterman incorporates investor views")
    print("     Black-Litterman如何纳入投资者观点")
    print("  3. How Monte Carlo simulates retirement outcomes")
    print("     蒙特卡洛如何模拟退休结果")
    print("  4. Risk metrics and their interpretations")
    print("     风险指标及其解读")


if __name__ == "__main__":
    main()
