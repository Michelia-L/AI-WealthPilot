import { getCme } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";

const CACHE_STATUS_STYLE: Record<string, string> = {
  fresh: "bg-emerald-900/60 text-emerald-300",
  cached: "bg-sky-900/60 text-sky-300",
  stale: "bg-amber-900/60 text-amber-300",
  fallback: "bg-rose-900/60 text-rose-300",
};

const REGIME_STYLE: Record<string, string> = {
  low: "bg-emerald-900/60 text-emerald-300",
  normal: "bg-sky-900/60 text-sky-300",
  elevated: "bg-amber-900/60 text-amber-300",
  high: "bg-rose-900/60 text-rose-300",
};

/**
 * Capital Market Expectations table, computed by the Python CME engine
 * (historical stats blended with implied volatility).
 */
export async function CmeSection() {
  const data = await getCme();

  if (!data) {
    return <ApiOffline resource="资本市场预期（CME）" />;
  }

  const { report } = data;
  const statusStyle = CACHE_STATUS_STYLE[data.cache_status] ?? CACHE_STATUS_STYLE.fallback;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-baseline gap-3">
        <h2 className="text-lg font-semibold text-slate-100">
          资本市场预期 <span className="text-sm font-normal text-slate-400">CME</span>
        </h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusStyle}`}>
          {data.cache_status}
        </span>
        <span className="text-xs text-slate-500">
          数据截至 {report.as_of_date} · 无风险利率 {fmtPct(report.risk_free_rate)}（
          {report.risk_free_rate_source}）· 回溯 {report.data_lookback_years} 年
        </span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="bg-slate-900 text-xs uppercase tracking-wide text-slate-400">
            <tr>
              <th className="px-4 py-3 font-medium">资产类别</th>
              <th className="px-4 py-3 text-right font-medium">预期收益</th>
              <th className="px-4 py-3 text-right font-medium">年化波动</th>
              <th className="px-4 py-3 text-right font-medium">混合波动 (IV)</th>
              <th className="px-4 py-3 text-right font-medium">夏普</th>
              <th className="px-4 py-3 text-right font-medium">最大回撤</th>
              <th className="px-4 py-3 text-right font-medium">波动状态</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800 bg-slate-900/40">
            {report.asset_classes.map((a) => (
              <tr key={a.ticker} className="text-slate-300">
                <td className="px-4 py-3">
                  <div className="font-medium text-slate-100">{a.name}</div>
                  <div className="font-mono text-xs text-slate-500">{a.ticker}</div>
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  {fmtPct(a.expected_return)}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  {fmtPct(a.volatility)}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  {fmtPct(a.blended_volatility)}
                </td>
                <td className="px-4 py-3 text-right font-mono">
                  {a.sharpe_ratio.toFixed(2)}
                </td>
                <td className="px-4 py-3 text-right font-mono text-rose-400">
                  {fmtPct(a.max_drawdown)}
                </td>
                <td className="px-4 py-3 text-right">
                  {a.volatility_regime ? (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        REGIME_STYLE[a.volatility_regime] ?? REGIME_STYLE.normal
                      }`}
                    >
                      {a.volatility_regime}
                    </span>
                  ) : (
                    <span className="text-slate-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
