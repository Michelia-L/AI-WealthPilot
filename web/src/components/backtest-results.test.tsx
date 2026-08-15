import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { BacktestResponse } from "@/lib/api";
import { common } from "@/lib/i18n/dictionaries/en/common";
import BacktestResults from "./backtest-results";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ common }),
}));
vi.mock("@/components/plot-chart", () => ({ default: () => null }));

const BASE: BacktestResponse = {
  document_id: "doc-1",
  client_name: "Jane",
  period: "5y",
  as_of: "2026-08-14",
  weights: { SPY: 0.6, AGG: 0.4 },
  metrics: {
    total_return: 0.4,
    cagr: 0.07,
    ann_volatility: 0.12,
    sharpe: 0.4,
    max_drawdown: -0.2,
    max_drawdown_peak: null,
    max_drawdown_trough: null,
    best_day: 0.03,
    worst_day: -0.03,
  } as never,
  benchmark: {
    name: "60% SPY / 40% AGG",
    metrics: {
      total_return: 0.35,
      cagr: 0.06,
      ann_volatility: 0.11,
      sharpe: 0.35,
      max_drawdown: -0.18,
      max_drawdown_peak: null,
      max_drawdown_trough: null,
      best_day: 0.02,
      worst_day: -0.02,
    } as never,
  },
  yearly: [],
  equity_chart: { data: [] } as never,
  drawdown_chart: { data: [] } as never,
  stress: [],
  fee: {
    annual_rate: 0,
    source: "none",
    gross_total_return: 0.4,
    net_total_return: 0.4,
    cumulative_impact_pp: 0,
  },
  notes: [],
  attribution: {
    months: 60,
    active_return: 0.05,
    allocation: 0.03,
    selection: 0.015,
    interaction: 0.005,
    groups: [
      {
        group: "equity",
        avg_weight_portfolio: 0.7,
        avg_weight_benchmark: 0.6,
        allocation: 0.025,
        selection: 0.01,
        interaction: 0.004,
        total: 0.039,
      },
      {
        group: "bond",
        avg_weight_portfolio: 0.3,
        avg_weight_benchmark: 0.4,
        allocation: 0.005,
        selection: 0.005,
        interaction: 0.001,
        total: 0.011,
      },
    ],
  },
};

describe("BacktestResults attribution block", () => {
  it("renders the per-group Brinson table with the active-return total row", () => {
    render(<BacktestResults bt={BASE} />);
    expect(
      screen.getByText("Performance Attribution (Brinson-Fachler · Carino-linked)")
    ).toBeInTheDocument();
    // localized group labels
    expect(screen.getByText("Equity")).toBeInTheDocument();
    expect(screen.getByText("Bonds")).toBeInTheDocument();
    // totals row: effects + cumulative active return
    expect(screen.getByText("Cumulative Active Return")).toBeInTheDocument();
    expect(screen.getByText("+5.00%")).toBeInTheDocument();
  });

  it("omits the block when attribution is null", () => {
    render(<BacktestResults bt={{ ...BASE, attribution: null }} />);
    expect(
      screen.queryByText(/Performance Attribution/)
    ).not.toBeInTheDocument();
  });
});
