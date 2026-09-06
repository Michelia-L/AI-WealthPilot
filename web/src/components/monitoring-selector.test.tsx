import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { common as en } from "@/lib/i18n/dictionaries/en/common";
import { common as zh } from "@/lib/i18n/dictionaries/zh/common";
import MonitoringSelector from "./monitoring-selector";

const state = vi.hoisted(() => ({ clientId: null as number | null, push: vi.fn(), locale: "en" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: state.push }) }));
vi.mock("@/components/client-context", () => ({
  useClient: () => ({ clientId: state.clientId, clientName: "Same Name" }),
}));
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ common: state.locale === "en" ? en : zh }),
}));

const documents = [
  { document_id: "ips_a_20260906_123401", profile_id: 1 },
  { document_id: "ips_b_20260906_123401", profile_id: 1 }, // same short suffix
  { document_id: "ips_c_20260906_123402", profile_id: 2 }, // same client name
  { document_id: "ips_legacy_20260906_123403" }, // no client ID
].map((d) => ({
  ...d, client_name: "Same Name", version: "1.0", risk_level: "Moderate",
  status: "approved", revision_rounds: 0, saved_at: "2026-09-06T12:34:01",
}));

beforeEach(() => { state.clientId = null; state.locale = "en"; state.push.mockReset(); });

describe("MonitoringSelector", () => {
  it("filters by stable client ID after hydration, and keeps legacy documents accessible", () => {
    const { rerender } = render(<MonitoringSelector documents={documents} selected="" />);
    expect(screen.getAllByRole("option")).toHaveLength(5);
    state.clientId = 1;
    rerender(<MonitoringSelector documents={documents} selected="" />);
    const picker = screen.getByRole("combobox", { name: en.monitoringSelector.label });
    expect(Array.from(picker.querySelectorAll("option")).map((o) => o.value))
      .toEqual(["", documents[0].document_id, documents[1].document_id]);
    const labels = Array.from(picker.querySelectorAll("option")).map((o) => o.textContent);
    expect(new Set(labels).size).toBe(labels.length);

    fireEvent.change(screen.getByRole("combobox", { name: "Filter by client" }), { target: { value: "all" } });
    expect(picker.querySelectorAll("option")).toHaveLength(5);
    expect(screen.getByRole("group", { name: "Unlinked documents" })).toBeInTheDocument();
    state.clientId = 2;
    rerender(<MonitoringSelector documents={documents} selected="" />);
    expect(Array.from(picker.querySelectorAll("option")).map((o) => o.value))
      .toEqual(["", documents[2].document_id]);
  });

  it("preserves explicit document links and clears an out-of-filter selection when requested", () => {
    state.clientId = 1;
    render(<MonitoringSelector documents={documents} selected={documents[2].document_id} />);
    expect(screen.getByRole("combobox", { name: en.monitoringSelector.label })).toHaveValue(documents[2].document_id);
    const filter = screen.getByRole("combobox", { name: "Filter by client" });
    expect(filter).toHaveValue("all");
    fireEvent.change(filter, { target: { value: "current" } });
    expect(state.push).toHaveBeenCalledWith("/monitoring");
    expect(screen.getByRole("combobox", { name: en.monitoringSelector.label })).toHaveValue("");
  });

  it("navigates to a selected document", () => {
    render(<MonitoringSelector documents={documents} selected="" />);
    fireEvent.change(screen.getByRole("combobox", { name: en.monitoringSelector.label }), {
      target: { value: documents[0].document_id },
    });
    expect(state.push).toHaveBeenCalledWith(`/monitoring?doc=${documents[0].document_id}`);
  });

  it("explains an empty client filter in Chinese without guessing legacy ownership", () => {
    state.clientId = 99;
    state.locale = "zh";
    render(<MonitoringSelector documents={documents} selected="" />);
    expect(screen.getByRole("status")).toHaveTextContent(zh.monitoringSelector.noClientDocuments);
    expect(screen.getByRole("combobox", { name: zh.monitoringSelector.label }).querySelectorAll("option")).toHaveLength(1);
    expect(screen.getByText(zh.monitoringSelector.unlinkedHint)).toBeInTheDocument();
  });
});
