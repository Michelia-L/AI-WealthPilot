import { Suspense } from "react";
import {
  DEFAULT_PERIOD,
  VALID_PERIODS,
  getAnalytics,
  getHealth,
  getUniverse,
} from "@/lib/api";
import { QuotesSection } from "@/components/quotes-section";
import { CmeSection } from "@/components/cme-section";
import { ApiOffline } from "@/components/api-offline";
import DashboardControls from "@/components/dashboard-controls";
import AnalyticsTabs from "@/components/analytics-tabs";

/** Small API status chip in the header — streams in independently. */
async function HealthBadge() {
  const health = await getHealth();
  if (!health) {
    return (
      <span className="rounded-full bg-rose-900/60 px-3 py-1 text-xs font-medium text-rose-300">
        API 离线
      </span>
    );
  }
  return (
    <span className="rounded-full bg-emerald-900/60 px-3 py-1 text-xs font-medium text-emerald-300">
      API 在线 · v{health.version}
    </span>
  );
}

function SectionSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      <div className="h-6 w-48 animate-pulse rounded bg-slate-800" />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-900" />
        ))}
      </div>
    </div>
  );
}

function ChartSkeleton() {
  return (
    <div className="space-y-3">
      <div className="h-9 w-72 animate-pulse rounded-lg bg-slate-800" />
      <div className="h-[540px] animate-pulse rounded-xl bg-slate-900" />
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
 * Market Dashboard — the real thing (Phase 2). Filter state lives in the
 * URL (?period=&categories=); every section streams in as its data arrives.
 */
export default async function Home({ searchParams }: PageProps) {
  const sp = await searchParams;
  const periodParam = typeof sp.period === "string" ? sp.period : DEFAULT_PERIOD;
  const period = VALID_PERIODS.includes(periodParam) ? periodParam : DEFAULT_PERIOD;

  const universe = await getUniverse();
  if (!universe) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <Header />
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
      <Header />

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

      <footer className="mt-auto border-t border-slate-800 pt-6 text-xs text-slate-500">
        数据来源：Yahoo Finance（yfinance），实时行情缓存 5 分钟。量化输出仅供参考，
        不构成投资建议。
      </footer>
    </div>
  );
}

function Header() {
  return (
    <header className="flex items-center justify-between">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">
          Global Markets Pulse
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          AI WealthPilot · 实时行情与量化分析
        </p>
      </div>
      <Suspense
        fallback={
          <span className="h-6 w-24 animate-pulse rounded-full bg-slate-800" />
        }
      >
        <HealthBadge />
      </Suspense>
    </header>
  );
}
