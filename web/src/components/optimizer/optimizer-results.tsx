import type { OptimizeResponse } from "@/lib/api";
import { cx } from "@/lib/cx";
import { fmtPct } from "@/lib/format";
import PlotChart from "@/components/plot-chart";
import { Badge } from "../ui/chip";
import Icon from "../ui/icon";
import Panel from "../ui/panel";
import StatTile from "../ui/stat";
import { Table, THead, TH, TR, TD } from "../ui/table";

const GROUP_LABEL: Record<string, string> = {
  equity: "权益",
  bond: "固收",
  alternative: "另类",
  cash: "现金",
};

/**
 * 优化结果区 —— 关键指标瓷贴、有效前沿/配置图、权重表（含 BL 均衡/后验
 * 收益的条件列）与 selected/max_sharpe/min_vol 三组合对比。
 */
export default function OptimizerResults({
  result,
}: {
  result: OptimizeResponse;
}) {
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
            已按 <span className="font-medium text-mist-100">{rc.profile_name}</span>{" "}
            的风险等级（{rc.risk_level}）注入权重约束
          </span>
          {Object.entries(rc.caps).map(([g, cap]) => (
            <Badge key={g} tone="gold">
              {GROUP_LABEL[g] ?? g} ≤ {fmtPct(cap, 0)}
            </Badge>
          ))}
          <span className="text-mist-500">
            对照组（最大夏普 / 最小波动）未施加约束
          </span>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3">
        <StatTile
          label="年化收益"
          value={fmtPct(result.selected.ann_return)}
          tone="jade"
        />
        <StatTile
          label="年化波动"
          value={fmtPct(result.selected.ann_volatility)}
        />
        <StatTile
          label="夏普比率"
          value={result.selected.sharpe.toFixed(2)}
          tone="gold"
        />
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
              <TH>资产</TH>
              <TH className="text-right">配置权重</TH>
              {result.selected.weight_std && (
                <TH className="text-right">权重波动 σ</TH>
              )}
              <TH className="text-right">年化收益</TH>
              <TH className="text-right">年化波动</TH>
              {result.bl && (
                <>
                  <TH className="text-right">均衡收益</TH>
                  <TH className="text-right">后验收益</TH>
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
            ["当前选中", result.selected],
            ["最大夏普", result.max_sharpe],
            ["最小波动", result.min_vol],
          ] as const
        ).map(([label, r]) => (
          <Panel key={label} innerClassName="p-4 text-sm">
            <div className="mb-2 font-medium text-mist-200">{label}</div>
            <div className="grid grid-cols-3 gap-2 font-mono text-xs text-mist-500">
              <span>
                收益
                <div className="tnum mt-0.5 text-sm text-mist-100">
                  {fmtPct(r.ann_return)}
                </div>
              </span>
              <span>
                波动
                <div className="tnum mt-0.5 text-sm text-mist-100">
                  {fmtPct(r.ann_volatility)}
                </div>
              </span>
              <span>
                夏普
                <div className="tnum mt-0.5 text-sm text-gold-300">
                  {r.sharpe.toFixed(2)}
                </div>
              </span>
            </div>
          </Panel>
        ))}
      </div>

      <p className="text-xs leading-5 text-mist-500">
        参数：{result.params.period} 窗口 · {result.params.trading_days}{" "}
        个交易日 · 无风险利率 {fmtPct(result.params.risk_free_rate)} ·{" "}
        {result.params.allow_short ? "允许做空" : "仅多头"}
        {result.params.n_simulations
          ? ` · ${result.params.n_simulations} 次重采样`
          : ""}
      </p>
    </>
  );
}
