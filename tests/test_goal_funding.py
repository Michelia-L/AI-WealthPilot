"""Funding is conserved across goals and never presented as realized progress."""

import pytest

from src.agents.profiler import ClientProfile, FinancialSituation, InvestmentGoal
from src.portfolio.goals import (
    GoalBudgetError,
    goal_allocation_method,
    plan_goal_funding,
    solve_required_return,
    years_to_target_at_zero_return,
)


def profile(goals, *, assets=600_000, income=120_000, expenses=60_000):
    return ClientProfile(
        financial=FinancialSituation(
            investable_assets=assets, annual_income=income, annual_expenses=expenses
        ),
        goals=[InvestmentGoal(**g) for g in goals],
    )


def test_priority_budgets_conserve_assets_and_savings_without_merging_names():
    client = profile(
        [
            {"name": "Same", "priority": p, "target_amount": 1_000_000, "years": 10}
            for p in ("low", "high", "medium")
        ]
    )
    plans = plan_goal_funding(client)
    assert [p.priority for p in plans] == ["low", "high", "medium"]
    assert [p.progress.allocated_assets for p in plans] == pytest.approx(
        [100_000, 300_000, 200_000]
    )
    assert sum(p.progress.allocated_assets for p in plans) == pytest.approx(600_000)
    assert sum(p.progress.annual_contribution for p in plans) == pytest.approx(60_000)
    assert client.goals[0].target_amount == 1_000_000


@pytest.mark.parametrize(
    "assets,income,expenses,target,years,status,ratio,required",
    [
        (300_000, 0, 0, 200_000, 10, "covered", 1.5, 0.0),
        (100_000, 20_000, 0, 200_000, 5, "covered_with_savings", 0.5, 0.0),
        (100_000, 0, 10_000, 200_000, 2, "growth_required", 0.5, 2**0.5 - 1),
        (0, 0, 0, 200_000, 10, "needs_funding", 0.0, None),
        # The only contribution arrives at the horizon, so it cannot grow.
        (0, 1_000, 0, 2_000, 1, "needs_funding", 0.0, None),
    ],
)
def test_funding_states_and_zero_capital_or_savings(
    assets, income, expenses, target, years, status, ratio, required
):
    plan = plan_goal_funding(
        profile(
            [{"name": "Goal", "target_amount": target, "years": years}],
            assets=assets,
            income=income,
            expenses=expenses,
        )
    )[0].progress
    assert plan.status == status
    assert plan.funding_ratio == pytest.approx(ratio)
    assert plan.funding_gap == max(target - assets, 0)
    assert plan.annual_contribution == max(income - expenses, 0)
    if required is None:
        assert plan.required_return is None
    else:
        assert plan.required_return == pytest.approx(required)


def test_incomplete_goals_are_visible_and_do_not_dilute_valid_budgets():
    plans = plan_goal_funding(
        profile(
            [
                {"name": "No target", "years": 10},
                {"name": "No horizon", "target_amount": 1_000_000},
                {"name": "Valid", "target_amount": 1_000_000, "years": 10},
            ]
        )
    )
    assert [p.name for p in plans] == ["No target", "No horizon", "Valid"]
    assert plans[0].progress is None
    assert plans[1].progress is None
    assert plans[2].progress.allocated_assets == 600_000
    assert plans[2].progress.annual_contribution == 60_000
    assert plan_goal_funding(profile([])) == []


def test_savings_only_can_fund_a_future_goal_and_unknown_priority_gets_low_weight():
    plans = plan_goal_funding(
        profile(
            [
                {
                    "name": "Legacy",
                    "priority": "unknown",
                    "target_amount": 10_000,
                    "years": 2,
                },
                {"name": "Low", "priority": "low", "target_amount": 10_000, "years": 2},
            ],
            assets=0,
            income=10_000,
            expenses=0,
        )
    )
    assert all(p.progress.funding_ratio == 0 for p in plans)
    assert all(p.progress.annual_contribution == 5_000 for p in plans)
    assert all(p.progress.status == "covered_with_savings" for p in plans)


def test_manual_budget_reserves_funding_before_other_goals_share_the_remainder():
    client = profile(
        [
            {
                "name": "Same",
                "target_amount": 1_000_000,
                "years": 10,
                "priority": "high",
            },
            {
                "name": "Same",
                "target_amount": 200_000,
                "years": 5,
                "priority": "low",
                "funding_budget": {
                    "allocated_assets": 100_000,
                    "annual_contribution": 20_000,
                },
            },
            {
                "name": "Third",
                "target_amount": 1_000_000,
                "years": 10,
                "priority": "low",
            },
            {"name": "Incomplete"},
        ]
    )
    plans = plan_goal_funding(client)
    assert [p.progress.allocated_assets for p in plans[:3]] == [
        375_000,
        100_000,
        125_000,
    ]
    assert [p.progress.annual_contribution for p in plans[:3]] == [
        30_000,
        20_000,
        10_000,
    ]
    assert plans[1].progress.allocation_method == "manual"
    assert plans[1].progress.required_return == 0
    assert plans[1].progress.years_to_target_at_zero_return == 5
    assert plans[3].progress is None
    assert goal_allocation_method(plans) == "mixed"
    # Budgets travel with goals when reordered; restoring automatic allocation
    # releases the reservation, including an explicitly zero manual budget.
    client.goals.reverse()
    reordered = plan_goal_funding(client)
    assert reordered[2].progress == plans[1].progress
    client.goals[2].funding_budget = None
    assert goal_allocation_method(plan_goal_funding(client)) == "priority_weighted"


def test_all_manual_budgets_keep_unassigned_assets_and_savings_outside_goals():
    plans = plan_goal_funding(
        profile(
            [
                {
                    "name": "Paused",
                    "target_amount": 100_000,
                    "years": 5,
                    "funding_budget": {"allocated_assets": 0, "annual_contribution": 0},
                },
                {
                    "name": "Funded",
                    "target_amount": 100_000,
                    "years": 5,
                    "funding_budget": {
                        "allocated_assets": 150_000,
                        "annual_contribution": 5_000,
                    },
                },
            ]
        )
    )
    assert goal_allocation_method(plans) == "manual"
    assert plans[0].progress.allocated_assets == 0
    assert plans[0].progress.required_return is None
    assert plans[0].progress.years_to_target_at_zero_return is None
    assert plans[1].progress.funding_ratio == 1.5
    assert plans[1].progress.years_to_target_at_zero_return == 0


@pytest.mark.parametrize(
    "budget,code",
    [
        (
            {"allocated_assets": 600_001, "annual_contribution": 0},
            "goals.budget_exceeds_assets",
        ),
        (
            {"allocated_assets": 0, "annual_contribution": 60_001},
            "goals.budget_exceeds_savings",
        ),
        ({"allocated_assets": -1, "annual_contribution": 0}, "goals.budget_invalid"),
        (
            {"allocated_assets": float("inf"), "annual_contribution": 0},
            "goals.budget_invalid",
        ),
        (
            {"allocated_assets": 0, "annual_contribution": float("nan")},
            "goals.budget_invalid",
        ),
    ],
)
def test_invalid_manual_budgets_are_rejected(budget, code):
    client = profile([{"target_amount": 100_000, "years": 5, "funding_budget": budget}])
    with pytest.raises(GoalBudgetError) as error:
        plan_goal_funding(client)
    assert error.value.code == code


def test_budget_validation_checks_totals_and_incomplete_goals():
    goals = [
        {
            "target_amount": 1_000_000,
            "years": 5,
            "funding_budget": {"allocated_assets": 400_000, "annual_contribution": 0},
        }
        for _ in range(2)
    ]
    with pytest.raises(GoalBudgetError, match="budget_exceeds_assets"):
        plan_goal_funding(profile(goals))
    with pytest.raises(GoalBudgetError, match="budget_incomplete"):
        plan_goal_funding(
            profile(
                [
                    {
                        "target_amount": 0,
                        "years": 5,
                        "funding_budget": {
                            "allocated_assets": 0,
                            "annual_contribution": 0,
                        },
                    }
                ]
            )
        )
    # Decimal-sized budgets should not reject a mathematically equal total.
    goals[0]["funding_budget"]["allocated_assets"] = 0.1
    goals[1]["funding_budget"]["allocated_assets"] = 0.2
    assert len(plan_goal_funding(profile(goals, assets=0.3))) == 2


@pytest.mark.parametrize(
    "target,assets,savings,years",
    [
        (100_000, 100_000, 0, 0),
        (100_000, 150_000, 10_000, 0),
        (100_000, 0, 10_000, 10),
        (100_001, 0, 10_000, 11),
        (100_000, 0, 0, None),
        (800_000, 0, 10_000, 80),
        (800_001, 0, 10_000, None),
        (0.8, 0.7, 0.1, 1),
    ],
)
def test_zero_return_timeline_uses_whole_year_end_contributions(
    target, assets, savings, years
):
    assert years_to_target_at_zero_return(target, assets, savings) == years
    if years is not None:
        assert solve_required_return(target, assets, savings, years) == 0
