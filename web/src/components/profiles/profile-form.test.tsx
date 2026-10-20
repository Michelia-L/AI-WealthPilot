import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { InvestmentGoalInput, ProfilePayload } from "@/lib/api";
import { en } from "@/lib/i18n/dictionaries/en";
import ProfileForm from "./profile-form";

vi.mock("@/components/locale-context", () => ({
  useT: () => en,
  useLocale: () => ({ locale: "en" }),
}));

const initial: ProfilePayload = {
  name: "Synthetic client", age: 40, marital_status: "single", dependents: 0,
  financial: {
    investable_assets: 200_000, annual_income: 100_000, annual_expenses: 60_000,
    total_liabilities: 0, emergency_fund_months: 6,
  },
  goals: [
    { name: "Education", target_amount: 100_000, years: 5, priority: "high" },
    { name: "Education", target_amount: 200_000, years: 10, priority: "low" },
  ],
  time_horizon_years: 10, is_multi_stage: false, liquidity_needs: 0,
  tax_status: "taxable", esg_preference: false, sector_restrictions: [], notes: "",
  risk_scores: { ability_score: 3, willingness_score: 3 },
  ability_answers: {}, willingness_answers: {},
};

function Harness({ onSave, goals = initial.goals }: {
  onSave: (form: ProfilePayload) => void;
  goals?: InvestmentGoalInput[];
}) {
  const [form, setForm] = useState({ ...initial, goals });
  return <ProfileForm
    mode="edit" form={form} restrictionsText="" onRestrictionsChange={vi.fn()}
    set={(key, value) => setForm((prev) => ({ ...prev, [key]: value }))}
    setFin={vi.fn()} setAnswer={vi.fn()}
    setGoal={(index, key, value) => setForm((prev) => ({
      ...prev, goals: prev.goals.map((goal, i) => i === index ? { ...goal, [key]: value } : goal),
    }))}
    questionnaire={null} busy={false} error={null}
    onSave={() => onSave(form)} onCancel={vi.fn()}
  />;
}

it("edits one goal's manual budget without changing a duplicate-name goal", () => {
  const onSave = vi.fn();
  render(<Harness onSave={onSave} />);
  const first = within(screen.getByRole("group", { name: "Goal 1" }));
  const second = within(screen.getByRole("group", { name: "Goal 2" }));
  fireEvent.click(first.getByRole("switch", { name: "Set a manual budget" }));
  fireEvent.change(first.getByLabelText("Planning budget"), { target: { value: "80000" } });
  fireEvent.change(first.getByLabelText("Annual contribution budget"), { target: { value: "10000" } });
  expect(second.getByRole("switch")).toHaveAttribute("aria-checked", "false");
  expect(second.queryByLabelText("Planning budget")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
  expect(onSave.mock.calls[0][0].goals[0].funding_budget).toEqual({
    allocated_assets: 80_000, annual_contribution: 10_000,
  });
  expect(onSave.mock.calls[0][0].goals[1].funding_budget).toBeUndefined();

  fireEvent.click(first.getByRole("switch"));
  fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
  expect(onSave.mock.calls[1][0].goals[0].funding_budget).toBeNull();
});

it("preserves an explicit zero budget and retains a budget when another goal is removed", () => {
  const onSave = vi.fn();
  render(<Harness onSave={onSave} goals={[
    initial.goals[0],
    { ...initial.goals[1], funding_budget: { allocated_assets: 0, annual_contribution: 0 } },
  ]} />);
  const second = within(screen.getByRole("group", { name: "Goal 2" }));
  expect(second.getByRole("switch")).toHaveAttribute("aria-checked", "true");
  expect(second.getByLabelText("Planning budget")).toHaveValue(0);
  fireEvent.click(within(screen.getByRole("group", { name: "Goal 1" })).getByRole("button", { name: "Delete goal" }));
  expect(screen.queryByRole("group", { name: "Goal 2" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
  expect(onSave.mock.calls[0][0].goals).toEqual([
    { ...initial.goals[1], funding_budget: { allocated_assets: 0, annual_contribution: 0 } },
  ]);
});
