"use client";

import type { BacktestResponse, PortfolioBacktestResponse } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtPct } from "@/lib/format";
import { useT } from "@/components/locale-context";
import PlotChart from "@/components/plot-chart";
import {
  Icon,
  Panel,
  StatTile,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";

function signedPct(value: number): string {
  return `${value > 0 ? "+" : ""}${fmtPct(value)}`;
}

function retClass(value: number): string {
  return value > 0 ? "text-jade-400" : value < 0 ? "text-cinnabar-400" : "text-mist-400";
}

/**
 * 回测结果展示（P13 复用件）—— 指标瓷贴、净值/回撤图、年度收益与
 * 压力测试表。监控页（SAA 回测）与优化器（任意权重回测）共用。
 */
export default function BacktestResults({
  bt,
}: {
  bt: BacktestResponse | PortfolioBacktestResponse;
}) {
  const t = useT();
  const labels = t.common.backtest;
  const GROUP_LABELS: Record<string, string> = {
    equity: labels.attrGroupEquity,
    bond: labels.attrGroupBond,
    alternative: labels.attrGroupAlternative,
    cash: labels.attrGroupCash,
    other: labels.attrGroupOther,
  };
  const bm = bt.benchmark;
  const fee = bt.fee;
  const hasFee = fee.annual_rate > 0;
  const feeSourceLabel =
    fee.source === "ips_fee_schedule"
      ? labels.feeSourceIps
      : fee.source === "manual"
        ? labels.feeSourceManual
        : "";

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label={hasFee ? labels.annReturnNet : labels.annReturnBacktest}
          value={fmtPct(bt.metrics.cagr)}
          hint={labels.benchmarkHint(fmtPct(bm.metrics.cagr))}
          tone="gold"
        />
        <StatTile
          label={labels.annVolatility}
          value={fmtPct(bt.metrics.ann_volatility)}
          hint={labels.benchmarkHint(fmtPct(bm.metrics.ann_volatility))}
        />
        <StatTile
          label={labels.sharpeRatio}
          value={bt.metrics.sharpe === null ? "—" : bt.metrics.sharpe.toFixed(2)}
          hint={
            bm.metrics.sharpe === null
              ? labels.benchmarkHint("—")
              : labels.benchmarkHint(bm.metrics.sharpe.toFixed(2))
          }
        />
        <StatTile
          label={labels.maxDrawdown}
          value={fmtPct(bt.metrics.max_drawdown)}
          hint={labels.benchmarkHint(fmtPct(bm.metrics.max_drawdown))}
          tone="cinnabar"
        />
      </div>

      {hasFee && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-gold-700/30 bg-gold-500/[0.05] px-5 py-3">
          <span className="flex items-center gap-2 text-xs font-medium text-gold-300">
            <Icon name="banknote" size={13} />
            {labels.feeDrag}
          </span>
          <span className="text-xs text-mist-400">
            {labels.feeSummary(
              fmtPct(fee.annual_rate),
              feeSourceLabel,
              (fee.cumulative_impact_pp * 100).toFixed(1)
            )}
          </span>
          <span className="tnum ml-auto font-mono text-[11px] text-mist-500">
            {labels.grossToNet(
              fmtPct(fee.gross_total_return),
              fmtPct(fee.net_total_return)
            )}
          </span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel pad={false} innerClassName="p-2">
          <PlotChart figure={bt.equity_chart} height={420} />
        </Panel>
        <Panel pad={false} innerClassName="p-2">
          <PlotChart figure={bt.drawdown_chart} height={420} />
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 年度收益 */}
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table>
            <THead>
              <tr>
                <TH>{labels.year}</TH>
                <TH className="text-right">{labels.portfolio}</TH>
                <TH className="text-right">{labels.benchmark}</TH>
                <TH className="text-right">{labels.diff}</TH>
              </tr>
            </THead>
            <tbody>
              {bt.yearly.map((y) => (
                <TR key={y.year}>
                  <TD className="font-mono">{y.year}</TD>
                  <TD className={cx("text-right font-mono", retClass(y.portfolio))}>
                    {signedPct(y.portfolio)}
                  </TD>
                  <TD className={cx("text-right font-mono", retClass(y.benchmark))}>
                    {signedPct(y.benchmark)}
                  </TD>
                  <TD
                    className={cx(
                      "text-right font-mono",
                      retClass(y.portfolio - y.benchmark)
                    )}
                  >
                    {signedPct(y.portfolio - y.benchmark)}
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Panel>

        {/* 压力测试 */}
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table>
            <THead>
              <tr>
                <TH>{labels.scenario}</TH>
                <TH className="text-right">{labels.portfolio}</TH>
                <TH className="text-right">{labels.benchmark}</TH>
              </tr>
            </THead>
            <tbody>
              {bt.stress.length === 0 ? (
                <TR>
                  <TD className="text-mist-500">{labels.stressEmpty}</TD>
                  <TD />
                  <TD />
                </TR>
              ) : (
                bt.stress.map((s) => (
                  <TR key={s.scenario}>
                    <TD>
                      <div className="font-medium text-mist-100">{s.scenario}</div>
                      <div className="font-mono text-xs text-mist-500">{s.window}</div>
                    </TD>
                    <TD className={cx("text-right font-mono", retClass(s.portfolio_return))}>
                      {signedPct(s.portfolio_return)}
                    </TD>
                    <TD className={cx("text-right font-mono", retClass(s.benchmark_return))}>
                      {signedPct(s.benchmark_return)}
                    </TD>
                  </TR>
                ))
              )}
            </tbody>
          </Table>
        </Panel>
      </div>

      {bt.attribution && (
        <Panel pad={false} innerClassName="overflow-hidden">
          <div className="border-b border-white/[0.05] px-5 py-3 text-xs font-medium text-mist-300">
            {labels.attrTitle}
          </div>
          <Table>
            <THead>
              <tr>
                <TH>{labels.attrGroup}</TH>
                <TH className="text-right">{labels.attrAvgWeightP}</TH>
                <TH className="text-right">{labels.attrAvgWeightB}</TH>
                <TH className="text-right">{labels.attrAllocation}</TH>
                <TH className="text-right">{labels.attrSelection}</TH>
                <TH className="text-right">{labels.attrInteraction}</TH>
                <TH className="text-right">{labels.attrTotal}</TH>
              </tr>
            </THead>
            <tbody>
              {bt.attribution.groups.map((g) => (
                <TR key={g.group}>
                  <TD className="font-medium text-mist-100">
                    {GROUP_LABELS[g.group] ?? g.group}
                  </TD>
                  <TD className="text-right font-mono text-mist-400">
                    {fmtPct(g.avg_weight_portfolio, 1)}
                  </TD>
                  <TD className="text-right font-mono text-mist-400">
                    {fmtPct(g.avg_weight_benchmark, 1)}
                  </TD>
                  <TD className={cx("text-right font-mono", retClass(g.allocation))}>
                    {signedPct(g.allocation)}
                  </TD>
                  <TD className={cx("text-right font-mono", retClass(g.selection))}>
                    {signedPct(g.selection)}
                  </TD>
                  <TD className={cx("text-right font-mono", retClass(g.interaction))}>
                    {signedPct(g.interaction)}
                  </TD>
                  <TD className={cx("text-right font-mono", retClass(g.total))}>
                    {signedPct(g.total)}
                  </TD>
                </TR>
              ))}
              <TR className="border-t border-white/[0.08]">
                <TD className="font-medium text-gold-300">{labels.attrActiveReturn}</TD>
                <TD /><TD />
                <TD className={cx("text-right font-mono", retClass(bt.attribution.allocation))}>
                  {signedPct(bt.attribution.allocation)}
                </TD>
                <TD className={cx("text-right font-mono", retClass(bt.attribution.selection))}>
                  {signedPct(bt.attribution.selection)}
                </TD>
                <TD className={cx("text-right font-mono", retClass(bt.attribution.interaction))}>
                  {signedPct(bt.attribution.interaction)}
                </TD>
                <TD className={cx("text-right font-mono font-medium", retClass(bt.attribution.active_return))}>
                  {signedPct(bt.attribution.active_return)}
                </TD>
              </TR>
            </tbody>
          </Table>
        </Panel>
      )}

      {bt.notes.length > 0 && (
        <div className="rounded-xl border border-gold-700/30 bg-gold-500/[0.05] px-5 py-4">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-gold-300">
            <Icon name="info" size={13} />
            {labels.notes}
          </div>
          <ul className="space-y-1 text-xs leading-5 text-mist-400">
            {bt.notes.map((n, i) => (
              <li key={i}>· {n}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
