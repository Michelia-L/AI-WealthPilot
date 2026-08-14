import { describe, expect, it } from "vitest";
import {
  fmtLocal,
  fmtMoney,
  fmtPct,
  fmtPrice,
  fmtSignedPct,
  fmtUtc,
  formatAssetChange,
  formatAssetPrice,
} from "./format";

describe("fmtPct", () => {
  it("formats a decimal ratio as a percent string", () => {
    expect(fmtPct(0.085)).toBe("8.50%");
    expect(fmtPct(0.085, 1)).toBe("8.5%");
    expect(fmtPct(0, 1)).toBe("0.0%");
    expect(fmtPct(-0.032)).toBe("-3.20%");
  });

  it("renders the dash for null/NaN", () => {
    expect(fmtPct(null)).toBe("—");
    expect(fmtPct(NaN)).toBe("—");
  });
});

describe("fmtSignedPct", () => {
  it("keeps an explicit plus sign for positive values", () => {
    expect(fmtSignedPct(0.85)).toBe("+0.85%");
    expect(fmtSignedPct(-0.85)).toBe("-0.85%");
    expect(fmtSignedPct(0)).toBe("0.00%");
    expect(fmtSignedPct(null)).toBe("—");
  });
});

describe("fmtMoney", () => {
  it("formats with thousands separators and no decimals", () => {
    expect(fmtMoney(4745560)).toBe("$4,745,560");
    expect(fmtMoney(1234.6, "¥")).toBe("¥1,235");
    expect(fmtMoney(null)).toBe("—");
  });
});

describe("fmtPrice", () => {
  it("caps at two decimals and handles null", () => {
    expect(fmtPrice(1234.567)).toBe("1,234.57");
    expect(fmtPrice(null)).toBe("—");
  });
});

describe("fmtUtc", () => {
  it("renders an ISO timestamp as an explicit UTC string", () => {
    expect(fmtUtc("2026-07-18T15:04:05.000Z")).toBe("2026-07-18 15:04:05 UTC");
    expect(fmtUtc("not-a-date")).toBe("not-a-date");
  });
});

describe("fmtLocal", () => {
  it("compacts a naive ISO timestamp", () => {
    expect(fmtLocal("2026-07-18T15:04:05")).toBe("2026-07-18 15:04");
    expect(fmtLocal("")).toBe("—");
  });
});

describe("formatAssetPrice", () => {
  it("follows the Streamlit decimal rules", () => {
    // FX rate → 4dp
    expect(formatAssetPrice(0.8567, "Rate", "", "EURUSD=X")).toBe("0.8567");
    // Index → 2dp
    expect(formatAssetPrice(5231.4, "Index", "", "^GSPC")).toBe("5,231.40");
    // JPY → 0dp
    expect(formatAssetPrice(156.32, "JPY", "¥", "JPY=X")).toBe("¥156");
    // >1000 → 0dp, >1 → 2dp, else 4dp
    expect(formatAssetPrice(45230.1, "USD", "$", "BTC-USD")).toBe("$45,230");
    expect(formatAssetPrice(234.5, "USD", "$", "SPY")).toBe("$234.50");
    expect(formatAssetPrice(0.92, "USD", "$", "XYZ")).toBe("$0.9200");
  });

  it("renders N/A for null", () => {
    expect(formatAssetPrice(null, "USD", "$", "SPY")).toBe("N/A");
  });
});

describe("formatAssetChange", () => {
  it("uses the price level for decimals and drops the sign", () => {
    expect(formatAssetChange(-3.21, "USD", "$", "SPY", 234.5)).toBe("$3.21");
    expect(formatAssetChange(null, "USD", "$", "SPY", 234.5)).toBe("—");
  });
});
