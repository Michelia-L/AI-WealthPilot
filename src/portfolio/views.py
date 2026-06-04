"""
AI WealthPilot - Black-Litterman View Processor
AI WealthPilot - Black-Litterman 观点处理器

Processes investor views into Black-Litterman model matrices (P, Q, Omega).
将投资者观点处理为 Black-Litterman 模型矩阵（P、Q、Omega）。

This module handles:
本模块处理：

    1. Absolute views: "Asset X will return 15%"
       绝对观点："资产X的预期收益为15%"
    2. Relative views: "Asset X will outperform Asset Y by 3%"
       相对观点："资产X将比资产Y高出3%"

Mathematical Background / 数学背景:
    The Black-Litterman model uses Bayesian inference to combine:
    Black-Litterman 模型使用贝叶斯推断结合：

    - Prior: Market equilibrium returns (from CAPM)
      先验：市场均衡收益（来自CAPM）
    - Likelihood: Investor views with uncertainty
      似然：带有不确定性的投资者观点

    The P matrix encodes which assets each view applies to.
    P矩阵编码了每个观点涉及的资产。

References / 参考文献:
    - Black, F., & Litterman, R. (1992). Global Portfolio Optimization.
      Financial Analysts Journal, 48(5), 28-43.
    - Idzorek, T. (2005). A Step-By-Step Guide to the Black-Litterman Model.
      Ibbotson Associates.
    - CFA® Program Curriculum, Level III — Asset Allocation: Black-Litterman Model
      CFA® 课程教材，三级 —— 资产配置：Black-Litterman 模型
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Union


@dataclass
class ViewInput:
    """
    Single investor view input.
    单个投资者观点输入。

    Supports both absolute and relative views:
    支持绝对观点和相对观点：

    - Absolute view: "Asset X will return 15%"
      绝对观点："资产X的预期收益为15%"
    - Relative view: "Asset X will outperform Asset Y by 3%"
      相对观点："资产X将比资产Y高出3%"

    CFA Reference / CFA 参考:
        CFA L3 Asset Allocation: Black-Litterman model allows investors
        to express views as absolute or relative return expectations,
        which are then combined with market equilibrium returns.
        CFA 三级资产配置：Black-Litterman 模型允许投资者将观点表达为
        绝对或相对收益预期，然后与市场均衡收益相结合。

    Attributes:
        view_type: 'absolute' or 'relative'
                   观点类型：'absolute'（绝对观点）或 'relative'（相对观点）
        asset_long: For absolute view: the asset name
                    For relative view: the "outperformed" asset
                    绝对观点：资产名称
                    相对观点："表现较好"的资产
        asset_short: For relative view: the "underperformed" asset (None for absolute)
                     相对观点："表现较差"的资产（绝对观点时为 None）
        expected_return: Expected return (annualized, e.g., 0.15 for 15%)
                         预期收益率（年化，如 0.15 表示 15%）
        confidence: Confidence level: 0-100% (will be converted to omega)
                    置信度：0-100%（将转换为 omega）
    """

    # View type: 'absolute' or 'relative'
    # 观点类型：'absolute'（绝对观点）或 'relative'（相对观点）
    view_type: str

    # Asset name for the view
    # 观点涉及的资产名称
    asset_long: str

    # For relative view: the "underperformed" asset (None for absolute views)
    # 相对观点："表现较差"的资产（绝对观点时为 None）
    asset_short: Union[str, None] = None

    # Expected return (annualized, e.g., 0.15 for 15%)
    # 预期收益率（年化，如 0.15 表示 15%）
    expected_return: float = 0.0

    # Confidence level: 0-100% (will be converted to omega)
    # 置信度：0-100%（将转换为 omega）
    confidence: float = 50.0


class ViewProcessor:
    """
    Process investor views into Black-Litterman model matrices.
    将投资者观点处理为 Black-Litterman 模型矩阵。

    Generates:
    生成：

        - P matrix: K x N pick matrix (观点选择矩阵)
        - Q vector: K x 1 expected return vector (观点收益向量)
        - Omega matrix: K x K uncertainty matrix (观点不确定性矩阵)

    CFA Reference / CFA 参考:
        CFA L3: The P matrix encodes which assets each view applies to.
        For absolute view on asset i: P has 1 in column i.
        For relative view "X outperforms Y": P has 1 in column X, -1 in column Y.
        CFA 三级：P矩阵编码了每个观点涉及的资产。
        对资产i的绝对观点：P矩阵第i列为1。
        相对观点"X优于Y"：P矩阵X列为1，Y列为-1。
    """

    def __init__(self, asset_names: list[str]):
        """
        Initialize the ViewProcessor.
        初始化观点处理器。

        Args:
            asset_names: List of asset names in the portfolio universe.
                         投资组合资产池中的资产名称列表。
        """
        self.asset_names = asset_names
        self.n_assets = len(asset_names)
        # Create mapping from asset name to index
        # 创建资产名称到索引的映射
        self.asset_to_idx = {name: idx for idx, name in enumerate(asset_names)}

    def generate_P_Q_omega(
        self,
        views: list[ViewInput],
        cov_matrix: pd.DataFrame,
        tau: float = 0.025,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Generate P, Q, and Omega matrices from investor views.
        从投资者观点生成 P、Q 和 Omega 矩阵。

        Mathematical Formulas / 数学公式:
            For each view k:
            对于每个观点k：

            Absolute view on asset i:
            对资产i的绝对观点:
                P[k, i] = 1, Q[k] = expected_return

            Relative view "X outperforms Y by d%":
            相对观点"X比Y高出d%":
                P[k, X] = 1, P[k, Y] = -1, Q[k] = d

            Omega construction (Idzorek method):
            Omega构建（Idzorek方法）:
                ω_kk = (1/confidence_k - 1) × (P_k × τΣ × P_k^T)

            Where:
            其中：

                - confidence_k ∈ [0, 1] is the investor's confidence in view k
                  confidence_k ∈ [0, 1] 是投资者对观点k的置信度
                - τ (tau) is the uncertainty scaling factor
                  τ（tau）是不确定性缩放因子
                - Σ (Sigma) is the covariance matrix
                  Σ（Sigma）是协方差矩阵

        Args:
            views: List of ViewInput objects.
                   ViewInput 对象列表。
            cov_matrix: Annualized covariance matrix (N x N).
                        年化协方差矩阵（N x N）。
            tau: Uncertainty scaling factor (typically 0.025-0.05).
                 不确定性缩放因子（通常为0.025-0.05）。

        Returns:
            Tuple of (P, Q, Omega) matrices.
            (P, Q, Omega) 矩阵元组。
        """
        K = len(views)
        N = self.n_assets

        # Validate views before processing / 处理前先验证观点
        warnings = self.validate_views(views)
        errors = [w for w in warnings if "Unknown asset" in w]
        if errors:
            raise ValueError(
                f"Invalid views detected / 检测到无效观点: {'; '.join(errors)}"
            )

        # Initialize P matrix and Q vector with zeros
        # 用零初始化 P 矩阵和 Q 向量
        P = np.zeros((K, N))
        Q = np.zeros(K)

        # Fill P and Q based on view type
        # 根据观点类型填充 P 和 Q
        for k, view in enumerate(views):
            if view.view_type == 'absolute':
                # Absolute view: P[k, asset_idx] = 1
                # 绝对观点：P[k, 资产索引] = 1
                idx = self.asset_to_idx[view.asset_long]
                P[k, idx] = 1.0
                Q[k] = view.expected_return

            elif view.view_type == 'relative':
                # Relative view: P[k, long_idx] = 1, P[k, short_idx] = -1
                # 相对观点：P[k, 多头索引] = 1, P[k, 空头索引] = -1
                if view.asset_short is None:
                    raise ValueError(
                        f"View {k+1}: relative view requires 'asset_short' to be set. / "
                        f"观点{k+1}：相对观点需要设置 'asset_short'。"
                    )
                long_idx = self.asset_to_idx[view.asset_long]
                short_idx = self.asset_to_idx[view.asset_short]
                P[k, long_idx] = 1.0
                P[k, short_idx] = -1.0
                Q[k] = view.expected_return

            else:
                raise ValueError(
                    f"Unknown view type: '{view.view_type}'. "
                    f"Must be 'absolute' or 'relative'. / "
                    f"未知观点类型：'{view.view_type}'。必须是 'absolute' 或 'relative'。"
                )

        # Construct Omega using Idzorek's confidence method
        # 使用Idzorek置信度方法构建Omega
        Omega = self._construct_omega(P, cov_matrix, views, tau)

        return P, Q, Omega

    def _construct_omega(
        self,
        P: np.ndarray,
        cov_matrix: pd.DataFrame,
        views: list[ViewInput],
        tau: float,
    ) -> np.ndarray:
        """
        Construct the diagonal Omega matrix using Idzorek's confidence method.
        使用Idzorek置信度方法构建对角Omega矩阵。

        Formula / 公式:
            ω_kk = (1/confidence_k - 1) × (P_k × τΣ × P_k^T)

        This method scales the uncertainty based on investor's stated confidence.
        Higher confidence → smaller omega → more weight on the view.
        该方法根据投资者声明的置信度缩放不确定性。
        置信度越高 → omega越小 → 观点权重越大。

        CFA Reference / CFA 参考:
            CFA L3: The confidence parameter reflects the investor's conviction.
            Omega represents the variance of the view itself — high confidence
            means low variance (precise view).
            CFA 三级：置信度参数反映投资者的确信程度。
            Omega代表观点本身的方差——高置信度意味着低方差（精确观点）。

        Args:
            P: Pick matrix (K x N).
               选择矩阵（K x N）。
            cov_matrix: Annualized covariance matrix (N x N).
                        年化协方差矩阵（N x N）。
            views: List of ViewInput objects.
                   ViewInput 对象列表。
            tau: Uncertainty scaling factor.
                 不确定性缩放因子。

        Returns:
            Diagonal Omega matrix (K x K).
            对角Omega矩阵（K x K）。
        """
        K = len(views)
        Sigma = cov_matrix.values

        # Initialize Omega as zero matrix
        # 用零矩阵初始化Omega
        Omega = np.zeros((K, K))

        for k in range(K):
            # Extract row k of P as column vector
            # 提取P的第k行作为列向量
            P_k = P[k, :].reshape(-1, 1)

            # Variance of the view: P_k' × (τΣ) × P_k
            # 观点的方差：P_k' × (τΣ) × P_k
            view_variance = float((P_k.T @ (tau * Sigma) @ P_k).item())

            # Scale by confidence (Idzorek method)
            # 按置信度缩放（Idzorek方法）
            confidence = views[k].confidence / 100.0  # Convert 0-100 to 0-1

            # Handle edge cases for confidence
            # 处理置信度的边界情况
            if confidence > 0.99:
                # Very high confidence → very small omega
                # 非常高的置信度 → 非常小的omega
                omega_kk = view_variance * 0.01
            elif confidence < 0.01:
                # Very low confidence → very large omega
                # 非常低的置信度 → 非常大的omega
                omega_kk = view_variance * 100.0
            else:
                # Standard Idzorek formula
                # 标准Idzorek公式
                omega_kk = (1.0 / confidence - 1.0) * view_variance

            Omega[k, k] = omega_kk

        return Omega

    def validate_views(self, views: list[ViewInput]) -> list[str]:
        """
        Validate views and return warnings for potential issues.
        验证观点并返回潜在问题的警告。

        Checks for:
        检查：

            - Multiple absolute views on the same asset
              对同一资产的多个绝对观点
            - Invalid asset names
              无效的资产名称
            - Invalid confidence values
              无效的置信度值

        Args:
            views: List of ViewInput objects.
                   ViewInput 对象列表。

        Returns:
            List of warning messages (empty if no issues).
            警告消息列表（如果没有问题则为空）。
        """
        warnings = []

        # Check for multiple absolute views on the same asset
        # 检查对同一资产的多个绝对观点
        absolute_views = [v for v in views if v.view_type == 'absolute']
        asset_view_count = {}
        for v in absolute_views:
            asset_view_count[v.asset_long] = asset_view_count.get(v.asset_long, 0) + 1

        for asset, count in asset_view_count.items():
            if count > 1:
                warnings.append(
                    f"Multiple absolute views on {asset}. "
                    f"Views will be blended by precision. / "
                    f"对{asset}有多个绝对观点。观点将按精度混合。"
                )

        # Check for invalid asset names
        # 检查无效的资产名称
        for v in views:
            if v.asset_long not in self.asset_to_idx:
                warnings.append(
                    f"Unknown asset: '{v.asset_long}'. "
                    f"Available: {self.asset_names} / "
                    f"未知资产：'{v.asset_long}'。可用：{self.asset_names}"
                )
            if v.view_type == 'relative' and v.asset_short not in self.asset_to_idx:
                warnings.append(
                    f"Unknown asset: '{v.asset_short}'. "
                    f"Available: {self.asset_names} / "
                    f"未知资产：'{v.asset_short}'。可用：{self.asset_names}"
                )

        # Check for invalid confidence values
        # 检查无效的置信度值
        for i, v in enumerate(views):
            if not (0 <= v.confidence <= 100):
                warnings.append(
                    f"View {i+1}: confidence {v.confidence}% is outside [0, 100]. / "
                    f"观点{i+1}：置信度{v.confidence}%超出[0, 100]范围。"
                )

        return warnings
