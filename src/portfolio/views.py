"""
AI WealthPilot - Black-Litterman View Processor

Processes investor views into Black-Litterman model matrices (P, Q, Omega).
Supports both absolute and relative return views.

CFA Reference:
- CFA L3 Asset Allocation: Black-Litterman model.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Union


@dataclass
class ViewInput:
    """Single investor view input.

    Attributes:
        view_type: 'absolute' or 'relative'.
        asset_long: Ticker of target asset (or outperforming asset in relative views).
        asset_short: Ticker of underperforming asset (None for absolute views).
        expected_return: Expected annualized return as a decimal (e.g. 0.15).
        confidence: Investor confidence level in percentage (0 to 100).
    """

    # View type: 'absolute' or 'relative'
    view_type: str

    # Asset name for the view
    asset_long: str

    # For relative view: the "underperformed" asset (None for absolute views)
    asset_short: Union[str, None] = None

    # Expected return (annualized, e.g., 0.15 for 15%)
    expected_return: float = 0.0

    # Confidence level: 0-100% (will be converted to omega)
    confidence: float = 50.0


class ViewProcessor:
    """Process investor views into Black-Litterman model matrices (P, Q, Omega)."""

    def __init__(self, asset_names: list[str]):
        """Initialize the ViewProcessor.

        Args:
            asset_names: List of asset names in the portfolio universe.
        """
        self.asset_names = asset_names
        self.n_assets = len(asset_names)
        # Create mapping from asset name to index
        self.asset_to_idx = {name: idx for idx, name in enumerate(asset_names)}

    def generate_P_Q_omega(
        self,
        views: list[ViewInput],
        cov_matrix: pd.DataFrame,
        tau: float = 0.025,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Generate P, Q, and Omega matrices from investor views.

        Args:
            views: List of ViewInput objects.
            cov_matrix: Annualized covariance matrix (N x N).
            tau: Uncertainty scaling factor (typically 0.025-0.05).

        Returns:
            tuple[np.ndarray, np.ndarray, np.ndarray]: Matrices (P, Q, Omega).
        """
        K = len(views)
        N = self.n_assets

        # Validate views before processing
        warnings = self.validate_views(views)
        errors = [w for w in warnings if "Unknown asset" in w]
        if errors:
            raise ValueError(
                f"Invalid views detected / 检测到无效观点: {'; '.join(errors)}"
            )

        # Initialize P matrix and Q vector with zeros
        P = np.zeros((K, N))
        Q = np.zeros(K)

        # Fill P and Q based on view type
        for k, view in enumerate(views):
            if view.view_type == 'absolute':
                # Absolute view: P[k, asset_idx] = 1
                idx = self.asset_to_idx[view.asset_long]
                P[k, idx] = 1.0
                Q[k] = view.expected_return

            elif view.view_type == 'relative':
                # Relative view: P[k, long_idx] = 1, P[k, short_idx] = -1
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
        Omega = self._construct_omega(P, cov_matrix, views, tau)

        return P, Q, Omega

    def _construct_omega(
        self,
        P: np.ndarray,
        cov_matrix: pd.DataFrame,
        views: list[ViewInput],
        tau: float,
    ) -> np.ndarray:
        """Construct the diagonal Omega matrix using Idzorek's confidence method.

        Args:
            P: Pick matrix (K x N).
            cov_matrix: Annualized covariance matrix (N x N).
            views: List of ViewInput objects.
            tau: Uncertainty scaling factor.

        Returns:
            np.ndarray: Diagonal Omega matrix (K x K).
        """
        K = len(views)
        Sigma = cov_matrix.values

        # Initialize Omega as zero matrix
        Omega = np.zeros((K, K))

        for k in range(K):
            # Extract row k of P as column vector
            P_k = P[k, :].reshape(-1, 1)

            # Variance of the view: P_k' × (τΣ) × P_k
            view_variance = float((P_k.T @ (tau * Sigma) @ P_k).item())

            # Scale by confidence (Idzorek method)
            confidence = views[k].confidence / 100.0  # Convert 0-100 to 0-1

            # Handle edge cases for confidence
            if confidence > 0.99:
                # Very high confidence → very small omega
                omega_kk = view_variance * 0.01
            elif confidence < 0.01:
                # Very low confidence → very large omega
                omega_kk = view_variance * 100.0
            else:
                # Standard Idzorek formula
                omega_kk = (1.0 / confidence - 1.0) * view_variance

            Omega[k, k] = omega_kk

        return Omega

    def validate_views(self, views: list[ViewInput]) -> list[str]:
        """Validate views and return warnings for potential issues.

        Args:
            views: List of ViewInput objects.

        Returns:
            list[str]: Warning messages (empty if valid).
        """
        warnings = []

        # Check for multiple absolute views on the same asset
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
        for i, v in enumerate(views):
            if not (0 <= v.confidence <= 100):
                warnings.append(
                    f"View {i+1}: confidence {v.confidence}% is outside [0, 100]. / "
                    f"观点{i+1}：置信度{v.confidence}%超出[0, 100]范围。"
                )

        return warnings
