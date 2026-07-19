"use client";

import { useState } from "react";
import type { RetirementRequest, RetirementResponse } from "@/lib/api";
import { SIMULATION_OPTIONS } from "@/lib/api";
import { fmtMoney, fmtPct } from "@/lib/format";
import PlotChart from "@/components/plot-chart";
import {
  Badge,
  Button,
  EmptyState,
  Field,
  Icon,
  NumInput,
  Panel,
  Segmented,
  Slider,
  StatTile,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";

const QUANTILE_KEYS = ["p5", "p25", "median", "p75", "p95", "mean"] as const;

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
    ? "default"
    : result.survival_rate >= 0.85
      ? "jade"
      : result.survival_rate >= 0.7
        ? "gold"
        : "cinnabar";
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
      <Panel>
        <div className="flex flex-col gap-6">
          <div className="grid gap-5 md:grid-cols-3">
            <Slider label="当前年龄" value={form.current_age} min={18} max={80} step={1}
              onChange={(v) => set("current_age", v)} format={(v) => `${v} 岁`} />
            <Slider label="退休年龄" value={form.retirement_age} min={19} max={90} step={1}
              onChange={(v) => set("retirement_age", v)} format={(v) => `${v} 岁`} />
            <Slider label="预期寿命" value={form.life_expectancy} min={30} max={110} step={1}
              onChange={(v) => set("life_expectancy", v)} format={(v) => `${v} 岁`} />
          </div>

          <div className="grid gap-5 md:grid-cols-3">
            <Field label="当前储蓄">
              <NumInput min={0} step={10000} value={form.current_savings}
                onChange={(e) => set("current_savings", Math.max(0, parseFloat(e.target.value) || 0))} />
            </Field>
            <Field label="年度储蓄">
              <NumInput min={0} step={10000} value={form.annual_savings}
                onChange={(e) => set("annual_savings", Math.max(0, parseFloat(e.target.value) || 0))} />
            </Field>
            <Field label="退休后期望年收入">
              <NumInput min={0} step={10000} value={form.desired_annual_income}
                onChange={(e) => set("desired_annual_income", Math.max(0, parseFloat(e.target.value) || 0))} />
            </Field>
          </div>

          <div className="grid gap-5 md:grid-cols-4">
            <Slider label="预期年化收益" value={form.expected_return} min={0.02} max={0.15} step={0.005}
              onChange={(v) => set("expected_return", v)} format={(v) => fmtPct(v, 1)} />
            <Slider label="年化波动率" value={form.volatility} min={0.05} max={0.3} step={0.01}
              onChange={(v) => set("volatility", v)} format={(v) => fmtPct(v, 0)} />
            <Slider label="通胀率" value={form.inflation_rate} min={0} max={0.08} step={0.005}
              onChange={(v) => set("inflation_rate", v)} format={(v) => fmtPct(v, 1)} />
            <div>
              <span className="mb-2 block text-xs text-mist-400">模拟次数</span>
              <Segmented
                size="sm"
                options={SIMULATION_OPTIONS}
                value={form.n_simulations}
                onChange={(v) => set("n_simulations", v)}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4 border-t border-white/[0.05] pt-5">
            <Button
              variant="primary"
              icon="sparkle"
              onClick={run}
              disabled={loading || !agesValid}
            >
              {loading ? "模拟计算中…" : "运行模拟"}
            </Button>
            {!agesValid && (
              <span className="inline-flex items-center gap-1.5 text-sm text-cinnabar-300">
                <Icon name="warning" size={14} />
                需满足：当前年龄 &lt; 退休年龄 &lt; 预期寿命
              </span>
            )}
            {error && (
              <span className="inline-flex items-center gap-1.5 text-sm text-cinnabar-300">
                <Icon name="warning" size={14} />
                {error}
              </span>
            )}
          </div>
        </div>
      </Panel>

      {/* ------------------------------ 结果区 ------------------------------ */}
      {result ? (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatTile label="计划存活率" value={fmtPct(result.survival_rate, 1)}
              tone={survivalTone} hint={survivalLabel} />
            <StatTile label="退休时中位资产" value={fmtMoney(result.terminal_at_retirement.median)} />
            <StatTile label="积累期" value={`${result.accumulation_years} 年`} />
            <StatTile label="支取期" value={`${result.distribution_years} 年`} />
          </div>

          <Panel pad={false} innerClassName="p-2">
            <PlotChart figure={result.accumulation_chart} height={480} />
          </Panel>
          <Panel pad={false} innerClassName="p-2">
            <PlotChart figure={result.distribution_chart} height={480} />
          </Panel>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-mist-200">资金枯竭分析</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatTile label="从未耗尽" value={fmtPct(result.depletion.never_depleted_pct, 1)} tone="jade" />
              <StatTile label="10 年内耗尽" value={fmtPct(result.depletion.depleted_within_10y_pct, 1)}
                tone={result.depletion.depleted_within_10y_pct > 0.1 ? "cinnabar" : "default"} />
              <StatTile label="中位耗尽年份"
                value={result.depletion.median_depletion_year !== null ? `第 ${result.depletion.median_depletion_year.toFixed(0)} 年` : "—"} />
            </div>
          </div>

          <Table>
            <THead>
              <tr>
                <TH>退休时资产分位数</TH>
                {QUANTILE_KEYS.map((k) => (
                  <TH key={k} className="text-right">
                    {k === "mean" ? "均值" : k === "median" ? "P50" : k.toUpperCase()}
                  </TH>
                ))}
              </tr>
            </THead>
            <tbody>
              <TR>
                <TD className="font-medium text-mist-100">终值分布</TD>
                {QUANTILE_KEYS.map((k) => (
                  <TD key={k} className="text-right">
                    {fmtMoney(result.terminal_at_retirement[k])}
                  </TD>
                ))}
              </TR>
            </tbody>
          </Table>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-mist-200">
              敏感性分析 <span className="font-normal text-mist-500">— 年度储蓄如何影响存活率</span>
            </h3>
            <Table>
              <THead>
                <tr>
                  <TH>年度储蓄</TH>
                  <TH className="text-right">存活率</TH>
                  <TH className="text-right">退休时中位资产</TH>
                </tr>
              </THead>
              <tbody>
                {result.sensitivity.map((row) => (
                  <TR key={row.annual_savings}
                    className={row.is_current ? "bg-gold-500/[0.06] hover:bg-gold-500/[0.08]" : undefined}>
                    <TD className={row.is_current ? "border-l-2 border-l-gold-400/70 text-gold-300" : "border-l-2 border-l-transparent"}>
                      <span className="inline-flex items-center gap-2">
                        {fmtMoney(row.annual_savings)}
                        {row.is_current && <Badge tone="gold">当前</Badge>}
                      </span>
                    </TD>
                    <TD className="text-right">{fmtPct(row.survival_rate, 1)}</TD>
                    <TD className="text-right">{fmtMoney(row.median_at_retirement)}</TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </div>

          <p className="text-xs text-mist-600">
            参数：{fmtPct(result.params.expected_return, 1)} 预期收益 · {fmtPct(result.params.volatility, 0)} 波动 ·{" "}
            {fmtPct(result.params.inflation_rate, 1)} 通胀 · {result.params.n_simulations.toLocaleString()} 次模拟 ·
            seed={result.params.seed}（结果可复现）
          </p>
        </>
      ) : (
        <Panel pad={false}>
          <EmptyState
            icon="target"
            title="设定参数并运行模拟"
            hint="默认 10,000 条几何布朗运动路径，覆盖积累期与支取期全程，输出存活率、资产分布与储蓄敏感性。"
          />
        </Panel>
      )}
    </div>
  );
}
