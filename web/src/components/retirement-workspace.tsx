"use client";

import { useState } from "react";
import type { RetirementRequest, RetirementResponse } from "@/lib/api";
import { SIMULATION_OPTIONS } from "@/lib/api";
import { fmtMoney, fmtPct } from "@/lib/format";
import { useT } from "@/components/locale-context";
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
  const t = useT();
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
          typeof data.detail === "string" ? data.detail : t.retirement.requestFailed(res.status)
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
      ? t.retirement.survivalSteady
      : result.survival_rate >= 0.7
        ? t.retirement.survivalWatch
        : t.retirement.survivalRisk;

  return (
    <div className="flex flex-col gap-8">
      {/* ------------------------------ 参数表单 ------------------------------ */}
      <Panel>
        <div className="flex flex-col gap-6">
          <div className="grid gap-5 md:grid-cols-3">
            <Slider label={t.retirement.currentAge} value={form.current_age} min={18} max={80} step={1}
              onChange={(v) => set("current_age", v)} format={t.retirement.ageYears} />
            <Slider label={t.retirement.retirementAge} value={form.retirement_age} min={19} max={90} step={1}
              onChange={(v) => set("retirement_age", v)} format={t.retirement.ageYears} />
            <Slider label={t.retirement.lifeExpectancy} value={form.life_expectancy} min={30} max={110} step={1}
              onChange={(v) => set("life_expectancy", v)} format={t.retirement.ageYears} />
          </div>

          <div className="grid gap-5 md:grid-cols-3">
            <Field label={t.retirement.currentSavings}>
              <NumInput min={0} step={10000} value={form.current_savings}
                onChange={(e) => set("current_savings", Math.max(0, parseFloat(e.target.value) || 0))} />
            </Field>
            <Field label={t.retirement.annualSavings}>
              <NumInput min={0} step={10000} value={form.annual_savings}
                onChange={(e) => set("annual_savings", Math.max(0, parseFloat(e.target.value) || 0))} />
            </Field>
            <Field label={t.retirement.desiredIncome}>
              <NumInput min={0} step={10000} value={form.desired_annual_income}
                onChange={(e) => set("desired_annual_income", Math.max(0, parseFloat(e.target.value) || 0))} />
            </Field>
          </div>

          <div className="grid gap-5 md:grid-cols-4">
            <Slider label={t.retirement.expectedReturn} value={form.expected_return} min={0.02} max={0.15} step={0.005}
              onChange={(v) => set("expected_return", v)} format={(v) => fmtPct(v, 1)} />
            <Slider label={t.retirement.volatility} value={form.volatility} min={0.05} max={0.3} step={0.01}
              onChange={(v) => set("volatility", v)} format={(v) => fmtPct(v, 0)} />
            <Slider label={t.retirement.inflationRate} value={form.inflation_rate} min={0} max={0.08} step={0.005}
              onChange={(v) => set("inflation_rate", v)} format={(v) => fmtPct(v, 1)} />
            <div>
              <span className="mb-2 block text-xs text-mist-400">{t.retirement.simulationCount}</span>
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
              {loading ? t.retirement.running : t.retirement.run}
            </Button>
            {!agesValid && (
              <span className="inline-flex items-center gap-1.5 text-sm text-cinnabar-300">
                <Icon name="warning" size={14} />
                {t.retirement.ageConstraint}
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
            <StatTile label={t.retirement.survivalRate} value={fmtPct(result.survival_rate, 1)}
              tone={survivalTone} hint={survivalLabel} />
            <StatTile label={t.retirement.medianAtRetirement} value={fmtMoney(result.terminal_at_retirement.median)} />
            <StatTile label={t.retirement.accumulationPhase} value={t.retirement.durationYears(result.accumulation_years)} />
            <StatTile label={t.retirement.distributionPhase} value={t.retirement.durationYears(result.distribution_years)} />
          </div>

          <Panel pad={false} innerClassName="p-2">
            <PlotChart figure={result.accumulation_chart} height={480} />
          </Panel>
          <Panel pad={false} innerClassName="p-2">
            <PlotChart figure={result.distribution_chart} height={480} />
          </Panel>

          <div>
            <h3 className="mb-3 text-sm font-semibold text-mist-200">{t.retirement.depletionTitle}</h3>
            <div className="grid gap-3 sm:grid-cols-3">
              <StatTile label={t.retirement.neverDepleted} value={fmtPct(result.depletion.never_depleted_pct, 1)} tone="jade" />
              <StatTile label={t.retirement.depletedWithin10y} value={fmtPct(result.depletion.depleted_within_10y_pct, 1)}
                tone={result.depletion.depleted_within_10y_pct > 0.1 ? "cinnabar" : "default"} />
              <StatTile label={t.retirement.medianDepletionYear}
                value={result.depletion.median_depletion_year !== null ? t.retirement.yearNth(result.depletion.median_depletion_year.toFixed(0)) : "—"} />
            </div>
          </div>

          <Table>
            <THead>
              <tr>
                <TH>{t.retirement.quantileTableTitle}</TH>
                {QUANTILE_KEYS.map((k) => (
                  <TH key={k} className="text-right">
                    {k === "mean" ? t.retirement.meanLabel : k === "median" ? "P50" : k.toUpperCase()}
                  </TH>
                ))}
              </tr>
            </THead>
            <tbody>
              <TR>
                <TD className="font-medium text-mist-100">{t.retirement.terminalDistribution}</TD>
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
              {t.retirement.sensitivityTitle} <span className="font-normal text-mist-500">{t.retirement.sensitivitySubtitle}</span>
            </h3>
            <Table>
              <THead>
                <tr>
                  <TH>{t.retirement.annualSavings}</TH>
                  <TH className="text-right">{t.retirement.survivalRateShort}</TH>
                  <TH className="text-right">{t.retirement.medianAtRetirement}</TH>
                </tr>
              </THead>
              <tbody>
                {result.sensitivity.map((row) => (
                  <TR key={row.annual_savings}
                    className={row.is_current ? "bg-gold-500/[0.06] hover:bg-gold-500/[0.08]" : undefined}>
                    <TD className={row.is_current ? "border-l-2 border-l-gold-400/70 text-gold-300" : "border-l-2 border-l-transparent"}>
                      <span className="inline-flex items-center gap-2">
                        {fmtMoney(row.annual_savings)}
                        {row.is_current && <Badge tone="gold">{t.retirement.currentBadge}</Badge>}
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
            {t.retirement.paramsPrefix}
            {fmtPct(result.params.expected_return, 1)} {t.retirement.expectedReturnShort} ·{" "}
            {fmtPct(result.params.volatility, 0)} {t.retirement.volatilityShort} ·{" "}
            {fmtPct(result.params.inflation_rate, 1)} {t.retirement.inflationShort} ·{" "}
            {t.retirement.simulationsShort(result.params.n_simulations.toLocaleString())} ·{" "}
            {t.retirement.seedNote(result.params.seed)}
          </p>
        </>
      ) : (
        <Panel pad={false}>
          <EmptyState
            icon="target"
            title={t.retirement.emptyTitle}
            hint={t.retirement.emptyHint}
          />
        </Panel>
      )}
    </div>
  );
}
