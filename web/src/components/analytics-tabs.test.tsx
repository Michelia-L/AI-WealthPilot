import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AnalyticsResponse, RiskStat } from "@/lib/api";
import { market } from "@/lib/i18n/dictionaries/en/market";
import AnalyticsTabs from "./analytics-tabs";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ market }),
}));
vi.mock("@/components/plot-chart", () => ({ default: () => null }));

const STATS: RiskStat[] = [
  {
    ticker: "AAA",
    name: "Charlie",
    ann_return: 0.08,
    ann_volatility: 0.2,
    sharpe: 0.4,
    max_drawdown: -0.25,
    var_95: -0.02,
  },
  {
    ticker: "BBB",
    name: "Alpha",
    ann_return: 0.12,
    ann_volatility: 0.1,
    sharpe: 0.9,
    max_drawdown: -0.1,
    var_95: -0.01,
  },
  {
    ticker: "CCC",
    name: "Bravo",
    ann_return: 0.04,
    ann_volatility: 0.15,
    sharpe: 0.2,
    max_drawdown: -0.4,
    var_95: -0.03,
  },
];

const ANALYTICS = {
  period: "1y",
  tickers: ["AAA", "BBB", "CCC"],
  as_of: "2026-01-01",
  price_chart: { data: [], layout: {} },
  correlation_chart: null,
  stats: STATS,
} as unknown as AnalyticsResponse;

/** First-cell (asset name) text of each body row, in DOM order. */
const rowNames = () =>
  [...document.querySelectorAll("tbody tr")].map(
    (tr) => tr.querySelector("td div")!.textContent
  );

function openStatsTab() {
  render(<AnalyticsTabs analytics={ANALYTICS} />);
  fireEvent.click(screen.getByRole("tab", { name: market.tabStats }));
}

describe("AnalyticsTabs risk-stats sorting", () => {
  it("keeps API order by default", () => {
    openStatsTab();
    expect(rowNames()).toEqual(["Charlie", "Alpha", "Bravo"]);
  });

  it("cycles a numeric column asc → desc → default on repeated clicks", () => {
    openStatsTab();
    const header = screen.getByRole("button", {
      name: `${market.thAnnReturn}: ${market.sortAsc}`,
    });

    fireEvent.click(header); // ascending
    expect(rowNames()).toEqual(["Bravo", "Charlie", "Alpha"]);

    fireEvent.click(
      screen.getByRole("button", {
        name: `${market.thAnnReturn}: ${market.sortDesc}`,
      })
    ); // descending
    expect(rowNames()).toEqual(["Alpha", "Charlie", "Bravo"]);

    fireEvent.click(
      screen.getByRole("button", {
        name: `${market.thAnnReturn}: ${market.sortReset}`,
      })
    ); // back to default order
    expect(rowNames()).toEqual(["Charlie", "Alpha", "Bravo"]);
  });

  it("sorts the asset column alphabetically", () => {
    openStatsTab();
    fireEvent.click(
      screen.getByRole("button", { name: `${market.thAsset}: ${market.sortAsc}` })
    );
    expect(rowNames()).toEqual(["Alpha", "Bravo", "Charlie"]);
  });

  it("switching columns restarts the new column at ascending", () => {
    openStatsTab();
    fireEvent.click(
      screen.getByRole("button", {
        name: `${market.thAnnReturn}: ${market.sortAsc}`,
      })
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: `${market.thAnnVol}: ${market.sortAsc}`,
      })
    );
    expect(rowNames()).toEqual(["Alpha", "Bravo", "Charlie"]); // by vol asc: 0.1, 0.15, 0.2
  });
});
