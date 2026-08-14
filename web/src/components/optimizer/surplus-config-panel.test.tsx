import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { AssetClassInfo, SurplusGrowthSource } from "@/lib/api";
import { optimizer } from "@/lib/i18n/dictionaries/en/optimizer";
import SurplusConfigPanel, {
  type SurplusInflationPreset,
  type SurplusSource,
} from "./surplus-config-panel";

// The panel reads copy through the locale context — serve the real English
// dictionary so tests assert actual user-facing keys, not stubs.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ optimizer }),
}));

const ASSET_CLASSES: Record<string, AssetClassInfo> = {
  US_BOND: { ticker: "AGG", name: "US Aggregate Bonds" },
  LONG_TREASURY_BOND: { ticker: "TLT", name: "Long-Term US Treasuries" },
  TIPS: { ticker: "TIP", name: "Treasury Inflation-Protected" },
  CN_TREASURY: { ticker: "511010.SS", name: "China 5Y Treasury ETF" },
};

function Harness({ hasClient = false }: { hasClient?: boolean }) {
  const [source, setSource] = useState<SurplusSource>("manual");
  const [growthSource, setGrowthSource] =
    useState<SurplusGrowthSource>("inflation");
  const [preset, setPreset] = useState<SurplusInflationPreset>("standard");
  return (
    <SurplusConfigPanel
      assetClasses={ASSET_CLASSES}
      hasClient={hasClient}
      clientName={hasClient ? "Jane" : null}
      source={source}
      setSource={setSource}
      liabilityRatio={1.2}
      setLiabilityRatio={() => {}}
      liabilityDuration={12}
      setLiabilityDuration={() => {}}
      proxy="US_BOND"
      setProxy={() => {}}
      growthSource={growthSource}
      setGrowthSource={setGrowthSource}
      customGrowth="3.0"
      setCustomGrowth={() => {}}
      inflationPreset={preset}
      setInflationPreset={setPreset}
      yearsToRetirement={20}
      setYearsToRetirement={() => {}}
      distributionYears={25}
      setDistributionYears={() => {}}
      annualIncome="80000"
      setAnnualIncome={() => {}}
      assetValue="1000000"
      setAssetValue={() => {}}
    />
  );
}

describe("SurplusConfigPanel", () => {
  it("shows the manual inputs by default", () => {
    render(<Harness />);
    expect(screen.getByText("Liability Ratio (L/A)")).toBeInTheDocument();
    expect(screen.getByText("Liability Duration")).toBeInTheDocument();
    expect(screen.queryByText("Years to Retirement")).not.toBeInTheDocument();
  });

  it("switches to the retirement channel inputs", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Retirement Stream" }));
    expect(screen.getByText("Years to Retirement")).toBeInTheDocument();
    expect(screen.getByText("Distribution Years")).toBeInTheDocument();
    expect(
      screen.getByText("Annual Income (today's money)")
    ).toBeInTheDocument();
    expect(screen.queryByText("Liability Ratio (L/A)")).not.toBeInTheDocument();
  });

  it("requires an explicit asset base without a client", () => {
    render(<Harness hasClient={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Retirement Stream" }));
    expect(screen.getByText("Asset Base")).toBeInTheDocument();
  });

  it("uses the profile asset base hint when a client is selected", () => {
    render(<Harness hasClient />);
    fireEvent.click(screen.getByRole("button", { name: "Retirement Stream" }));
    expect(screen.queryByText("Asset Base")).not.toBeInTheDocument();
    expect(
      screen.getByText(/selected client profile/)
    ).toBeInTheDocument();
  });

  it("blocks the profile channel when no client is selected", () => {
    render(<Harness hasClient={false} />);
    fireEvent.click(screen.getByRole("button", { name: "From Client Profile" }));
    // Guarded onChange: source stays manual.
    expect(screen.getByText("Liability Ratio (L/A)")).toBeInTheDocument();
  });

  it("hides the preset selector on the age-driven profile channel", () => {
    render(<Harness hasClient />);
    // Manual first: preset selector is visible.
    expect(screen.getByText("Inflation Segment")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "From Client Profile" }));
    expect(screen.queryByText("Inflation Segment")).not.toBeInTheDocument();
    expect(screen.getByText(/picks the segment by client age/)).toBeInTheDocument();
  });

  it("shows the custom growth input when growth_source is custom", () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole("button", { name: "Custom" }));
    expect(
      screen.getByLabelText("Custom liability growth (%)")
    ).toBeInTheDocument();
  });

  it("offers all four hedge proxies incl. the CN treasury ETF", () => {
    render(<Harness />);
    const select = screen.getByLabelText("Hedge Proxy") as HTMLSelectElement;
    expect(select.options).toHaveLength(4);
    expect(
      screen.getByRole("option", { name: "China 5Y Treasury ETF" })
    ).toBeInTheDocument();
  });
});
