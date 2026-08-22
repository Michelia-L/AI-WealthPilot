import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ProfilePayload, QuestionnaireResponse } from "@/lib/api";
import { common } from "@/lib/i18n/dictionaries/en/common";
import { profiles } from "@/lib/i18n/dictionaries/en/profiles";
import RiskQuestionnaire from "./questionnaire";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ profiles, common }),
  useLocale: () => ({ locale: "en" }),
}));

const QUESTIONNAIRE: QuestionnaireResponse = {
  ability: [
    {
      key: "a1",
      question: "How stable is your income?",
      options: [
        { key: "stable", label: "Very stable", score: 4 },
        { key: "volatile", label: "Volatile", score: 2 },
      ],
    },
    {
      key: "a2",
      question: "Do you have an emergency fund?",
      options: [
        { key: "yes", label: "Yes, 6+ months", score: 4 },
        { key: "no", label: "No", score: 1 },
      ],
    },
  ],
  willingness: [
    {
      key: "w1",
      question: "How do you react to losses?",
      options: [
        { key: "calm", label: "Stay the course", score: 5 },
        { key: "panic", label: "Sell immediately", score: 1 },
      ],
    },
  ],
};

function makeForm(overrides: Partial<ProfilePayload> = {}): ProfilePayload {
  return {
    risk_scores: { ability_score: 0, willingness_score: 0 },
    ability_answers: {},
    willingness_answers: {},
    ...overrides,
  } as ProfilePayload;
}

function renderQ(
  form: ProfilePayload,
  questionnaire: QuestionnaireResponse | null = QUESTIONNAIRE
) {
  const onAnswer = vi.fn();
  const onRiskScoreChange = vi.fn();
  render(
    <RiskQuestionnaire
      questionnaire={questionnaire}
      form={form}
      onAnswer={onAnswer}
      onRiskScoreChange={onRiskScoreChange}
    />
  );
  return { onAnswer, onRiskScoreChange };
}

describe("RiskQuestionnaire with questionnaire data", () => {
  it("renders both tracks and reports answer clicks", () => {
    const { onAnswer } = renderQ(makeForm());
    expect(screen.getByText("How stable is your income?")).toBeInTheDocument();
    expect(screen.getByText("How do you react to losses?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Very stable" }));
    expect(onAnswer).toHaveBeenCalledWith("ability_answers", "a1", "stable");
  });

  it("computes the live preview from answered tracks", () => {
    renderQ(
      makeForm({
        ability_answers: { a1: "stable", a2: "yes" }, // (4+4)/2 = 4.0
        willingness_answers: { w1: "calm" }, // 5.0
      })
    );
    // ability 4.0, willingness 5.0, combined = min = 4.0
    expect(screen.getByText("Ability to Take Risk")).toBeInTheDocument();
    const tiles = screen.getAllByText("4.0");
    expect(tiles.length).toBeGreaterThanOrEqual(2); // ability + combined
    expect(screen.getByText("5.0")).toBeInTheDocument();
  });

  it("keeps manual scores for unanswered tracks", () => {
    renderQ(
      makeForm({
        risk_scores: { ability_score: 2.5, willingness_score: 0 },
        ability_answers: {},
        willingness_answers: {},
      })
    );
    expect(screen.getByText("2.5")).toBeInTheDocument();
    // combined needs both tracks > 0 → unassessed dash
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });
});

describe("RiskQuestionnaire fallback (no questionnaire)", () => {
  it("renders manual sliders and reports changes", () => {
    const { onRiskScoreChange } = renderQ(
      makeForm({ risk_scores: { ability_score: 1.5, willingness_score: 3 } }),
      null
    );
    expect(
      screen.queryByText("How stable is your income?")
    ).not.toBeInTheDocument();

    const sliders = screen.getAllByRole("slider");
    expect(sliders).toHaveLength(2);
    fireEvent.change(sliders[0], { target: { value: "4" } });
    expect(onRiskScoreChange).toHaveBeenCalledWith("ability_score", 4);
  });
});
