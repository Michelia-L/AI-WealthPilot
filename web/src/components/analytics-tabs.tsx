"use client";

import { useMemo, useState } from "react";
import type { AnalyticsResponse, PlotlyFigure, RiskStat } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { cx } from "@/lib/cx";
import { useT } from "@/components/locale-context";
import PlotChart from "@/components/plot-chart";
import Panel from "./ui/panel";
import Tabs from "./ui/tabs";
import Toggle from "./ui/toggle";
import Icon from "./ui/icon";
import { Table, THead, TH, TR, TD } from "./ui/table";

type TabKey = "price" | "correlation" | "stats";

/** Sortable columns of the risk-stats table (RiskStat keys; "name" sorts by label). */
type SortKey =
  | "name"
  | "ann_return"
  | "ann_volatility"
  | "sharpe"
  | "max_drawdown"
  | "var_95";

type SortState = { key: SortKey; dir: 1 | -1 } | null;

/** Decode plotly.py's base64 typed-array encoding ({bdata, dtype}). */
function decodeBdata(bdata: string, dtype: string): ArrayLike<number> {
  const bin = atob(bdata);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  switch (dtype) {
    case "f4":
      return new Float32Array(bytes.buffer);
    case "i4":
      return new Int32Array(bytes.buffer);
    case "i2":
      return new Int16Array(bytes.buffer);
    case "i1":
      return new Int8Array(bytes.buffer);
    case "u4":
      return new Uint32Array(bytes.buffer);
    case "u2":
      return new Uint16Array(bytes.buffer);
    case "u1":
      return bytes;
    case "f8":
    default:
      return new Float64Array(bytes.buffer);
  }
}

interface BdataArray {
  bdata: string;
  dtype: string;
}

function isBdata(v: unknown): v is BdataArray {
  return (
    typeof v === "object" &&
    v !== null &&
    "bdata" in (v as Record<string, unknown>)
  );
}

/** Rebase a trace y-axis to 100, handling plain arrays and bdata encodings. */
function rebaseTo100(y: unknown): unknown {
  if (Array.isArray(y)) {
    const first = y.find((v): v is number => typeof v === "number");
    if (first === undefined || first === 0) return y;
    return y.map((v) => (typeof v === "number" ? (v / first) * 100 : null));
  }
  if (isBdata(y)) {
    const arr = decodeBdata(y.bdata, y.dtype);
    const base = Number(arr[0]);
    if (!base) return y;
    const out = new Float64Array(arr.length);
    for (let i = 0; i < arr.length; i++) out[i] = (Number(arr[i]) / base) * 100;
    // plotly.js accepts typed arrays natively — no re-encoding needed.
    return out;
  }
  return y;
}

function normalizeFigure(figure: PlotlyFigure): PlotlyFigure {
  return {
    ...figure,
    data: figure.data.map((trace) => {
      const t = trace as Record<string, unknown>;
      return { ...t, y: rebaseTo100(t.y) };
    }),
    layout: {
      ...figure.layout,
      yaxis: {
        ...(figure.layout.yaxis ?? {}),
        title: { text: "Normalized (base = 100)" },
      },
    },
  };
}

/**
 * Sortable stats-table header cell: click cycles ascending → descending →
 * default (API) order. The chevron points up for ascending, down for
 * descending, and fades in on hover for inactive columns.
 */
function SortableTH({
  label,
  sortKey,
  sort,
  onSort,
  numeric = true,
  t,
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (key: SortKey) => void;
  numeric?: boolean;
  t: { sortAsc: string; sortDesc: string; sortReset: string };
}) {
  const active = sort?.key === sortKey;
  const action = !active ? t.sortAsc : sort.dir === 1 ? t.sortDesc : t.sortReset;
  return (
    <TH className={numeric ? "text-right" : undefined}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        aria-label={`${label}: ${action}`}
        title={action}
        className={cx(
          "group inline-flex cursor-pointer items-center gap-1",
          numeric && "flex-row-reverse"
        )}
      >
        {label}
        <Icon
          name="chevronDown"
          size={11}
          className={cx(
            "transition-all duration-200",
            active
              ? cx("text-gold-400", sort.dir === 1 && "rotate-180")
              : "opacity-0 group-hover:opacity-40"
          )}
        />
      </button>
    </TH>
  );
}

/**
 * Analytics tabs: price trajectory (with a client-side base-100 normalize
 * toggle — no refetch), correlation heatmap, and the risk stats table.
 */
export default function AnalyticsTabs({
  analytics,
}: {
  analytics: AnalyticsResponse;
}) {
  const t = useT();
  const [tab, setTab] = useState<TabKey>("price");
  const [normalize, setNormalize] = useState(true);
  const [sort, setSort] = useState<SortState>(null);

  const tabs: { key: TabKey; label: string }[] = [
    { key: "price", label: t.market.tabPrice },
    { key: "correlation", label: t.market.tabCorrelation },
    { key: "stats", label: t.market.tabStats },
  ];

  const priceFigure = useMemo(
    () =>
      normalize ? normalizeFigure(analytics.price_chart) : analytics.price_chart,
    [normalize, analytics.price_chart]
  );

  /** Tri-state cycle: none → asc → desc → none (default = API order). */
  const toggleSort = (key: SortKey) =>
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, dir: 1 };
      if (prev.dir === 1) return { key, dir: -1 };
      return null;
    });

  const sortedStats = useMemo<RiskStat[]>(() => {
    if (!sort) return analytics.stats;
    const rows = [...analytics.stats];
    rows.sort((a, b) => {
      const cmp =
        sort.key === "name"
          ? a.name.localeCompare(b.name)
          : a[sort.key] - b[sort.key];
      return cmp * sort.dir;
    });
    return rows;
  }, [analytics.stats, sort]);

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs
          tabs={tabs}
          active={tab}
          onChange={(k) => setTab(k as TabKey)}
          className="border-b-0"
        />
        {tab === "price" && (
          <Toggle
            checked={normalize}
            onChange={setNormalize}
            label={t.market.normalizeToggle}
          />
        )}
      </div>

      {tab === "price" && (
        <Panel pad={false} innerClassName="p-2">
          <PlotChart figure={priceFigure} height={540} />
        </Panel>
      )}

      {tab === "correlation" && (
        <div className="grid gap-4 lg:grid-cols-[3fr_1fr]">
          <Panel pad={false} innerClassName="p-2">
            {analytics.correlation_chart ? (
              <PlotChart figure={analytics.correlation_chart} height={540} />
            ) : (
              <p className="p-6 text-sm text-mist-400">
                {t.market.correlationEmpty}
              </p>
            )}
          </Panel>
          <Panel innerClassName="text-sm">
            <h3 className="font-display mb-4 text-base text-mist-100">{t.market.corrGuideTitle}</h3>
            <p className="mb-2 font-medium text-mist-200">{t.market.corrGuideSubtitle}</p>
            <ul className="space-y-2.5 text-mist-400">
              <li>
                <span className="font-semibold text-cinnabar-400">
                  {t.market.corrRedLabel}
                </span>
                {t.market.corrRedDesc}
              </li>
              <li>
                <span className="font-semibold text-steel-400">{t.market.corrBlueLabel}</span>
                {t.market.corrBlueDesc}
              </li>
              <li>
                <span className="font-semibold text-mist-200">{t.market.corrWhiteLabel}</span>
                {t.market.corrWhiteDesc}
              </li>
            </ul>
            <p className="mt-4 border-t border-white/[0.06] pt-3 text-xs leading-5 text-mist-500">
              {t.market.corrTip}
            </p>
          </Panel>
        </div>
      )}

      {tab === "stats" && (
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table className="min-w-[820px]">
            <THead>
              <tr>
                <SortableTH
                  label={t.market.thAsset}
                  sortKey="name"
                  sort={sort}
                  onSort={toggleSort}
                  numeric={false}
                  t={t.market}
                />
                <SortableTH
                  label={t.market.thAnnReturn}
                  sortKey="ann_return"
                  sort={sort}
                  onSort={toggleSort}
                  t={t.market}
                />
                <SortableTH
                  label={t.market.thAnnVol}
                  sortKey="ann_volatility"
                  sort={sort}
                  onSort={toggleSort}
                  t={t.market}
                />
                <SortableTH
                  label={t.market.thSharpe}
                  sortKey="sharpe"
                  sort={sort}
                  onSort={toggleSort}
                  t={t.market}
                />
                <SortableTH
                  label={t.market.thMaxDrawdown}
                  sortKey="max_drawdown"
                  sort={sort}
                  onSort={toggleSort}
                  t={t.market}
                />
                <SortableTH
                  label={t.market.thDailyVar}
                  sortKey="var_95"
                  sort={sort}
                  onSort={toggleSort}
                  t={t.market}
                />
              </tr>
            </THead>
            <tbody>
              {sortedStats.map((s) => (
                <TR key={s.ticker}>
                  <TD>
                    <div className="font-medium text-mist-100">{s.name}</div>
                    <div className="font-mono text-xs text-mist-500">
                      {s.ticker}
                    </div>
                  </TD>
                  <TD className="text-right font-mono">
                    {fmtPct(s.ann_return)}
                  </TD>
                  <TD className="text-right font-mono">
                    {fmtPct(s.ann_volatility)}
                  </TD>
                  <TD className="text-right font-mono">{s.sharpe.toFixed(2)}</TD>
                  <TD className="text-right font-mono text-cinnabar-400">
                    {fmtPct(s.max_drawdown)}
                  </TD>
                  <TD className="text-right font-mono">{fmtPct(s.var_95)}</TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </section>
  );
}
