"use client";

import { useMemo, useState } from "react";
import type { AnalyticsResponse, PlotlyFigure } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import PlotChart from "@/components/plot-chart";
import Panel from "./ui/panel";
import Tabs from "./ui/tabs";
import Toggle from "./ui/toggle";
import { Table, THead, TH, TR, TD } from "./ui/table";

type TabKey = "price" | "correlation" | "stats";

const TABS: { key: TabKey; label: string }[] = [
  { key: "price", label: "价格走势" },
  { key: "correlation", label: "资产相关性" },
  { key: "stats", label: "风险统计" },
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
        <Tabs
          tabs={TABS}
          active={tab}
          onChange={(k) => setTab(k as TabKey)}
          className="border-b-0"
        />
        {tab === "price" && (
          <Toggle
            checked={normalize}
            onChange={setNormalize}
            label="基准归一化（Base = 100）"
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
                至少需要 2 个资产才能计算相关性矩阵。
              </p>
            )}
          </Panel>
          <Panel innerClassName="text-sm">
            <h3 className="font-display mb-4 text-base text-mist-100">解读</h3>
            <p className="mb-2 font-medium text-mist-200">分散化分析</p>
            <ul className="space-y-2.5 text-mist-400">
              <li>
                <span className="font-semibold text-cinnabar-400">
                  红 (+1.0)
                </span>
                ：高度正相关，资产同涨同跌。
              </li>
              <li>
                <span className="font-semibold text-steel-400">蓝 (−1.0)</span>
                ：高度负相关，优秀的对冲组合。
              </li>
              <li>
                <span className="font-semibold text-mist-200">白 (0.0)</span>
                ：不相关，纯粹的分散化收益。
              </li>
            </ul>
            <p className="mt-4 border-t border-white/[0.06] pt-3 text-xs leading-5 text-mist-500">
              提示：用低相关性的资产构建组合，可以最大化夏普比率。
            </p>
          </Panel>
        </div>
      )}

      {tab === "stats" && (
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table className="min-w-[820px]">
            <THead>
              <tr>
                <TH>资产</TH>
                <TH className="text-right">年化收益</TH>
                <TH className="text-right">年化波动</TH>
                <TH className="text-right">夏普</TH>
                <TH className="text-right">最大回撤</TH>
                <TH className="text-right">日 VaR (95%)</TH>
              </tr>
            </THead>
            <tbody>
              {analytics.stats.map((s) => (
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
