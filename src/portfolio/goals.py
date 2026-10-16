"""Deterministic goal funding budgets, shared by planning and recommendations.

Budgets are a priority-weighted model of recorded assets and annual savings.
They are not earmarked account balances, realized progress or forecasts.
"""

from dataclasses import dataclass
from typing import Literal

from src.agents.profiler import ClientProfile

_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
UNATTAINABLE_RATE = 10.0


def goal_priority_rank(priority: str) -> int:
    """Numeric priority for ordering; legacy unknown values sort below low."""
    return _PRIORITY_RANK.get(priority, 0)


def solve_required_return(
    target_amount: float,
    present_value: float,
    annual_contribution: float,
    years: int,
    iterations: int = 60,
) -> float:
    """Solve nominal TVM with constant, nonnegative end-of-year contributions.

    Returns zero when no growth is needed, otherwise bisects on [0, 10].
    The upper bound is a sentinel for an unsolved requirement, not a forecast.
    """
    if years <= 0:
        return 0.0 if present_value >= target_amount else UNATTAINABLE_RATE
    if present_value + annual_contribution * years >= target_amount:
        return 0.0

    def funding_gap(rate: float) -> float:
        growth = (1 + rate) ** years
        contributions = (
            annual_contribution * ((growth - 1) / rate)
            if rate > 0
            else annual_contribution * years
        )
        return present_value * growth + contributions - target_amount

    lo, hi = 0.0, UNATTAINABLE_RATE
    if funding_gap(hi) < 0:
        return UNATTAINABLE_RATE
    for _ in range(iterations):
        mid = (lo + hi) / 2
        if funding_gap(mid) <= 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


@dataclass(frozen=True)
class GoalFundingProgress:
    allocated_assets: float
    annual_contribution: float
    funding_ratio: float
    funding_gap: float
    required_return: float | None
    status: Literal[
        "covered", "covered_with_savings", "growth_required", "needs_funding"
    ]


@dataclass(frozen=True)
class GoalFundingPlan:
    name: str
    target_amount: float
    years: int
    priority: str
    progress: GoalFundingProgress | None


def plan_goal_funding(profile: ClientProfile) -> list[GoalFundingPlan]:
    """Split capital and positive annual savings once, using priority 3:2:1.

    Preserve profile order (including duplicate names). Incomplete goals stay
    visible without a budget and do not dilute the evaluable goals' funding.
    Ratios may exceed one; visualizations may cap the bar, not the value.
    """
    total_weight = sum(
        max(goal_priority_rank(g.priority), 1)
        for g in profile.goals
        if g.target_amount > 0 and g.years > 0
    )
    savings = max(
        profile.financial.annual_income - profile.financial.annual_expenses, 0.0
    )
    assets = max(profile.financial.investable_assets, 0.0)
    plans = []
    for goal in profile.goals:
        progress = None
        if goal.target_amount > 0 and goal.years > 0:
            weight = max(goal_priority_rank(goal.priority), 1) / total_weight
            allocated = assets * weight
            contribution = savings * weight
            required = solve_required_return(
                goal.target_amount, allocated, contribution, goal.years
            )
            if allocated >= goal.target_amount:
                status = "covered"
            elif required == 0:
                status = "covered_with_savings"
            elif required >= UNATTAINABLE_RATE:
                status = "needs_funding"
            else:
                status = "growth_required"
            progress = GoalFundingProgress(
                allocated_assets=allocated,
                annual_contribution=contribution,
                funding_ratio=allocated / goal.target_amount,
                funding_gap=max(goal.target_amount - allocated, 0.0),
                required_return=required if required < UNATTAINABLE_RATE else None,
                status=status,
            )
        plans.append(
            GoalFundingPlan(
                name=goal.name,
                target_amount=goal.target_amount,
                years=goal.years,
                priority=goal.priority,
                progress=progress,
            )
        )
    return plans
