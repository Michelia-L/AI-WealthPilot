import { getQuotes, type Quote } from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatAssetChange, formatAssetPrice, fmtUtc } from "@/lib/format";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
import { ApiOffline } from "@/components/api-offline";
import Icon from "@/components/ui/icon";
import Reveal from "@/components/ui/reveal";

// ---------------------------------------------------------------------------
// 涨跌 pill（细线趋势图标；颜色走 rise/fall 语义令牌，随 locale 红绿翻转）
// ---------------------------------------------------------------------------

function TrendPill({ quote }: { quote: Quote }) {
  const { change, change_pct, currency, symbol, ticker, price } = quote;
  if (change === null || change_pct === null) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.04] px-2.5 py-0.5 font-mono text-xs text-mist-500">
        — NO DATA
      </span>
    );
  }
  const up = change > 0;
  const flat = change === 0;
  const cls = flat
    ? "border-white/10 bg-white/[0.04] text-mist-400"
    : up
      ? "border-rise/30 bg-rise/10 text-rise"
      : "border-fall/30 bg-fall/10 text-fall";
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-xs",
        cls
      )}
    >
      {!flat && (
        <Icon name={up ? "trendUp" : "trendDown"} size={11} strokeWidth={1.8} />
      )}
      {flat && <span>•</span>}
      <span>
        {formatAssetChange(change, currency, symbol, ticker, price)} (
        {Math.abs(change_pct).toFixed(2)}%)
      </span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// 30 日迷你走势线（纯 SVG，线 + 末端锚点 + 淡色面积）
// ---------------------------------------------------------------------------

function Sparkline({ values }: { values: number[] }) {
  const up = values[values.length - 1] >= values[0];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [
    (i / (values.length - 1)) * 100,
    33 - ((v - min) / span) * 30,
  ]);
  const line = pts
    .map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ");
  const last = pts[pts.length - 1];
  return (
    <svg
      viewBox="0 0 100 36"
      preserveAspectRatio="none"
      className={cx(
        "h-9 w-full opacity-80 transition-opacity duration-300 group-hover:opacity-100",
        up ? "text-rise" : "text-fall"
      )}
      aria-hidden
    >
      <path d={`${line} L100,36 L0,36 Z`} fill="currentColor" opacity={0.07} stroke="none" />
      <path
        d={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={last[0]} cy={last[1]} r={2.2} fill="currentColor" stroke="none" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// 单资产卡片：类别眉题 + 名称 + 价格 + 涨跌 pill + 30 日走势
// ---------------------------------------------------------------------------

/** VIX 恐慌等级标签（QuotesSection 从字典注入，卡片保持同步函数）。 */
type VixLabels = {
  complacent: string;
  calm: string;
  elevated: string;
  fear: string;
  extremeFear: string;
};

/**
 * Map a VIX print (index points) to a fear-level badge. Empirical zones:
 * <12 complacent, 12–17 calm, 17–25 elevated, 25–35 fear, ≥35 extreme fear.
 */
function vixLevel(price: number, labels: VixLabels) {
  if (price < 12)
    return { label: labels.complacent, cls: "border-white/10 bg-white/[0.04] text-mist-400" };
  if (price < 17)
    return { label: labels.calm, cls: "border-jade-500/30 bg-jade-500/10 text-jade-400" };
  if (price < 25)
    return { label: labels.elevated, cls: "border-gold-500/30 bg-gold-500/10 text-gold-400" };
  if (price < 35)
    return { label: labels.fear, cls: "border-cinnabar-500/30 bg-cinnabar-500/10 text-cinnabar-400" };
  return { label: labels.extremeFear, cls: "border-cinnabar-500/50 bg-cinnabar-500/20 text-cinnabar-300" };
}

function QuoteCard({
  quote,
  index,
  vixLabels,
}: {
  quote: Quote;
  index: number;
  vixLabels?: VixLabels;
}) {
  const spark = quote.spark ?? [];
  const pct30 =
    spark.length >= 2 && spark[0] !== 0
      ? (spark[spark.length - 1] / spark[0] - 1) * 100
      : null;
  const up30 = pct30 !== null && pct30 >= 0;
  const fear =
    quote.ticker === "^VIX" && quote.price !== null && vixLabels
      ? vixLevel(quote.price, vixLabels)
      : null;

  return (
    <Reveal delay={Math.min(index, 12) * 40} className="h-full">
      <div className="group flex h-full flex-col rounded-xl border border-white/[0.06] bg-ink-900/70 p-4 transition-all duration-300 ease-luxe hover:-translate-y-0.5 hover:border-gold-500/25 hover:bg-ink-900">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-[10px] font-medium tracking-[0.18em] text-mist-600 uppercase">
            {quote.category}
          </span>
          <span
            className="shrink-0 rounded border px-1.5 py-0.5 font-mono text-[10px]"
            style={{
              color: quote.color,
              borderColor: `${quote.color}44`,
              backgroundColor: `${quote.color}14`,
            }}
          >
            {quote.ticker}
          </span>
        </div>
        <div
          className="mt-1.5 truncate text-sm font-medium text-mist-200"
          title={quote.name}
        >
          {quote.name}
        </div>
        <div className="tnum mt-1 font-mono text-2xl font-semibold text-mist-100">
          {formatAssetPrice(quote.price, quote.currency, quote.symbol, quote.ticker)}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <TrendPill quote={quote} />
          {fear && (
            <span
              className={cx(
                "inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-xs",
                fear.cls
              )}
            >
              {fear.label}
            </span>
          )}
        </div>
        {spark.length >= 2 && (
          <div className="mt-3 flex items-end gap-3 border-t border-white/[0.05] pt-3">
            <div className="min-w-0 flex-1">
              <Sparkline values={spark} />
            </div>
            {pct30 !== null && (
              <div className="shrink-0 text-right">
                <div
                  className={cx(
                    "tnum font-mono text-xs",
                    up30 ? "text-rise" : "text-fall"
                  )}
                >
                  {pct30 > 0 ? "+" : ""}
                  {pct30.toFixed(1)}%
                </div>
                <div className="text-[10px] tracking-[0.14em] text-mist-600 uppercase">
                  30D
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Reveal>
  );
}

// ---------------------------------------------------------------------------
// 市场 breadth 汇总条
// ---------------------------------------------------------------------------

async function BreadthStrip({ quotes }: { quotes: Quote[] }) {
  const t = await getDict();
  const known = quotes.filter((q) => q.change !== null && q.change_pct !== null);
  const up = known.filter((q) => q.change! > 0).length;
  const down = known.filter((q) => q.change! < 0).length;
  const flat = known.length - up - down;
  const best = known.length
    ? known.reduce((a, b) => (a.change_pct! >= b.change_pct! ? a : b))
    : null;
  const worst = known.length
    ? known.reduce((a, b) => (a.change_pct! <= b.change_pct! ? a : b))
    : null;

  const items: Array<{ tone: string; label: string }> = [
    { tone: "text-rise", label: t.market.breadthUp(up) },
    { tone: "text-fall", label: t.market.breadthDown(down) },
    { tone: "text-mist-500", label: t.market.breadthFlat(flat) },
  ];

  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-white/[0.06] bg-ink-900/70 px-5 py-3 text-xs">
      <div className="flex items-center gap-4">
        {items.map((it) => (
          <span key={it.label} className={cx("flex items-center gap-1.5", it.tone)}>
            <Icon name="dot" size={6} />
            <span className="tnum font-mono">{it.label}</span>
          </span>
        ))}
      </div>
      {best && best.change_pct! > 0 && (
        <span className="text-mist-400">
          {t.market.breadthBest}{" "}
          <span className="text-mist-200">{best.name}</span>{" "}
          <span className="tnum font-mono text-rise">
            +{best.change_pct!.toFixed(2)}%
          </span>
        </span>
      )}
      {worst && worst.change_pct! < 0 && (
        <span className="text-mist-400">
          {t.market.breadthWorst}{" "}
          <span className="text-mist-200">{worst.name}</span>{" "}
          <span className="tnum font-mono text-fall">
            {worst.change_pct!.toFixed(2)}%
          </span>
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 市场速览：统一密网格（类别退为卡片眉题，空间利用率优先）
// ---------------------------------------------------------------------------

/**
 * Real-time quote cards in one dense bento grid. Category demoted to a card
 * eyebrow so single-asset categories no longer strand whole grid rows; each
 * card carries a 30-day sparkline for density.
 */
export async function QuotesSection({ tickers }: { tickers: string[] }) {
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];

  const data = await getQuotes(tickers);

  if (!data || data.quotes.length === 0) {
    return <ApiOffline resource={t.market.offlineQuotes} />;
  }

  const quotes = [...data.quotes].sort(
    (a, b) => a.category.localeCompare(b.category) || a.ticker.localeCompare(b.ticker)
  );

  return (
    <section>
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-display text-xl text-mist-100">
          {t.market.snapshotTitle}{" "}
          <span className="font-sans text-sm font-normal text-mist-500">
            {alt.market.snapshotTitle}
          </span>
        </h2>
        <span className="tnum text-xs text-mist-500">{fmtUtc(data.as_of)}</span>
      </div>

      <BreadthStrip quotes={quotes} />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 3xl:grid-cols-6">
        {quotes.map((q, i) => (
          <QuoteCard
            key={q.ticker}
            quote={q}
            index={i}
            vixLabels={{
              complacent: t.market.vixComplacent,
              calm: t.market.vixCalm,
              elevated: t.market.vixElevated,
              fear: t.market.vixFear,
              extremeFear: t.market.vixExtremeFear,
            }}
          />
        ))}
      </div>
    </section>
  );
}
