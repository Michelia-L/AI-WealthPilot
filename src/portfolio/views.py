"""
AI WealthPilot - Black-Litterman View Processor

Processes investor views into Black-Litterman model matrices (P, Q, Omega).
Supports both absolute and relative return views.

"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Union


# Bilingual user-facing strings (validation errors/warnings surfaced through
# the API as 422 details). zh keeps the Chinese half of the pre-i18n
# bilingual wording; kept here rather than in api/i18n.py because src/ must
# not import from the api/ transport shell.
_VIEW_STRINGS: dict[str, dict[str, str]] = {
    "invalid_views": {
        "zh": "检测到无效观点: {errors}",
        "en": "Invalid views detected: {errors}",
    },
    "relative_requires_short": {
        "zh": "观点{k}：相对观点需要设置 'asset_short'。",
        "en": "View {k}: relative view requires 'asset_short' to be set.",
    },
    "unknown_view_type": {
        "zh": "未知观点类型：'{view_type}'。必须是 'absolute' 或 'relative'。",
        "en": "Unknown view type: '{view_type}'. Must be 'absolute' or 'relative'.",
    },
    "multiple_absolute": {
        "zh": "对{asset}有多个绝对观点。观点将按精度混合。",
        "en": "Multiple absolute views on {asset}. Views will be blended by precision.",
    },
    "unknown_asset": {
        "zh": "未知资产：'{asset}'。可用：{names}",
        "en": "Unknown asset: '{asset}'. Available: {names}",
    },
    "confidence_out_of_range": {
        "zh": "观点{k}：置信度{confidence}%超出[0, 100]范围。",
        "en": "View {k}: confidence {confidence}% is outside [0, 100].",
    },
    "relative_cycle": {
        "zh": "相对观点存在循环矛盾：{cycle}。请检查观点一致性。",
        "en": "Circular contradiction among relative views: {cycle}. Please review view consistency.",
    },
    "prior_divergence": {
        "zh": "观点{k}（{asset} 目标 {view}）与先验 {prior} 背离超过 3 倍波动率，后验将大幅倾斜。",
        "en": "View {k} ({asset} target {view}) diverges from the prior {prior} by more than 3σ — the posterior will tilt heavily.",
    },
}


def _vs(key: str, locale: str, **fmt) -> str:
    """Render a bilingual view-processor string; unknown locales use zh."""
    template = _VIEW_STRINGS[key].get(locale) or _VIEW_STRINGS[key]["zh"]
    return template.format(**fmt) if fmt else template


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

    def __init__(self, asset_names: list[str], locale: str = "zh"):
        """Initialize the ViewProcessor.

        Args:
            asset_names: List of asset names in the portfolio universe.
            locale: Language for validation errors/warnings ("zh" / "en").
        """
        self.asset_names = asset_names
        self.n_assets = len(asset_names)
        self.locale = locale
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

        # Validate views before processing. Unknown assets are detected
        # directly (not by matching warning text) so the check is
        # locale-independent.
        unknown = [
            _vs("unknown_asset", self.locale, asset=v.asset_long, names=self.asset_names)
            for v in views
            if v.asset_long not in self.asset_to_idx
        ] + [
            _vs("unknown_asset", self.locale, asset=v.asset_short, names=self.asset_names)
            for v in views
            if v.view_type == 'relative' and v.asset_short not in self.asset_to_idx
        ]
        if unknown:
            raise ValueError(
                _vs("invalid_views", self.locale, errors="; ".join(unknown))
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
                        _vs("relative_requires_short", self.locale, k=k + 1)
                    )
                long_idx = self.asset_to_idx[view.asset_long]
                short_idx = self.asset_to_idx[view.asset_short]
                P[k, long_idx] = 1.0
                P[k, short_idx] = -1.0
                Q[k] = view.expected_return

            else:
                raise ValueError(
                    _vs("unknown_view_type", self.locale, view_type=view.view_type)
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
                warnings.append(_vs("multiple_absolute", self.locale, asset=asset))

        # Check for invalid asset names
        for v in views:
            if v.asset_long not in self.asset_to_idx:
                warnings.append(
                    _vs(
                        "unknown_asset",
                        self.locale,
                        asset=v.asset_long,
                        names=self.asset_names,
                    )
                )
            if v.view_type == 'relative' and v.asset_short not in self.asset_to_idx:
                warnings.append(
                    _vs(
                        "unknown_asset",
                        self.locale,
                        asset=v.asset_short,
                        names=self.asset_names,
                    )
                )

        # Check for invalid confidence values
        for i, v in enumerate(views):
            if not (0 <= v.confidence <= 100):
                warnings.append(
                    _vs(
                        "confidence_out_of_range",
                        self.locale,
                        k=i + 1,
                        confidence=v.confidence,
                    )
                )

        return warnings

    def detect_relative_cycles(self, views: list[ViewInput]) -> list[str]:
        """Detect circular contradictions among relative views.

        Builds the long→short directed graph (A>B is an edge A→B) and
        reports every strongly connected component with more than one
        member — a cycle means the views are mutually inconsistent
        (A>B>C>A can never hold). Direct flips (A>B, B>A) are 2-cycles.

        Args:
            views: List of ViewInput objects.

        Returns:
            Warning strings, one per contradictory cycle (empty if none).
        """
        edges: dict[str, set[str]] = {}
        for v in views:
            if v.view_type == "relative" and v.asset_short is not None:
                edges.setdefault(v.asset_long, set()).add(v.asset_short)

        # Tarjan SCC (iterative)
        index_of: dict[str, int] = {}
        lowlink: dict[str, int] = {}
        on_stack: set[str] = set()
        stack: list[str] = []
        counter = [0]
        sccs: list[list[str]] = []

        def strongconnect(root: str) -> None:
            work = [(root, iter(sorted(edges.get(root, ()))))]
            index_of[root] = lowlink[root] = counter[0]
            counter[0] += 1
            stack.append(root)
            on_stack.add(root)
            while work:
                node, it = work[-1]
                advanced = False
                for succ in it:
                    if succ not in index_of:
                        index_of[succ] = lowlink[succ] = counter[0]
                        counter[0] += 1
                        stack.append(succ)
                        on_stack.add(succ)
                        work.append((succ, iter(sorted(edges.get(succ, ())))))
                        advanced = True
                        break
                    elif succ in on_stack:
                        lowlink[node] = min(lowlink[node], index_of[succ])
                if not advanced:
                    work.pop()
                    if work:
                        parent = work[-1][0]
                        lowlink[parent] = min(lowlink[parent], lowlink[node])
                    if lowlink[node] == index_of[node]:
                        scc = []
                        while True:
                            member = stack.pop()
                            on_stack.discard(member)
                            scc.append(member)
                            if member == node:
                                break
                        if len(scc) > 1:
                            sccs.append(sorted(scc))

        for root in sorted(edges):
            if root not in index_of:
                strongconnect(root)

        return [
            _vs("relative_cycle", self.locale, cycle=" ↔ ".join(scc))
            for scc in sccs
        ]

    def divergence_warnings(
        self,
        views: list[ViewInput],
        prior: np.ndarray,
        sigma: np.ndarray,
    ) -> list[str]:
        """Warn on absolute views that diverge far from the prior.

        An absolute target more than 3σ away from the asset's prior
        return tilts the posterior heavily — surfaced as a warning for
        sanity-checking (not an error).

        Args:
            views: List of ViewInput objects.
            prior: Prior return vector Π (annualized, asset order).
            sigma: Per-asset annualized volatilities (diag of Σ).

        Returns:
            Warning strings (empty if all views are within 3σ).
        """
        warnings: list[str] = []
        for k, v in enumerate(views):
            if v.view_type != "absolute":
                continue
            idx = self.asset_to_idx.get(v.asset_long)
            if idx is None:
                continue  # unknown assets are rejected upstream
            if sigma[idx] > 0 and abs(v.expected_return - prior[idx]) > 3 * sigma[idx]:
                warnings.append(
                    _vs(
                        "prior_divergence",
                        self.locale,
                        k=k + 1,
                        asset=v.asset_long,
                        view=f"{v.expected_return:.1%}",
                        prior=f"{prior[idx]:.1%}",
                    )
                )
        return warnings
