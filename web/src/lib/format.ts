/** Number formatting helpers shared by dashboard sections. */

export function fmtPrice(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

/** Decimal places for a price-level value (mirrors the Streamlit rules). */
function decimalsFor(price: number, currency: string, ticker: string): number {
  if (currency === "Rate") return 4;
  if (currency === "Index" || ticker.startsWith("^")) return 2;
  if (currency === "JPY") return 0;
  if (price > 1000) return 0;
  if (price > 1) return 2;
  return 4;
}

function withSymbol(num: string, symbol: string): string {
  return symbol ? `${symbol}${num}` : num;
}

/**
 * Asset-aware price formatting — mirrors the Streamlit dashboard rules:
 * FX rates 4dp, indices 2dp, JPY 0dp, then magnitude-based for the rest.
 */
export function formatAssetPrice(
  price: number | null,
  currency: string,
  symbol: string,
  ticker: string
): string {
  if (price === null || Number.isNaN(price)) return "N/A";
  const d = decimalsFor(price, currency, ticker);
  return withSymbol(
    price.toLocaleString("en-US", {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }),
    symbol
  );
}

/** Absolute price change; decimals follow the price level, not the change. */
export function formatAssetChange(
  change: number | null,
  currency: string,
  symbol: string,
  ticker: string,
  price: number | null
): string {
  if (change === null || Number.isNaN(change)) return "—";
  const d = decimalsFor(price ?? Math.abs(change), currency, ticker);
  return withSymbol(
    Math.abs(change).toLocaleString("en-US", {
      minimumFractionDigits: d,
      maximumFractionDigits: d,
    }),
    symbol
  );
}

/** Format a decimal ratio (0.085) as a percent string ("8.50%"). */
export function fmtPct(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

/** Format a percentage-point value already in percent (e.g. -0.85) with sign. */
export function fmtSignedPct(value: number | null, digits = 2): string {
  if (value === null || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

/** Render an ISO timestamp as an unambiguous UTC string. */
export function fmtUtc(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

/** Format a monetary amount with thousands separators ("4,745,560"). */
export function fmtMoney(value: number | null, prefix = "$"): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${prefix}${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}
