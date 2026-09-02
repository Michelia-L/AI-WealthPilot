import type { Metadata } from "next";
import { getIpsDocuments, getMonitoring, type MonitoringHolding } from "@/lib/api";
import { fmtLocal, fmtPct } from "@/lib/format";
import { cx } from "@/lib/cx";
import { Suspense } from "react";
import { ApiOffline } from "@/components/api-offline";
import BacktestSection from "@/components/backtest-section";
import MonitoringSelector from "@/components/monitoring-selector";
import RebalanceAdvice from "@/components/rebalance-advice";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
import {
  Badge,
  ButtonLink,
  EmptyState,
  Icon,
  Panel,
  SectionHeader,
  Skeleton,
  StatTile,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.monitoring.title} · AI WealthPilot` };
}

const BAND_TONE: Record<string, "jade" | "cinnabar" | "gold" | "mist"> = {
  within: "jade",
  above: "cinnabar",
  below: "gold",
  unknown: "mist",
};

/** IPS 资产配置键 → 优化器资产宇宙键（EWH 港股在优化器宇宙中无代理，跳过）。 */
const OPTIMIZER_KEY_MAP: Record<string, string> = {
  domestic_equity: "CHINA_EQUITY",
  international_equity_dm: "INTL_EQUITY",
  fixed_income: "US_BOND",
  alternative_gold: "GOLD",
  alternative_reit: "REIT",
  cash: "CASH",
};

function signedPp(value: number | null): string {
  if (value === null) return "—";
  const pp = value * 100;
  return `${pp > 0 ? "+" : ""}${pp.toFixed(1)}pp`;
}

/** 权重对比条：金色=漂移后权重，竖线=目标，浅带=IPS 允许区间。 */
function WeightBar({
  holding,
  scale,
  title,
}: {
  holding: MonitoringHolding;
  scale: number;
  title: string;
}) {
  const pct = (v: number) => `${Math.min(100, (v / scale) * 100)}%`;
  return (
    <div
      className="relative h-2.5 w-full rounded-full bg-ink-700/50"
      title={title}
    >
      <div
        className="absolute top-0 h-full rounded-full bg-white/[0.08]"
        style={{
          left: pct(holding.min_weight),
          width: pct(holding.max_weight - holding.min_weight),
        }}
      />
      {holding.drifted_weight !== null && (
        <div
          className={cx(
            "absolute top-0 h-full rounded-full transition-all duration-700 ease-luxe",
            holding.band_status === "within"
              ? "bg-gold-500/75"
              : holding.band_status === "above"
                ? "bg-cinnabar-500/75"
                : "bg-gold-300/75"
          )}
          style={{ width: pct(holding.drifted_weight) }}
        />
      )}
      <div
        className="absolute -top-1 h-[18px] w-px bg-mist-100/80"
        style={{ left: pct(holding.target_weight) }}
      />
    </div>
  );
}

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * 组合监控（P10）—— 以 IPS 的 SAA 目标配置为锚，展示买入持有漂移、
 * 偏离区间状态与复衡建议；组合指标基于 CME 与相关性矩阵计算。
 */
export default async function MonitoringPage({ searchParams }: PageProps) {
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];
  const sp = await searchParams;
  const docId = typeof sp.doc === "string" ? sp.doc : "";
  const btPeriod =
    typeof sp.bt === "string" && ["3y", "5y", "10y"].includes(sp.bt)
      ? sp.bt
      : "5y";

  const documents = (await getIpsDocuments())?.documents ?? null;

  if (documents === null) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader
          eyebrow={alt.monitoring.title}
          title={t.monitoring.title}
          description={t.monitoring.descriptionOffline}
        />
        <ApiOffline resource={t.monitoring.resourceIpsList} />
      </div>
    );
  }

  const data = docId ? await getMonitoring(docId, locale) : null;

  const bandLabels: Record<string, string> = {
    within: t.monitoring.bandWithin,
    above: t.monitoring.bandAbove,
    below: t.monitoring.bandBelow,
    unknown: t.monitoring.bandUnknown,
  };

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow={alt.monitoring.title}
        title={t.monitoring.title}
        description={t.monitoring.description}
      />

      <MonitoringSelector documents={documents} selected={docId} />

      {!docId ? (
        <Panel pad={false}>
          <EmptyState
            icon="eye"
            title={t.monitoring.emptyTitle}
            hint={t.monitoring.emptyHint}
          />
        </Panel>
      ) : !data ? (
        <ApiOffline resource={t.monitoring.resourceMonitoring} />
      ) : (
        <>
          {/* 头部信息 */}
          <div className="flex flex-wrap items-center gap-3 text-xs text-mist-500">
            <span className="text-sm font-medium text-mist-100">
              {data.client_name}
            </span>
            <span>{t.monitoring.ipsSavedAt(fmtLocal(data.saved_at))}</span>
            <span>·</span>
            <span className="tnum">{t.monitoring.asOf(fmtLocal(data.as_of))}</span>
            <span>·</span>
            <span>{t.monitoring.cmeCache(data.cme_cache_status)}</span>
            {(() => {
              const optimizerKeys = [
                ...new Set(
                  data.holdings
                    .map((h) => (h.key ? OPTIMIZER_KEY_MAP[h.key] : undefined))
                    .filter((k): k is string => Boolean(k))
                ),
              ];
              return optimizerKeys.length >= 2 ? (
                <span className="ml-auto">
                  <ButtonLink
                    href={`/optimizer?assets=${optimizerKeys.join(",")}`}
                    size="sm"
                    icon="pie"
                  >
                    {t.monitoring.analyzeInOptimizer}
                  </ButtonLink>
                </span>
              ) : null;
            })()}
          </div>

          {/* 组合指标：目标口径 vs 漂移口径 */}
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            <StatTile
              label={t.monitoring.statReturnTarget}
              value={fmtPct(data.portfolio.expected_return)}
              hint={t.monitoring.driftedHint(
                fmtPct(data.drifted_portfolio.expected_return)
              )}
              tone="gold"
            />
            <StatTile
              label={t.monitoring.statVolTarget}
              value={fmtPct(data.portfolio.volatility)}
              hint={t.monitoring.driftedHint(
                fmtPct(data.drifted_portfolio.volatility)
              )}
            />
            <StatTile
              label={t.monitoring.statSharpeTarget}
              value={
                data.portfolio.sharpe === null
                  ? "—"
                  : data.portfolio.sharpe.toFixed(2)
              }
              hint={t.monitoring.driftedHint(
                data.drifted_portfolio.sharpe === null
                  ? "—"
                  : data.drifted_portfolio.sharpe.toFixed(2)
              )}
            />
          </div>

          {/* 漂移与区间 */}
          <Panel>
            <div className="mb-5 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
                <Icon name="chartUp" size={15} className="text-gold-400" />
                {t.monitoring.driftPanelTitle}
              </h3>
              <span className="text-[11px] text-mist-600">
                {t.monitoring.driftLegend}
              </span>
            </div>
            <div className="space-y-5">
              {(() => {
                const barScale =
                  Math.max(
                    ...data.holdings.map((x) => x.max_weight),
                    0.2
                  ) * 1.15;
                return data.holdings.map((h) => {
                  const tone = BAND_TONE[h.band_status] ?? BAND_TONE.unknown;
                  return (
                    <div
                      key={h.name}
                      className="grid grid-cols-[130px_1fr_92px] items-center gap-4 sm:grid-cols-[180px_1fr_110px]"
                    >
                      <div className="min-w-0">
                        <div className="truncate text-sm text-mist-100" title={h.name}>
                          {h.name}
                        </div>
                        <div className="font-mono text-[11px] text-mist-600">
                          {h.ticker ?? "—"}
                        </div>
                      </div>
                      <WeightBar
                        holding={h}
                        scale={barScale}
                        title={t.monitoring.barTitle(
                          fmtPct(h.target_weight, 1),
                          fmtPct(h.min_weight, 1),
                          fmtPct(h.max_weight, 1)
                        )}
                      />
                      <div className="text-right">
                        <div
                          className={cx(
                            "tnum font-mono text-sm",
                            h.band_status === "above"
                              ? "text-cinnabar-300"
                              : h.band_status === "below"
                                ? "text-gold-300"
                                : "text-mist-200"
                          )}
                        >
                          {h.drifted_weight === null
                            ? "—"
                            : fmtPct(h.drifted_weight, 1)}
                        </div>
                        <div className="tnum font-mono text-[11px] text-mist-500">
                          {signedPp(h.drift_pp)}
                        </div>
                        <div className="mt-1 flex justify-end">
                          <Badge tone={tone}>
                            {bandLabels[h.band_status] ?? bandLabels.unknown}
                          </Badge>
                        </div>
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          </Panel>

          {/* 复衡建议 */}
          <Panel>
            <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-mist-200">
              <Icon name="refresh" size={15} className="text-gold-400" />
              {t.monitoring.rebalanceTitle}
            </h3>
            {!data.rebalance.needed ? (
              <div className="flex items-center gap-2.5 text-sm text-jade-300">
                <Icon name="check" size={16} />
                {t.monitoring.rebalanceNone}
              </div>
            ) : (
              <div className="flex flex-col divide-y divide-white/[0.05]">
                {data.rebalance.trades.map((trade) => (
                  <div
                    key={trade.name}
                    className="flex items-center justify-between gap-3 py-2.5"
                  >
                    <span className="text-sm text-mist-100">{trade.name}</span>
                    <span className="flex items-center gap-3">
                      <Badge tone={trade.action === "buy" ? "jade" : "cinnabar"}>
                        {trade.action === "buy"
                          ? t.monitoring.actionBuy
                          : t.monitoring.actionSell}
                      </Badge>
                      <span className="tnum font-mono text-sm text-mist-200">
                        {Math.abs(trade.weight_pp * 100).toFixed(1)}pp
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </Panel>

          {/* AI 调仓建议（SSE 流式） */}
          <RebalanceAdvice documentId={data.document_id} />

          {/* 单资产指标 */}
          <Panel pad={false} innerClassName="overflow-hidden">
            <Table className="min-w-[820px]">
              <THead>
                <tr>
                  <TH>{t.monitoring.colAsset}</TH>
                  <TH className="text-right">{t.monitoring.colExpectedReturn}</TH>
                  <TH className="text-right">{t.monitoring.colVolatility}</TH>
                  <TH className="text-right">{t.monitoring.colSharpe}</TH>
                  <TH className="text-right">{t.monitoring.colMaxDrawdown}</TH>
                  <TH className="text-right">VaR 95</TH>
                  <TH className="text-right">CVaR 95</TH>
                  <TH className="text-right">{t.monitoring.colPeriodReturn}</TH>
                </tr>
              </THead>
              <tbody>
                {data.holdings.map((h) => (
                  <TR key={h.name}>
                    <TD>
                      <div className="font-medium text-mist-100">{h.name}</div>
                      <div className="font-mono text-xs text-mist-500">
                        {h.ticker ?? "—"}
                      </div>
                    </TD>
                    <TD className="text-right font-mono">
                      {h.metrics ? fmtPct(h.metrics.expected_return) : "—"}
                    </TD>
                    <TD className="text-right font-mono">
                      {h.metrics ? fmtPct(h.metrics.volatility) : "—"}
                    </TD>
                    <TD className="text-right font-mono">
                      {h.metrics ? h.metrics.sharpe.toFixed(2) : "—"}
                    </TD>
                    <TD className="text-right font-mono text-cinnabar-400">
                      {h.metrics ? fmtPct(h.metrics.max_drawdown) : "—"}
                    </TD>
                    <TD className="text-right font-mono">
                      {h.metrics ? fmtPct(h.metrics.var_95) : "—"}
                    </TD>
                    <TD className="text-right font-mono">
                      {h.metrics ? fmtPct(h.metrics.cvar_95) : "—"}
                    </TD>
                    <TD
                      className={cx(
                        "text-right font-mono",
                        h.period_return === null
                          ? "text-mist-500"
                          : h.period_return > 0
                            ? "text-rise"
                            : h.period_return < 0
                              ? "text-fall"
                              : "text-mist-400"
                      )}
                    >
                      {h.period_return === null
                        ? "—"
                        : `${h.period_return > 0 ? "+" : ""}${fmtPct(h.period_return)}`}
                    </TD>
                  </TR>
                ))}
              </tbody>
            </Table>
          </Panel>

          {/* 历史回测（P13） */}
          <Suspense
            fallback={<Skeleton className="h-[420px] rounded-[1.4rem]" />}
          >
            <BacktestSection documentId={docId} period={btPeriod} />
          </Suspense>

          {/* 说明 */}
          {data.notes.length > 0 && (
            <div className="rounded-xl border border-gold-700/30 bg-gold-500/[0.05] px-5 py-4">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium text-gold-300">
                <Icon name="info" size={13} />
                {t.monitoring.notesTitle}
              </div>
              <ul className="space-y-1 text-xs leading-5 text-mist-400">
                {data.notes.map((n, i) => (
                  <li key={i}>· {n}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
