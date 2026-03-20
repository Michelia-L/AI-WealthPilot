"""
AI WealthPilot - Portfolio Optimizer
AI WealthPilot - 投资组合优化器

Implements the core quantitative engine for portfolio construction:
实现投资组合构建的核心量化引擎：

    1. Mean-Variance Optimization (MVO) — Markowitz framework
       均值-方差优化（MVO）—— Markowitz 框架
    2. Efficient Frontier construction
       有效前沿构建
    3. Black-Litterman model (planned for future implementation)
       Black-Litterman 模型（计划在未来版本实现）

Key Concepts / 核心概念:
    MVO seeks to find portfolio weights that either:
    MVO 的目标是寻找投资组合权重，使得：
    - Minimize risk (volatility) for a given level of expected return
      在给定预期收益水平下最小化风险（波动率）
    - Maximize return for a given level of risk
      在给定风险水平下最大化收益
    - Maximize the Sharpe ratio (risk-adjusted return)
      最大化夏普比率（风险调整后收益）

References / 参考文献:
    - Markowitz, H. (1952). Portfolio Selection. The Journal of Finance.
    - CFA® Program Curriculum, Level III — Asset Allocation
      CFA® 课程教材，三级 —— 资产配置
    - CFA® Level I — Portfolio Management: Mean-Variance Framework
      CFA® 一级 —— 投资组合管理：均值-方差框架
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from typing import Optional

# 从项目配置中导入无风险利率和年交易日数
# Import risk-free rate and annual trading days from project config
from src.config import RISK_FREE_RATE, TRADING_DAYS_PER_YEAR


class PortfolioOptimizer:
    """
    Mean-Variance Portfolio Optimizer.
    均值-方差投资组合优化器。

    Given historical returns, computes optimal portfolio weights
    along the efficient frontier using Markowitz's Modern Portfolio Theory (MPT).

    基于历史收益率数据，运用 Markowitz 的现代投资组合理论（MPT），
    沿有效前沿计算最优投资组合权重。

    The optimizer uses scipy's SLSQP (Sequential Least Squares Programming)
    solver to handle the constrained optimization problem.
    优化器使用 scipy 的 SLSQP（序列最小二乘规划）求解器来处理约束优化问题。

    CFA Reference / CFA 参考:
        CFA L1 Portfolio Management: The efficient frontier represents the set
        of portfolios offering the highest expected return for each level of risk.
        CFA 一级投资组合管理：有效前沿代表在每个风险水平下提供最高预期收益的组合集合。
    """

    def __init__(
        self,
        returns: pd.DataFrame,
        risk_free_rate: float = RISK_FREE_RATE,
    ):
        """
        Initialize the optimizer with historical return data.
        使用历史收益率数据初始化优化器。

        Args:
            returns: DataFrame of asset returns (daily frequency).
                     Each column represents one asset, each row is one trading day.
                     资产日收益率 DataFrame。每列代表一个资产，每行是一个交易日。
            risk_free_rate: Annual risk-free rate, used for Sharpe ratio calculation.
                            Typically the yield on short-term government bonds (e.g., 10-year Treasury).
                            年化无风险利率，用于夏普比率计算。
                            通常使用短期国债收益率（如十年期美国国债）。
        """
        self.returns = returns
        # 资产数量 / Number of assets in the universe
        self.n_assets = returns.shape[1]
        # 资产名称列表 / List of asset names (column headers)
        self.asset_names = returns.columns.tolist()
        self.risk_free_rate = risk_free_rate

        # ============================================================
        # 将日频统计量年化 / Annualize daily statistics
        # ============================================================
        # 年化预期收益率 = 日均收益率 × 年交易日数（通常252天）
        # Annualized expected return = daily mean return × trading days per year (typically 252)
        # 假设: 日收益率独立同分布（i.i.d.），这是 MVO 的标准假设
        # Assumption: daily returns are i.i.d. — a standard MVO assumption
        self.mean_returns = returns.mean() * TRADING_DAYS_PER_YEAR

        # 年化协方差矩阵 = 日协方差矩阵 × 年交易日数
        # Annualized covariance matrix = daily covariance matrix × trading days per year
        # 协方差矩阵是 MVO 的核心输入，描述了资产之间的联动关系
        # The covariance matrix is the core input of MVO, capturing co-movements between assets
        self.cov_matrix = returns.cov() * TRADING_DAYS_PER_YEAR

    def portfolio_performance(self, weights: np.ndarray) -> tuple[float, float, float]:
        """
        Calculate annualized return, volatility, and Sharpe ratio
        for a given set of portfolio weights.
        根据给定的投资组合权重，计算年化收益率、波动率和夏普比率。

        Mathematical Formulas / 数学公式:
            Portfolio Return / 组合收益率:
                R_p = Σ(w_i × R_i) = w^T × μ
                其中 w_i 是资产 i 的权重，R_i 是资产 i 的预期收益率

            Portfolio Volatility / 组合波动率:
                σ_p = √(w^T × Σ × w)
                其中 Σ 是协方差矩阵
                这就是 Markowitz 的核心贡献：组合风险不仅取决于各资产的风险，
                还取决于资产之间的协方差（相关性）

            Sharpe Ratio / 夏普比率:
                S = (R_p - R_f) / σ_p
                衡量每承担一单位风险所获得的超额收益
                This measures the excess return earned per unit of total risk

        CFA Reference / CFA 参考:
            CFA L1: Sharpe ratio is the slope of the Capital Allocation Line (CAL).
            The tangency portfolio (max Sharpe) is where the CAL is tangent to
            the efficient frontier.
            CFA 一级：夏普比率是资本配置线（CAL）的斜率。
            切点组合（最大夏普比率）是 CAL 与有效前沿的切点。

        Args:
            weights: Array of portfolio weights (must sum to 1.0).
                     投资组合权重数组（必须加总为 1.0）。

        Returns:
            Tuple of (annualized_return, annualized_volatility, sharpe_ratio).
            返回元组：(年化收益率, 年化波动率, 夏普比率)。
        """
        # R_p = w^T × μ（组合收益率 = 权重向量与预期收益率向量的点积）
        # Portfolio return = dot product of weights and expected returns
        portfolio_return = np.dot(weights, self.mean_returns)

        # σ_p = √(w^T × Σ × w)（组合波动率 = 权重的二次型的平方根）
        # Portfolio volatility = square root of the quadratic form of weights and covariance
        portfolio_volatility = np.sqrt(
            np.dot(weights.T, np.dot(self.cov_matrix, weights))
        )

        # 夏普比率 = (组合收益率 - 无风险利率) / 组合波动率
        # Sharpe ratio = (portfolio return - risk-free rate) / portfolio volatility
        # 当波动率为 0 时返回 0，避免除零错误
        # Return 0 when volatility is 0 to avoid division by zero
        sharpe_ratio = (
            (portfolio_return - self.risk_free_rate) / portfolio_volatility
            if portfolio_volatility > 0
            else 0
        )
        return portfolio_return, portfolio_volatility, sharpe_ratio

    def minimize_volatility(
        self,
        target_return: Optional[float] = None,
        allow_short: bool = False,
    ) -> dict:
        """
        Find the minimum volatility portfolio, optionally targeting
        a specific return level.
        寻找最小波动率组合，可选地约束在特定收益率水平。

        This solves the classic Markowitz optimization problem:
        这是求解经典的 Markowitz 优化问题：

            minimize    σ_p = √(w^T × Σ × w)       最小化组合波动率
            subject to  Σw_i = 1                     权重之和等于 1（全额投资约束）
                        w^T × μ = target_return      收益率等于目标值（可选）
                        0 ≤ w_i ≤ 1 (if no shorting) 禁止做空时权重在 [0,1] 范围

        CFA Reference / CFA 参考:
            CFA L3 Asset Allocation: The Global Minimum-Variance Portfolio (GMV)
            is the leftmost point on the efficient frontier (lowest risk).
            When target_return is None, this function finds the GMV portfolio.
            CFA 三级资产配置：全局最小方差组合（GMV）是有效前沿上最左边的点（最低风险）。
            当 target_return 为 None 时，本函数寻找 GMV 组合。

        Args:
            target_return: If specified, find the min-vol portfolio at this return level.
                           This creates one point on the efficient frontier.
                           如果指定，则在该收益率水平下寻找最小波动率组合。
                           这会生成有效前沿上的一个点。
            allow_short: If True, allow negative weights (short selling).
                         In practice, many institutional investors face
                         long-only constraints.
                         如果为 True，允许负权重（做空）。
                         实际中，许多机构投资者面临只做多（long-only）约束。

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
            返回字典，包含：权重、收益率、波动率、夏普比率、优化是否成功。
        """
        n = self.n_assets

        # 初始权重：等权分配（1/N 策略），作为优化的起始点
        # Initial weights: equal-weight allocation (1/N strategy) as starting point
        init_weights = np.ones(n) / n

        # 设置权重边界：允许做空时 [-1, 1]，否则 [0, 1]
        # Set weight bounds: [-1, 1] if shorting allowed, else [0, 1]
        bounds = ((-1, 1) if allow_short else (0, 1),) * n

        # 约束条件列表 / List of constraints
        # 约束1：权重之和 = 1（全额投资约束 / fully invested constraint）
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        # 约束2（可选）：组合收益率 = 目标收益率
        # Constraint 2 (optional): portfolio return = target return
        if target_return is not None:
            constraints.append({
                "type": "eq",
                "fun": lambda w: np.dot(w, self.mean_returns) - target_return,
            })

        # 使用 SLSQP 求解器进行约束优化
        # 目标函数：最小化组合波动率 σ_p = √(w^T × Σ × w)
        # Use SLSQP solver for constrained optimization
        # Objective function: minimize portfolio volatility σ_p = √(w^T × Σ × w)
        result = minimize(
            fun=lambda w: np.sqrt(np.dot(w.T, np.dot(self.cov_matrix, w))),
            x0=init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        # 提取优化结果并计算组合表现指标
        # Extract optimization result and compute portfolio performance metrics
        weights = result.x
        ret, vol, sharpe = self.portfolio_performance(weights)

        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "success": result.success,  # 优化器是否成功收敛 / whether the optimizer converged
        }

    def maximize_sharpe(self, allow_short: bool = False) -> dict:
        """
        Find the maximum Sharpe ratio portfolio (tangency portfolio).
        寻找最大夏普比率组合（切点组合）。

        The tangency portfolio is the optimal risky portfolio:
        切点组合是最优风险组合：

            maximize    S = (R_p - R_f) / σ_p    最大化夏普比率
            subject to  Σw_i = 1                  权重之和等于 1

        In practice, we minimize the NEGATIVE Sharpe ratio (since scipy.optimize
        only supports minimization).
        实际实现中，我们最小化夏普比率的负值（因为 scipy.optimize 只支持最小化问题）。

        CFA Reference / CFA 参考:
            CFA L1/L3: The tangency portfolio lies at the point where the
            Capital Market Line (CML) is tangent to the efficient frontier.
            All rational investors should hold this portfolio of risky assets,
            combined with lending/borrowing at the risk-free rate
            (Two-Fund Separation Theorem / Tobin's Separation Theorem).

            CFA 一级/三级：切点组合位于资本市场线（CML）与有效前沿的切点处。
            所有理性投资者都应持有这个风险资产组合，
            再结合无风险利率的借贷来调整风险水平
            （两基金分离定理 / Tobin 分离定理）。

        Args:
            allow_short: If True, allow short selling.
                         如果为 True，允许做空。

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
            返回字典，包含：权重、收益率、波动率、夏普比率、优化是否成功。
        """
        n = self.n_assets

        # 初始权重：等权分配 / Initial weights: equal allocation
        init_weights = np.ones(n) / n

        # 权重边界 / Weight bounds
        bounds = ((-1, 1) if allow_short else (0, 1),) * n

        # 全额投资约束 / Fully invested constraint
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        def neg_sharpe(w):
            """
            Negative Sharpe ratio as the objective function.
            夏普比率的负值作为目标函数（因为 scipy 只做最小化）。
            
            最小化 -S 等价于最大化 S。
            Minimizing -S is equivalent to maximizing S.
            """
            ret, vol, _ = self.portfolio_performance(w)
            return -(ret - self.risk_free_rate) / vol if vol > 0 else 0

        # 运行优化求解器 / Run the optimization solver
        result = minimize(
            fun=neg_sharpe,
            x0=init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        # 提取结果 / Extract results
        weights = result.x
        ret, vol, sharpe = self.portfolio_performance(weights)

        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "success": result.success,
        }

    def efficient_frontier(
        self,
        n_points: int = 100,
        allow_short: bool = False,
    ) -> pd.DataFrame:
        """
        Compute the efficient frontier by finding minimum-volatility
        portfolios across a range of target returns.
        通过在一系列目标收益率上求解最小波动率组合来构建有效前沿。

        The efficient frontier is the upper portion of the minimum-variance
        frontier — portfolios below the Global Minimum-Variance (GMV) point
        are considered "inefficient" because a higher return can be achieved
        at the same risk level.

        有效前沿是最小方差前沿的上半部分——
        在全局最小方差（GMV）点以下的组合被认为是"无效的"，
        因为在相同风险水平下可以获得更高的收益率。

        CFA Reference / CFA 参考:
            CFA L1: The efficient frontier is the set of optimal portfolios
            that offer the highest expected return for a defined level of risk.
            CFA 一级：有效前沿是在给定风险水平下提供最高预期收益的最优组合集合。

        Args:
            n_points: Number of points to compute on the frontier.
                      More points = smoother curve but slower computation.
                      有效前沿上的计算点数。
                      点数越多曲线越平滑，但计算越慢。
            allow_short: If True, allow short selling.
                         如果为 True，允许做空。

        Returns:
            DataFrame with columns: 'return', 'volatility', 'sharpe',
            and one column per asset (weights at each point).
            返回 DataFrame，列包含：收益率、波动率、夏普比率，
            以及每个资产的权重列（对应前沿上的每个点）。
        """
        # 确定收益率的范围：从最低资产收益率到最高资产收益率
        # Determine the return range: from lowest to highest individual asset return
        min_ret = self.mean_returns.min()
        max_ret = self.mean_returns.max()

        # 在最低和最高收益率之间均匀取 n_points 个目标值
        # Create n_points evenly spaced target returns between min and max
        target_returns = np.linspace(min_ret, max_ret, n_points)

        frontier = []
        for target in target_returns:
            try:
                # 对每个目标收益率，求解最小波动率组合
                # For each target return, solve for the minimum volatility portfolio
                result = self.minimize_volatility(
                    target_return=target, allow_short=allow_short
                )
                # 只保留优化成功收敛的结果
                # Only keep results where the optimizer successfully converged
                if result["success"]:
                    row = {
                        "return": result["return"],
                        "volatility": result["volatility"],
                        "sharpe": result["sharpe"],
                    }
                    # 将各资产的权重也加入该行数据
                    # Also add each asset's weight to the row
                    row.update(result["weights"])
                    frontier.append(row)
            except Exception:
                # 某些目标收益率可能不可行（如超出约束范围），跳过
                # Some target returns may be infeasible (e.g., outside constraint bounds), skip
                continue

        return pd.DataFrame(frontier)

    def random_portfolios(self, n_portfolios: int = 5000) -> pd.DataFrame:
        """
        Generate random portfolio allocations for visualization
        (the 'cloud' around the efficient frontier).
        生成随机投资组合配置用于可视化
        （有效前沿周围的"散点云"）。

        Uses the Dirichlet distribution to generate random weights that
        automatically sum to 1.0 and are all non-negative.
        使用 Dirichlet 分布生成随机权重，自动满足加总为 1 且非负的条件。

        This visualization helps demonstrate the benefit of optimization:
        the efficient frontier lies on the upper-left boundary of this cloud,
        showing that optimized portfolios dominate random ones.
        这种可视化有助于展示优化的价值：
        有效前沿位于散点云的左上边界，说明优化后的组合优于随机组合。

        CFA Reference / CFA 参考:
            CFA L1: This visualization illustrates the "diversification benefit" —
            most random portfolios are sub-optimal (dominated by frontier portfolios).
            CFA 一级：这种可视化展示了"分散化收益"——
            大多数随机组合是次优的（被前沿组合所支配）。

        Args:
            n_portfolios: Number of random portfolios to generate.
                          要生成的随机组合数量。

        Returns:
            DataFrame with 'return', 'volatility', 'sharpe' columns.
            返回包含收益率、波动率、夏普比率的 DataFrame。
        """
        records = []
        for _ in range(n_portfolios):
            # Dirichlet 分布：参数全为 1 时等价于均匀分布在单纯形上
            # 生成的权重自动满足：所有 w_i ≥ 0 且 Σw_i = 1
            # Dirichlet distribution: with all params = 1, equivalent to uniform on the simplex
            # Generated weights automatically satisfy: all w_i ≥ 0 and Σw_i = 1
            weights = np.random.dirichlet(np.ones(self.n_assets))
            ret, vol, sharpe = self.portfolio_performance(weights)
            records.append({
                "return": ret,
                "volatility": vol,
                "sharpe": sharpe,
            })
        return pd.DataFrame(records)

    def summary(self) -> str:
        """
        Generate a human-readable summary of the optimization universe.
        生成优化资产池的可读性摘要。

        Displays the annualized expected returns and volatilities for each asset,
        providing a quick overview of the input data before optimization.
        展示每个资产的年化预期收益率和波动率，
        提供优化前输入数据的快速概览。

        Returns:
            Formatted string summary.
            格式化的字符串摘要。
        """
        lines = [
            f"Portfolio Optimizer — {self.n_assets} assets",
            f"Risk-free rate: {self.risk_free_rate:.2%}",
            "",
            "Annualized Expected Returns:",
        ]
        for name, ret in self.mean_returns.items():
            lines.append(f"  {name}: {ret:.2%}")

        lines.append("")
        lines.append("Annualized Volatilities:")
        for name in self.asset_names:
            # 从协方差矩阵的对角线元素提取方差，再开方得到波动率
            # Extract variance from diagonal of covariance matrix, then take square root for volatility
            # σ_i = √(Σ_{i,i})
            vol = np.sqrt(self.cov_matrix.loc[name, name])
            lines.append(f"  {name}: {vol:.2%}")

        return "\n".join(lines)


# ==========================================
# 主程序入口 - 使用合成数据进行快速演示
# Main entry point - Quick demo with synthetic data
# ==========================================
if __name__ == "__main__":
    # 设置随机种子以保证结果可复现
    # Set random seed for reproducibility
    np.random.seed(42)

    # 模拟 5 年的日收益率数据（252个交易日/年 × 5年 = 1260天）
    # Simulate 5 years of daily returns (252 trading days/year × 5 years = 1260 days)
    n_days = 252 * 5

    # 四种资产：美股、国际股票、债券、黄金
    # Four assets: US Equity, International Equity, Bonds, Gold
    assets = ["US Equity", "Intl Equity", "Bonds", "Gold"]

    # 生成随机收益率数据：
    # - 标准差约 1%/天（年化约 15.9%）
    # - 均值分别为 0.04%、0.03%、0.01%、0.02%/天（年化约 10%、7.5%、2.5%、5%）
    # Generate random return data:
    # - Std dev ≈ 1%/day (annualized ≈ 15.9%)
    # - Means: 0.04%, 0.03%, 0.01%, 0.02%/day (annualized ≈ 10%, 7.5%, 2.5%, 5%)
    returns_data = pd.DataFrame(
        np.random.randn(n_days, len(assets)) * 0.01
        + np.array([0.0004, 0.0003, 0.0001, 0.0002]),
        columns=assets,
    )

    # 创建优化器实例并打印资产池摘要
    # Create optimizer instance and print asset universe summary
    opt = PortfolioOptimizer(returns_data)
    print(opt.summary())

    # 求解最大夏普比率组合（切点组合）
    # Solve for the maximum Sharpe ratio portfolio (tangency portfolio)
    print("\n--- Maximum Sharpe Portfolio ---")
    max_sharpe = opt.maximize_sharpe()
    print(f"Return: {max_sharpe['return']:.2%}")
    print(f"Volatility: {max_sharpe['volatility']:.2%}")
    print(f"Sharpe: {max_sharpe['sharpe']:.2f}")
    print("Weights:")
    for asset, w in max_sharpe["weights"].items():
        print(f"  {asset}: {w:.1%}")
