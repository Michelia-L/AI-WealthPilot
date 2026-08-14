import type { OptimizeResponse } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtPct } from "@/lib/format";
import PlotChart from "@/components/plot-chart";
import { useT } from "@/components/locale-context";
import { Badge } from "../ui/chip";
import Icon from "../ui/icon";
import Panel from "../ui/panel";
import StatTile from "../ui/stat";
import { Table, THead, TH, TR, TD } from "../ui/table";
import OptimizerBacktest from "./optimizer-backtest";

/**
 * 优化结果区 —— 关键指标瓷贴、有效前沿/配置图、权重表（含 BL 均衡/后验
 * 收益的条件列）与 selected/max_sharpe/min_vol 三组合对比。
 */
export default function OptimizerResults({
  result,
}: {
  result: OptimizeResponse;
}) {
  const t = useT();
  const GROUP_LABEL: Record<string, string> = {
    equity: t.optimizer.groupEquity,
    bond: t.optimizer.groupBond,
    alternative: t.optimizer.groupAlternative,
    cash: t.optimizer.groupCash,
  };
  const selectedWeightOf = (name: string) => result.selected.weights[name] ?? 0;
  const sortedStats = [...result.asset_stats].sort(
    (a, b) =>
      Math.abs(selectedWeightOf(b.name)) - Math.abs(selectedWeightOf(a.name))
  );
  const rc = result.risk_constraints;

  return (
    <>
      {rc && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-gold-500/25 bg-gold-500/[0.06] px-4 py-2.5 text-xs text-mist-300">
          <Icon name="shield" size={13} className="shrink-0 text-gold-400" />
          <span>
            {t.optimizer.constraintsPrefix}
            <span className="font-medium text-mist-100">{rc.profile_name}</span>
            {t.optimizer.constraintsSuffix(rc.risk_level)}
          </span>
          {Object.entries(rc.caps).map(([g, cap]) => (
            <Badge key={g} tone="gold">
              {GROUP_LABEL[g] ?? g} ≤ {fmtPct(cap, 0)}
            </Badge>
          ))}
          <span className="text-mist-500">
            {t.optimizer.benchmarksUnconstrained}
          </span>
        </div>
      )}

      <div
        className={cx(
          "grid gap-3",
          result.selected.cvar != null || result.surplus != null
            ? "grid-cols-2 lg:grid-cols-4"
            : "grid-cols-3"
        )}
      >
        <StatTile
          label={t.optimizer.annReturn}
          value={fmtPct(result.selected.ann_return)}
          tone="jade"
        />
        <StatTile
          label={t.optimizer.annVolatility}
          value={fmtPct(result.selected.ann_volatility)}
        />
        <StatTile
          label={t.optimizer.sharpeRatio}
          value={result.selected.sharpe.toFixed(2)}
          tone="gold"
        />
        {result.selected.cvar != null && (
          <StatTile
            label={t.optimizer.cvarLabel(
              result.params.cvar_confidence ?? 0.95
            )}
            value={fmtPct(result.selected.cvar)}
            tone="cinnabar"
          />
        )}
        {result.surplus != null && (
          <StatTile
            label={t.optimizer.fundingRatio}
            value={result.surplus.funding_ratio.toFixed(2)}
            tone={result.surplus.funding_ratio >= 1 ? "jade" : "cinnabar"}
          />
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel pad={false} innerClassName="p-2">
          <PlotChart figure={result.frontier_chart} height={480} />
        </Panel>
        <Panel pad={false} innerClassName="p-2">
          <PlotChart figure={result.allocation_chart} height={480} />
        </Panel>
      </div>

      <Panel pad={false} innerClassName="overflow-hidden">
        <Table className="min-w-[860px]">
          <THead>
            <tr>
              <TH>{t.optimizer.colAsset}</TH>
              <TH className="text-right">{t.optimizer.colAllocation}</TH>
              {result.selected.weight_std && (
                <TH className="text-right">{t.optimizer.colWeightStd}</TH>
              )}
              {result.selected.risk_contributions && (
                <TH className="text-right">{t.optimizer.colRiskContribution}</TH>
              )}
              <TH className="text-right">{t.optimizer.annReturn}</TH>
              <TH className="text-right">{t.optimizer.annVolatility}</TH>
              {result.bl && (
                <>
                  <TH className="text-right">{t.optimizer.colEquilibrium}</TH>
                  <TH className="text-right">{t.optimizer.colPosterior}</TH>
                </>
              )}
            </tr>
          </THead>
          <tbody>
            {sortedStats.map((s) => {
              const w = selectedWeightOf(s.name);
              return (
                <TR key={s.key}>
                  <TD>
                    <div className="font-medium text-mist-100">{s.name}</div>
                    <div className="font-mono text-xs text-mist-500">
                      {s.ticker}
                    </div>
                  </TD>
                  <TD
                    className={cx(
                      "text-right font-mono",
                      w < -0.0005
                        ? "text-cinnabar-400"
                        : w > 0.0005
                          ? "text-jade-400"
                          : "text-mist-600"
                    )}
                  >
                    {fmtPct(w, 1)}
                  </TD>
                  {result.selected.weight_std && (
                    <TD className="text-right font-mono text-mist-400">
                      {fmtPct(result.selected.weight_std[s.name] ?? null, 1)}
                    </TD>
                  )}
                  {result.selected.risk_contributions && (
                    <TD className="text-right font-mono text-gold-300">
                      {fmtPct(
                        result.selected.risk_contributions[s.name] ?? null,
                        1
                      )}
                    </TD>
                  )}
                  <TD className="text-right font-mono">
                    {fmtPct(s.ann_return)}
                  </TD>
                  <TD className="text-right font-mono">
                    {fmtPct(s.ann_volatility)}
                  </TD>
                  {result.bl && (
                    <>
                      <TD className="text-right font-mono text-mist-400">
                        {fmtPct(result.bl.equilibrium_returns[s.name] ?? null)}
                      </TD>
                      <TD className="text-right font-mono text-gold-300">
                        {fmtPct(result.bl.posterior_returns[s.name] ?? null)}
                      </TD>
                    </>
                  )}
                </TR>
              );
            })}
          </tbody>
        </Table>
      </Panel>

      <div className="grid gap-3 md:grid-cols-3">
        {(
          [
            [t.optimizer.currentSelected, result.selected],
            [t.optimizer.modeMaxSharpe, result.max_sharpe],
            [t.optimizer.modeMinVol, result.min_vol],
          ] as const
        ).map(([label, r]) => (
          <Panel key={label} innerClassName="p-4 text-sm">
            <div className="mb-2 font-medium text-mist-200">{label}</div>
            <div className="grid grid-cols-3 gap-2 font-mono text-xs text-mist-500">
              <span>
                {t.optimizer.returnLabel}
                <div className="tnum mt-0.5 text-sm text-mist-100">
                  {fmtPct(r.ann_return)}
                </div>
              </span>
              <span>
                {t.optimizer.volLabel}
                <div className="tnum mt-0.5 text-sm text-mist-100">
                  {fmtPct(r.ann_volatility)}
                </div>
              </span>
              <span>
                {t.optimizer.sharpeLabel}
                <div className="tnum mt-0.5 text-sm text-gold-300">
                  {r.sharpe.toFixed(2)}
                </div>
              </span>
            </div>
          </Panel>
        ))}
      </div>

      {result.params.method === "risk-parity" && (
        <p className="text-xs leading-5 text-mist-500">
          {t.optimizer.rpBenchmarkHint}
        </p>
      )}

      {result.surplus && (
        <p className="text-xs leading-5 text-mist-500">
          {t.optimizer.surplusAssumptions({
            source:
              result.surplus.source === "profile"
                ? t.optimizer.surplusSourceProfile
                : t.optimizer.surplusSourceManual,
            ratio: result.surplus.liability_ratio.toFixed(2),
            duration: t.optimizer.durationYears(
              Math.round(result.surplus.liability_duration)
            ),
            growth: fmtPct(result.surplus.liability_growth, 1),
            proxy: result.surplus.proxy,
          })}
        </p>
      )}

      {result.params.cme_fallback_assets != null &&
        result.params.cme_fallback_assets.length > 0 && (
          <p className="text-xs leading-5 text-mist-500">
            {t.optimizer.cmeFallbackHint(
              result.params.cme_fallback_assets.join(" · ")
            )}
          </p>
        )}

      <p className="text-xs leading-5 text-mist-500">
        {t.optimizer.paramsSummary({
          period: result.params.period,
          tradingDays: result.params.trading_days,
          riskFreeRate: fmtPct(result.params.risk_free_rate),
          allowShort: result.params.allow_short,
          nSimulations: result.params.n_simulations,
        })}
      </p>

      <OptimizerBacktest result={result} />
    </>
  );
}
