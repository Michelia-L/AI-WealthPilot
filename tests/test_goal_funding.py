"""Funding is conserved across goals and never presented as realized progress."""

import pytest

from src.agents.profiler import ClientProfile, FinancialSituation, InvestmentGoal
from src.portfolio.goals import plan_goal_funding


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
