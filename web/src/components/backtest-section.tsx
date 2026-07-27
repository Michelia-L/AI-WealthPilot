import { getBacktest } from "@/lib/api";
import { ApiOffline } from "@/components/api-offline";
import BacktestPeriodSelector from "@/components/backtest-period-selector";
import BacktestResults from "@/components/backtest-results";
import { Icon } from "@/components/ui";
import { getDict, getLocale } from "@/lib/i18n/server";

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
  const t = await getDict();
  const locale = await getLocale();
  const bt = await getBacktest(documentId, period, locale);
  if (!bt) {
    return <ApiOffline resource={t.monitoring.resourceBacktest} />;
  }

  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="clock" size={15} className="text-gold-400" />
          {t.monitoring.backtestTitle}
          <span className="text-xs font-normal text-mist-500">
            {t.monitoring.backtestSub(bt.benchmark.name)}
          </span>
        </h3>
        <BacktestPeriodSelector documentId={documentId} period={period} />
      </div>

      <BacktestResults bt={bt} />
    </section>
  );
}
