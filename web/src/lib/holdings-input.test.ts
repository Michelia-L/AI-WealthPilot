import { describe, expect, it } from "vitest";
import { dictionaries } from "@/lib/i18n/dictionaries";
import { holdingsInputError, valuationDate } from "./holdings-input";

describe("holdings input", () => {
  it.each([
    ["2026-09-09T15:59:59Z", "2026-09-09"],
    ["2026-09-09T16:00:00Z", "2026-09-10"],
    ["2026-09-10T00:30:00+09:00", "2026-09-09"],
  ])("formats %s in the API's business timezone", (instant, expected) => {
    expect(valuationDate(new Date(instant), "Asia/Shanghai")).toBe(expected);
  });

  it.each(["en", "zh"] as const)("localizes structured validation errors in %s without echoing input", (locale) => {
    const c = dictionaries[locale].monitoring.holdings;
    expect(holdingsInputError([
      { loc: ["body", "holdings", 1, "unit_price"], type: "greater_than", input: "private", msg: "raw message" },
      { loc: ["body", "as_of"], type: "date_from_datetime_parsing" },
      { loc: ["body", "holdings", 0, "quantity"], type: "greater_than_equal" },
    ], c)).toBe([
      c.rowError(2, c.price, c.positivePrice), `${c.asOf}: ${c.invalidDate}`,
      c.rowError(1, c.quantity, c.nonNegative),
    ].join("\n"));
    expect(holdingsInputError([{ loc: ["body", "secret-field"], type: "extra_forbidden" }], c))
      .toBe(`${c.title}: ${c.unexpectedField}`);
    expect(holdingsInputError(null, c)).toBe(c.failed);
    expect(holdingsInputError([null, {}], c)).toBe(c.failed);
  });
});
