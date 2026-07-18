"use client";

import { useState } from "react";
import type { RetirementRequest, RetirementResponse } from "@/lib/api";
import { SIMULATION_OPTIONS } from "@/lib/api";
import { fmtMoney, fmtPct } from "@/lib/format";
import PlotChart from "@/components/plot-chart";

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format: (v: number) => string;
}) {
  return (
    <label className="block text-sm text-slate-300">
      <span className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
          {label}
        </span>
        <span className="font-mono text-sm text-slate-100">{format(value)}</span>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full accent-amber-500"
      />
    </label>
  );
}

function MoneyInput({
  label,
  value,
  onChange,
  step = 10000,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
}) {
  return (
    <label className="block text-sm text-slate-300">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <input
        type="number"
        min={0}
        step={step}
        value={value}
        onChange={(e) => onChange(Math.max(0, parseFloat(e.target.value) || 0))}
        className="w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-1.5 font-mono text-sm text-slate-100"
      />
    </label>
  );
}

function Tile({
  label,
  value,
  tone = "text-slate-100",
  sub,
}: {
  label: string;
  value: string;
  tone?: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-1 font-mono text-2xl font-semibold ${tone}`}>{value}</div>
      {sub && <div className="mt-1 text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export default function RetirementWorkspace() {
  const [form, setForm] = useState<RetirementRequest>({
    current_age: 30,
    retirement_age: 60,
    life_expectancy: 85,
    current_savings: 100000,
    annual_savings: 50000,
    desired_annual_income: 80000,
    inflation_rate: 0.025,
    expected_return: 0.07,
    volatility: 0.15,
    n_simulations: 10000,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RetirementResponse | null>(null);

  const set = <K extends keyof RetirementRequest>(key: K, value: RetirementRequest[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const agesValid =
    form.retirement_age > form.current_age && form.life_expectancy > form.retirement_age;

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/retirement/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : `请求失败（HTTP ${res.status}）`
        );
      }
      setResult(data as RetirementResponse);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const survivalTone = !result
    ? ""
    : result.survival_rate >= 0.85
      ? "text-emerald-400"
      : result.survival_rate >= 0.7
        ? "text-amber-300"
        : "text-rose-400";
  const survivalLabel = !result
    ? ""
    : result.survival_rate >= 0.85
      ? "计划稳健"
      : result.survival_rate >= 0.7
        ? "需要关注"
        : "存在风险";

  return (
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 参数表单 ------------------------------ */}
      <div className="space-y-5 rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="grid gap-5 md:grid-cols-3">
          <Slider label="当前年龄" value={form.current_age} min={18} max={80} step={1}
            onChange={(v) => set("current_age", v)} format={(v) => `${v} 岁`} />
          <Slider label="退休年龄" value={form.retirement_age} min={19} max={90} step={1}
            onChange={(v) => set("retirement_age", v)} format={(v) => `${v} 岁`} />
          <Slider label="预期寿命" value={form.life_expectancy} min={30} max={110} step={1}
            onChange={(v) => set("life_expectancy", v)} format={(v) => `${v} 岁`} />
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          <MoneyInput label="当前储蓄" value={form.current_savings}
            onChange={(v) => set("current_savings", v)} />
          <MoneyInput label="年度储蓄" value={form.annual_savings}
            onChange={(v) => set("annual_savings", v)} />
          <MoneyInput label="退休后期望年收入" value={form.desired_annual_income}
            onChange={(v) => set("desired_annual_income", v)} />
        </div>

        <div className="grid gap-5 md:grid-cols-4">
          <Slider label="预期年化收益" value={form.expected_return} min={0.02} max={0.15} step={0.005}
            onChange={(v) => set("expected_return", v)} format={(v) => fmtPct(v, 1)} />
          <Slider label="年化波动率" value={form.volatility} min={0.05} max={0.3} step={0.01}
            onChange={(v) => set("volatility", v)} format={(v) => fmtPct(v, 0)} />
          <Slider label="通胀率" value={form.inflation_rate} min={0} max={0.08} step={0.005}
            onChange={(v) => set("inflation_rate", v)} format={(v) => fmtPct(v, 1)} />
          <div className="text-sm text-slate-300">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-slate-500">
              模拟次数
            </span>
            <div className="flex overflow-hidden rounded-lg border border-slate-700">
              {SIMULATION_OPTIONS.map((o) => (
                <button
                  key={o.value}
                  type="button"
                  onClick={() => set("n_simulations", o.value)}
                  className={`flex-1 px-2 py-1.5 text-xs font-medium transition-colors ${
                    form.n_simulations === o.value
                      ? "bg-slate-700 text-slate-100"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {o.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4 pt-1">
          <button
            type="button"
            onClick={run}
            disabled={loading || !agesValid}
            className="rounded-lg bg-amber-500 px-6 py-2.5 text-sm font-semibold text-slate-950 transition-colors hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? "模拟计算中…" : "运行模拟"}
          </button>
          {!agesValid && (
            <span className="text-sm text-amber-300">
              需满足：当前年龄 &lt; 退休年龄 &lt; 预期寿命
            </span>
          )}
          {error && <span className="text-sm text-rose-400">⚠ {error}</span>}
        </div>
      </div>

      {/* ------------------------------ 结果区 ------------------------------ */}
      {result && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Tile label="计划存活率" value={fmtPct(result.survival_rate, 1)} tone={survivalTone} sub={survivalLabel} />
            <Tile label="退休时中位资产" value={fmtMoney(result.terminal_at_retirement.median)} />
            <Tile label="积累期" value={`${result.accumulation_years} 年`} />
            <Tile label="支取期" value={`${result.distribution_years} 年`} />
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-2">
            <PlotChart figure={result.accumulation_chart} height={480} />
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-2">
            <PlotChart figure={result.distribution_chart} height={480} />
          </div>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-200">资金枯竭分析</h3>
            <div className="grid grid-cols-3 gap-3">
              <Tile label="从未耗尽" value={fmtPct(result.depletion.never_depleted_pct, 1)} tone="text-emerald-400" />
              <Tile label="10 年内耗尽" value={fmtPct(result.depletion.depleted_within_10y_pct, 1)}
                tone={result.depletion.depleted_within_10y_pct > 0.1 ? "text-rose-400" : "text-slate-100"} />
              <Tile label="中位耗尽年份"
                value={result.depletion.median_depletion_year !== null ? `第 ${result.depletion.median_depletion_year.toFixed(0)} 年` : "—"} />
            </div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">退休时资产分位数</th>
                  {(["p5", "p25", "median", "p75", "p95", "mean"] as const).map((k) => (
                    <th key={k} className="px-4 py-3 text-right font-medium">
                      {k === "mean" ? "均值" : k === "median" ? "P50" : k.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-slate-900/40">
                <tr className="text-slate-300">
                  <td className="px-4 py-3 font-medium text-slate-100">终值分布</td>
                  {(["p5", "p25", "median", "p75", "p95", "mean"] as const).map((k) => (
                    <td key={k} className="px-4 py-3 text-right font-mono">
                      {fmtMoney(result.terminal_at_retirement[k])}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-slate-200">
              敏感性分析 <span className="font-normal text-slate-500">— 年度储蓄如何影响存活率</span>
            </h3>
            <div className="overflow-x-auto rounded-xl border border-slate-800">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-4 py-3 font-medium">年度储蓄</th>
                    <th className="px-4 py-3 text-right font-medium">存活率</th>
                    <th className="px-4 py-3 text-right font-medium">退休时中位资产</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                  {result.sensitivity.map((row) => (
                    <tr key={row.annual_savings} className={row.is_current ? "text-amber-300" : "text-slate-300"}>
                      <td className="px-4 py-2.5 font-mono">
                        {fmtMoney(row.annual_savings)}
                        {row.is_current && <span className="ml-2 text-xs">⬅ 当前</span>}
                      </td>
                      <td className="px-4 py-2.5 text-right font-mono">{fmtPct(row.survival_rate, 1)}</td>
                      <td className="px-4 py-2.5 text-right font-mono">{fmtMoney(row.median_at_retirement)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="text-xs text-slate-600">
            参数：{fmtPct(result.params.expected_return, 1)} 预期收益 · {fmtPct(result.params.volatility, 0)} 波动 ·{" "}
            {fmtPct(result.params.inflation_rate, 1)} 通胀 · {result.params.n_simulations.toLocaleString()} 次模拟 ·
            seed={result.params.seed}（结果可复现）
          </p>
        </>
      )}
    </div>
  );
}
