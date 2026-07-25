"use client";

import { useState } from "react";
import type { OptimizeResponse, PortfolioBacktestResponse } from "@/lib/api";
import BacktestResults from "@/components/backtest-results";
import { Button, Icon, Panel, Segmented } from "@/components/ui";

const PERIOD_OPTIONS = [
  { value: "3y", label: "3Y" },
  { value: "5y", label: "5Y" },
  { value: "10y", label: "10Y" },
] as const;

/**
 * 优化器回测联动 —— 把选中的组合权重（显示名→ticker 经 asset_stats 映射）
 * 交给 P13 回测引擎，验证"这组配置历史上的真实表现"。
 */
export default function OptimizerBacktest({
  result,
}: {
  result: OptimizeResponse;
}) {
  const [period, setPeriod] = useState<string>("5y");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bt, setBt] = useState<PortfolioBacktestResponse | null>(null);

  async function run(nextPeriod: string) {
    setBusy(true);
    setError(null);
    try {
      const tickerOf = Object.fromEntries(
        result.asset_stats.map((s) => [s.name, s.ticker])
      );
      const weights = Object.fromEntries(
        Object.entries(result.selected.weights)
          .filter(([, w]) => Math.abs(w) > 1e-4)
          .map(([name, w]) => [tickerOf[name] ?? name, w])
      );
      const res = await fetch("/api/portfolio/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ weights, period: nextPeriod }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : `回测失败（HTTP ${res.status}）`
        );
      }
      setBt(data as PortfolioBacktestResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="clock" size={15} className="text-gold-400" />
          组合回测
          <span className="text-xs font-normal text-mist-500">
            用历史验证这组权重（月初再平衡）
          </span>
        </h3>
        <div className="flex items-center gap-3">
          {bt && (
            <Segmented
              size="sm"
              options={PERIOD_OPTIONS}
              value={period}
              onChange={(v) => {
                setPeriod(v);
                void run(v);
              }}
            />
          )}
          <Button
            size="sm"
            variant={bt ? "secondary" : "primary"}
            icon="clock"
            disabled={busy}
            onClick={() => void run(period)}
          >
            {busy ? "回测计算中…" : bt ? "重新回测" : "回测该组合"}
          </Button>
        </div>
      </div>

      {error && (
        <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-cinnabar-500/25 bg-cinnabar-500/[0.08] px-4 py-3 text-sm text-cinnabar-300">
          <Icon name="warning" size={15} className="mt-0.5 text-cinnabar-400" />
          <span>{error}</span>
        </div>
      )}

      {busy && (
        <div className="mt-4 flex items-center gap-2 py-4 text-sm text-mist-500">
          <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-gold-400" />
          正在拉取历史行情并模拟净值…
        </div>
      )}

      {bt && !busy && (
        <div className="mt-5">
          <BacktestResults bt={bt} />
        </div>
      )}
    </Panel>
  );
}
