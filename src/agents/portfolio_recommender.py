"""
AI WealthPilot - Portfolio Recommender Module

Integrates the quantitative portfolio optimization engine with client profiling
to generate personalized asset allocation recommendations based on risk scores.


"""

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from src.agents.profiler import (
    RISK_SCORE_BREAKPOINTS,
    ClientProfile,
    classify_risk_score,
)
from src.config import RISK_FREE_RATE, RISK_VOLATILITY_BANDS
from src.portfolio.optimizer import PortfolioOptimizer

# Goal priority ranking used to pick the primary (most important) goal.
# Replaces the previous `max(goals, key=lambda g: g.priority == "high")`,
# which collapsed priority to a bool and could not distinguish medium from low.
_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}

# Absolute tolerance when comparing a goal portfolio's volatility against the
# risk budget, absorbing SLSQP numeric noise around the frontier point.
_VOL_TOLERANCE = 1e-3


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
    # Goal feasibility vs. the risk budget: "" (no evaluable goal),
    # "on_track" (met within budget), "constrained" (needs more risk than
    # the budget allows), "infeasible" (beyond the asset universe).
    goal_status: str = ""
    goal_name: str = ""
    goal_required_return: Optional[float] = None
    # Per-goal feasibility detail (name, priority, years, target_amount,
    # allocated_assets, annual_contribution, required_return, status),
    # ordered by priority. Capital and ongoing savings are split across
    # goals proportionally to priority rank.
    goal_details: list = field(default_factory=list)


# Risk Score to Target Volatility Mapping

# Piecewise-linear interpolation over the canonical per-level bands
# (config.RISK_VOLATILITY_BANDS, P25 single source — shared with
# validate_saa enforcement and the IPS agent prompts). Segment
# boundaries stay aligned with RISK_SCORE_BREAKPOINTS from profiler.


def _get_target_volatility(risk_score: float) -> float:
    """Map client risk score to target portfolio volatility.

    Each risk level's score segment — delimited by
    ``RISK_SCORE_BREAKPOINTS`` — maps linearly onto that level's
    canonical volatility band, so the extremes land exactly on the band
    edges (score 1.0 → 4%, score 5.0 → 25%).

    Args:
        risk_score: Client's final risk score (1-5).

    Returns:
        Target annualized volatility.
    """
    # Clamp risk_score to valid range [1.0, 5.0]
    # Risk scores outside this range indicate uninitialized or invalid profiles
    risk_score = max(1.0, min(5.0, risk_score))

    bands = list(RISK_VOLATILITY_BANDS.values())
    edges = [1.0, *RISK_SCORE_BREAKPOINTS, 5.0]
    for i, (band_lo, band_hi) in enumerate(bands):
        seg_lo, seg_hi = edges[i], edges[i + 1]
        if risk_score <= seg_hi:
            frac = (risk_score - seg_lo) / (seg_hi - seg_lo)
            return band_lo + frac * (band_hi - band_lo)
    return bands[-1][1]  # Unreachable after clamping; defensive default.


# Core Recommendation Function


def _solve_at_target_volatility(
    optimizer: PortfolioOptimizer,
    target_vol: float,
    iterations: int = 40,
) -> dict:
    """Find the efficient portfolio whose volatility best matches ``target_vol``.

    The efficient frontier is monotonic above the GMV return (higher target
    return → higher volatility), so binary-searching ``target_return`` on the
    min-volatility solver lands on the frontier point at the volatility
    target — this is what makes the risk-score → volatility mapping an actual
    constraint rather than a documentation-only value.

    Args:
        optimizer: PortfolioOptimizer built on the returns universe.
        target_vol: Annualized volatility target (e.g. 0.10 for 10%).
        iterations: Binary-search depth.

    Returns:
        Optimizer result dict ('weights', 'return', 'volatility', 'sharpe',
        'success'). Falls back to the GMV portfolio when even it exceeds the
        target (universe cannot de-risk far enough).
    """
    gmv = optimizer.minimize_volatility()
    if not gmv.get("success", False) or gmv["volatility"] >= target_vol:
        return gmv

    lo, hi = gmv["return"], float(optimizer.mean_returns.max())
    best = gmv
    for _ in range(iterations):
        mid = (lo + hi) / 2
        res = optimizer.minimize_volatility(target_return=mid)
        if not res.get("success", False):
            hi = mid
            continue
        if res["volatility"] <= target_vol:
            best = res
            lo = mid
        else:
            hi = mid
    return best


# Goal Evaluation — Contribution-Aware TVM

# Upper bisection bound for _solve_required_return; a solved rate at this
# bound means the goal is unattainable and downstream evaluation reports
# 'infeasible' (no asset universe delivers ~1000% p.a.).
_UNATTAINABLE_RATE = 10.0


def _solve_required_return(
    target_amount: float,
    present_value: float,
    annual_contribution: float,
    years: int,
    iterations: int = 60,
) -> float:
    """Solve the contribution-aware TVM equation for the annual return r.

        PV·(1+r)^n + PMT·[((1+r)^n − 1)/r]  =  FV

    (ordinary annuity, end-of-year contributions). Reduces to the lump-sum
    formula r = (FV/PV)^(1/n) − 1 when PMT = 0. Ongoing savings therefore
    lower the return a goal actually requires.

    Args:
        target_amount: Future amount needed (FV).
        present_value: Capital allocated to the goal today (PV).
        annual_contribution: Yearly savings allocated to the goal (PMT ≥ 0).
        years: Years until the goal must be funded (n > 0).
        iterations: Bisection depth.

    Returns:
        0.0 when the goal is fundable without growth (PV + PMT·n ≥ FV);
        otherwise the solved rate; _UNATTAINABLE_RATE when even 1000% p.a.
        cannot fund it (a sentinel the goal evaluation maps to 'infeasible').
    """
    if years <= 0:
        return 0.0 if present_value >= target_amount else _UNATTAINABLE_RATE
    # Fundable without any growth?
    if present_value + annual_contribution * years >= target_amount:
        return 0.0

    def _funding_gap(rate: float) -> float:
        growth = (1 + rate) ** years
        fv_contributions = (
            annual_contribution * ((growth - 1) / rate)
            if rate > 0
            else annual_contribution * years
        )
        return present_value * growth + fv_contributions - target_amount

    lo, hi = 0.0, _UNATTAINABLE_RATE
    if _funding_gap(hi) < 0:
        return _UNATTAINABLE_RATE
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if _funding_gap(mid) <= 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def _evaluate_goal(
    optimizer: PortfolioOptimizer,
    gmv: dict,
    required_return: float,
    target_volatility: float,
) -> tuple:
    """Classify a goal's required return against the risk budget.

    Args:
        optimizer: PortfolioOptimizer built on the returns universe.
        gmv: Pre-computed global minimum-variance portfolio.
        required_return: Annual return the goal requires.
        target_volatility: Client's volatility budget (hard cap).

    Returns:
        (status, portfolio) where status is "on_track" (portfolio is the
        lowest-risk way to stay funded), "constrained" (attainable only by
        breaching the budget; portfolio is None), or "infeasible" (beyond
        the asset universe; portfolio is None).
    """
    if required_return <= gmv["return"]:
        # GMV already earns more than the goal needs, so it is the
        # lowest-risk on-track portfolio. (An equality-constrained solve
        # below the GMV return would land on the dominated lower branch of
        # the frontier: higher vol, lower return.)
        goal_portfolio = gmv
    else:
        goal_portfolio = optimizer.minimize_volatility(target_return=required_return)
    if not goal_portfolio.get("success", False):
        return "infeasible", None
    if goal_portfolio["volatility"] <= target_volatility + _VOL_TOLERANCE:
        return "on_track", goal_portfolio
    return "constrained", None


def recommend_portfolio(
    profile: ClientProfile,
    returns_data: pd.DataFrame,
    risk_free_rate: float = RISK_FREE_RATE,
    locale: str = "zh",
) -> PortfolioRecommendation:
    """Generate personalized portfolio recommendation based on client profile.

    Args:
        profile: Complete ClientProfile with risk assessment.
        returns_data: DataFrame of historical asset returns.
        risk_free_rate: Annual risk-free rate.
        locale: Rationale language ("zh" keeps the original bilingual wording
            verbatim, "en" is English-only).

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

    # Step 4: Solve the efficient portfolio at the target volatility
    result = _solve_at_target_volatility(optimizer, target_volatility)

    # Step 5: Evaluate goals against the risk budget.
    #
    # The risk-score → volatility mapping is a hard cap and is never
    # overridden: a goal-derived portfolio is accepted only when it stays
    # within the volatility budget (goals-based de-risking); otherwise the
    # risk-budget portfolio stands and the shortfall is surfaced through
    # goal_status instead of silently raising the client's risk exposure.
    #
    # Investable assets and ongoing savings (income − expenses) are split
    # across goals proportionally to priority rank (high=3, medium=2, low=1)
    # — a documented heuristic giving high-priority goals more funding weight.
    # Each goal's required return is solved with the contribution-aware TVM
    # equation, so regular savings lower the required return.
    goal_status = ""
    goal_name = ""
    goal_required_return: Optional[float] = None
    goal_details: list = []
    evaluable_goals = [g for g in profile.goals if g.years > 0 and g.target_amount > 0]
    if evaluable_goals:
        # Priority order (stable for ties); the primary goal drives the
        # portfolio-level decision.
        ordered_goals = sorted(evaluable_goals, key=_goal_priority_rank, reverse=True)
        primary_goal = ordered_goals[0]
        annual_savings = max(
            profile.financial.annual_income - profile.financial.annual_expenses,
            0.0,
        )
        total_weight = sum(max(_goal_priority_rank(g), 1) for g in ordered_goals)
        gmv = optimizer.minimize_volatility()
        for goal in ordered_goals:
            weight = max(_goal_priority_rank(goal), 1) / total_weight
            allocated = profile.financial.investable_assets * weight
            contribution = annual_savings * weight
            required = _solve_required_return(
                goal.target_amount, allocated, contribution, goal.years
            )
            status, goal_portfolio = _evaluate_goal(
                optimizer, gmv, required, target_volatility
            )
            goal_details.append(
                {
                    "name": goal.name,
                    "priority": goal.priority,
                    "years": goal.years,
                    "target_amount": float(goal.target_amount),
                    "allocated_assets": float(allocated),
                    "annual_contribution": float(contribution),
                    "required_return": float(required),
                    "status": status,
                }
            )
            if goal is primary_goal:
                goal_status, goal_name = status, goal.name
                goal_required_return = required
                if goal_portfolio is not None:
                    result = goal_portfolio

    # Step 6: Build recommendation
    weights = np.array(list(result["weights"].values()))
    asset_classes = list(result["weights"].keys())

    # Generate rationale
    rationale = _generate_rationale(
        profile,
        risk_level,
        target_volatility,
        result,
        goal_status=goal_status,
        goal_name=goal_name,
        goal_required_return=goal_required_return,
        goal_details=goal_details,
        locale=locale,
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
        goal_status=goal_status,
        goal_name=goal_name,
        goal_required_return=goal_required_return,
        goal_details=goal_details,
    )


def _generate_rationale(
    profile: ClientProfile,
    risk_level: str,
    target_volatility: float,
    optimization_result: dict,
    goal_status: str = "",
    goal_name: str = "",
    goal_required_return: Optional[float] = None,
    goal_details: Optional[list] = None,
    locale: str = "zh",
) -> str:
    """
    Generate human-readable rationale for the portfolio recommendation.
    生成投资组合推荐的人类可读理由。

    Args:
        profile: Client profile.
        risk_level: Classified risk level.
        target_volatility: Target volatility.
        optimization_result: MVO optimization result.
        goal_status: "", "on_track", "constrained", or "infeasible".
        goal_name: Name of the primary goal evaluated.
        goal_required_return: Annual return the primary goal requires.
        goal_details: Per-goal feasibility dicts (see PortfolioRecommendation).
        locale: "zh" keeps the original bilingual wording verbatim, "en" is
            English-only.

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
        rationale_parts.extend(
            [
                "⚠️ **Note**: There is a significant difference between your "
                "objective risk ability and subjective willingness. "
                "Per prudential guidelines, we use the lower score to protect you.",
                "",
            ]
        )

    # Add allocation explanation
    rationale_parts.extend(
        [
            "The recommended allocation is optimized using **Mean-Variance "
            "Optimization (MVO)** based on Modern Portfolio Theory (MPT):",
            "",
        ]
    )

    # List top allocations
    sorted_alloc = sorted(
        optimization_result["weights"].items(),
        key=lambda x: x[1],
        reverse=True,
    )
    for asset, weight in sorted_alloc[:5]:  # Top 5 assets
        if weight > 0.01:  # Only show > 1%
            rationale_parts.append(f"- **{asset}**: {weight:.1%}")

    # Goal feasibility section — the volatility budget is a hard cap, so any
    # gap between the goal's required return and the achievable return is
    # disclosed here instead of being silently overridden.
    if goal_status and goal_required_return is not None:
        en_only = locale == "en"
        rationale_parts.extend(
            [
                "",
                "**Goal Feasibility**:"
                if en_only
                else "**Goal Feasibility / 目标可行性**:",
                "",
            ]
        )
        req_text = (
            f"{goal_required_return:.1%}"
            if goal_required_return < _UNATTAINABLE_RATE
            else "≥1000%"
        )
        if goal_status == "on_track":
            en_text = (
                f"Your primary goal **{goal_name}** requires an estimated "
                f"**{req_text}** annual return (after counting your ongoing "
                f"savings), which the recommended portfolio meets within your "
                f"risk budget."
            )
            rationale_parts.append(
                en_text
                if en_only
                else f"{en_text} / 计入持续储蓄后,您的主要目标「{goal_name}」"
                f"预计需要年化 **{req_text}**,当前推荐组合可在您的风险预算内达成。"
            )
        elif goal_status == "constrained":
            en_text = (
                f"Your primary goal **{goal_name}** requires an estimated "
                f"**{req_text}** annual return (after counting your ongoing "
                f"savings), but staying within your "
                f"**{target_volatility:.1%}** volatility budget yields "
                f"approximately **{optimization_result['return']:.1%}**. The "
                f"recommendation respects your risk budget; closing the gap "
                f"requires higher risk tolerance, additional savings, or a "
                f"longer horizon."
            )
            rationale_parts.append(
                en_text
                if en_only
                else f"{en_text} / 计入持续储蓄后,您的主要目标「{goal_name}」"
                f"预计需要年化 **{req_text}**,但在 **{target_volatility:.1%}** 的"
                f"波动预算内预期收益约为 **{optimization_result['return']:.1%}**。"
                f"推荐组合严守您的风险预算;弥补缺口需要提高风险承受、增加储蓄或延长投资期限。"
            )
        elif goal_status == "infeasible":
            en_text = (
                f"Your primary goal **{goal_name}** requires an estimated "
                f"**{req_text}** annual return, which exceeds what the available "
                f"asset universe can deliver. Consider increasing ongoing "
                f"savings, extending the horizon, or revising the target "
                f"amount."
            )
            rationale_parts.append(
                en_text
                if en_only
                else f"{en_text} / 您的主要目标「{goal_name}」预计需要年化 **{req_text}**,"
                f"已超出现有资产类别可实现的范围;建议增加持续储蓄、延长投资期限"
                f"或调整目标金额。"
            )

        # Multi-goal breakdown: every evaluable goal gets its own required
        # return (on its priority-weighted share of capital and savings) and
        # its own feasibility status.
        if goal_details and len(goal_details) > 1:
            _STATUS_LABELS = {
                "on_track": ("on track within budget", "预算内可达成"),
                "constrained": ("beyond the risk budget", "超出风险预算"),
                "infeasible": ("beyond the asset universe", "超出资产可实现范围"),
            }
            rationale_parts.extend(
                [
                    "",
                    "All goals, by priority:"
                    if en_only
                    else "All goals, by priority / 全部目标(按优先级):",
                    "",
                ]
            )
            for detail in goal_details:
                en_label, zh_label = _STATUS_LABELS[detail["status"]]
                detail_req = (
                    f"{detail['required_return']:.1%}"
                    if detail["required_return"] < _UNATTAINABLE_RATE
                    else "≥1000%"
                )
                if en_only:
                    rationale_parts.append(
                        f"- **{detail['name']}**: requires ~{detail_req} p.a. — "
                        f"{en_label}"
                    )
                else:
                    rationale_parts.append(
                        f"- **{detail['name']}**: requires ~{detail_req} p.a. — "
                        f"{en_label} / 需年化约 {detail_req},{zh_label}"
                    )

    return "\n".join(rationale_parts)


# Utility Functions


def get_recommended_allocation_text(
    recommendation: PortfolioRecommendation, locale: str = "zh"
) -> str:
    """Format portfolio recommendation as readable markdown text.

    Args:
        recommendation: PortfolioRecommendation instance.
        locale: "zh" keeps the original bilingual headings verbatim, "en" is
            English-only.

    Returns:
        Formatted text string.
    """
    en = locale == "en"
    lines = [
        "## Recommended Portfolio" if en else "## Recommended Portfolio / 推荐投资组合",
        "",
        f"**{'Risk Level' if en else 'Risk Level / 风险等级'}**: {recommendation.risk_level}",
        f"**{'Expected Return' if en else 'Expected Return / 预期收益'}**: {recommendation.expected_return:.2%}",
        f"**{'Expected Volatility' if en else 'Expected Volatility / 预期波动率'}**: {recommendation.expected_volatility:.2%}",
        f"**{'Sharpe Ratio' if en else 'Sharpe Ratio / 夏普比率'}**: {recommendation.sharpe_ratio:.2f}",
        "",
        "### Asset Allocation" if en else "### Asset Allocation / 资产配置",
        "",
    ]

    for asset, weight in sorted(
        recommendation.suggested_allocation.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        if weight > 0.001:  # Only show > 0.1%
            lines.append(f"- {asset}: {weight:.1%}")

    lines.extend(
        [
            "",
            "### Rationale" if en else "### Rationale / 配置理由",
            "",
            recommendation.rationale,
        ]
    )

    return "\n".join(lines)
