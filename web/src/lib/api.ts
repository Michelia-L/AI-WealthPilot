/**
 * Typed client for the AI WealthPilot FastAPI backend.
 *
 * Server Components call the API over the internal network (API_ORIGIN),
 * so requests never cross the browser and no CORS is involved. Local dev
 * defaults to localhost:8000; Docker Compose injects http://api:8000.
 *
 * Responses are NOT cached here — freshness is owned by the API layer
 * (TTL caches + the CME file cache). Slow sections stream via <Suspense>.
 */

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

export interface AssetInfo {
  name: string;
  category: string;
  color: string;
  currency: string;
  symbol: string;
}

export interface UniverseResponse {
  assets: Record<string, AssetInfo>;
}

export interface Quote {
  ticker: string;
  name: string;
  category: string;
  price: number | null;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  currency: string;
  symbol: string;
  color: string;
}

export interface QuotesResponse {
  as_of: string;
  quotes: Quote[];
}

export interface RiskFreeRateResponse {
  rate: number;
  as_of: string;
}

/** Plotly figure as serialized by fig.to_json() on the API side. */
export interface PlotlyFigure {
  data: unknown[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  layout: Record<string, any>;
}

export interface RiskStat {
  ticker: string;
  name: string;
  ann_return: number;
  ann_volatility: number;
  sharpe: number;
  max_drawdown: number;
  var_95: number;
}

export interface AnalyticsResponse {
  period: string;
  tickers: string[];
  as_of: string;
  price_chart: PlotlyFigure;
  correlation_chart: PlotlyFigure | null;
  stats: RiskStat[];
}

export interface AssetClassCME {
  name: string;
  ticker: string;
  expected_return: number;
  volatility: number;
  sharpe_ratio: number;
  max_drawdown: number;
  var_95: number;
  cvar_95: number;
  data_points: number;
  implied_volatility: number | null;
  iv_source: string | null;
  blended_volatility: number | null;
  volatility_regime: string | null;
}

export interface CMEReport {
  as_of_date: string;
  data_lookback_years: number;
  risk_free_rate: number;
  risk_free_rate_source: string;
  inflation_assumption: number;
  asset_classes: AssetClassCME[];
  correlation_matrix: Record<string, Record<string, number>>;
  methodology_notes: string;
  iv_blending_tau: number;
  iv_data_available: boolean;
}

export interface CMEResponse {
  cache_status: "fresh" | "cached" | "stale" | "fallback";
  report: CMEReport;
}

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
}

/** Analysis horizons offered by the dashboard (mirror of the Streamlit page). */
export const PERIOD_OPTIONS = [
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "3y", label: "3Y" },
  { value: "5y", label: "5Y" },
] as const;

export const DEFAULT_PERIOD = "1y";
export const VALID_PERIODS: readonly string[] = PERIOD_OPTIONS.map((p) => p.value);

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API_ORIGIN}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    // API unreachable (not started, network partition) — callers render a
    // degraded panel instead of crashing the page.
    return null;
  }
}

function tickersParam(tickers: string[]): string {
  return tickers.map(encodeURIComponent).join(",");
}

export const getHealth = () => getJson<HealthResponse>("/api/health");

export const getUniverse = () => getJson<UniverseResponse>("/api/market/universe");

export const getQuotes = (tickers?: string[]) =>
  getJson<QuotesResponse>(
    `/api/market/quotes${tickers?.length ? `?tickers=${tickersParam(tickers)}` : ""}`
  );

export const getRiskFreeRate = () =>
  getJson<RiskFreeRateResponse>("/api/market/risk-free-rate");

export const getCme = () => getJson<CMEResponse>("/api/cme");

export const getAnalytics = (period: string, tickers: string[]) =>
  getJson<AnalyticsResponse>(
    `/api/market/analytics?period=${encodeURIComponent(period)}&tickers=${tickersParam(tickers)}`
  );

// ---------------------------------------------------------------------------
// Portfolio optimization
// ---------------------------------------------------------------------------

export interface AssetClassInfo {
  ticker: string;
  name: string;
}

export interface AssetClassesResponse {
  asset_classes: Record<string, AssetClassInfo>;
}

export interface BLViewInput {
  view_type: "absolute" | "relative";
  asset_long: string;
  asset_short?: string | null;
  expected_return: number;
  confidence: number;
}

export interface BLConfigInput {
  tau: number;
  delta: number;
  market_weights?: Record<string, number> | null;
  views: BLViewInput[];
}

export type OptimizeMethod = "mvo" | "resampled" | "black-litterman";
export type OptimizeMode = "max-sharpe" | "min-vol";

export interface OptimizeRequest {
  assets: string[];
  period: string;
  risk_free_rate?: number | null;
  method: OptimizeMethod;
  mode: OptimizeMode;
  allow_short: boolean;
  n_simulations: number;
  bl?: BLConfigInput | null;
}

export interface PortfolioResult {
  weights: Record<string, number>;
  ann_return: number;
  ann_volatility: number;
  sharpe: number;
  success: boolean;
  weight_std: Record<string, number> | null;
}

export interface AssetStat {
  key: string;
  ticker: string;
  name: string;
  ann_return: number;
  ann_volatility: number;
}

export interface BLInsight {
  equilibrium_returns: Record<string, number>;
  posterior_returns: Record<string, number>;
}

export interface OptimizeResponse {
  as_of: string;
  params: {
    assets: string[];
    period: string;
    risk_free_rate: number;
    method: OptimizeMethod;
    mode: OptimizeMode;
    allow_short: boolean;
    n_simulations: number | null;
    trading_days: number;
  };
  selected: PortfolioResult;
  max_sharpe: PortfolioResult;
  min_vol: PortfolioResult;
  frontier_chart: PlotlyFigure;
  allocation_chart: PlotlyFigure;
  asset_stats: AssetStat[];
  bl: BLInsight | null;
}

export const OPTIMIZER_PERIOD_OPTIONS = [
  { value: "1y", label: "1Y" },
  { value: "2y", label: "2Y" },
  { value: "3y", label: "3Y" },
  { value: "5y", label: "5Y" },
  { value: "10y", label: "10Y" },
] as const;

export const getAssetClasses = () =>
  getJson<AssetClassesResponse>("/api/portfolio/asset-classes");

// ---------------------------------------------------------------------------
// Retirement planning
// ---------------------------------------------------------------------------

export interface RetirementRequest {
  current_age: number;
  retirement_age: number;
  life_expectancy: number;
  current_savings: number;
  annual_savings: number;
  desired_annual_income: number;
  inflation_rate: number;
  expected_return: number;
  volatility: number;
  n_simulations: number;
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

export interface RetirementResponse {
  as_of: string;
  params: RetirementRequest & { seed: number };
  survival_rate: number;
  accumulation_years: number;
  distribution_years: number;
  terminal_at_retirement: TerminalStats;
  accumulation_chart: PlotlyFigure;
  distribution_chart: PlotlyFigure;
  depletion: DepletionAnalysis;
  sensitivity: SensitivityRow[];
}

export const SIMULATION_OPTIONS = [
  { value: 1000, label: "1k" },
  { value: 5000, label: "5k" },
  { value: 10000, label: "10k" },
  { value: 50000, label: "50k" },
] as const;
