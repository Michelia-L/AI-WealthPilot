import { getBacktest } from "@/lib/api";
import { ApiOffline } from "@/components/api-offline";
import BacktestPeriodSelector from "@/components/backtest-period-selector";
import BacktestResults from "@/components/backtest-results";
import { Icon } from "@/components/ui";

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

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="clock" size={15} className="text-gold-400" />
          历史回测
          <span className="text-xs font-normal text-mist-500">
            月初再平衡 · 对照 {bt.benchmark.name}
          </span>
        </h3>
        <BacktestPeriodSelector documentId={documentId} period={period} />
      </div>

      <BacktestResults bt={bt} />
    </section>
  );
}
