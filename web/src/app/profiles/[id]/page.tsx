import Link from "next/link";
import { Suspense } from "react";
import {
  getAdvisorReports,
  getIpsDocuments,
  getProfile,
  getRecommendation,
} from "@/lib/api";
import { fmtLocal, fmtMoney, fmtPct } from "@/lib/format";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
import { ApiOffline } from "@/components/api-offline";
import Markdown from "@/components/markdown";
import HubActions from "@/components/profiles/hub-actions";
import { localizedRiskLabel, RiskBadge } from "@/components/profiles/shared";
import {
  Badge,
  ButtonLink,
  EmptyState,
  Icon,
  Panel,
  SectionHeader,
  Skeleton,
  StatTile,
  type BadgeTone,
} from "@/components/ui";
import type { IconName } from "@/components/ui";

export async function generateMetadata() {
  const t = await getDict();
  return { title: `${t.profileDetail.title} · AI WealthPilot` };
}

const PRIORITY_META: Record<string, { tone: BadgeTone }> = {
  high: { tone: "gold" },
  medium: { tone: "steel" },
  low: { tone: "mist" },
};

/** 定义列表行 —— 标签 + 等宽数值。 */
function MetaRow({
  label,
  value,
  border = true,
}: {
  label: string;
  value: React.ReactNode;
  border?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between gap-4 py-2.5 ${border ? "border-b border-white/[0.05]" : ""}`}
    >
      <span className="text-xs text-mist-500">{label}</span>
      <span className="tnum text-sm text-mist-100">{value}</span>
    </div>
  );
}

/** 风险双轨分数条。 */
function ScoreBar({
  label,
  score,
  unassessed,
}: {
  label: string;
  score: number;
  unassessed: string;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs text-mist-500">{label}</span>
        <span className="tnum font-mono text-sm text-gold-300">
          {score > 0 ? score.toFixed(1) : unassessed}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-ink-700/70">
        <div
          className="h-full rounded-full bg-gradient-to-r from-gold-600 to-gold-400 transition-all duration-700 ease-luxe"
          style={{ width: `${Math.min(100, (score / 5) * 100)}%` }}
        />
      </div>
    </div>
  );
}

interface PageProps {
  params: Promise<{ id: string }>;
}

/** 推荐配置区块 —— 基于风险分数的目标波动率组合（服务端流式渲染）。 */
async function RecommendationSection({ profileId }: { profileId: number }) {
  const [locale, rec] = await Promise.all([
    getLocale(),
    getRecommendation(profileId),
  ]);
  const t = dictionaries[locale];
  if (!rec) return null;

  const entries = Object.entries(rec.allocation)
    .filter(([, w]) => w > 0.001)
    .sort((a, b) => b[1] - a[1]);
  const maxW = entries[0]?.[1] ?? 1;

  return (
    <Panel>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="pie" size={15} className="text-gold-400" />
          {t.profileDetail.recommendation}
        </h3>
        <Badge tone="gold">
          {localizedRiskLabel(rec.risk_level, locale, t.profileDetail.unassessed)}
        </Badge>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <div>
          <div className="mb-4 grid grid-cols-3 gap-3">
            <StatTile
              label={t.profileDetail.expectedReturn}
              value={fmtPct(rec.expected_return)}
              tone="jade"
            />
            <StatTile
              label={t.profileDetail.expectedVolatility}
              value={fmtPct(rec.expected_volatility)}
            />
            <StatTile
              label={t.profileDetail.sharpeRatio}
              value={rec.sharpe_ratio.toFixed(2)}
              tone="gold"
            />
          </div>
          <div className="space-y-2.5">
            {entries.map(([name, w]) => (
              <div key={name} className="grid grid-cols-[130px_1fr_48px] items-center gap-3">
                <span className="truncate text-xs text-mist-400" title={name}>
                  {name}
                </span>
                <div className="h-1.5 overflow-hidden rounded-full bg-ink-700/60">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-gold-600 to-gold-400"
                    style={{ width: `${(w / maxW) * 100}%` }}
                  />
                </div>
                <span className="tnum text-right font-mono text-xs text-mist-200">
                  {fmtPct(w, 1)}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="border-t border-white/[0.06] pt-4 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-6">
          <Markdown>{rec.rationale}</Markdown>
        </div>
      </div>
    </Panel>
  );
}

/**
 * 客户枢纽（P8 客户中心制）—— 单客户的全景视图：
 * 画像详情 + 财务指标 + 该客户的建议书与 IPS 交付物 + 快捷工作流入口。
 */
export default async function ClientHubPage({ params }: PageProps) {
  const [{ id: raw }, locale] = await Promise.all([params, getLocale()]);
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];
  const id = Number(raw);

  if (!Number.isInteger(id) || id <= 0) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <Panel>
          <EmptyState
            icon="warning"
            title={t.profileDetail.invalidId}
            action={
              <ButtonLink href="/profiles">
                {t.profileDetail.backToList}
              </ButtonLink>
            }
          />
        </Panel>
      </div>
    );
  }

  const detail = await getProfile(id);

  if (!detail) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader
          eyebrow={alt.profileDetail.title}
          title={t.profileDetail.title}
        />
        <ApiOffline resource={t.profileDetail.detailResource} />
        <div>
          <ButtonLink href="/profiles" variant="ghost">
            {t.profileDetail.backToList}
          </ButtonLink>
        </div>
      </div>
    );
  }

  const { profile, derived } = detail;
  const [reportsData, ipsData] = await Promise.all([
    getAdvisorReports(profile.name),
    getIpsDocuments(),
  ]);
  const reports = reportsData?.reports ?? [];
  const ipsDocs = (ipsData?.documents ?? []).filter(
    (d) => d.client_name === profile.name
  );

  const deliverables = [
    ...reports.map((r) => ({
      key: `a-${r.report_id}`,
      icon: "sparkle" as IconName,
      label: t.profileDetail.advisorReport,
      sub: `${r.model} · ${r.total_tokens} tokens`,
      when: r.generated_at,
      href: `/deliverables/advisor/${encodeURIComponent(r.report_id)}`,
    })),
    ...ipsDocs.map((d) => ({
      key: `i-${d.document_id}`,
      icon: "scroll" as IconName,
      label: `IPS v${d.version}`,
      sub: d.status,
      when: d.saved_at,
      href: `/deliverables/ips/${encodeURIComponent(d.document_id)}`,
    })),
  ].sort((a, b) => (a.when < b.when ? 1 : -1));

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow={alt.profileDetail.title}
        title={profile.name}
        description={t.profileDetail.headerDescription(
          profile.age,
          t.profileDetail.maritalLabel(profile.marital_status),
          profile.dependents,
          fmtLocal(detail.updated_at)
        )}
        actions={
          <div className="flex items-center gap-3">
            <RiskBadge
              level={derived.tolerance_level}
              locale={locale}
              unassessed={t.profileDetail.unassessed}
            />
            <ButtonLink href={`/profiles?edit=${id}`} icon="pencil">
              {t.profileDetail.editProfile}
            </ButtonLink>
          </div>
        }
      />

      <HubActions id={id} name={profile.name} />

      {/* 关键指标 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile
          label={t.profileDetail.netWorth}
          value={fmtMoney(derived.net_worth)}
          tone="gold"
        />
        <StatTile
          label={t.profileDetail.savingsRate}
          value={fmtPct(derived.savings_rate)}
          hint={t.profileDetail.annualSavingsHint(
            fmtMoney(derived.annual_savings)
          )}
        />
        <StatTile
          label={t.profileDetail.debtToAssetRatio}
          value={
            derived.debt_to_asset_ratio === null
              ? "∞"
              : fmtPct(derived.debt_to_asset_ratio)
          }
          tone={
            derived.debt_to_asset_ratio !== null &&
            derived.debt_to_asset_ratio > 0.5
              ? "cinnabar"
              : "default"
          }
        />
        <StatTile
          label={t.profileDetail.finalRiskScore}
          value={
            derived.final_risk_score > 0
              ? derived.final_risk_score.toFixed(1)
              : t.profileDetail.unassessed
          }
          hint={t.profileDetail.finalRiskScoreHint}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 财务状况 */}
        <Panel>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="banknote" size={15} className="text-gold-400" />
            {t.profileDetail.financials}
          </h3>
          <MetaRow
            label={t.profileDetail.annualIncome}
            value={fmtMoney(profile.financial.annual_income)}
          />
          <MetaRow
            label={t.profileDetail.annualExpenses}
            value={fmtMoney(profile.financial.annual_expenses)}
          />
          <MetaRow
            label={t.profileDetail.investableAssets}
            value={fmtMoney(profile.financial.investable_assets)}
          />
          <MetaRow
            label={t.profileDetail.totalLiabilities}
            value={fmtMoney(profile.financial.total_liabilities)}
          />
          <MetaRow
            label={t.profileDetail.emergencyFund}
            value={t.profileDetail.monthsValue(
              profile.financial.emergency_fund_months
            )}
            border={false}
          />
        </Panel>

        {/* 风险画像 */}
        <Panel>
          <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="shield" size={15} className="text-gold-400" />
            {t.profileDetail.riskProfile}
          </h3>
          <div className="space-y-4">
            <ScoreBar
              label={t.profileDetail.abilityScoreLabel}
              score={profile.risk_profile.ability_score}
              unassessed={t.profileDetail.unassessed}
            />
            <ScoreBar
              label={t.profileDetail.willingnessScoreLabel}
              score={profile.risk_profile.willingness_score}
              unassessed={t.profileDetail.unassessed}
            />
          </div>
          {profile.risk_profile.description && (
            <p className="mt-4 border-t border-white/[0.06] pt-3 text-xs leading-6 text-mist-400">
              {profile.risk_profile.description}
            </p>
          )}
        </Panel>

        {/* 投资目标 */}
        <Panel>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="target" size={15} className="text-gold-400" />
            {t.profileDetail.goals}
          </h3>
          {profile.goals.length === 0 ? (
            <p className="text-xs leading-5 text-mist-500">
              {t.profileDetail.noGoals}
            </p>
          ) : (
            <div className="flex flex-col divide-y divide-white/[0.05]">
              {profile.goals.map((g, i) => {
                const meta = PRIORITY_META[g.priority] ?? PRIORITY_META.medium;
                return (
                  <div key={i} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-mist-100">{g.name}</div>
                      <div className="text-xs text-mist-500">
                        {t.profileDetail.yearsLater(g.years)}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="tnum font-mono text-sm text-mist-100">
                        {fmtMoney(g.target_amount)}
                      </span>
                      <Badge tone={meta.tone}>
                        {t.profileDetail.priorityBadge(g.priority)}
                      </Badge>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        {/* 约束与偏好 */}
        <Panel>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="sliders" size={15} className="text-gold-400" />
            {t.profileDetail.constraints}
          </h3>
          <MetaRow
            label={t.profileDetail.timeHorizon}
            value={t.profileDetail.horizonValue(
              profile.time_horizon_years,
              profile.is_multi_stage
            )}
          />
          <MetaRow
            label={t.profileDetail.liquidityNeeds}
            value={fmtMoney(profile.liquidity_needs)}
          />
          <MetaRow
            label={t.profileDetail.taxStatus}
            value={t.profileDetail.taxLabel(profile.tax_status)}
          />
          <MetaRow
            label={t.profileDetail.esgPreference}
            value={
              profile.esg_preference ? (
                <Badge tone="jade">{t.profileDetail.esgYes}</Badge>
              ) : (
                <span className="text-mist-500">{t.profileDetail.esgNo}</span>
              )
            }
          />
          <div className="flex items-start justify-between gap-4 py-2.5">
            <span className="shrink-0 text-xs text-mist-500">
              {t.profileDetail.sectorRestrictions}
            </span>
            <span className="flex flex-wrap justify-end gap-1.5">
              {profile.sector_restrictions.length === 0 ? (
                <span className="text-sm text-mist-500">
                  {t.profileDetail.none}
                </span>
              ) : (
                profile.sector_restrictions.map((s) => (
                  <Badge key={s} tone="mist">
                    {s}
                  </Badge>
                ))
              )}
            </span>
          </div>
          {profile.notes && (
            <p className="border-t border-white/[0.06] pt-3 text-xs leading-6 text-mist-400">
              {profile.notes}
            </p>
          )}
        </Panel>
      </div>

      {/* 推荐配置（P12，风险分数 → 目标波动率的个性化配置） */}
      <Suspense fallback={<Skeleton className="h-56 rounded-[1.4rem]" />}>
        <RecommendationSection profileId={id} />
      </Suspense>

      {/* 交付物 */}
      <Panel innerClassName="flex flex-col">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="briefcase" size={15} className="text-gold-400" />
            {t.profileDetail.deliverables}
          </h3>
          <span className="text-xs text-mist-600">
            {t.profileDetail.deliverableCount(deliverables.length)}
          </span>
        </div>
        {deliverables.length === 0 ? (
          <EmptyState
            icon="briefcase"
            title={t.profileDetail.deliverablesEmptyTitle}
            hint={t.profileDetail.deliverablesEmptyHint}
          />
        ) : (
          <div className="grid gap-x-8 sm:grid-cols-2">
            {deliverables.map((d) => (
              <Link
                key={d.key}
                href={d.href}
                className="group flex items-center gap-3 border-b border-white/[0.05] py-3"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/[0.06] bg-ink-850 text-gold-400">
                  <Icon name={d.icon} size={14} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-mist-100 transition-colors group-hover:text-gold-300">
                    {d.label}
                  </span>
                  <span className="block truncate text-xs text-mist-500">{d.sub}</span>
                </span>
                <span className="tnum shrink-0 font-mono text-[11px] text-mist-600">
                  {fmtLocal(d.when)}
                </span>
              </Link>
            ))}
          </div>
        )}
      </Panel>

      <div>
        <ButtonLink href="/profiles" variant="ghost" size="sm">
          {t.profileDetail.backToList}
        </ButtonLink>
      </div>
    </div>
  );
}
