/** Shared goal funding estimates; no advisor-only or market-provider fields. */
export interface GoalFundingProgress {
  allocated_assets: number;
  annual_contribution: number;
  funding_ratio: number;
  funding_gap: number;
  required_return: number | null;
  allocation_method: "priority_weighted" | "manual";
  years_to_target_at_zero_return: number | null;
  status: "covered" | "covered_with_savings" | "growth_required" | "needs_funding";
}

export interface GoalFundingPlan {
  name: string;
  target_amount: number;
  years: number;
  priority: string;
  progress: GoalFundingProgress | null;
}

export interface ProfileGoalsResponse {
  goals: GoalFundingPlan[];
  allocation_method: "priority_weighted" | "manual" | "mixed";
  profile_updated_at: string;
  progress_explanation: string;
}
