import type { PlotlyFigure } from "./market";
import { getJson } from "./client";

// ---------------------------------------------------------------------------
// Backtest & stress test (P13)
// ---------------------------------------------------------------------------

export interface BacktestMetrics {
  total_return: number;
  cagr: number;
  ann_volatility: number;
  /** 零波动时数学上无定义，为 null */
  sharpe: number | null;
  max_drawdown: number;
  max_drawdown_peak: string | null;
  max_drawdown_trough: string | null;
  best_day: number;
  worst_day: number;
}

export interface BacktestYearlyRow {
  year: number;
  portfolio: number;
  benchmark: number;
}

export interface BacktestStressRow {
  scenario: string;
  window: string;
  portfolio_return: number;
  benchmark_return: number;
}

/** 费用拖累信息（Phase 18 — IPS TER 折日计入组合 NAV，基准为指数口径）。 */
export interface BacktestFeeInfo {
  annual_rate: number;
  source: "ips_fee_schedule" | "manual" | "none";
  gross_total_return: number;
  net_total_return: number;
  cumulative_impact_pp: number;
}

/** Brinson-Fachler 归因：单组一行（Carino 链接累计）。 */
export interface BrinsonGroupRow {
  group: string;
  avg_weight_portfolio: number;
  avg_weight_benchmark: number;
  allocation: number;
  selection: number;
  interaction: number;
  total: number;
}

/** 业绩归因块：累计超额收益 = 配置 + 选择 + 交互（精确成立）。 */
export interface BacktestAttribution {
  months: number;
  active_return: number;
  allocation: number;
  selection: number;
  interaction: number;
  groups: BrinsonGroupRow[];
}

export interface BacktestResponse {
  document_id: string;
  client_name: string;
  period: string;
  as_of: string;
  weights: Record<string, number>;
  metrics: BacktestMetrics;
  benchmark: { name: string; metrics: BacktestMetrics };
  yearly: BacktestYearlyRow[];
  equity_chart: PlotlyFigure;
  drawdown_chart: PlotlyFigure;
  stress: BacktestStressRow[];
  fee: BacktestFeeInfo;
  notes: string[];
  attribution: BacktestAttribution | null;
}

export const getBacktest = (documentId: string, period: string, locale?: string) =>
  getJson<BacktestResponse>(
    `/api/monitoring/${encodeURIComponent(documentId)}/backtest?period=${encodeURIComponent(period)}`,
    locale
  );

/** 任意权重组合的回测响应（优化器回测联动）。 */
export type PortfolioBacktestResponse = Omit<
  BacktestResponse,
  "document_id" | "client_name"
>;
