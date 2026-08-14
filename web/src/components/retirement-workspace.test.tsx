import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { retirement } from "@/lib/i18n/dictionaries/en/retirement";
import RetirementWorkspace from "./retirement-workspace";

// The workspace reads copy through the locale context — serve the real
// English dictionary; Plotly stays out of jsdom.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ retirement }),
}));
vi.mock("@/components/plot-chart", () => ({ default: () => null }));

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
