import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AssetClassInfo, BLViewInput } from "@/lib/api";
import { optimizer } from "@/lib/i18n/dictionaries/en/optimizer";
import BLConfigPanel from "./bl-config-panel";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ optimizer }),
}));

const ASSETS = ["US_EQUITY", "INTL_EQUITY"];
const ASSET_CLASSES: Record<string, AssetClassInfo> = {
  US_EQUITY: { ticker: "SPY", name: "US Equities (S&P 500)" },
  INTL_EQUITY: { ticker: "EFA", name: "International Developed Equities" },
};

function Harness() {
  const [equalWeights, setEqualWeights] = useState(true);
  const [marketWeights, setMarketWeights] = useState<Record<string, string>>({});
  const [views, setViews] = useState<BLViewInput[]>([]);
  return (
    <BLConfigPanel
      assets={ASSETS}
      assetClasses={ASSET_CLASSES}
      blTau="0.025"
      setBlTau={() => {}}
      blDelta="2.5"
      setBlDelta={() => {}}
      equalWeights={equalWeights}
      setEqualWeights={setEqualWeights}
      marketWeights={marketWeights}
      setMarketWeights={setMarketWeights}
      views={views}
      setViews={setViews}
    />
  );
}

describe("BLConfigPanel", () => {
  it("shows the empty hint until a view is added", () => {
    render(<Harness />);
    expect(screen.getByText(/requires at least one view/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add View" }));
    expect(screen.queryByText(/requires at least one view/i)).not.toBeInTheDocument();
  });

  it("adds a default absolute view on the first asset", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Add View" }));
    expect(screen.getByLabelText("View return (%)")).toHaveValue(10);
    expect(screen.getByLabelText("View type")).toHaveValue("absolute");
    expect(screen.getByLabelText("Long asset")).toHaveValue("US_EQUITY");
  });

  it("reveals the excess-return field for relative views", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Add View" }));
    expect(screen.queryByLabelText("Short asset")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("View type"), {
      target: { value: "relative" },
    });
    expect(screen.getByLabelText("Short asset")).toBeInTheDocument();
  });

  it("deletes a view row", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Add View" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete view" }));
    expect(screen.getByText(/requires at least one view/i)).toBeInTheDocument();
  });

  it("shows per-asset weight inputs when custom weights are enabled", () => {
    render(<Harness />);
    expect(screen.queryByLabelText(/benchmark weight/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("switch"));
    expect(
      screen.getByLabelText("US Equities (S&P 500) benchmark weight (%)")
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("International Developed Equities benchmark weight (%)")
    ).toBeInTheDocument();
  });
});
