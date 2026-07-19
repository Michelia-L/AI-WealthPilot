import { Suspense } from "react";
import {
  DEFAULT_PERIOD,
  VALID_PERIODS,
  getAnalytics,
  getUniverse,
} from "@/lib/api";
import { QuotesSection } from "@/components/quotes-section";
import { CmeSection } from "@/components/cme-section";
import { ApiOffline } from "@/components/api-offline";
import DashboardControls from "@/components/dashboard-controls";
import AnalyticsTabs from "@/components/analytics-tabs";
import SectionHeader from "@/components/ui/section-header";
import Skeleton from "@/components/ui/skeleton";

function SectionSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      <Skeleton className="h-6 w-48" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: rows }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="space-y-3">
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-[540px] rounded-xl" />
    </div>
  );
}

/** Fetches the analytics bundle and hands it to the client tabs. */
async function AnalyticsSection({
  period,
  tickers,
}: {
  period: string;
  tickers: string[];
}) {
  const analytics = await getAnalytics(period, tickers);
  if (!analytics) {
    return <ApiOffline resource="分析数据" />;
  }
  return <AnalyticsTabs analytics={analytics} />;
}

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * Market Dashboard — filter state lives in the URL (?period=&categories=);
 * every section streams in as its data arrives.
 */
export default async function MarketPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const periodParam = typeof sp.period === "string" ? sp.period : DEFAULT_PERIOD;
  const period = VALID_PERIODS.includes(periodParam)
    ? periodParam
    : DEFAULT_PERIOD;

  const universe = await getUniverse();
  if (!universe) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader eyebrow="Market Dashboard" title="市场仪表盘" />
        <ApiOffline resource="资产宇宙元数据" />
      </div>
    );
  }

  const allCategories = [
    ...new Set(Object.values(universe.assets).map((a) => a.category)),
  ].sort();

  const requested =
    typeof sp.categories === "string" && sp.categories.length > 0
      ? sp.categories.split(",").filter((c) => allCategories.includes(c))
      : allCategories;
  const selectedCategories = requested.length > 0 ? requested : allCategories;

  const selectedTickers = Object.entries(universe.assets)
    .filter(([, info]) => selectedCategories.includes(info.category))
    .map(([ticker]) => ticker);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-10">
      <SectionHeader
        eyebrow="Global Markets Pulse"
        title="市场仪表盘"
        description="实时行情、跨资产相关性与资本市场预期（CME）。"
      />

      <DashboardControls
        categories={allCategories}
        selectedCategories={selectedCategories}
        period={period}
        assetCount={selectedTickers.length}
      />

      <Suspense fallback={<SectionSkeleton rows={8} />}>
        <QuotesSection tickers={selectedTickers} />
      </Suspense>

      <Suspense fallback={<ChartSkeleton />}>
        <AnalyticsSection period={period} tickers={selectedTickers} />
      </Suspense>

      <Suspense fallback={<SectionSkeleton rows={7} />}>
        <CmeSection />
      </Suspense>

      <footer className="mt-auto border-t border-white/[0.06] pt-6 text-xs leading-5 text-mist-500">
        数据来源：Yahoo Finance（yfinance），实时行情缓存 5
        分钟。量化输出仅供参考，不构成投资建议。
      </footer>
    </div>
  );
}
