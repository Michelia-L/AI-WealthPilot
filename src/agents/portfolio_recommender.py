"""
AI WealthPilot - Portfolio Recommender Module

Integrates the quantitative portfolio optimization engine with client profiling
to generate personalized asset allocation recommendations based on risk scores.

CFA Reference:
- CFA L3 Asset Allocation: Risk tolerance drives strategic asset allocation (SAA).
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional

from src.agents.profiler import ClientProfile, RiskProfile
from src.agents.profiler import RISK_SCORE_BREAKPOINTS, classify_risk_score
from src.portfolio.optimizer import PortfolioOptimizer
from src.config import RISK_FREE_RATE


# Goal priority ranking used to pick the primary (most important) goal.
# Replaces the previous `max(goals, key=lambda g: g.priority == "high")`,
# which collapsed priority to a bool and could not distinguish medium from low.
_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _goal_priority_rank(goal) -> int:
    """Numeric rank for a goal's priority; unknown/missing → lowest."""
    return _PRIORITY_RANK.get(getattr(goal, "priority", "low"), 0)


# Data Model — Portfolio Recommendation

@dataclass
class PortfolioRecommendation:
    """Represents a personalized portfolio recommendation with allocation and rationale."""
    risk_level: str = ""
    suggested_allocation: dict = field(default_factory=dict)
    expected_return: float = 0.0
    expected_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    rationale: str = ""
    asset_classes: list = field(default_factory=list)
    weights: np.ndarray = field(default_factory=lambda: np.array([]))


# Risk Score to Target Volatility Mapping

# Risk score → target volatility range (documentation constant).
# Breakpoints align with RISK_SCORE_BREAKPOINTS from profiler.
RISK_VOLATILITY_MAP = {
    # Conservative: 1.0-1.5 → 5-8% volatility
    "conservative": {"min_score": 1.0, "max_score": RISK_SCORE_BREAKPOINTS[0], "target_vol": 0.06},
    # Moderately Conservative: 1.5-2.5 → 8-12% volatility
    "moderately_conservative": {"min_score": RISK_SCORE_BREAKPOINTS[0], "max_score": RISK_SCORE_BREAKPOINTS[1], "target_vol": 0.10},
    # Moderate: 2.5-3.5 → 12-15% volatility
    "moderate": {"min_score": RISK_SCORE_BREAKPOINTS[1], "max_score": RISK_SCORE_BREAKPOINTS[2], "target_vol": 0.13},
    # Moderately Aggressive: 3.5-4.5 → 15-18% volatility
    "moderately_aggressive": {"min_score": RISK_SCORE_BREAKPOINTS[2], "max_score": RISK_SCORE_BREAKPOINTS[3], "target_vol": 0.16},
    # Aggressive: 4.5-5.0 → 18-22% volatility
    "aggressive": {"min_score": RISK_SCORE_BREAKPOINTS[3], "max_score": 5.0, "target_vol": 0.20},
}


def _get_target_volatility(risk_score: float) -> float:
    """Map client risk score to target portfolio volatility.

    Args:
        risk_score: Client's final risk score (1-5).

    Returns:
        Target annualized volatility.
    """
    # Clamp risk_score to valid range [1.0, 5.0]
    # Risk scores outside this range indicate uninitialized or invalid profiles
    risk_score = max(1.0, min(5.0, risk_score))

    # Linear interpolation between risk levels using shared breakpoints
    bp = RISK_SCORE_BREAKPOINTS  # [1.5, 2.5, 3.5, 4.5]

    if risk_score <= bp[0]:
        # Conservative: 5-8% volatility
        return 0.05 + (risk_score - 1.0) * 0.06
    elif risk_score <= bp[1]:
        # Moderately Conservative: 8-12% volatility
        return 0.08 + (risk_score - bp[0]) * 0.04
    elif risk_score <= bp[2]:
        # Moderate: 12-15% volatility
        return 0.12 + (risk_score - bp[1]) * 0.03
    elif risk_score <= bp[3]:
        # Moderately Aggressive: 15-18% volatility
        return 0.15 + (risk_score - bp[2]) * 0.03
    else:
        # Aggressive: 18-22% volatility
        return 0.18 + (risk_score - bp[3]) * 0.04


# Core Recommendation Function

def recommend_portfolio(
    profile: ClientProfile,
    returns_data: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
) -> PortfolioRecommendation:
    """Generate personalized portfolio recommendation based on client profile.

    Args:
        profile: Complete ClientProfile with risk assessment.
        returns_data: DataFrame of historical asset returns.
        risk_free_rate: Annual risk-free rate.

    Returns:
        PortfolioRecommendation containing suggested allocation and metrics.
    """
    # Step 1: Get risk score from profile
    risk_score = profile.risk_profile.final_score
    risk_level = classify_risk_score(risk_score).split(" / ")[0]

    # Step 2: Map to target volatility
    target_volatility = _get_target_volatility(risk_score)

    # Step 3: Initialize optimizer
    optimizer = PortfolioOptimizer(returns_data, risk_free_rate)

    # Step 4: Find optimal portfolio at target volatility
    result = optimizer.minimize_volatility()

    # Step 5: If target return is specified in goals, try to achieve it
    if profile.goals:
        # Calculate required return based on most important goal
        primary_goal = max(profile.goals, key=_goal_priority_rank)
        if primary_goal.years > 0:
            required_return = (
                (primary_goal.target_amount / max(profile.financial.investable_assets, 1))
                ** (1 / primary_goal.years)
                - 1
            )
            # Try to find portfolio with target return
            result_with_return = optimizer.minimize_volatility(
                target_return=required_return
            )
            if result_with_return.get("success", False):
                result = result_with_return

    # Step 6: Build recommendation
    weights = np.array(list(result["weights"].values()))
    asset_classes = list(result["weights"].keys())

    # Generate rationale
    rationale = _generate_rationale(
        profile, risk_level, target_volatility, result
    )

    return PortfolioRecommendation(
        risk_level=risk_level,
        suggested_allocation=result["weights"],
        expected_return=result["return"],
        expected_volatility=result["volatility"],
        sharpe_ratio=result["sharpe"],
        rationale=rationale,
        asset_classes=asset_classes,
        weights=weights,
    )


def _generate_rationale(
    profile: ClientProfile,
    risk_level: str,
    target_volatility: float,
    optimization_result: dict,
) -> str:
    """
    Generate human-readable rationale for the portfolio recommendation.
    生成投资组合推荐的人类可读理由。

    Args:
        profile: Client profile.
        risk_level: Classified risk level.
        target_volatility: Target volatility.
        optimization_result: MVO optimization result.

    Returns:
        Formatted rationale string.
    """
    rp = profile.risk_profile

    rationale_parts = [
        f"Based on your risk profile assessment (Ability: {rp.ability_score:.1f}/5, "
        f"Willingness: {rp.willingness_score:.1f}/5), "
        f"you are classified as **{risk_level}** investor.",
        "",
        f"Your target portfolio volatility is approximately "
        f"**{target_volatility:.1%}** annualized.",
        "",
    ]

    # Add conflict note if applicable
    if abs(rp.ability_score - rp.willingness_score) >= 1.0:
        rationale_parts.extend([
            "⚠️ **Note**: There is a significant difference between your "
            "objective risk ability and subjective willingness. "
            "Per CFA guidelines, we use the lower score to protect you.",
            "",
        ])

    # Add allocation explanation
    rationale_parts.extend([
        "The recommended allocation is optimized using **Mean-Variance "
        "Optimization (MVO)** based on Modern Portfolio Theory (MPT):",
        "",
    ])

    # List top allocations
    sorted_alloc = sorted(
        optimization_result["weights"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    for asset, weight in sorted_alloc[:5]:  # Top 5 assets
        if weight > 0.01:  # Only show > 1%
            rationale_parts.append(f"- **{asset}**: {weight:.1%}")

    return "\n".join(rationale_parts)


# Utility Functions

def get_recommended_allocation_text(recommendation: PortfolioRecommendation) -> str:
    """Format portfolio recommendation as readable markdown text.

    Args:
        recommendation: PortfolioRecommendation instance.

    Returns:
        Formatted text string.
    """
    lines = [
        f"## Recommended Portfolio / 推荐投资组合",
        f"",
        f"**Risk Level / 风险等级**: {recommendation.risk_level}",
        f"**Expected Return / 预期收益**: {recommendation.expected_return:.2%}",
        f"**Expected Volatility / 预期波动率**: {recommendation.expected_volatility:.2%}",
        f"**Sharpe Ratio / 夏普比率**: {recommendation.sharpe_ratio:.2f}",
        f"",
        f"### Asset Allocation / 资产配置",
        f"",
    ]

    for asset, weight in sorted(
        recommendation.suggested_allocation.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        if weight > 0.001:  # Only show > 0.1%
            lines.append(f"- {asset}: {weight:.1%}")

    lines.extend([
        f"",
        f"### Rationale / 配置理由",
        f"",
        recommendation.rationale,
    ])

    return "\n".join(lines)
