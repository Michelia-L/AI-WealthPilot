"""Deterministic goal funding budgets, shared by planning and recommendations.

Manual budgets reserve recorded assets and annual savings before remaining
funding is split by priority. These are not actual balances or market forecasts.
"""

from dataclasses import dataclass
from math import fsum, isclose, isfinite
from typing import Literal

from src.agents.profiler import ClientProfile

_PRIORITY_RANK = {"high": 3, "medium": 2, "low": 1}
UNATTAINABLE_RATE = 10.0
MAX_PROJECTION_YEARS = 80


def _covers_target(amount: float, target: float) -> bool:
    return amount >= target or isclose(amount, target, rel_tol=1e-12, abs_tol=1e-8)


class GoalBudgetError(ValueError):
    """A budget cannot be applied; code is safe for API localization."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_goal_budgets(profile: ClientProfile) -> None:
    """Keep explicit budgets finite, complete and within available funding."""
    budgets = []
    for goal in profile.goals:
        budget = goal.funding_budget
        if budget is None:
            continue
        if goal.target_amount <= 0 or goal.years <= 0:
            raise GoalBudgetError("goals.budget_incomplete")
        if any(
            not isfinite(value) or value < 0
            for value in (budget.allocated_assets, budget.annual_contribution)
        ):
            raise GoalBudgetError("goals.budget_invalid")
        budgets.append(budget)
    for total, available, code in (
        (
            sum(b.allocated_assets for b in budgets),
            max(profile.financial.investable_assets, 0.0),
            "goals.budget_exceeds_assets",
        ),
        (
            sum(b.annual_contribution for b in budgets),
            max(
                profile.financial.annual_income - profile.financial.annual_expenses, 0.0
            ),
            "goals.budget_exceeds_savings",
        ),
    ):
        if total > available and not isclose(
            total, available, rel_tol=1e-12, abs_tol=1e-8
        ):
            raise GoalBudgetError(code)


def years_to_target_at_zero_return(
    target: float, assets: float, annual_contribution: float
) -> int | None:
    """First year-end reaching the nominal target at 0%, up to 80 years."""
    for years in range(MAX_PROJECTION_YEARS + 1):
        if _covers_target(assets + annual_contribution * years, target):
            return years
    return None


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
        return (
            0.0 if _covers_target(present_value, target_amount) else UNATTAINABLE_RATE
        )
    if _covers_target(present_value + annual_contribution * years, target_amount):
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
    allocation_method: Literal["priority_weighted", "manual"]
    years_to_target_at_zero_return: int | None
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
    """Reserve manual budgets, then split remaining funding by priority 3:2:1.

    Preserve profile order (including duplicate names). Incomplete goals stay
    visible without a budget and do not dilute the evaluable goals' funding.
    Ratios may exceed one; visualizations may cap the bar, not the value.
    """
    validate_goal_budgets(profile)
    total_weight = sum(
        max(goal_priority_rank(g.priority), 1)
        for g in profile.goals
        if g.target_amount > 0 and g.years > 0 and g.funding_budget is None
    )
    savings = max(
        profile.financial.annual_income - profile.financial.annual_expenses, 0.0
    )
    assets = max(profile.financial.investable_assets, 0.0)
    manual = [g.funding_budget for g in profile.goals if g.funding_budget is not None]
    remaining_assets = max(assets - fsum(b.allocated_assets for b in manual), 0.0)
    remaining_savings = max(savings - fsum(b.annual_contribution for b in manual), 0.0)
    plans = []
    for goal in profile.goals:
        progress = None
        if goal.target_amount > 0 and goal.years > 0:
            if goal.funding_budget is not None:
                allocated = goal.funding_budget.allocated_assets
                contribution = goal.funding_budget.annual_contribution
            else:
                weight = max(goal_priority_rank(goal.priority), 1) / total_weight
                allocated = remaining_assets * weight
                contribution = remaining_savings * weight
            required = solve_required_return(
                goal.target_amount, allocated, contribution, goal.years
            )
            if _covers_target(allocated, goal.target_amount):
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
                allocation_method=(
                    "manual" if goal.funding_budget is not None else "priority_weighted"
                ),
                years_to_target_at_zero_return=years_to_target_at_zero_return(
                    goal.target_amount, allocated, contribution
                ),
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


def goal_allocation_method(
    plans: list[GoalFundingPlan],
) -> Literal["priority_weighted", "manual", "mixed"]:
    """Summarize the methods actually used by the evaluable goals."""
    methods = {p.progress.allocation_method for p in plans if p.progress is not None}
    if len(methods) > 1:
        return "mixed"
    return "manual" if "manual" in methods else "priority_weighted"
