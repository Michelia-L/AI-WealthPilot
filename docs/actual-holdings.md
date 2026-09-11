# Actual holdings snapshots

On `/monitoring`, select an IPS and use **Actual Holdings** to save a complete valuation. Each asset class accepts either a market value or a quantity plus a manually supplied unit price. An optional aggregate cost basis requires a cost basis date; a date can also be recorded without a cost amount.

All monetary inputs, including unit prices and cost basis, must already be expressed in the IPS base currency (CNY when unspecified). There is no automatic quote lookup, currency conversion, brokerage sync, cash-flow ledger, trade execution or tax-lot accounting. Quantities are not quantities of the asset-class proxy index. Prices are the user's valuation of their actual holdings.

The form also provides a JSON template and import area. Use asset class identifiers from that document's template; translated display labels may differ. Edit the template's zero amounts before saving. Imports and manual entry use the same backend validation and persistence.

## Valuation and history

- Every snapshot is complete. Omitted assets have zero market value. Holdings must be nonnegative, finite, and have a strictly positive total; short positions and an entirely empty portfolio are not supported. JSON booleans in numeric fields are rejected, not coerced to numbers.
- Each asset class occurs once. Aggregate multiple securities or lots in the same class before entry. Options include the normalized IPS allocation (including a cash plug, when needed) and other configured asset classes. A holding outside the IPS receives a zero target and zero policy band and is included in drift checks.
- The valuation date cannot be later than today in the explicit business timezone **Asia/Shanghai**, regardless of the API server or browser timezone. The form discloses this timezone and the JSON template uses the same calendar date. Cost basis dates cannot follow the valuation date. Cost basis is retained as context and does not determine market value or investment returns.
- The most recent valuation date drives monitoring, the overview's band alerts, and the quantitative input to AI rebalancing advice. Same-day corrections create a new record; the last record on that date wins. Backfilling an older date does not replace the latest valuation. There is no update/delete endpoint.
- Current weights equal asset market value divided by total snapshot market value. No proxy return is applied to a stored valuation, even when it is older than today. The monitor displays the source and valuation date. `as_of` remains the date the diagnostics were computed, on the Asia/Shanghai business calendar; IPS `saved_at` timestamps are recorded timezone-aware on the same calendar.
- A snapshot is only read under the base currency it was recorded in. If the IPS base currency changes afterwards, single-document monitoring and AI advice return 422 and the fleet row reports `unknown` with an explanation, until a new valuation is recorded in the current currency.
- The history selector displays any saved snapshot and compares it with its immediate predecessor in valuation-date / record-ID order. Value and weight differences include contributions, withdrawals, trades and revaluations; they are **not investment returns**.
- CME risk/return metrics, estimated currency exposure and historical SAA backtests still use the existing asset-class proxies. A historical holdings snapshot is not a historical CME report or a portfolio performance backtest. Cost amounts and quantities are excluded from the AI advice prompt.

## API and persistence

`GET /api/monitoring/{document_id}/holdings` returns the base currency, accepted asset options and snapshot history (newest first). `POST` to the same path appends one snapshot and returns `201`. Missing documents return `404`; invalid input returns `422`. Business validation messages follow `X-Locale: en|zh`.

An illustrative request (replace the asset identifiers with those returned by GET):

```json
{
  "as_of": "2026-06-10",
  "base_currency": "CNY",
  "holdings": [
    {
      "asset_class": "固定收益",
      "market_value": 800,
      "cost_basis": 700,
      "cost_basis_date": "2026-01-01"
    },
    {
      "asset_class": "现金等价物",
      "quantity": 200,
      "unit_price": 1
    }
  ]
}
```

The example totals 1,000 CNY and yields weights of 80% and 20%. It is synthetic input, not a client result.

Snapshots are appended to the `holding_snapshots` table in the existing SQLite database (`AIWP_DB_URL`, default `data/wealthpilot.db`). Startup creates the table without changing existing tables. Back up this database together with the IPS JSON files; copying IPS files alone does not copy holdings history. Records retain the input, derived market values and weights, valuation date, document ID, and creation timestamp.

The monitoring API adds `valuation_source` (`actual_holdings` or `buy_and_hold`), `valuation_as_of`, `snapshot_id`, `total_market_value`, and per-holding `market_value`. Without a snapshot, existing buy-and-hold behavior remains, and the new value fields are null. Snapshot entry/history does not require CME or market data. The full diagnostics endpoint still uses CME for its metrics.

Fleet caching uses a fixed date/locale key (Asia/Shanghai business date) and a version covering both snapshot writes and the IPS document set, so adding, editing or deleting a stored IPS file invalidates the entry. Cache hits read only the indexed maximum snapshot ID; cache misses select the latest row per document in SQL. Versions replace the existing cache entry, and expired entries are evicted on subsequent cache access.
