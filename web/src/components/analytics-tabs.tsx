"use client";

import { useMemo, useState } from "react";
import type { AnalyticsResponse, PlotlyFigure } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import PlotChart from "@/components/plot-chart";

type TabKey = "price" | "correlation" | "stats";

const TABS: { key: TabKey; label: string }[] = [
  { key: "price", label: "📈 价格走势" },
  { key: "correlation", label: "🕸️ 资产相关性" },
  { key: "stats", label: "📊 风险统计" },
];

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
 * Analytics tabs: price trajectory (with a client-side base-100 normalize
 * toggle — no refetch), correlation heatmap, and the risk stats table.
 */
export default function AnalyticsTabs({
  analytics,
}: {
  analytics: AnalyticsResponse;
}) {
  const [tab, setTab] = useState<TabKey>("price");
  const [normalize, setNormalize] = useState(true);

  const priceFigure = useMemo(
    () =>
      normalize ? normalizeFigure(analytics.price_chart) : analytics.price_chart,
    [normalize, analytics.price_chart]
  );

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                tab === t.key
                  ? "bg-slate-700 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {tab === "price" && (
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
            <button
              role="switch"
              aria-checked={normalize}
              onClick={() => setNormalize((v) => !v)}
              className={`relative h-5 w-9 rounded-full transition-colors ${
                normalize ? "bg-amber-500" : "bg-slate-700"
              }`}
            >
              <span
                className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                  normalize ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </button>
            基准归一化（Base = 100）
          </label>
        )}
      </div>

      {tab === "price" && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-2">
          <PlotChart figure={priceFigure} height={540} />
        </div>
      )}

      {tab === "correlation" && (
        <div className="grid gap-4 lg:grid-cols-[3fr_1fr]">
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-2">
            {analytics.correlation_chart ? (
              <PlotChart figure={analytics.correlation_chart} height={540} />
            ) : (
              <p className="p-6 text-sm text-slate-400">
                至少需要 2 个资产才能计算相关性矩阵。
              </p>
            )}
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-5 text-sm text-slate-300">
            <h3 className="mb-3 font-semibold text-slate-100">🔍 解读</h3>
            <p className="mb-2 font-medium">分散化分析</p>
            <ul className="space-y-2 text-slate-400">
              <li>
                <span className="font-semibold text-rose-400">红 (+1.0)</span>
                ：高度正相关，资产同涨同跌。
              </li>
              <li>
                <span className="font-semibold text-sky-400">蓝 (−1.0)</span>
                ：高度负相关，优秀的对冲组合。
              </li>
              <li>
                <span className="font-semibold text-slate-200">白 (0.0)</span>
                ：不相关，纯粹的分散化收益。
              </li>
            </ul>
            <p className="mt-4 text-xs text-slate-500">
              提示：用低相关性的资产构建组合，可以最大化夏普比率。
            </p>
          </div>
        </div>
      )}

      {tab === "stats" && (
        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">资产</th>
                <th className="px-4 py-3 text-right font-medium">年化收益</th>
                <th className="px-4 py-3 text-right font-medium">年化波动</th>
                <th className="px-4 py-3 text-right font-medium">夏普</th>
                <th className="px-4 py-3 text-right font-medium">最大回撤</th>
                <th className="px-4 py-3 text-right font-medium">
                  日 VaR (95%)
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-slate-900/40">
              {analytics.stats.map((s) => (
                <tr key={s.ticker} className="text-slate-300">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-100">{s.name}</div>
                    <div className="font-mono text-xs text-slate-500">
                      {s.ticker}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtPct(s.ann_return)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtPct(s.ann_volatility)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {s.sharpe.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-rose-400">
                    {fmtPct(s.max_drawdown)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {fmtPct(s.var_95)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
