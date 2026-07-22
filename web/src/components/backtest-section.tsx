import { getBacktest } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtPct } from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";
import BacktestPeriodSelector from "@/components/backtest-period-selector";
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
 * 历史回测区块（P13）—— 以 IPS 的 SAA 权重做月初再平衡回测，
 * 对照 60/40 股债基准，含年度收益与危机情景压力测试。
 */
export default async function BacktestSection({
  documentId,
  period,
}: {
  documentId: string;
  period: string;
}) {
  const bt = await getBacktest(documentId, period);
  if (!bt) {
    return <ApiOffline resource="回测数据（历史行情不可用，或文档缺少 SAA）" />;
  }
  const bm = bt.benchmark;

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="clock" size={15} className="text-gold-400" />
          历史回测
          <span className="text-xs font-normal text-mist-500">
            月初再平衡 · 对照 {bm.name}
          </span>
        </h3>
        <BacktestPeriodSelector documentId={documentId} period={period} />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label="年化收益（回测）"
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
    </section>
  );
}
