import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { HoldingSnapshotHistory } from "@/lib/api";
import { dictionaries } from "@/lib/i18n/dictionaries";
import HoldingsWorkspace from "./holdings-workspace";

const state = vi.hoisted(() => ({ refresh: vi.fn(), locale: "en" as "en" | "zh" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: state.refresh }) }));
vi.mock("@/components/locale-context", () => ({ useT: () => dictionaries[state.locale] }));
const c = dictionaries.en.monitoring.holdings;
const history: HoldingSnapshotHistory = {
  document_id: "ips_example", base_currency: "CNY", valuation_timezone: "Asia/Shanghai",
  assets: [{ asset_class: "Fixed Income", key: "fixed_income" }, { asset_class: "Cash", key: "cash" }], snapshots: [],
};
const fetchMock = vi.fn();
beforeEach(() => { state.locale = "en"; state.refresh.mockReset(); fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); });
afterEach(() => vi.unstubAllGlobals());

function fillAmount() {
  fireEvent.change(screen.getByLabelText(c.asOf), { target: { value: "2026-06-10" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: c.amount }), { target: { value: "800" } });
}

describe("HoldingsWorkspace", () => {
  it("records a base-currency amount and refreshes the monitoring snapshot", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 7 }), { status: 201 }));
    render(<HoldingsWorkspace history={history} />);
    expect(screen.getByText(c.empty)).toBeInTheDocument();
    fillAmount();
    fireEvent.change(screen.getByLabelText(c.cost), { target: { value: "700" } });
    fireEvent.change(screen.getByLabelText(c.costDate), { target: { value: "2026-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: c.save }));
    await waitFor(() => expect(state.refresh).toHaveBeenCalledOnce());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/monitoring/ips_example/holdings");
    expect(JSON.parse(init.body)).toEqual({
      as_of: "2026-06-10", base_currency: "CNY", holdings: [{
        asset_class: "Fixed Income", market_value: 800, cost_basis: 700, cost_basis_date: "2026-01-01",
      }],
    });
    expect(screen.getByRole("status")).toHaveTextContent(c.saved);
  });

  it("switches to quantities without sending the previous amount", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 8 }), { status: 201 }));
    render(<HoldingsWorkspace history={history} />);
    fillAmount();
    fireEvent.change(screen.getByLabelText(c.method), { target: { value: "units" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: c.quantity }), { target: { value: "40" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: c.price }), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: c.save }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).holdings[0]).toEqual({
      asset_class: "Fixed Income", quantity: 40, unit_price: 20, cost_basis: null, cost_basis_date: null,
    });
  });

  it("adds and removes rows without losing the remaining inputs", () => {
    render(<HoldingsWorkspace history={history} />);
    fillAmount();
    fireEvent.click(screen.getByRole("button", { name: c.add }));
    expect(screen.getAllByLabelText(c.asset)).toHaveLength(2);
    expect(screen.getAllByLabelText(c.asset)[1]).toHaveValue("Cash");
    fireEvent.click(screen.getAllByRole("button", { name: c.remove })[1]);
    expect(screen.getByRole("spinbutton", { name: c.amount })).toHaveValue(800);
  });

  it("keeps failed input reviewable and renders localized backend errors", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "The valuation date cannot be in the future." }), { status: 422 }));
    render(<HoldingsWorkspace history={history} />);
    fillAmount();
    fireEvent.click(screen.getByRole("button", { name: c.save }));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be in the future");
    expect(screen.getByRole("spinbutton", { name: c.amount })).toHaveValue(800);
    expect(state.refresh).not.toHaveBeenCalled();
  });

  it("validates JSON syntax and sends imports through the same proxy", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 9 }), { status: 201 }));
    render(<HoldingsWorkspace history={history} />);
    fireEvent.click(screen.getByText(c.importTitle));
    fireEvent.change(screen.getByLabelText(c.importData), { target: { value: "{" } });
    fireEvent.click(screen.getByRole("button", { name: c.importSave }));
    expect(screen.getByRole("alert")).toHaveTextContent(c.importFailed);
    expect(fetchMock).not.toHaveBeenCalled();
    const payload = { as_of: "2026-06-01", base_currency: "CNY", holdings: [{ asset_class: "Cash", market_value: 10 }] };
    fireEvent.change(screen.getByLabelText(c.importData), { target: { value: JSON.stringify(payload) } });
    fireEvent.click(screen.getByRole("button", { name: c.importSave }));
    await waitFor(() => expect(state.refresh).toHaveBeenCalledOnce());
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual(payload);
  });

  it("shows recorded comparisons without calculating investment returns", () => {
    const snapshots = [2, 1].map((id) => ({
      id, document_id: history.document_id, as_of: `2026-06-0${id}`, created_at: `2026-06-0${id}T12:00:00`,
      base_currency: "CNY", total_market_value: 100 * id, previous_snapshot_id: id === 2 ? 1 : null,
      total_market_value_change: id === 2 ? 100 : null,
      holdings: [{ asset_class: "Cash", market_value: 100 * id, weight: 1, market_value_change: id === 2 ? 100 : null, weight_change: id === 2 ? 0 : null }],
    }));
    render(<HoldingsWorkspace history={{ ...history, snapshots }} />);
    expect(screen.getByLabelText(c.choose)).toHaveValue("2");
    expect(screen.getByText(/Compared with previous snapshot: 2026-06-01/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(c.choose), { target: { value: "1" } });
    expect(screen.queryByText(/Compared with previous snapshot: 2026-06-01/)).not.toBeInTheDocument();
    expect(screen.getByText(c.comparisonHint)).toBeInTheDocument();
  });

  it("uses Chinese copy", () => {
    state.locale = "zh";
    render(<HoldingsWorkspace history={history} />);
    expect(screen.getByRole("heading", { name: "实际持仓" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存新快照" })).toBeInTheDocument();
  });
});

it("rejects zero unit prices before POST and clears validity after correction", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ id: 10 }), { status: 201 }));
  render(<HoldingsWorkspace history={history} />);
  fillAmount();
  fireEvent.change(screen.getByLabelText(c.method), { target: { value: "units" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: c.quantity }), { target: { value: "1" } });
  const price = screen.getByRole("spinbutton", { name: c.price }) as HTMLInputElement;
  fireEvent.change(price, { target: { value: "0" } });
  expect(price.validity.valid).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: c.save }));
  expect(fetchMock).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent(c.positivePrice);
  fireEvent.change(price, { target: { value: "0.000001" } });
  expect(price.validity.valid).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: c.save }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
});

it.each(["en", "zh"] as const)("renders field-level import errors in %s", async (locale) => {
  state.locale = locale;
  const copy = dictionaries[locale].monitoring.holdings;
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: [
    { loc: ["body", "holdings", 0, "unit_price"], type: "greater_than", input: 0 },
  ] }), { status: 422 }));
  render(<HoldingsWorkspace history={history} />);
  fireEvent.click(screen.getByText(copy.importTitle));
  fireEvent.change(screen.getByLabelText(copy.importData), { target: { value: JSON.stringify({
    as_of: "2026-06-10", base_currency: "CNY", holdings: [{ asset_class: "Cash", quantity: 1, unit_price: 0 }],
  }) } });
  fireEvent.click(screen.getByRole("button", { name: copy.importSave }));
  expect(await screen.findByRole("alert")).toHaveTextContent(copy.rowError(1, copy.price, copy.positivePrice));
});
