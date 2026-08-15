import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { retirement } from "@/lib/i18n/dictionaries/en/retirement";
import RetirementWorkspace from "./retirement-workspace";

// The workspace reads copy through the locale context — serve the real
// English dictionary; Plotly stays out of jsdom.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ retirement }),
  useLocale: () => ({ locale: "en" }),
}));
vi.mock("@/components/client-context", () => ({
  useClient: () => ({ clientId: null, clientName: null, select: vi.fn() }),
}));
vi.mock("@/components/plot-chart", () => ({ default: () => null }));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const RETIREMENT_RESULT = {
  as_of: "2026-08-14T00:00:00Z",
  params: {
    expected_return: 0.07,
    volatility: 0.15,
    inflation_rate: 0.025,
    distribution_inflation_rate: 0.0325,
    n_simulations: 10000,
    seed: 42,
  },
  survival_rate: 0.82,
  accumulation_years: 30,
  distribution_years: 25,
  terminal_at_retirement: {
    mean: 900000,
    median: 850000,
    p5: 400000,
    p25: 650000,
    p75: 1100000,
    p95: 1500000,
  },
  accumulation_chart: { data: [] },
  distribution_chart: { data: [] },
  depletion: {
    never_depleted_pct: 0.82,
    depleted_within_10y_pct: 0.03,
    median_depletion_year: 20,
  },
  sensitivity: [],
  comparison: {
    fixed_survival_rate: 0.7,
    guardrails_survival_rate: 0.82,
    survival_lift: 0.12,
    guardrail_band: 0.2,
    guardrail_adjust: 0.1,
  },
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

beforeEach(() => {
  fetchMock.mockReset();
  // Fresh Response per call: the workspace fetches the CME suggestion on
  // mount AND the simulation on run — a shared Response body drains once.
  fetchMock.mockImplementation(() =>
    Promise.resolve(jsonResponse(RETIREMENT_RESULT))
  );
});

describe("RetirementWorkspace LDI deep link", () => {
  it("links the current income stream into the optimizer's retirement channel", () => {
    render(<RetirementWorkspace />);
    const link = screen.getByRole("link", { name: /Optimize with LDI/ });
    const href = link.getAttribute("href") ?? "";
    // Default form: 30→60 (ytr=30), 60→85 (dy=25), income 80k, savings 100k.
    expect(href).toContain("method=surplus");
    expect(href).toContain("source=retirement");
    expect(href).toContain("ytr=30");
    expect(href).toContain("dy=25");
    expect(href).toContain("income=80000");
    expect(href).toContain("asset_value=100000");
  });
});

describe("RetirementWorkspace form behavior", () => {
  it("shows the custom inflation slider only for the custom preset", () => {
    render(<RetirementWorkspace />);
    expect(screen.queryByText("Distribution-Phase Inflation")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Elderly" }));
    expect(screen.queryByText("Distribution-Phase Inflation")).not.toBeInTheDocument();
    expect(screen.getByText(/segment-adjusted rate/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    expect(screen.getByText("Distribution-Phase Inflation")).toBeInTheDocument();
  });

  it("reveals guardrail sliders and sends the strategy payload", async () => {
    render(<RetirementWorkspace />);
    expect(screen.queryByText("Guardrail Band")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));
    expect(screen.getByText("Guardrail Band")).toBeInTheDocument();
    expect(screen.getByText("Adjustment")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          (url as string).includes("/simulate")
        )
      ).toBe(true)
    );
    const simCall = fetchMock.mock.calls.find(([url]) =>
      (url as string).includes("/simulate")
    )!;
    const [, init] = simCall;
    const body = JSON.parse(init.body as string);
    expect(body.withdrawal_strategy).toBe("guardrails");
    expect(body.guardrail_band).toBe(0.2);
    expect(body.guardrail_adjust).toBe(0.1);
  });

  it("blocks the run and warns when ages are inconsistent", () => {
    render(<RetirementWorkspace />);
    const sliders = screen.getAllByRole("slider");
    // Slider order: current age, retirement age, life expectancy, ...
    fireEvent.change(sliders[1], { target: { value: "25" } });
    expect(screen.getByText(/current age < retirement age/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Simulation" })).toBeDisabled();
    // The CME suggestion fetch on mount is fine; the simulate POST must not fire.
    expect(
      fetchMock.mock.calls.some(([url]) => (url as string).includes("/simulate"))
    ).toBe(false);
  });
});

describe("RetirementWorkspace results", () => {
  it("renders the guardrails comparison tiles when present", async () => {
    render(<RetirementWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: "Guardrails" }));
    fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));

    expect(await screen.findByText("Fixed-Strategy Survival")).toBeInTheDocument();
    expect(screen.getByText("Survival Lift")).toBeInTheDocument();
    expect(screen.getByText("70.0%")).toBeInTheDocument();
    expect(screen.getByText("+12.0 pp")).toBeInTheDocument();
  });

  it("surfaces API errors as localized messages", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        jsonResponse({ detail: "retirement_age must be greater than current_age." }, 422)
      )
    );
    render(<RetirementWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
    expect(
      await screen.findByText(/retirement_age must be greater/)
    ).toBeInTheDocument();
  });
});

describe("RetirementWorkspace CME suggestion", () => {
  const SUGGESTION = {
    expected_return: 0.064,
    volatility: 0.12,
    allocation: { "Fixed Income": 0.4 },
    as_of_date: "2026-08-14",
    cache_status: "fresh",
  };

  it("adopts the suggested μ/σ into the simulation request", async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes("/cme-suggestion")
        ? Promise.resolve(jsonResponse(SUGGESTION))
        : Promise.resolve(jsonResponse(RETIREMENT_RESULT))
    );
    render(<RetirementWorkspace />);

    const adopt = await screen.findByRole("button", { name: "Adopt" });
    fireEvent.click(adopt);

    fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          (url as string).includes("/simulate")
        )
      ).toBe(true)
    );
    const simCall = fetchMock.mock.calls.find(([url]) =>
      (url as string).includes("/simulate")
    )!;
    const body = JSON.parse((simCall[1] as RequestInit).body as string);
    expect(body.expected_return).toBeCloseTo(0.064);
    expect(body.volatility).toBeCloseTo(0.12);
  });

  it("hides the card when the suggestion endpoint fails", async () => {
    fetchMock.mockImplementation((url: string) =>
      url.includes("/cme-suggestion")
        ? Promise.resolve(jsonResponse({ detail: "boom" }, 502))
        : Promise.resolve(jsonResponse(RETIREMENT_RESULT))
    );
    render(<RetirementWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          (url as string).includes("/simulate")
        )
      ).toBe(true)
    );
    expect(screen.queryByRole("button", { name: "Adopt" })).not.toBeInTheDocument();
  });
});

describe("RetirementWorkspace client channel", () => {
  const PROFILES = [
    { id: 1, name: "Jane Doe", age: 45, risk_level: "Moderate / 平衡型" },
  ] as never;

  const PROFILE_DETAIL = {
    id: 1,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    profile: {
      name: "Jane Doe",
      age: 45,
      marital_status: "married",
      dependents: 1,
      financial: {
        annual_income: 200000,
        annual_expenses: 120000,
        investable_assets: 800000,
        total_liabilities: 0,
        emergency_fund_months: 6,
      },
      goals: [],
      time_horizon_years: 20,
      is_multi_stage: false,
      liquidity_needs: 0,
      tax_status: "taxable",
      esg_preference: false,
      sector_restrictions: [],
      notes: "",
      risk_profile: {
        ability_score: 3,
        willingness_score: 3,
        tolerance_level: "Moderate / 平衡型",
        description: "",
      },
      ability_answers: {},
      willingness_answers: {},
      created_at: "2026-01-01",
      updated_at: "2026-01-01",
    },
    derived: {},
  };

  const LEVEL_SUGGESTION = {
    expected_return: 0.052,
    volatility: 0.10,
    allocation: { "Fixed Income": 0.6 },
    as_of_date: "2026-08-15",
    cache_status: "cached",
    risk_level: "Moderate / 平衡型",
  };

  function mockClientChannel() {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/cme-suggestion?profile_id=1")) {
        return Promise.resolve(jsonResponse(LEVEL_SUGGESTION));
      }
      if (url.includes("/cme-suggestion")) {
        return Promise.resolve(
          jsonResponse({ ...LEVEL_SUGGESTION, risk_level: null })
        );
      }
      if (url.includes("/api/profiles/1")) {
        return Promise.resolve(jsonResponse(PROFILE_DETAIL));
      }
      return Promise.resolve(jsonResponse(RETIREMENT_RESULT));
    });
  }

  it("prefills the form from the profile and fetches the level-keyed suggestion", async () => {
    mockClientChannel();
    render(<RetirementWorkspace profiles={PROFILES} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });

    // level-keyed suggestion card appears
    expect(
      await screen.findByText(/Moderate reference portfolio/)
    ).toBeInTheDocument();

    // run and read the simulate body: prefilled age/savings/income
    fireEvent.click(screen.getByRole("button", { name: "Adopt" }));
    fireEvent.click(screen.getByRole("button", { name: "Run Simulation" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          (url as string).includes("/simulate")
        )
      ).toBe(true)
    );
    const simCall = fetchMock.mock.calls.find(([url]) =>
      (url as string).includes("/simulate")
    )!;
    const body = JSON.parse((simCall[1] as RequestInit).body as string);
    expect(body.current_age).toBe(45);
    expect(body.current_savings).toBe(800000);
    expect(body.annual_savings).toBe(80000); // 200k income − 120k expenses
    expect(body.desired_annual_income).toBe(120000);
    // adopted the level-keyed suggestion
    expect(body.expected_return).toBeCloseTo(0.052);
    expect(body.volatility).toBeCloseTo(0.1);
  });

  it("manual option returns to the un-keyed suggestion", async () => {
    mockClientChannel();
    render(<RetirementWorkspace profiles={PROFILES} />);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "1" } });
    await screen.findByText(/Moderate reference portfolio/);

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "" } });
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url]) =>
            (url as string).includes("/cme-suggestion") &&
            !(url as string).includes("profile_id")
        )
      ).toBe(true)
    );
  });

  it("hides the selector when no profiles are available", () => {
    render(<RetirementWorkspace profiles={[]} />);
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
