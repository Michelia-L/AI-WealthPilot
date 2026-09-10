import { getJson } from "./client";

// ---------------------------------------------------------------------------
// Portfolio monitoring (Phase P10 — SAA drift & rebalancing)
// ---------------------------------------------------------------------------

export interface PortfolioMetrics {
  expected_return: number | null;
  volatility: number | null;
  sharpe: number | null;
}

export interface HoldingMetrics {
  expected_return: number;
  volatility: number;
  sharpe: number;
  max_drawdown: number;
  var_95: number;
  cvar_95: number;
}

export type BandStatus = "within" | "above" | "below" | "unknown";

export interface MonitoringHolding {
  key: string | null;
  name: string;
  ticker: string | null;
  target_weight: number;
  min_weight: number;
  max_weight: number;
  drifted_weight: number | null;
  drift_pp: number | null;
  band_status: BandStatus;
  period_return: number | null;
  metrics: HoldingMetrics | null;
  market_value?: number | null;
}

export interface RebalanceTrade {
  key: string | null;
  name: string;
  action: "buy" | "sell";
  weight_pp: number;
}

/**
 * Rebalancing conclusion rollup. "insufficient_data" separates "no breach
 * detected" from "drift unmeasurable" — the page must not claim all
 * holdings are within bands when they could not be measured.
 */
export type RebalanceStatus = "needed" | "within_bands" | "insufficient_data";

/** One currency's share of the SAA (target vs drifted weights). */
export interface CurrencyExposureItem {
  currency: string;
  target_weight: number;
  drifted_weight: number | null;
}

/** Per-currency exposure breakdown and net currency mismatch. */
export interface CurrencyExposure {
  base_currency: string;
  breakdown: CurrencyExposureItem[];
  foreign_target: number;
  foreign_drifted: number | null;
  net_mismatch: number;
  advisory: string;
}

export interface MonitoringResponse {
  document_id: string;
  client_name: string;
  saved_at: string;
  as_of: string;
  valuation_source: "buy_and_hold" | "actual_holdings";
  valuation_as_of: string | null;
  snapshot_id: number | null;
  total_market_value: number | null;
  cme_cache_status: string;
  portfolio: PortfolioMetrics;
  drifted_portfolio: PortfolioMetrics;
  holdings: MonitoringHolding[];
  rebalance: {
    needed: boolean;
    status: RebalanceStatus;
    trades: RebalanceTrade[];
  };
  currency_exposure: CurrencyExposure;
  notes: string[];
}

export const getMonitoring = (documentId: string, locale?: string) =>
  getJson<MonitoringResponse>(
    `/api/monitoring/${encodeURIComponent(documentId)}`,
    locale
  );

/** Fleet-wide drift status (Phase 17 — overview alert light). */
export type FleetStatus = "ok" | "breach" | "unknown";

export interface MonitoringFleetItem {
  document_id: string;
  client_name: string;
  saved_at: string;
  status: FleetStatus;
  out_of_band: number;
  max_abs_drift_pp: number | null;
  note: string | null;
}

export interface MonitoringFleetResponse {
  as_of: string;
  price_as_of: string | null;
  items: MonitoringFleetItem[];
  summary: { total: number; breach: number; ok: number; unknown: number };
}

export const getMonitoringFleetStatus = (locale?: string) =>
  getJson<MonitoringFleetResponse>("/api/monitoring/status", locale);


export interface ActualHoldingInput {
  asset_class: string;
  market_value?: number | null;
  quantity?: number | null;
  unit_price?: number | null;
  cost_basis?: number | null;
  cost_basis_date?: string | null;
}

export interface HoldingSnapshotInput {
  as_of: string;
  base_currency: string;
  holdings: ActualHoldingInput[];
}

export interface HoldingSnapshot extends HoldingSnapshotInput {
  id: number;
  document_id: string;
  created_at: string;
  total_market_value: number;
  previous_snapshot_id: number | null;
  total_market_value_change: number | null;
  holdings: (ActualHoldingInput & {
    market_value: number;
    weight: number;
    market_value_change: number | null;
    weight_change: number | null;
  })[];
}

export interface HoldingSnapshotHistory {
  valuation_timezone: string;
  document_id: string;
  base_currency: string;
  assets: { asset_class: string; key: string | null }[];
  snapshots: HoldingSnapshot[];
}

export const getHoldingSnapshots = (documentId: string, locale?: string) =>
  getJson<HoldingSnapshotHistory>(`/api/monitoring/${encodeURIComponent(documentId)}/holdings`, locale);
