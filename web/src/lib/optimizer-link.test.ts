import { describe, expect, it } from "vitest";
import {
  buildRetirementLdiHref,
  parseOptimizerDeepLink,
} from "./optimizer-link";

describe("buildRetirementLdiHref", () => {
  it("carries the full retirement channel signature", () => {
    const href = buildRetirementLdiHref({
      years_to_retirement: 30,
      distribution_years: 25,
      annual_income: 80000,
      asset_value: 100000,
    });
    expect(href).toBe(
      "/optimizer?method=surplus&source=retirement&ytr=30&dy=25&income=80000&asset_value=100000"
    );
  });

  it("omits asset_value when not provided", () => {
    const href = buildRetirementLdiHref({
      years_to_retirement: 5,
      distribution_years: 20,
      annual_income: 50000,
    });
    expect(href).toBe(
      "/optimizer?method=surplus&source=retirement&ytr=5&dy=20&income=50000"
    );
  });
});

describe("parseOptimizerDeepLink", () => {
  it("parses a complete link into workspace prefill", () => {
    expect(
      parseOptimizerDeepLink({
        method: "surplus",
        source: "retirement",
        ytr: "30",
        dy: "25",
        income: "80000",
        asset_value: "100000",
      })
    ).toEqual({
      method: "surplus",
      surplusSource: "retirement",
      yearsToRetirement: 30,
      distributionYears: 25,
      annualIncome: 80000,
      assetValue: 100000,
    });
  });

  it("round-trips with the builder", () => {
    const href = buildRetirementLdiHref({
      years_to_retirement: 10,
      distribution_years: 15,
      annual_income: 60000,
      asset_value: 500000,
    });
    const sp = Object.fromEntries(new URLSearchParams(href.split("?")[1]));
    expect(parseOptimizerDeepLink(sp)).toEqual({
      method: "surplus",
      surplusSource: "retirement",
      yearsToRetirement: 10,
      distributionYears: 15,
      annualIncome: 60000,
      assetValue: 500000,
    });
  });

  it("clamps out-of-range years into the schema bounds", () => {
    const parsed = parseOptimizerDeepLink({
      method: "surplus",
      source: "retirement",
      ytr: "99",
      dy: "0",
      income: "80000",
    });
    expect(parsed.yearsToRetirement).toBe(50);
    expect(parsed.distributionYears).toBe(1);
  });

  it("ignores links for other methods or channels", () => {
    expect(parseOptimizerDeepLink({ method: "mvo" })).toEqual({});
    expect(parseOptimizerDeepLink({ method: "surplus", source: "manual" })).toEqual({});
  });

  it("ignores incomplete or malformed links", () => {
    expect(
      parseOptimizerDeepLink({ method: "surplus", source: "retirement", ytr: "30" })
    ).toEqual({});
    expect(
      parseOptimizerDeepLink({
        method: "surplus",
        source: "retirement",
        ytr: "abc",
        dy: "25",
        income: "80000",
      })
    ).toEqual({});
  });
});
