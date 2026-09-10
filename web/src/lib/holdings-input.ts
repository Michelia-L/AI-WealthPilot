import type { monitoring } from "@/lib/i18n/dictionaries/en/monitoring";

type Copy = typeof monitoring.holdings;

/** Format a calendar date in the valuation timezone, never the browser's zone. */
export function valuationDate(now: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone, year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(now);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((p) => p.type === type)!.value;
  return `${part("year")}-${part("month")}-${part("day")}`;
}

/** Translate structured 422 errors without echoing raw input, ctx or provider text. */
export function holdingsInputError(detail: unknown, c: Copy): string {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return c.failed;
  const fields: Record<string, string> = {
    asset_class: c.asset, market_value: c.amount, quantity: c.quantity,
    unit_price: c.price, cost_basis: c.cost, cost_basis_date: c.costDate,
    as_of: c.asOf, base_currency: c.currency, holdings: c.title,
  };
  const messages = detail.slice(0, 10).flatMap((error) => {
    if (!error || !Array.isArray(error.loc) || typeof error.type !== "string") return [];
    const field = error.loc.at(-1);
    const label = typeof field === "string" && Object.hasOwn(fields, field) ? fields[field] : c.title;
    const type: string = error.type;
    const reason = field === "unit_price" && type === "greater_than" ? c.positivePrice
      : type === "missing" ? c.requiredValue
      : type === "greater_than_equal" ? c.nonNegative
      : type === "extra_forbidden" ? c.unexpectedField
      : type.startsWith("date") ? c.invalidDate
      : type.startsWith("float") || type === "finite_number" ? c.invalidNumber
      : c.invalidValue;
    const rowIndex = error.loc.indexOf("holdings") + 1;
    const row = rowIndex > 0 ? error.loc[rowIndex] : undefined;
    return [typeof row === "number" ? c.rowError(row + 1, label, reason) : `${label}: ${reason}`];
  });
  return messages.length ? messages.join("\n") : c.failed;
}
