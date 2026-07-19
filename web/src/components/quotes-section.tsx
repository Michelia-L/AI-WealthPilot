import { getQuotes, type Quote } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatAssetChange, formatAssetPrice, fmtUtc } from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";

function TrendPill({ quote }: { quote: Quote }) {
  const { change, change_pct, currency, symbol, ticker, price } = quote;
  if (change === null || change_pct === null) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 font-mono text-xs text-mist-500">
        — NO DATA
      </span>
    );
  }
  // 沿用产品既有约定：绿涨红跌
  const up = change > 0;
  const flat = change === 0;
  const cls = flat
    ? "border-white/10 bg-white/[0.04] text-mist-400"
    : up
      ? "border-jade-500/30 bg-jade-500/10 text-jade-400"
      : "border-cinnabar-500/30 bg-cinnabar-500/10 text-cinnabar-400";
  const icon = flat ? "•" : up ? "▲" : "▼";
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-xs",
        cls
      )}
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
        <h2 className="font-display text-xl text-mist-100">
          市场速览{" "}
          <span className="font-sans text-sm font-normal text-mist-500">
            Market Snapshot
          </span>
        </h2>
        <span className="tnum text-xs text-mist-500">{fmtUtc(data.as_of)}</span>
      </div>

      {categories.map((category) => (
        <div key={category} className="mb-7">
          <div className="mb-3 border-b border-white/[0.07] pb-1.5 text-[11px] font-semibold tracking-[0.18em] text-mist-500 uppercase">
            {category}
          </div>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {byCategory.get(category)!.map((q) => (
              <div
                key={q.ticker}
                className="rounded-xl border border-white/[0.06] bg-ink-900/70 p-4 transition-all duration-300 ease-luxe hover:border-gold-500/25 hover:bg-ink-900"
              >
                <div className="flex items-start justify-between gap-2">
                  <span
                    className="truncate text-sm font-medium text-mist-200"
                    title={q.name}
                  >
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
                <div className="tnum mt-2 font-mono text-xl font-semibold text-mist-100">
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
