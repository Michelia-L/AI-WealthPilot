import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { OptimizeResponse } from "@/lib/api";
import { optimizer } from "@/lib/i18n/dictionaries/en/optimizer";
import OptimizerBacktest from "./optimizer-backtest";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ optimizer }),
}));
vi.mock("@/components/backtest-results", () => ({
  default: ({ bt }: { bt: { period: string } }) => (
    <div data-testid="backtest-results">{bt.period}</div>
  ),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const RESULT = {
  asset_stats: [
    { name: "US Equities (S&P 500)", ticker: "SPY" },
    { name: "US Aggregate Bonds", ticker: "AGG" },
    { name: "Gold", ticker: "GLD" },
  ],
  selected: {
    weights: {
      "US Equities (S&P 500)": 0.6,
      "US Aggregate Bonds": 0.35,
      Gold: 0.00005, // below the 1e-4 cutoff — must be filtered out
    },
  },
} as unknown as OptimizeResponse;

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(() =>
    Promise.resolve(jsonResponse({ period: "5y" }))
  );
});

describe("OptimizerBacktest", () => {
  it("maps display names to tickers and drops near-zero weights", async () => {
    render(<OptimizerBacktest result={RESULT} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Backtest This Portfolio" })
    );

    expect(await screen.findByTestId("backtest-results")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/portfolio/backtest");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      weights: { SPY: 0.6, AGG: 0.35 },
      period: "5y",
    });
  });

  it("re-runs on period switch once a result exists", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const period = init?.body
        ? JSON.parse(init.body as string).period
        : "5y";
      return Promise.resolve(jsonResponse({ period }));
    });
    render(<OptimizerBacktest result={RESULT} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Backtest This Portfolio" })
    );
    expect(await screen.findByTestId("backtest-results")).toHaveTextContent("5y");

    fireEvent.click(screen.getByRole("button", { name: "3Y" }));
    await waitFor(() =>
      expect(screen.getByTestId("backtest-results")).toHaveTextContent("3y")
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
    // button now reads as a re-run
    expect(
      screen.getByRole("button", { name: "Re-run Backtest" })
    ).toBeInTheDocument();
  });

  it("shows API errors", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: "price history missing" }, 422))
    );
    render(<OptimizerBacktest result={RESULT} />);
    fireEvent.click(
      screen.getByRole("button", { name: "Backtest This Portfolio" })
    );
    expect(
      await screen.findByText("price history missing")
    ).toBeInTheDocument();
  });
});
