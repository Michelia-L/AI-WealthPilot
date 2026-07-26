import type { BacktestResponse, PortfolioBacktestResponse } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtPct } from "@/lib/format";
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
  const bm = bt.benchmark;
  const fee = bt.fee;
  const hasFee = fee.annual_rate > 0;
  const feeSourceLabel =
    fee.source === "ips_fee_schedule"
      ? "IPS 披露 TER"
      : fee.source === "manual"
        ? "手动费率"
        : "";

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label={hasFee ? "年化收益（费后）" : "年化收益（回测）"}
          value={fmtPct(bt.metrics.cagr)}
          hint={`基准 ${fmtPct(bm.metrics.cagr)}`}
          tone="gold"
        />
        <StatTile
          label="年化波动"
          value={fmtPct(bt.metrics.ann_volatility)}
          hint={`基准 ${fmtPct(bm.metrics.ann_volatility)}`}
        />
        <StatTile
          label="夏普比率"
          value={bt.metrics.sharpe === null ? "—" : bt.metrics.sharpe.toFixed(2)}
          hint={
            bm.metrics.sharpe === null
              ? "基准 —"
              : `基准 ${bm.metrics.sharpe.toFixed(2)}`
          }
        />
        <StatTile
          label="最大回撤"
          value={fmtPct(bt.metrics.max_drawdown)}
          hint={`基准 ${fmtPct(bm.metrics.max_drawdown)}`}
          tone="cinnabar"
        />
      </div>

      {hasFee && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-gold-700/30 bg-gold-500/[0.05] px-5 py-3">
          <span className="flex items-center gap-2 text-xs font-medium text-gold-300">
            <Icon name="banknote" size={13} />
            费用拖累
          </span>
          <span className="text-xs text-mist-400">
            年化 {fmtPct(fee.annual_rate)}（{feeSourceLabel}） · 区间累计
            −{(fee.cumulative_impact_pp * 100).toFixed(1)}pp
          </span>
          <span className="tnum ml-auto font-mono text-[11px] text-mist-500">
            费前 {fmtPct(fee.gross_total_return)} → 费后{" "}
            {fmtPct(fee.net_total_return)}
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
                <TH>年度</TH>
                <TH className="text-right">组合</TH>
                <TH className="text-right">基准</TH>
                <TH className="text-right">差值</TH>
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
                <TH>情景</TH>
                <TH className="text-right">组合</TH>
                <TH className="text-right">基准</TH>
              </tr>
            </THead>
            <tbody>
              {bt.stress.length === 0 ? (
                <TR>
                  <TD className="text-mist-500">
                    回测窗口未覆盖内置危机情景（2008 / 2020 / 2022）。
                  </TD>
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

      {bt.notes.length > 0 && (
        <div className="rounded-xl border border-gold-700/30 bg-gold-500/[0.05] px-5 py-4">
          <div className="mb-2 flex items-center gap-2 text-xs font-medium text-gold-300">
            <Icon name="info" size={13} />
            回测说明
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
