import { getQuotes, type Quote } from "@/lib/api";
import {
  formatAssetChange,
  formatAssetPrice,
  fmtUtc,
} from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";

function TrendPill({ quote }: { quote: Quote }) {
  const { change, change_pct, currency, symbol, ticker, price } = quote;
  if (change === null || change_pct === null) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-700 bg-slate-800/40 px-2.5 py-0.5 font-mono text-xs text-slate-400">
        • NO DATA
      </span>
    );
  }
  // 沿用产品既有约定：绿涨红跌
  const up = change > 0;
  const flat = change === 0;
  const cls = flat
    ? "border-slate-700 bg-slate-800/40 text-slate-400"
    : up
      ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
      : "border-rose-500/30 bg-rose-500/10 text-rose-400";
  const icon = flat ? "•" : up ? "▲" : "▼";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-xs ${cls}`}
    >
      <span>{icon}</span>
      <span>
        {formatAssetChange(change, currency, symbol, ticker, price)} (
        {Math.abs(change_pct).toFixed(2)}%)
      </span>
    </span>
  );
}

/**
 * Real-time quote cards grouped by asset category, mirroring the Streamlit
 * market overview. Prices use the universe's currency/decimal conventions.
 */
export async function QuotesSection({ tickers }: { tickers: string[] }) {
  const data = await getQuotes(tickers);

  if (!data || data.quotes.length === 0) {
    return <ApiOffline resource="行情数据" />;
  }

  const byCategory = new Map<string, Quote[]>();
  for (const q of data.quotes) {
    const list = byCategory.get(q.category) ?? [];
    list.push(q);
    byCategory.set(q.category, list);
  }
  const categories = [...byCategory.keys()].sort();

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-lg font-semibold text-slate-100">
          市场速览 <span className="text-sm font-normal text-slate-400">Market Snapshot</span>
        </h2>
        <span className="text-xs text-slate-500">{fmtUtc(data.as_of)}</span>
      </div>

      {categories.map((category) => (
        <div key={category} className="mb-6">
          <div className="mb-3 border-b border-slate-800/80 pb-1 text-xs font-semibold uppercase tracking-widest text-slate-500">
            {category}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {byCategory.get(category)!.map((q) => (
              <div
                key={q.ticker}
                className="rounded-xl border border-slate-800 bg-slate-900/60 p-4 transition-colors hover:border-slate-700"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="truncate text-sm font-medium text-slate-200" title={q.name}>
                    {q.name}
                  </span>
                  <span
                    className="shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px]"
                    style={{
                      color: q.color,
                      borderColor: `${q.color}44`,
                      backgroundColor: `${q.color}14`,
                    }}
                  >
                    {q.ticker}
                  </span>
                </div>
                <div className="mt-2 font-mono text-xl font-semibold text-slate-50">
                  {formatAssetPrice(q.price, q.currency, q.symbol, q.ticker)}
                </div>
                <div className="mt-2">
                  <TrendPill quote={q} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
