import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import GoalFundingCards from "./goal-funding-cards";
import type { GoalFundingPlan } from "@/lib/api/goals";
import { en } from "@/lib/i18n/dictionaries/en";
import { zh } from "@/lib/i18n/dictionaries/zh";

const goal: GoalFundingPlan = {
  name: "Education",
  target_amount: 200_000,
  years: 10,
  priority: "high",
  progress: {
    allocated_assets: 100_000,
    annual_contribution: 5_000,
    funding_ratio: 0.5,
    funding_gap: 100_000,
    required_return: 0.03,
    status: "growth_required",
  },
};

it("shows backend budgets, required growth and accessible coverage for each goal", () => {
  render(
    <GoalFundingCards
      goals={[goal, { ...goal, priority: "low", progress: null }]}
      t={en.goalTracking}
    />,
  );
  // Duplicate goal names retain distinct cards rather than merging budgets.
  const cards = screen.getAllByRole("article", { name: "Education" });
  expect(cards).toHaveLength(2);
  expect(within(cards[0]).getByText("Planning budget")).toBeVisible();
  expect(within(cards[0]).getByText("3.00%")).toBeVisible();
  expect(within(cards[0]).getByText("Investment growth required")).toBeVisible();
  expect(within(cards[0]).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
  expect(within(cards[1]).getByText(en.goalTracking.incomplete)).toBeVisible();
  expect(within(cards[1]).queryByRole("progressbar")).not.toBeInTheDocument();
});

it("caps the bar at 100% while retaining an overfunded planning ratio", () => {
  render(
    <GoalFundingCards
      goals={[{ ...goal, progress: { ...goal.progress!, funding_ratio: 1.5, status: "covered" } }]}
      t={en.goalTracking}
    />,
  );
  const bar = screen.getByRole("progressbar");
  expect(bar).toHaveAttribute("aria-valuenow", "100");
  expect(bar).toHaveAttribute("aria-valuetext", "150.0%");
  expect(bar.firstChild).toHaveStyle({ width: "100%" });
  expect(screen.getByText("150.0%")).toBeVisible();
});

it("distinguishes an unsolved required return from zero and localizes its state", () => {
  render(
    <GoalFundingCards
      goals={[{
        ...goal,
        progress: { ...goal.progress!, funding_ratio: 0, required_return: null, status: "needs_funding" },
      }]}
      t={zh.goalTracking}
    />,
  );
  expect(screen.getByText("计算范围内无法满足目标")).toBeVisible();
  expect(screen.getByText("需复核资金与目标")).toBeVisible();
  expect(screen.getByRole("progressbar")).toHaveAccessibleName("Education · 规划资金覆盖率");
  expect(screen.queryByText("0.00%")).not.toBeInTheDocument();
});

it("shows an explicit empty state without inventing progress", () => {
  render(<GoalFundingCards goals={[]} t={en.goalTracking} />);
  expect(screen.getByText("No goals recorded yet")).toBeVisible();
  expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
});
