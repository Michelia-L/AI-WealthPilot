import type { PlotlyFigure } from "./market";
// ---------------------------------------------------------------------------
// Retirement planning
// ---------------------------------------------------------------------------

export type InflationPreset = "standard" | "elderly" | "luxury" | "custom";

/** CME-derived μ/σ suggestion for the retirement planner. */
export interface CmeSuggestion {
  expected_return: number;
  volatility: number;
  allocation: Record<string, number>;
  as_of_date: string;
  cache_status: string;
  risk_level: string | null;
}

export interface RetirementRequest {
  current_age: number;
  retirement_age: number;
  life_expectancy: number;
  current_savings: number;
  annual_savings: number;
  desired_annual_income: number;
  inflation_rate: number;
  inflation_preset: InflationPreset;
  custom_inflation_rate?: number;
  expected_return: number;
  volatility: number;
  n_simulations: number;
  /** 提款策略：fixed 刚性通胀调整；guardrails 动态护栏（Guyton-Klinger）。 */
  withdrawal_strategy?: "fixed" | "guardrails";
  /** 护栏带：相对初始提款率的触发带宽（0.2 = ±20%）。 */
  guardrail_band?: number;
  /** 触发后的提款削减/回补幅度（0.1 = ∓10%）。 */
  guardrail_adjust?: number;
}

export interface TerminalStats {
  mean: number;
  median: number;
  p5: number;
  p25: number;
  p75: number;
  p95: number;
}

export interface DepletionAnalysis {
  never_depleted_pct: number;
  depleted_within_10y_pct: number;
  median_depletion_year: number | null;
}

export interface SensitivityRow {
  annual_savings: number;
  is_current: boolean;
  survival_rate: number;
  median_at_retirement: number;
}

export interface StrategyComparison {
  fixed_survival_rate: number;
  guardrails_survival_rate: number;
  survival_lift: number;
  guardrail_band: number;
  guardrail_adjust: number;
}

export interface RetirementResponse {
  as_of: string;
  params: RetirementRequest & { seed: number; distribution_inflation_rate: number };
  survival_rate: number;
  accumulation_years: number;
  distribution_years: number;
  terminal_at_retirement: TerminalStats;
  accumulation_chart: PlotlyFigure;
  distribution_chart: PlotlyFigure;
  depletion: DepletionAnalysis;
  sensitivity: SensitivityRow[];
  /** 护栏策略与固定策略的同抽对比（仅 guardrails 模式返回）。 */
  comparison?: StrategyComparison | null;
}

export const SIMULATION_OPTIONS = [
  { value: 1000, label: "1k" },
  { value: 5000, label: "5k" },
  { value: 10000, label: "10k" },
  { value: 50000, label: "50k" },
] as const;

