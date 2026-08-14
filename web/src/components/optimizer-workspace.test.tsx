import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AssetClassInfo } from "@/lib/api";
import { optimizer } from "@/lib/i18n/dictionaries/en/optimizer";
import OptimizerWorkspace from "./optimizer-workspace";

// Real English dictionary for the whole component tree.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ optimizer }),
}));

// Client context is varied per test.
const useClientMock = vi.fn(() => ({ clientId: 42, clientName: "Jane" }));
vi.mock("@/components/client-context", () => ({
  useClient: () => useClientMock(),
}));

vi.mock("@/components/plot-chart", () => ({ default: () => null }));

// The resampled path streams progress over SSE — complete immediately.
vi.mock("@/lib/sse", () => ({
  readSseStream: vi.fn(
    async (_body: unknown, onEvent: (e: Record<string, unknown>) => void) => {
      onEvent({ type: "done", result: OPTIMIZE_RESULT });
    }
  ),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const OPTIMIZE_RESULT = {
  as_of: "2026-08-14T00:00:00Z",
  params: {
    assets: ["US_EQUITY"],
    period: "5y",
    risk_free_rate: 0.0,
    method: "mvo",
    mode: "max-sharpe",
    allow_short: false,
    n_simulations: null,
    trading_days: 100,
  },
  selected: {
    weights: {},
    ann_return: 0.05,
    ann_volatility: 0.1,
    sharpe: 0.5,
    success: true,
    weight_std: null,
    cvar: null,
    risk_contributions: null,
  },
  max_sharpe: {
    weights: {},
    ann_return: 0.05,
    ann_volatility: 0.1,
    sharpe: 0.5,
    success: true,
    weight_std: null,
    cvar: null,
    risk_contributions: null,
  },
  min_vol: {
    weights: {},
    ann_return: 0.05,
    ann_volatility: 0.1,
    sharpe: 0.5,
    success: true,
    weight_std: null,
    cvar: null,
    risk_contributions: null,
  },
  frontier_chart: { data: [] },
  allocation_chart: { data: [] },
  asset_stats: [],
  bl: null,
  surplus: null,
  risk_constraints: null,
};

const ASSET_CLASSES: Record<string, AssetClassInfo> = {
  US_EQUITY: { ticker: "SPY", name: "US Equities (S&P 500)" },
  INTL_EQUITY: { ticker: "EFA", name: "International Developed Equities" },
  US_BOND: { ticker: "AGG", name: "US Aggregate Bonds" },
  GOLD: { ticker: "GLD", name: "Gold" },
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

function renderWorkspace() {
  return render(<OptimizerWorkspace assetClasses={ASSET_CLASSES} />);
}

async function runAndReadBody(buttonName = "Run Optimization") {
  fireEvent.click(screen.getByRole("button", { name: buttonName }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalled());
  const [, init] = fetchMock.mock.calls[0];
  return JSON.parse(init.body as string);
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation((url: string) => {
    if (url.includes("/optimize/async")) {
      return Promise.resolve(jsonResponse({ task_id: "task-1" }, 202));
    }
    return Promise.resolve(jsonResponse(OPTIMIZE_RESULT));
  });
  useClientMock.mockReturnValue({ clientId: 42, clientName: "Jane" });
  sessionStorage.clear();
});

describe("OptimizerWorkspace buildBody", () => {
  it("mvo: sends the selected client's profile_id for risk caps", async () => {
    renderWorkspace();
    const body = await runAndReadBody();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/portfolio/optimize");
    expect(body.method).toBe("mvo");
    expect(body.profile_id).toBe(42);
    expect(body.bl).toBeUndefined();
    expect(body.surplus).toBeUndefined();
    expect(body.expected_return_source).toBeUndefined();
  });

  it("resampled: goes async with n_simulations", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Resampled MVO" }));
    const body = await runAndReadBody();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/portfolio/optimize/async");
    expect(body.method).toBe("resampled");
    expect(body.n_simulations).toBe(200);
  });

  it("black-litterman: suppresses a stale cme expected-return source", async () => {
    renderWorkspace();
    // Pick CME first, then switch to BL — the source must not leak into the body.
    fireEvent.click(screen.getByRole("button", { name: "CME" }));
    fireEvent.click(screen.getByRole("button", { name: "Black-Litterman" }));
    fireEvent.click(screen.getByRole("button", { name: "Add View" }));
    const body = await runAndReadBody();
    expect(body.method).toBe("black-litterman");
    expect(body.bl.views).toHaveLength(1);
    expect(body.bl.views[0]).toMatchObject({
      view_type: "absolute",
      asset_long: "US_EQUITY",
      expected_return: 0.1,
    });
    expect(body.expected_return_source).toBeUndefined();
  });

  it("mean-cvar: sends the confidence level", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Mean-CVaR" }));
    const body = await runAndReadBody();
    expect(body.method).toBe("mean-cvar");
    expect(body.cvar_confidence).toBe(0.95);
  });

  it("surplus manual channel: ratio/duration, no profile_id", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Surplus (LDI)" }));
    const body = await runAndReadBody();
    expect(body.method).toBe("surplus");
    expect(body.surplus).toMatchObject({
      liability_ratio: 1.0,
      liability_duration: 10,
      growth_source: "inflation",
      inflation_preset: "standard",
      proxy: "US_BOND",
    });
    expect(body.profile_id).toBeUndefined();
  });

  it("surplus retirement channel with a client: profile_id, no preset, no asset_value", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Surplus (LDI)" }));
    fireEvent.click(screen.getByRole("button", { name: "Retirement Stream" }));
    const body = await runAndReadBody();
    expect(body.profile_id).toBe(42);
    expect(body.surplus).toMatchObject({
      years_to_retirement: 20,
      distribution_years: 25,
      annual_income: 80000,
    });
    expect(body.surplus.liability_ratio).toBeUndefined();
    expect(body.surplus.asset_value).toBeUndefined();
    expect(body.surplus.inflation_preset).toBeUndefined();
  });

  it("surplus retirement channel without a client: explicit asset_value + preset", async () => {
    useClientMock.mockReturnValue({ clientId: null, clientName: null });
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Surplus (LDI)" }));
    fireEvent.click(screen.getByRole("button", { name: "Retirement Stream" }));
    const body = await runAndReadBody();
    expect(body.profile_id).toBeUndefined();
    expect(body.surplus.asset_value).toBe(1000000);
    expect(body.surplus.inflation_preset).toBe("standard");
  });

  it("risk-parity: forces allow_short off even when toggled", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("switch", { name: "Allow Shorting" }));
    fireEvent.click(screen.getByRole("button", { name: "Risk Parity (ERC)" }));
    const body = await runAndReadBody();
    expect(body.method).toBe("risk-parity");
    expect(body.allow_short).toBe(false);
  });
});
