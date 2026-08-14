/**
 * Deep links into the optimizer workspace (URL deep-link contract).
 *
 * The retirement planner links here with the income stream the user just
 * simulated, pre-filling the LDI surplus method's retirement channel:
 *   /optimizer?method=surplus&source=retirement&ytr=20&dy=25&income=80000&asset_value=100000
 * Parsing is defensive — anything missing or malformed yields no prefill.
 */

export interface RetirementLdiParams {
  years_to_retirement: number;
  distribution_years: number;
  annual_income: number;
  asset_value?: number;
}

/** Build the /optimizer href pre-filling the surplus retirement channel. */
export function buildRetirementLdiHref(p: RetirementLdiParams): string {
  const q = new URLSearchParams({
    method: "surplus",
    source: "retirement",
    ytr: String(p.years_to_retirement),
    dy: String(p.distribution_years),
    income: String(p.annual_income),
  });
  if (p.asset_value !== undefined) q.set("asset_value", String(p.asset_value));
  return `/optimizer?${q.toString()}`;
}

/** Workspace prefill carried by the deep link (all optional). */
export interface OptimizerDeepLink {
  method?: "surplus";
  surplusSource?: "retirement";
  yearsToRetirement?: number;
  distributionYears?: number;
  annualIncome?: number;
  assetValue?: number;
}

function toNum(v: string | string[] | undefined): number | undefined {
  if (typeof v !== "string" || v.trim() === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function clampInt(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, Math.round(n)));
}

/**
 * Parse optimizer search params into workspace prefill props. Only the
 * complete surplus/retirement signature is honored; partial or malformed
 * links are ignored so the workspace falls back to its defaults.
 */
export function parseOptimizerDeepLink(
  sp: Record<string, string | string[] | undefined>
): OptimizerDeepLink {
  if (sp.method !== "surplus" || sp.source !== "retirement") return {};
  const yearsToRetirement = toNum(sp.ytr);
  const distributionYears = toNum(sp.dy);
  const annualIncome = toNum(sp.income);
  if (
    yearsToRetirement === undefined ||
    distributionYears === undefined ||
    annualIncome === undefined
  ) {
    return {};
  }
  return {
    method: "surplus",
    surplusSource: "retirement",
    yearsToRetirement: clampInt(yearsToRetirement, 0, 50),
    distributionYears: clampInt(distributionYears, 1, 60),
    annualIncome,
    assetValue: toNum(sp.asset_value),
  };
}
