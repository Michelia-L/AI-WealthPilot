"""
AI WealthPilot - Portfolio Optimizer
AI WealthPilot - 投资组合优化器

Implements the core quantitative engine for portfolio construction:
实现投资组合构建的核心量化引擎：

    1. Mean-Variance Optimization (MVO) — Markowitz framework
       均值-方差优化（MVO）—— Markowitz 框架
    2. Efficient Frontier construction
       有效前沿构建
    3. Black-Litterman model — Bayesian combination of equilibrium and views
       Black-Litterman 模型 —— 均衡收益与投资者观点的贝叶斯结合

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
        covariance_method: str = 'sample',
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
            covariance_method: Method to estimate covariance matrix ('sample', 'ledoit-wolf', 'oas').
                               协方差矩阵估计方法（'sample', 'ledoit-wolf', 'oas'）。
        """
        if covariance_method not in ['sample', 'ledoit-wolf', 'oas']:
            raise ValueError(
                f"Unknown covariance method: {covariance_method}. "
                f"Supported methods are 'sample', 'ledoit-wolf', 'oas'."
            )

        self.returns = returns
        # 资产数量 / Number of assets in the universe
        self.n_assets = returns.shape[1]
        # 资产名称列表 / List of asset names (column headers)
        self.asset_names = returns.columns.tolist()
        self.risk_free_rate = risk_free_rate
        self.covariance_method = covariance_method

        # ============================================================
        # 将日频统计量年化 / Annualize daily statistics
        # ============================================================
        # 年化预期收益率 = 日均收益率 × 年交易日数（通常252天）
        # Annualized expected return = daily mean return × trading days per year (typically 252)
        # 假设: 日收益率独立同分布（i.i.d.），这是 MVO 的标准假设
        # Assumption: daily returns are i.i.d. — a standard MVO assumption
        self.mean_returns = returns.mean() * TRADING_DAYS_PER_YEAR

        # 估算年化协方差矩阵
        # Estimate annualized covariance matrix
        if covariance_method == 'ledoit-wolf':
            from sklearn.covariance import ledoit_wolf
            shrunk_cov, _ = ledoit_wolf(returns.values)
            self.cov_matrix = pd.DataFrame(
                shrunk_cov,
                index=returns.columns,
                columns=returns.columns,
            ) * TRADING_DAYS_PER_YEAR
        elif covariance_method == 'oas':
            from sklearn.covariance import oas
            shrunk_cov, _ = oas(returns.values)
            self.cov_matrix = pd.DataFrame(
                shrunk_cov,
                index=returns.columns,
                columns=returns.columns,
            ) * TRADING_DAYS_PER_YEAR
        else:
            # 年化协方差矩阵 = 日协方差矩阵 × 年交易日数
            # Annualized covariance matrix = daily covariance matrix × trading days per year
            # 协方差矩阵是 MVO 的核心输入，描述了资产之间的联动关系
            # The covariance matrix is the core input of MVO, capturing co-movements between assets
            self.cov_matrix = returns.cov() * TRADING_DAYS_PER_YEAR

        # ============================================================
        # 协方差矩阵正则化和条件数检查
        # Covariance matrix regularization and condition number check
        # ============================================================
        # 检查协方差矩阵条件数，如果条件数过大则进行正则化
        # Check covariance matrix condition number, regularize if too large
        self.condition_number = self._check_condition_number()
        if self.condition_number > 1e10:
            # 条件数过大，进行正则化以提高数值稳定性
            # Condition number too large, regularize for numerical stability
            self.cov_matrix = self._regularize_covariance_matrix()
            self.is_regularized = True
        else:
            self.is_regularized = False

        # 缓存 numpy 数组格式以提高优化器迭代性能
        # Cache numpy array formats to optimize iteration speed
        self.cov_values = self.cov_matrix.values

    def _check_condition_number(self) -> float:
        """
        Check the condition number of the covariance matrix.
        检查协方差矩阵的条件数。

        The condition number measures how sensitive the matrix inversion is to small changes.
        A high condition number (> 1e10) indicates near-singularity, which can cause numerical instability.
        条件数衡量矩阵求逆对微小变化的敏感程度。
        高条件数（> 1e10）表示接近奇异，可能导致数值不稳定。

        CFA Reference / CFA 参考:
            CFA L3: Numerical stability is crucial for portfolio optimization.
            Ill-conditioned covariance matrices can lead to extreme and unreliable portfolio weights.
            CFA 三级：数值稳定性对投资组合优化至关重要。
            病态协方差矩阵可能导致极端且不可靠的投资组合权重。

        Returns:
            Condition number as float.
            条件数（浮点数）。
        """
        try:
            # 使用numpy计算条件数（2-范数条件数）
            # Calculate condition number using numpy (2-norm condition number)
            return np.linalg.cond(self.cov_matrix.values)
        except np.linalg.LinAlgError:
            # 如果计算失败，返回无穷大表示需要正则化
            # If calculation fails, return infinity to indicate regularization needed
            return float('inf')

    def _regularize_covariance_matrix(
        self,
        epsilon: float = 1e-6,
        method: str = 'diagonal',
    ) -> pd.DataFrame:
        """
        Regularize the covariance matrix to improve numerical stability.
        正则化协方差矩阵以提高数值稳定性。

        Two regularization methods are supported:
        支持两种正则化方法：

        1. Diagonal loading (diagonal): Add small positive value to diagonal
           对角加载（diagonal）：在对角线上添加小的正值
        2. Eigenvalue clipping (eigenvalue): Clip small eigenvalues to minimum threshold
           特征值裁剪（eigenvalue）：将小特征值裁剪到最小阈值

        Mathematical Formula / 数学公式:
            Diagonal loading: Σ_reg = Σ + ε × I
            Eigenvalue clipping: Σ_reg = V × max(Λ, ε) × V^T

            Where / 其中:
            - Σ = original covariance matrix (原始协方差矩阵)
            - ε = regularization parameter (正则化参数)
            - I = identity matrix (单位矩阵)
            - V = eigenvector matrix (特征向量矩阵)
            - Λ = eigenvalue diagonal matrix (特征值对角矩阵)

        CFA Reference / CFA 参考:
            CFA L3: Regularization helps prevent extreme portfolio allocations
            that result from estimation error in the covariance matrix.
            CFA 三级：正则化有助于防止因协方差矩阵估计误差导致的极端投资组合配置。

        Args:
            epsilon: Regularization parameter (正则化参数).
                     Larger values = more regularization (更大的值 = 更多正则化).
            method: Regularization method ('diagonal' or 'eigenvalue').
                    正则化方法（'diagonal' 或 'eigenvalue'）。

        Returns:
            Regularized covariance matrix as DataFrame.
            正则化后的协方差矩阵（DataFrame）。
        """
        cov_values = self.cov_matrix.values

        if method == 'diagonal':
            # 对角加载：Σ_reg = Σ + ε × I
            # Diagonal loading: Σ_reg = Σ + ε × I
            regularized = cov_values + epsilon * np.eye(self.n_assets)
        elif method == 'eigenvalue':
            # 特征值裁剪：将小特征值裁剪到最小阈值
            # Eigenvalue clipping: clip small eigenvalues to minimum threshold
            eigenvalues, eigenvectors = np.linalg.eigh(cov_values)
            # 将小于epsilon的特征值设置为epsilon
            # Set eigenvalues smaller than epsilon to epsilon
            regularized_eigenvalues = np.maximum(eigenvalues, epsilon)
            # 重构协方差矩阵：V × max(Λ, ε) × V^T
            # Reconstruct covariance matrix: V × max(Λ, ε) × V^T
            regularized = eigenvectors @ np.diag(regularized_eigenvalues) @ eigenvectors.T
        else:
            raise ValueError(f"Unknown regularization method: {method}")

        # 确保正则化后的矩阵是对称的
        # Ensure the regularized matrix is symmetric
        regularized = (regularized + regularized.T) / 2

        # 转换回DataFrame格式
        # Convert back to DataFrame format
        return pd.DataFrame(
            regularized,
            index=self.cov_matrix.index,
            columns=self.cov_matrix.columns,
        )

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
            np.dot(weights.T, np.dot(self.cov_values, weights))
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
                        0 ≤ w_i ≤ 1 (if no shorting) 禁止做空时权重在 [0,1] range

        We optimize by minimizing the portfolio variance (w^T * Sigma * w) instead of standard deviation
        and pass the analytical Jacobian (2 * Sigma * w) for numerical stability and a massive speedup.

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

        # 缓存的 numpy 数组，避免在迭代中多次提取和 Pandas Series 开销
        cov = self.cov_values
        mean_vals = self.mean_returns.values

        # 约束条件列表 / List of constraints
        # 约束1：权重之和 = 1（全额投资约束 / fully invested constraint）
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        # 约束2（可选）：组合收益率 = 目标收益率
        # Constraint 2 (optional): portfolio return = target return
        if target_return is not None:
            constraints.append({
                "type": "eq",
                "fun": lambda w: np.dot(w, mean_vals) - target_return,
            })

        # 使用 SLSQP 求解器进行约束优化
        # 目标函数：最小化组合方差 σ_p^2 = w^T × Σ × w
        # 雅可比导数：2 × Σ × w
        # Replaced standard deviation with variance for numerical stability and speed.
        # Minimizing variance yields identical weights to minimizing standard deviation.
        result = minimize(
            fun=lambda w: np.dot(w.T, np.dot(cov, w)),
            jac=lambda w: 2.0 * np.dot(cov, w),
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

    def resampled_efficient_frontier(
        self,
        n_points: int = 100,
        n_simulations: int = 1000,
        allow_short: bool = False,
    ) -> pd.DataFrame:
        """
        Compute the resampled efficient frontier using Michaud's method.
        使用Michaud方法计算重抽样有效前沿。

        Resampled MVO addresses the "garbage in, garbage out" problem of traditional MVO
        by averaging over multiple simulated samples of expected returns.
        重抽样MVO通过在多个模拟的预期收益样本上取平均，解决了传统MVO的"垃圾进，垃圾出"问题。

        Mathematical Foundation / 数学基础:
            1. Simulate N sets of expected returns from multivariate normal distribution
               从多元正态分布模拟N组预期收益
            2. For each simulation, compute the efficient frontier
               对每次模拟，计算有效前沿
            3. Average the frontiers point-by-point
               逐点平均所有前沿

            Formula / 公式:
                μ_i ~ N(μ_hat, Σ/T)
                w_resampled = (1/N) × Σ w_i

                Where / 其中:
                - μ_hat = sample mean return (样本均值收益)
                - Σ = covariance matrix (协方差矩阵)
                - T = number of observations (观测数量)
                - N = number of simulations (模拟次数)

        CFA Reference / CFA 参考:
            CFA L3 Asset Allocation: Resampled MVO (Michaud, 1998) is a practical
            solution to the estimation error problem in mean-variance optimization.
            It produces more diversified and stable portfolios than traditional MVO.
            CFA 三级资产配置：重抽样MVO（Michaud, 1998）是解决均值-方差优化中
            估计误差问题的实用方法。它比传统MVO产生更多元化和稳定的投资组合。

        References / 参考文献:
            - Michaud, R. (1998). Efficient Asset Management: A Practical Guide
              to Stock Portfolio Optimization and Asset Allocation.
            - Scherer, B. (2007). Portfolio Resampling: Review and Critique.

        Args:
            n_points: Number of points on each frontier (每个前沿上的点数).
            n_simulations: Number of Monte Carlo simulations (蒙特卡洛模拟次数).
                           More simulations = more stable results but slower computation.
                           更多模拟 = 更稳定的结果但计算更慢。
            allow_short: If True, allow short selling (如果为True，允许做空).

        Returns:
            DataFrame with resampled frontier: 'return', 'volatility', 'sharpe',
            and asset weights (averaged across simulations).
            返回重抽样前沿的DataFrame：收益率、波动率、夏普比率，
            以及资产权重（跨模拟平均）。
        """
        # 存储所有模拟的前沿结果
        # Store all simulation frontier results
        all_frontiers = []

        # 在循环外计算好协方差矩阵/T和日均收益，避免在循环中重复计算
        # Calculate daily covariance and mean outside the loop
        daily_cov = self.returns.cov().values
        daily_mean = self.returns.mean().values
        n_days = len(self.returns)
        cov_over_T = daily_cov / n_days

        # 临时覆盖以进行原地优化，保存原始预期收益
        # Temporarily override mean_returns to perform in-place optimization
        original_mean_returns = self.mean_returns

        try:
            for sim in range(n_simulations):
                # 从多元正态分布中抽样日预期收益
                # Sample daily expected returns from multivariate normal distribution
                # 使用样本均值和协方差矩阵/T（标准误差）
                # Use sample mean and covariance matrix/T (standard error)
                sampled_daily_returns = np.random.multivariate_normal(
                    daily_mean,
                    cov_over_T,
                )

                # 年化抽样收益
                # Annualize sampled returns
                sampled_annual_returns = sampled_daily_returns * TRADING_DAYS_PER_YEAR

                # 原地覆盖预期收益，避免在循环中重复实例化 PortfolioOptimizer
                # Mutate mean_returns in-place to avoid expensive optimizer reinstantiation
                self.mean_returns = pd.Series(
                    sampled_annual_returns,
                    index=self.asset_names,
                )

                # 计算该次模拟的有效前沿
                # Calculate efficient frontier for this simulation
                frontier = self.efficient_frontier(
                    n_points=n_points,
                    allow_short=allow_short,
                )

                if not frontier.empty:
                    all_frontiers.append(frontier)
        finally:
            # 恢复原始收益
            # Restore original expected returns
            self.mean_returns = original_mean_returns

        if not all_frontiers:
            # 如果没有成功的模拟，返回空DataFrame
            # If no successful simulations, return empty DataFrame
            return pd.DataFrame()

        # 计算重抽样前沿：在统一的收益率轴上对齐后取平均
        # Calculate resampled frontier: align on unified return axis then average
        # NOTE: Simple groupby(level=0) is INCORRECT because different simulations
        # may have different numbers of successful points (some target returns are
        # infeasible), so integer index i does NOT correspond to the same target
        # return across simulations. We must interpolate onto a common return axis.

        # Step 1: Build a unified return axis spanning the intersection of all frontiers
        # 步骤1: 构建跨越所有前沿交集的统一收益率轴
        all_ret_values = np.concatenate([f['return'].values for f in all_frontiers])
        unified_returns = np.linspace(all_ret_values.min(), all_ret_values.max(), n_points)

        # Step 2: For each frontier, interpolate all columns onto the unified axis
        # 步骤2: 对每个前沿，将所有列插值到统一轴上
        weight_cols = [c for c in all_frontiers[0].columns
                       if c not in ('return', 'volatility', 'sharpe')]
        interp_cols = ['volatility'] + weight_cols

        interpolated = []
        for frontier in all_frontiers:
            frontier_sorted = frontier.sort_values('return')
            row_data = {'return': unified_returns}
            for col in interp_cols:
                row_data[col] = np.interp(
                    unified_returns,
                    frontier_sorted['return'].values,
                    frontier_sorted[col].values,
                )
            interpolated.append(pd.DataFrame(row_data))

        # Step 3: Average across all simulations
        # 步骤3: 在所有模拟上取平均
        resampled_frontier = pd.concat(interpolated).groupby(level=0).mean()
        resampled_frontier['return'] = unified_returns

        # 重新计算夏普比率（因为平均后需要重新计算）
        # Recalculate Sharpe ratio (need to recalculate after averaging)
        if 'return' in resampled_frontier.columns and 'volatility' in resampled_frontier.columns:
            resampled_frontier['sharpe'] = (
                (resampled_frontier['return'] - self.risk_free_rate) /
                resampled_frontier['volatility']
            )

        return resampled_frontier

    def resampled_maximize_sharpe(
        self,
        n_simulations: int = 1000,
        allow_short: bool = False,
    ) -> dict:
        """
        Find the maximum Sharpe portfolio using resampled returns.
        使用重抽样收益寻找最大夏普组合。

        This method averages the optimal weights from multiple simulations,
        producing a more diversified and stable portfolio than traditional MVO.
        该方法对多次模拟的最优权重取平均，产生比传统MVO更多元化和稳定的投资组合。

        Args:
            n_simulations: Number of Monte Carlo simulations (蒙特卡洛模拟次数).
            allow_short: If True, allow short selling (如果为True，允许做空).

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
            返回字典：权重、收益率、波动率、夏普比率、成功标志。
        """
        # 存储所有模拟的最优权重
        # Store optimal weights from all simulations
        all_weights = []
        all_returns = []
        all_vols = []

        # 在循环外计算，避免重复开销
        daily_cov = self.returns.cov().values
        daily_mean = self.returns.mean().values
        n_days = len(self.returns)
        cov_over_T = daily_cov / n_days

        # 临时覆盖以进行原地优化，保存原始预期收益
        original_mean_returns = self.mean_returns

        try:
            for sim in range(n_simulations):
                # 抽样预期收益
                # Sample expected returns
                sampled_daily_returns = np.random.multivariate_normal(
                    daily_mean,
                    cov_over_T,
                )
                sampled_annual_returns = sampled_daily_returns * TRADING_DAYS_PER_YEAR

                # 原地覆盖预期收益，避免在循环中重复实例化 PortfolioOptimizer
                self.mean_returns = pd.Series(
                    sampled_annual_returns,
                    index=self.asset_names,
                )

                # 寻找最大夏普组合
                # Find maximum Sharpe portfolio
                result = self.maximize_sharpe(allow_short=allow_short)

                if result['success']:
                    weights = np.array(list(result['weights'].values()))
                    all_weights.append(weights)
                    all_returns.append(result['return'])
                    all_vols.append(result['volatility'])
        finally:
            # 恢复原始预期收益
            self.mean_returns = original_mean_returns

        if not all_weights:
            # 如果没有成功的模拟，返回等权组合
            # If no successful simulations, return equal weight portfolio
            equal_weights = np.ones(self.n_assets) / self.n_assets
            ret, vol, sharpe = self.portfolio_performance(equal_weights)
            return {
                'weights': dict(zip(self.asset_names, equal_weights)),
                'return': ret,
                'volatility': vol,
                'sharpe': sharpe,
                'success': False,
            }

        # 计算平均权重
        # Calculate average weights
        avg_weights = np.mean(all_weights, axis=0)

        # 确保权重加总为1（可能由于浮点运算略有偏差）
        # Ensure weights sum to 1 (may have slight deviation due to floating point)
        avg_weights = avg_weights / np.sum(avg_weights)

        # 计算平均组合的表现
        # Calculate performance of average portfolio
        ret, vol, sharpe = self.portfolio_performance(avg_weights)

        return {
            'weights': dict(zip(self.asset_names, avg_weights)),
            'return': ret,
            'volatility': vol,
            'sharpe': sharpe,
            'success': True,
            'n_simulations': n_simulations,
            'weight_std': np.std(all_weights, axis=0).tolist(),  # 权重标准差（不确定性度量）
        }

    def resampled_minimize_volatility(
        self,
        target_return: Optional[float] = None,
        n_simulations: int = 1000,
        allow_short: bool = False,
    ) -> dict:
        """
        Find the minimum volatility portfolio using resampled returns.
        使用重抽样收益寻找最小波动率组合。

        Similar to resampled_maximize_sharpe, this method averages the optimal weights
        from multiple simulations to construct a robust minimum volatility portfolio.
        This mitigates the estimation error in MVO inputs.

        CFA Reference / CFA 参考:
            CFA L3 Asset Allocation: Resampled MVO reduces the sensitivity of MVO
            to small changes in inputs by performing Monte Carlo simulations of returns
            and averaging the resulting optimal portfolios.

        Args:
            target_return: Optional target return constraint (年化目标收益率约束).
            n_simulations: Number of Monte Carlo simulations (蒙特卡洛模拟次数).
            allow_short: If True, allow short selling (如果为True，允许做空).

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success',
            'n_simulations', and 'weight_std'.
            返回字典，包含：权重、收益率、波动率、夏普比率、成功标志、模拟次数和权重标准差。
        """
        # Store optimal weights from all simulations
        all_weights = []
        all_returns = []
        all_vols = []

        # Get daily covariance and mean outside loop
        daily_cov = self.returns.cov().values
        daily_mean = self.returns.mean().values
        n_days = len(self.returns)
        cov_over_T = daily_cov / n_days

        # Temporarily override mean_returns for in-place optimization
        original_mean_returns = self.mean_returns

        try:
            for sim in range(n_simulations):
                # Sample expected returns from multivariate normal distribution
                # μ_i ~ N(μ_hat, Σ/T)
                sampled_daily_returns = np.random.multivariate_normal(
                    daily_mean,
                    cov_over_T,
                )
                sampled_annual_returns = sampled_daily_returns * TRADING_DAYS_PER_YEAR

                # Override mean_returns in-place to avoid expensive optimizer reinstantiation
                self.mean_returns = pd.Series(
                    sampled_annual_returns,
                    index=self.asset_names,
                )

                # Solve minimum volatility for this simulation
                # minimize w^T * Sigma * w
                result = self.minimize_volatility(
                    target_return=target_return,
                    allow_short=allow_short,
                )

                if result['success']:
                    weights = np.array(list(result['weights'].values()))
                    all_weights.append(weights)
                    all_returns.append(result['return'])
                    all_vols.append(result['volatility'])
        finally:
            # Restore original expected returns
            self.mean_returns = original_mean_returns

        if not all_weights:
            # Fallback: equal weight portfolio
            equal_weights = np.ones(self.n_assets) / self.n_assets
            ret, vol, sharpe = self.portfolio_performance(equal_weights)
            return {
                'weights': dict(zip(self.asset_names, equal_weights)),
                'return': ret,
                'volatility': vol,
                'sharpe': sharpe,
                'success': False,
            }

        # Average optimal weights across simulations: w_resampled = (1/N) * sum(w_i)
        avg_weights = np.mean(all_weights, axis=0)

        # Normalize weights to ensure they sum to 1.0 (correcting potential float errors)
        avg_weights = avg_weights / np.sum(avg_weights)

        # Compute resampled portfolio metrics under the original parameters
        ret, vol, sharpe = self.portfolio_performance(avg_weights)

        return {
            'weights': dict(zip(self.asset_names, avg_weights)),
            'return': ret,
            'volatility': vol,
            'sharpe': sharpe,
            'success': True,
            'n_simulations': n_simulations,
            'weight_std': np.std(all_weights, axis=0).tolist(),
        }

    def optimize_with_asset_class_constraints(
        self,
        asset_classes: dict,
        target_return: Optional[float] = None,
        allow_short: bool = False,
    ) -> dict:
        """
        Optimize portfolio with asset class weight constraints.
        使用资产类别权重约束优化投资组合。

        This method allows imposing minimum and maximum weight constraints
        on groups of assets (e.g., equity, bonds, alternatives).
        该方法允许对资产组（如股票、债券、另类资产）施加最小和最大权重约束。

        Mathematical Formulation / 数学公式:
            minimize    σ_p = √(w^T × Σ × w)       最小化组合波动率
            subject to  Σw_i = 1                     权重之和等于1
                        w^T × μ = target_return      收益率等于目标值（可选）
                        min_c ≤ Σ_{i∈c} w_i ≤ max_c  资产类别权重约束
                        0 ≤ w_i ≤ 1 (if no shorting) 禁止做空时权重在[0,1]范围

            Where / 其中:
            - c = asset class index (资产类别索引)
            - min_c = minimum weight for class c (类别c的最小权重)
            - max_c = maximum weight for class c (类别c的最大权重)
            - i ∈ c = asset i belongs to class c (资产i属于类别c)

        CFA Reference / CFA 参考:
            CFA L3 Asset Allocation: Real-world portfolio construction must consider
            investment constraints including asset class diversification requirements.
            Asset class constraints help maintain strategic alignment and prevent
            excessive concentration in any single asset class.
            CFA 三级资产配置：现实世界的投资组合构建必须考虑投资约束，
            包括资产类别多元化要求。资产类别约束有助于保持战略一致性，
            防止过度集中于任何单一资产类别。

        Args:
            asset_classes: Dict defining asset class constraints.
                           定义资产类别约束的字典。
                           Format / 格式:
                           {
                               'class_name': {
                                   'assets': [list of asset indices or names],
                                   'min': minimum weight (0.0 to 1.0),
                                   'max': maximum weight (0.0 to 1.0),
                               }
                           }
                           Example / 示例:
                           {
                               'equity': {'assets': ['US_EQUITY', 'INTL_EQUITY'], 'min': 0.3, 'max': 0.7},
                               'bonds': {'assets': ['US_BOND'], 'min': 0.2, 'max': 0.5},
                               'alternatives': {'assets': ['GOLD'], 'min': 0.0, 'max': 0.2},
                           }
            target_return: Optional target return constraint (可选的目标收益约束).
            allow_short: If True, allow short selling (如果为True，允许做空).

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success',
            and 'asset_class_weights' (weights per asset class).
            返回字典：权重、收益率、波动率、夏普比率、成功标志，
            以及'asset_class_weights'（每个资产类别的权重）。
        """
        n = self.n_assets

        # 初始权重：等权分配
        # Initial weights: equal allocation
        init_weights = np.ones(n) / n

        # 权重边界
        # Weight bounds
        bounds = ((-1, 1) if allow_short else (0, 1),) * n

        # 基本约束：权重之和 = 1
        # Basic constraint: weights sum to 1
        constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]

        # 目标收益约束（如果指定）
        # Target return constraint (if specified)
        if target_return is not None:
            constraints.append({
                'type': 'eq',
                'fun': lambda w: np.dot(w, self.mean_returns) - target_return,
            })

        # 资产类别约束
        # Asset class constraints
        asset_class_indices = {}
        for class_name, class_config in asset_classes.items():
            # 将资产名称转换为索引
            # Convert asset names to indices
            assets = class_config['assets']
            if isinstance(assets[0], str):
                # 如果是资产名称，转换为索引
                # If asset names, convert to indices
                indices = [self.asset_names.index(a) for a in assets]
            else:
                # 如果已经是索引
                # If already indices
                indices = assets

            asset_class_indices[class_name] = indices
            min_weight = class_config.get('min', 0.0)
            max_weight = class_config.get('max', 1.0)

            # 下界约束：Σ_{i∈c} w_i ≥ min_c
            # Lower bound constraint: Σ_{i∈c} w_i ≥ min_c
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, idx=indices, m=min_weight: sum(w[i] for i in idx) - m,
            })

            # 上界约束：Σ_{i∈c} w_i ≤ max_c
            # Upper bound constraint: Σ_{i∈c} w_i ≤ max_c
            constraints.append({
                'type': 'ineq',
                'fun': lambda w, idx=indices, m=max_weight: m - sum(w[i] for i in idx),
            })

        # 目标函数：最小化波动率
        # Objective function: minimize volatility
        def portfolio_volatility(w):
            return np.sqrt(np.dot(w.T, np.dot(self.cov_matrix, w)))

        # 运行优化
        # Run optimization
        result = minimize(
            fun=portfolio_volatility,
            x0=init_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
        )

        # 提取结果
        # Extract results
        weights = result.x
        ret, vol, sharpe = self.portfolio_performance(weights)

        # 计算每个资产类别的权重
        # Calculate weights per asset class
        asset_class_weights = {}
        for class_name, indices in asset_class_indices.items():
            asset_class_weights[class_name] = sum(weights[i] for i in indices)

        return {
            'weights': dict(zip(self.asset_names, weights)),
            'return': ret,
            'volatility': vol,
            'sharpe': sharpe,
            'success': result.success,
            'asset_class_weights': asset_class_weights,
        }


class BlackLittermanOptimizer(PortfolioOptimizer):
    """
    Black-Litterman Portfolio Optimizer.
    Black-Litterman 投资组合优化器。

    Extends the base PortfolioOptimizer with Black-Litterman model capabilities,
    allowing incorporation of investor views into the optimization process.
    扩展基础 PortfolioOptimizer，添加 Black-Litterman 模型功能，
    允许将投资者观点纳入优化过程。

    Mathematical Foundation / 数学基础:
        The BL model combines:
        BL模型结合了：

        1. Market Equilibrium Returns (from CAPM):
           市场均衡收益（来自CAPM）:
           Π = δ × Σ × w_mkt

           Where:
           其中：
           - δ (delta) = risk aversion coefficient (风险厌恶系数)
           - Σ = covariance matrix (协方差矩阵)
           - w_mkt = market capitalization weights (市值权重)

        2. Investor Views (from ViewProcessor):
           投资者观点（来自ViewProcessor）:
           - P matrix: pick matrix (选择矩阵)
           - Q vector: view returns (观点收益)
           - Omega: view uncertainty (观点不确定性)

        3. Posterior Returns (BL formula):
           后验收益（BL公式）:
           μ_BL = [(τΣ)^{-1} + P'Ω^{-1}P]^{-1} × [(τΣ)^{-1}Π + P'Ω^{-1}Q]

           Σ_BL = Σ + [(τΣ)^{-1} + P'Ω^{-1}P]^{-1}

    CFA Reference / CFA 参考:
        CFA L3 Asset Allocation: The Black-Litterman model overcomes the
        "garbage in, garbage out" problem of MVO by starting from a
        market equilibrium baseline and allowing investors to express
        views with varying confidence levels.
        CFA 三级资产配置：Black-Litterman 模型通过从市场均衡基准开始，
        并允许投资者表达具有不同置信度的观点，克服了 MVO 的
        "垃圾进，垃圾出"问题。

    References / 参考文献:
        - Black, F., & Litterman, R. (1992). Global Portfolio Optimization.
          Financial Analysts Journal, 48(5), 28-43.
        - Idzorek, T. (2005). A Step-By-Step Guide to the Black-Litterman Model.
          Ibbotson Associates.
    """

    def __init__(
        self,
        returns: pd.DataFrame,
        risk_free_rate: float = RISK_FREE_RATE,
        market_cap_weights: Optional[np.ndarray] = None,
        delta: Optional[float] = None,
        tau: float = 0.025,
        covariance_method: str = 'sample',
    ):
        """
        Initialize the Black-Litterman optimizer.
        初始化 Black-Litterman 优化器。

        Args:
            returns: DataFrame of asset daily returns.
                     资产日收益率 DataFrame。
            risk_free_rate: Annual risk-free rate.
                            年化无风险利率。
            market_cap_weights: Market capitalization weights (must sum to 1).
                                If None, equal weights are used.
                                市值权重（必须加总为1）。
                                如果为None，使用等权重。
            delta: Risk aversion coefficient. If None, estimated from
                   market data using: δ = (E[R_mkt] - R_f) / σ²_mkt
                   风险厌恶系数。如果为None，使用市场数据估计：
                   δ = (E[R_mkt] - R_f) / σ²_mkt
            tau: Uncertainty scaling factor for the prior (typically 0.025-0.05).
                 先验分布的不确定性缩放因子（通常为0.025-0.05）。
            covariance_method: Method to estimate covariance matrix ('sample', 'ledoit-wolf', 'oas').
                               协方差矩阵估计方法（'sample', 'ledoit-wolf', 'oas'）。
        """
        # Initialize parent class
        # 初始化父类
        super().__init__(
            returns=returns,
            risk_free_rate=risk_free_rate,
            covariance_method=covariance_method,
        )

        self.tau = tau

        # Set market cap weights (default to equal weights if not provided)
        # 设置市值权重（如果未提供则使用等权重）
        if market_cap_weights is not None:
            if len(market_cap_weights) != self.n_assets:
                raise ValueError(
                    f"market_cap_weights length ({len(market_cap_weights)}) "
                    f"must match number of assets ({self.n_assets}). / "
                    f"市值权重长度（{len(market_cap_weights)}）必须匹配资产数量（{self.n_assets}）。"
                )
            if abs(np.sum(market_cap_weights) - 1.0) > 1e-6:
                raise ValueError(
                    f"market_cap_weights must sum to 1.0, got {np.sum(market_cap_weights)}. / "
                    f"市值权重必须加总为1.0，当前为{np.sum(market_cap_weights)}。"
                )
            self.market_cap_weights = market_cap_weights
        else:
            # Default: equal weights (1/N)
            # 默认：等权重（1/N）
            self.market_cap_weights = np.ones(self.n_assets) / self.n_assets

        # Set risk aversion coefficient
        # 设置风险厌恶系数
        if delta is not None:
            self.delta = delta
        else:
            # Estimate delta from market data
            # 从市场数据估计delta
            # δ = (E[R_mkt] - R_f) / σ²_mkt
            market_return = np.dot(self.market_cap_weights, self.mean_returns)
            market_variance = float(
                self.market_cap_weights.T @ self.cov_matrix.values @ self.market_cap_weights
            )
            # Avoid division by zero
            # 避免除零
            if market_variance > 0:
                self.delta = (market_return - self.risk_free_rate) / market_variance
            else:
                self.delta = 2.5  # Default value if variance is zero

        # Compute market-implied equilibrium returns (Pi)
        # 计算市场隐含均衡收益（Pi）
        self.Pi = self.implied_equilibrium_returns()

        # BL posterior returns and covariance (computed after views are added)
        # BL后验收益和协方差（在添加观点后计算）
        self.mu_bl = None
        self.Sigma_bl = None
        self.views_applied = False

    def implied_equilibrium_returns(self) -> np.ndarray:
        """
        Calculate market-implied equilibrium excess returns.
        计算市场隐含均衡超额收益。

        Mathematical Formula / 数学公式:
            Π = δ × Σ × w_mkt

            Where:
            其中：
            - Π (Pi) = implied excess returns vector (隐含超额收益向量)
            - δ (delta) = risk aversion coefficient (风险厌恶系数)
            - Σ = covariance matrix (协方差矩阵)
            - w_mkt = market capitalization weights (市值权重)

        Interpretation / 解释:
            These are the returns that would clear the market if all investors
            held the market portfolio and had no views. The BL model uses this
            as the "prior" or "default" expectation.
            这些是如果所有投资者都持有市场组合且没有观点时，能够出清市场的收益。
            BL模型将其作为"先验"或"默认"预期。

        CFA Reference / CFA 参考:
            CFA L3: Under CAPM assumptions, the market portfolio is mean-variance
            efficient, so its expected returns reflect equilibrium.
            The implied returns represent the returns investors require
            to hold the current market portfolio.
            CFA 三级：在CAPM假设下，市场组合是均值-方差有效的，
            因此其预期收益反映了均衡。
            隐含收益代表投资者持有当前市场组合所要求的收益。

        Returns:
            Numpy array of implied excess returns (N,).
            隐含超额收益的Numpy数组（N,）。
        """
        Sigma = self.cov_matrix.values
        w_mkt = self.market_cap_weights

        # Π = δ × Σ × w_mkt
        Pi = self.delta * Sigma @ w_mkt

        return Pi

    def bl_posterior_returns(
        self,
        P: np.ndarray,
        Q: np.ndarray,
        Omega: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Calculate Black-Litterman posterior returns and covariance.
        计算 Black-Litterman 后验收益和协方差。

        Mathematical Formulas / 数学公式:
            Posterior Expected Returns / 后验预期收益:
            μ_BL = [(τΣ)^{-1} + P'Ω^{-1}P]^{-1} × [(τΣ)^{-1}Π + P'Ω^{-1}Q]

            Posterior Covariance / 后验协方差:
            Σ_BL = Σ + [(τΣ)^{-1} + P'Ω^{-1}P]^{-1}

            Where:
            其中：
            - τ (tau) = uncertainty scaling factor (不确定性缩放因子)
            - Σ = prior covariance matrix (先验协方差矩阵)
            - Π = market-implied equilibrium returns (市场隐含均衡收益)
            - P = pick matrix (K x N) (选择矩阵)
            - Q = view return vector (K x 1) (观点收益向量)
            - Ω = view uncertainty matrix (K x K, diagonal) (观点不确定性矩阵)

        Interpretation / 解释:
            The posterior mean μ_BL is a weighted average of:
            后验均值μ_BL是以下两者的加权平均：
            1. The prior (equilibrium returns Π)
               先验（均衡收益Π）
            2. The views (Q), weighted by their precision (1/Ω)
               观点（Q），按其精度（1/Ω）加权

            The weight depends on the relative uncertainty:
            权重取决于相对不确定性：
            - High confidence views (small Ω) → μ_BL closer to Q
              高置信度观点（小Ω）→ μ_BL更接近Q
            - Low confidence views (large Ω) → μ_BL closer to Π
              低置信度观点（大Ω）→ μ_BL更接近Π
            - No views (P=0, Ω→∞) → μ_BL = Π (revert to equilibrium)
              无观点（P=0, Ω→∞）→ μ_BL = Π（回归均衡）

        CFA Reference / CFA 参考:
            CFA L3: The BL posterior is a Bayesian combination of the
            market equilibrium (prior) and investor views (likelihood).
            The relative weight on each depends on their precision
            (inverse of variance).
            CFA 三级：BL后验是市场均衡（先验）和投资者观点（似然）
            的贝叶斯组合。每个的相对权重取决于其精度（方差的倒数）。

        Args:
            P: Pick matrix (K x N). Each row encodes one view.
               选择矩阵（K x N）。每行编码一个观点。
            Q: View returns vector (K,).
               观点收益向量（K,）。
            Omega: View uncertainty matrix (K x K, diagonal).
                   观点不确定性矩阵（K x K，对角矩阵）。

        Returns:
            Tuple of (mu_BL, Sigma_BL):
            - mu_BL: Posterior expected returns (N,)
              后验预期收益（N,）
            - Sigma_BL: Posterior covariance matrix (N x N)
              后验协方差矩阵（N x N）
        """
        Sigma = self.cov_matrix.values
        Pi = self.Pi
        tau = self.tau

        # Add small regularization to prevent singular matrices
        # 添加小的正则化项防止奇异矩阵
        epsilon = 1e-8
        tau_Sigma = tau * Sigma + epsilon * np.eye(self.n_assets)

        # Compute inverse matrices
        # 计算逆矩阵
        try:
            tau_Sigma_inv = np.linalg.inv(tau_Sigma)
            Omega_inv = np.linalg.inv(Omega)
        except np.linalg.LinAlgError:
            # Use pseudo-inverse as fallback
            # 使用伪逆作为备选
            tau_Sigma_inv = np.linalg.pinv(tau_Sigma)
            Omega_inv = np.linalg.pinv(Omega)

        # BL posterior mean formula
        # BL后验均值公式
        # μ_BL = [(τΣ)^{-1} + P'Ω^{-1}P]^{-1} × [(τΣ)^{-1}Π + P'Ω^{-1}Q]
        M = np.linalg.inv(tau_Sigma_inv + P.T @ Omega_inv @ P)
        mu_bl = M @ (tau_Sigma_inv @ Pi + P.T @ Omega_inv @ Q)

        # BL posterior covariance formula
        # BL后验协方差公式
        # Σ_BL = Σ + [(τΣ)^{-1} + P'Ω^{-1}P]^{-1}
        Sigma_bl = Sigma + M

        return mu_bl, Sigma_bl

    def apply_views(
        self,
        views: list,
    ) -> None:
        """
        Apply investor views to compute BL posterior.
        应用投资者观点以计算BL后验。

        This method processes the views using ViewProcessor and computes
        the BL posterior returns and covariance.
        本方法使用 ViewProcessor 处理观点，并计算 BL 后验收益和协方差。

        Args:
            views: List of ViewInput objects from src.portfolio.views.
                   ViewInput 对象列表（来自 src.portfolio.views）。
        """
        from src.portfolio.views import ViewProcessor

        # Create view processor and generate matrices
        # 创建观点处理器并生成矩阵
        view_processor = ViewProcessor(self.asset_names)
        P, Q, Omega = view_processor.generate_P_Q_omega(
            views, self.cov_matrix, self.tau
        )

        # Compute BL posterior
        # 计算BL后验
        self.mu_bl, self.Sigma_bl = self.bl_posterior_returns(P, Q, Omega)
        self.views_applied = True

    def bl_portfolio_performance(
        self,
        weights: np.ndarray,
    ) -> tuple[float, float, float]:
        """
        Calculate portfolio performance using BL posterior returns.
        使用BL后验收益计算组合表现。

        Similar to portfolio_performance(), but uses BL posterior returns
        instead of historical mean returns.
        类似于 portfolio_performance()，但使用BL后验收益而非历史均值收益。

        Args:
            weights: Portfolio weights (N,).
                     组合权重（N,）。

        Returns:
            Tuple of (return, volatility, sharpe).
            (收益率, 波动率, 夏普比率) 元组。
        """
        if not self.views_applied:
            raise ValueError(
                "Must call apply_views() before bl_portfolio_performance(). / "
                "必须先调用 apply_views() 才能使用 bl_portfolio_performance()。"
            )

        # BL posterior return: w' × μ_BL
        # BL后验收益：w' × μ_BL
        portfolio_return = float(np.dot(weights, self.mu_bl))

        # BL posterior volatility: √(w' × Σ_BL × w)
        # BL后验波动率：√(w' × Σ_BL × w)
        portfolio_volatility = float(
            np.sqrt(np.dot(weights.T, np.dot(self.Sigma_bl, weights)))
        )

        # Sharpe ratio
        # 夏普比率
        sharpe_ratio = (
            (portfolio_return - self.risk_free_rate) / portfolio_volatility
            if portfolio_volatility > 0
            else 0
        )

        return portfolio_return, portfolio_volatility, sharpe_ratio

    def bl_maximize_sharpe(self, allow_short: bool = False) -> dict:
        """
        Find the maximum Sharpe portfolio using BL posterior returns.
        使用BL后验收益寻找最大夏普组合。

        Args:
            allow_short: If True, allow short selling.
                         如果为True，允许做空。

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
            包含权重、收益率、波动率、夏普比率、成功标志的字典。
        """
        if not self.views_applied:
            raise ValueError(
                "Must call apply_views() before bl_maximize_sharpe(). / "
                "必须先调用 apply_views() 才能使用 bl_maximize_sharpe()。"
            )

        n = self.n_assets

        # Initial weights: equal allocation
        # 初始权重：等权分配
        init_weights = np.ones(n) / n

        # Weight bounds
        # 权重边界
        bounds = ((-1, 1) if allow_short else (0, 1),) * n

        # Fully invested constraint
        # 全额投资约束
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        # Objective: minimize negative Sharpe ratio using BL returns
        # 目标函数：使用BL收益最小化负夏普比率
        def neg_sharpe_bl(w):
            ret, vol, _ = self.bl_portfolio_performance(w)
            return -(ret - self.risk_free_rate) / vol if vol > 0 else 0

        # Run optimizer
        # 运行优化器
        result = minimize(
            fun=neg_sharpe_bl,
            x0=init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        # Extract results
        # 提取结果
        weights = result.x
        ret, vol, sharpe = self.bl_portfolio_performance(weights)

        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "success": result.success,
        }

    def bl_minimize_volatility(
        self,
        target_return: Optional[float] = None,
        allow_short: bool = False,
    ) -> dict:
        """
        Find the minimum volatility portfolio using BL posterior returns.
        使用BL后验收益寻找最小波动率组合。

        Args:
            target_return: Optional target return constraint.
                           可选的目标收益约束。
            allow_short: If True, allow short selling.
                         如果为True，允许做空。

        Returns:
            Dict with 'weights', 'return', 'volatility', 'sharpe', 'success'.
            包含权重、收益率、波动率、夏普比率、成功标志的字典。
        """
        if not self.views_applied:
            raise ValueError(
                "Must call apply_views() before bl_minimize_volatility(). / "
                "必须先调用 apply_views() 才能使用 bl_minimize_volatility()。"
            )

        n = self.n_assets

        # Initial weights
        # 初始权重
        init_weights = np.ones(n) / n

        # Weight bounds
        # 权重边界
        bounds = ((-1, 1) if allow_short else (0, 1),) * n

        # Constraints
        # 约束条件
        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]

        # Add target return constraint if specified
        # 如果指定了目标收益，添加约束
        if target_return is not None:
            constraints.append({
                "type": "eq",
                "fun": lambda w: np.dot(w, self.mu_bl) - target_return,
            })

        # Objective: minimize BL posterior volatility
        # 目标函数：最小化BL后验波动率
        def bl_volatility(w):
            return np.sqrt(np.dot(w.T, np.dot(self.Sigma_bl, w)))

        # Run optimizer
        # 运行优化器
        result = minimize(
            fun=bl_volatility,
            x0=init_weights,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
        )

        # Extract results
        # 提取结果
        weights = result.x
        ret, vol, sharpe = self.bl_portfolio_performance(weights)

        return {
            "weights": dict(zip(self.asset_names, weights)),
            "return": ret,
            "volatility": vol,
            "sharpe": sharpe,
            "success": result.success,
        }

    def bl_efficient_frontier(
        self,
        n_points: int = 100,
        allow_short: bool = False,
    ) -> pd.DataFrame:
        """
        Compute the BL efficient frontier.
        计算BL有效前沿。

        Args:
            n_points: Number of points on the frontier.
                      前沿上的点数。
            allow_short: If True, allow short selling.
                         如果为True，允许做空。

        Returns:
            DataFrame with columns: 'return', 'volatility', 'sharpe', and asset weights.
            包含列：收益率、波动率、夏普比率和资产权重的DataFrame。
        """
        if not self.views_applied:
            raise ValueError(
                "Must call apply_views() before bl_efficient_frontier(). / "
                "必须先调用 apply_views() 才能使用 bl_efficient_frontier()。"
            )

        # Determine return range from BL posterior
        # 从BL后验确定收益范围
        min_ret = float(self.mu_bl.min())
        max_ret = float(self.mu_bl.max())

        target_returns = np.linspace(min_ret, max_ret, n_points)

        frontier = []
        for target in target_returns:
            try:
                result = self.bl_minimize_volatility(
                    target_return=target, allow_short=allow_short
                )
                if result["success"]:
                    row = {
                        "return": result["return"],
                        "volatility": result["volatility"],
                        "sharpe": result["sharpe"],
                    }
                    row.update(result["weights"])
                    frontier.append(row)
            except Exception:
                continue

        return pd.DataFrame(frontier)

    def bl_summary(self) -> str:
        """
        Generate a summary comparing market-implied returns, views, and BL posterior.
        生成市场隐含收益、观点和BL后验的对比摘要。

        Returns:
            Formatted string with comparison table.
            包含对比表的格式化字符串。
        """
        if not self.views_applied:
            return "No views applied yet. Call apply_views() first."

        lines = [
            "Black-Litterman Model Summary",
            "=" * 60,
            "",
            f"Risk Aversion (δ): {self.delta:.4f}",
            f"Uncertainty Scale (τ): {self.tau}",
            f"Market Cap Weights: {dict(zip(self.asset_names, self.market_cap_weights))}",
            "",
            "Asset Returns Comparison / 资产收益率对比:",
            "-" * 60,
            f"{'Asset / 资产':<15} {'Equilibrium / 均衡':>18} {'BL Posterior / BL后验':>20} {'Adjustment / 调整':>18}",
        ]

        for i, name in enumerate(self.asset_names):
            eq_ret = self.Pi[i]
            bl_ret = self.mu_bl[i]
            adj = bl_ret - eq_ret
            lines.append(f"{name:<15} {eq_ret:>17.2%} {bl_ret:>19.2%} {adj:>+17.2%}")

        lines.append("")
        lines.append("Note / 注释:")
        lines.append("BL posterior blends equilibrium returns with your views.")
        lines.append("BL后验将均衡收益与您的观点相结合。")
        lines.append("Positive adjustment = model increased expected return vs equilibrium.")
        lines.append("正向调整 = 模型相对于均衡提高了预期收益。")

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
