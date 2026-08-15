import { getJson } from "./client";

// ---------------------------------------------------------------------------
// Client profiles (Phase 3c — SQLite persistence)
// ---------------------------------------------------------------------------

export interface ProfileSummary {
  id: number;
  name: string;
  age: number;
  risk_level: string;
  updated_at: string;
}

export interface ProfileListResponse {
  profiles: ProfileSummary[];
}

export interface FinancialSituationInput {
  annual_income: number;
  annual_expenses: number;
  investable_assets: number;
  total_liabilities: number;
  emergency_fund_months: number;
}

export interface InvestmentGoalInput {
  name: string;
  target_amount: number;
  years: number;
  priority: "high" | "medium" | "low";
}

/** Editable payload for create/update — mirrors the API's ProfilePayload. */
export interface ProfilePayload {
  name: string;
  age: number;
  marital_status: "single" | "married" | "divorced" | "widowed";
  dependents: number;
  financial: FinancialSituationInput;
  goals: InvestmentGoalInput[];
  time_horizon_years: number;
  is_multi_stage: boolean;
  liquidity_needs: number;
  tax_status: "tax-exempt" | "taxable" | "tax-deferred";
  esg_preference: boolean;
  sector_restrictions: string[];
  notes: string;
  risk_scores: { ability_score: number; willingness_score: number };
  ability_answers: Record<string, string>;
  willingness_answers: Record<string, string>;
}

export interface ProfileDerived {
  net_worth: number;
  annual_savings: number;
  savings_rate: number;
  debt_to_asset_ratio: number | null; // null = +inf (debt without assets)
  final_risk_score: number;
  tolerance_level: string;
}

/** Full stored profile — the asdict(ClientProfile) shape returned by the API. */
export interface StoredProfile extends Omit<ProfilePayload, "risk_scores"> {
  risk_profile: {
    ability_score: number;
    willingness_score: number;
    tolerance_level: string;
    description: string;
  };
  created_at: string;
  updated_at: string;
}

export interface ProfileDetailResponse {
  id: number;
  created_at: string;
  updated_at: string;
  profile: StoredProfile;
  derived: ProfileDerived;
}

export interface ProfileImportResponse {
  files_found: number;
  imported: number;
  skipped: number;
}

/** Convert the stored detail shape back into the editable form payload. */
export function detailToPayload(detail: ProfileDetailResponse): ProfilePayload {
  const p = detail.profile;
  return {
    name: p.name,
    age: p.age,
    marital_status: p.marital_status,
    dependents: p.dependents,
    financial: { ...p.financial },
    goals: p.goals.map((g) => ({ ...g })),
    time_horizon_years: p.time_horizon_years,
    is_multi_stage: p.is_multi_stage,
    liquidity_needs: p.liquidity_needs,
    tax_status: p.tax_status,
    esg_preference: p.esg_preference,
    sector_restrictions: [...p.sector_restrictions],
    notes: p.notes,
    risk_scores: {
      ability_score: p.risk_profile.ability_score,
      willingness_score: p.risk_profile.willingness_score,
    },
    ability_answers: { ...p.ability_answers },
    willingness_answers: { ...p.willingness_answers },
  };
}

/** Client-side mirror of src RISK_SCORE_BREAKPOINTS for live preview only —
 *  the server recomputes the authoritative level on save. */
const RISK_LEVEL_LABELS = [
  "Conservative / 保守型",
  "Moderately Conservative / 稳健型",
  "Moderate / 平衡型",
  "Moderately Aggressive / 成长型",
  "Aggressive / 进取型",
];

export function classifyRiskPreview(ability: number, willingness: number): string {
  if (ability === 0 || willingness === 0) return "未评估";
  const score = Math.min(ability, willingness);
  for (const [i, bp] of [1.5, 2.5, 3.5, 4.5].entries()) {
    if (score <= bp) return RISK_LEVEL_LABELS[i];
  }
  return RISK_LEVEL_LABELS[RISK_LEVEL_LABELS.length - 1];
}

export const MARITAL_STATUS_OPTIONS = [
  { value: "single", label: "未婚" },
  { value: "married", label: "已婚" },
  { value: "divorced", label: "离异" },
  { value: "widowed", label: "丧偶" },
] as const;

export const TAX_STATUS_OPTIONS = [
  { value: "taxable", label: "应税账户" },
  { value: "tax-exempt", label: "免税账户" },
  { value: "tax-deferred", label: "延税账户" },
] as const;

export const getProfiles = () => getJson<ProfileListResponse>("/api/profiles");

export const getProfile = (id: number) =>
  getJson<ProfileDetailResponse>(`/api/profiles/${id}`);

// ---------------------------------------------------------------------------
// Risk questionnaire (Phase 5b — 9-question dual-track assessment)
// ---------------------------------------------------------------------------

export interface QuestionnaireOption {
  key: string;
  label: string; // locale-resolved by the API (X-Locale)
  score: number; // 1-5 — client live preview only; server recomputes on save
}

export interface QuestionnaireQuestion {
  key: string;
  question: string; // locale-resolved by the API
  options: QuestionnaireOption[];
}

export interface QuestionnaireResponse {
  ability: QuestionnaireQuestion[];
  willingness: QuestionnaireQuestion[];
}

export const getQuestionnaire = (locale?: string) =>
  getJson<QuestionnaireResponse>("/api/profiles/questionnaire", locale);

// ---------------------------------------------------------------------------
// Profile comparison + behavioral biases (Phase 5c)
// ---------------------------------------------------------------------------

export interface BiasItem {
  bias_type: string;
  name: string; // bilingual "English / 中文"
  description: string;
  severity: string; // high / medium / low
  recommendation: string;
}

export interface ProfileFinancialSummary {
  annual_income: number;
  net_worth: number;
  annual_savings: number;
  savings_rate: number;
  emergency_fund_months: number;
  risk_score: number;
  risk_level: string;
}

export interface ProfileCompareEntry {
  id: number;
  name: string;
  financial_summary: ProfileFinancialSummary;
  bias_count: number;
  biases: BiasItem[];
}

export interface ProfileCompareResponse {
  comparison_date: string;
  insights: string[];
  profiles: ProfileCompareEntry[];
}

/**
 * Client mirror of src compute_*_score for live preview: average the option
 * scores of the answered questions only. Returns 0 when nothing is answered
 * (matches src "unassessed" semantics).
 */
export function scoreFromAnswers(
  questions: QuestionnaireQuestion[],
  answers: Record<string, string>
): number {
  const scores = questions
    .map((q) => q.options.find((o) => o.key === answers[q.key])?.score)
    .filter((s): s is number => s !== undefined);
  return scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
}

