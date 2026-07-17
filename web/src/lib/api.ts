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
