import Link from "next/link";
import {
  MARITAL_STATUS_OPTIONS,
  TAX_STATUS_OPTIONS,
  getAdvisorReports,
  getIpsDocuments,
  getProfile,
} from "@/lib/api";
import { fmtLocal, fmtMoney, fmtPct } from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";
import HubActions from "@/components/profiles/hub-actions";
import { RiskBadge } from "@/components/profiles/shared";
import {
  Badge,
  ButtonLink,
  EmptyState,
  Icon,
  Panel,
  SectionHeader,
  StatTile,
  type BadgeTone,
} from "@/components/ui";
import type { IconName } from "@/components/ui";

export const metadata = {
  title: "客户枢纽 · AI WealthPilot",
};

const PRIORITY_META: Record<string, { label: string; tone: BadgeTone }> = {
  high: { label: "高", tone: "gold" },
  medium: { label: "中", tone: "steel" },
  low: { label: "低", tone: "mist" },
};

function optionLabel(
  options: ReadonlyArray<{ value: string; label: string }>,
  value: string
): string {
  return options.find((o) => o.value === value)?.label ?? value;
}

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
function ScoreBar({ label, score }: { label: string; score: number }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-xs text-mist-500">{label}</span>
        <span className="tnum font-mono text-sm text-gold-300">
          {score > 0 ? score.toFixed(1) : "未评估"}
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

/**
 * 客户枢纽（P8 客户中心制）—— 单客户的全景视图：
 * 画像详情 + 财务指标 + 该客户的建议书与 IPS 交付物 + 快捷工作流入口。
 */
export default async function ClientHubPage({ params }: PageProps) {
  const { id: raw } = await params;
  const id = Number(raw);

  if (!Number.isInteger(id) || id <= 0) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <Panel>
          <EmptyState
            icon="warning"
            title="无效的客户编号"
            action={<ButtonLink href="/profiles">返回客户列表</ButtonLink>}
          />
        </Panel>
      </div>
    );
  }

  const detail = await getProfile(id);

  if (!detail) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader eyebrow="Client Hub" title="客户枢纽" />
        <ApiOffline resource="客户详情（客户可能不存在，或 API 离线）" />
        <div>
          <ButtonLink href="/profiles" variant="ghost">
            返回客户列表
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
      label: "AI 建议书",
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
        eyebrow="Client Hub"
        title={profile.name}
        description={`${profile.age} 岁 · ${optionLabel(MARITAL_STATUS_OPTIONS, profile.marital_status)} · 抚养/赡养 ${profile.dependents} 人 · 更新于 ${fmtLocal(detail.updated_at)}`}
        actions={
          <div className="flex items-center gap-3">
            <RiskBadge level={derived.tolerance_level} />
            <ButtonLink href={`/profiles?edit=${id}`} icon="pencil">
              编辑画像
            </ButtonLink>
          </div>
        }
      />

      <HubActions id={id} name={profile.name} />

      {/* 关键指标 */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="净资产" value={fmtMoney(derived.net_worth)} tone="gold" />
        <StatTile
          label="年储蓄率"
          value={fmtPct(derived.savings_rate)}
          hint={`年储蓄 ${fmtMoney(derived.annual_savings)}`}
        />
        <StatTile
          label="负债资产比"
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
          label="综合风险分"
          value={derived.final_risk_score > 0 ? derived.final_risk_score.toFixed(1) : "未评估"}
          hint="min（能力， 意愿） · 满分 5"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* 财务状况 */}
        <Panel>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="banknote" size={15} className="text-gold-400" />
            财务状况
          </h3>
          <MetaRow label="年收入" value={fmtMoney(profile.financial.annual_income)} />
          <MetaRow label="年支出" value={fmtMoney(profile.financial.annual_expenses)} />
          <MetaRow label="可投资资产" value={fmtMoney(profile.financial.investable_assets)} />
          <MetaRow label="总负债" value={fmtMoney(profile.financial.total_liabilities)} />
          <MetaRow
            label="应急基金"
            value={`${profile.financial.emergency_fund_months} 个月`}
            border={false}
          />
        </Panel>

        {/* 风险画像 */}
        <Panel>
          <h3 className="mb-4 flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="shield" size={15} className="text-gold-400" />
            风险画像
          </h3>
          <div className="space-y-4">
            <ScoreBar label="风险承受能力（客观）" score={profile.risk_profile.ability_score} />
            <ScoreBar label="风险承受意愿（主观）" score={profile.risk_profile.willingness_score} />
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
            投资目标
          </h3>
          {profile.goals.length === 0 ? (
            <p className="text-xs leading-5 text-mist-500">尚未设定投资目标。</p>
          ) : (
            <div className="flex flex-col divide-y divide-white/[0.05]">
              {profile.goals.map((g, i) => {
                const meta = PRIORITY_META[g.priority] ?? PRIORITY_META.medium;
                return (
                  <div key={i} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <div className="truncate text-sm text-mist-100">{g.name}</div>
                      <div className="text-xs text-mist-500">{g.years} 年后</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="tnum font-mono text-sm text-mist-100">
                        {fmtMoney(g.target_amount)}
                      </span>
                      <Badge tone={meta.tone}>{meta.label}优先</Badge>
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
            约束与偏好
          </h3>
          <MetaRow label="投资期限" value={`${profile.time_horizon_years} 年${profile.is_multi_stage ? "（多阶段）" : ""}`} />
          <MetaRow label="流动性需求" value={fmtMoney(profile.liquidity_needs)} />
          <MetaRow
            label="税务状态"
            value={optionLabel(TAX_STATUS_OPTIONS, profile.tax_status)}
          />
          <MetaRow
            label="ESG 偏好"
            value={
              profile.esg_preference ? (
                <Badge tone="jade">是</Badge>
              ) : (
                <span className="text-mist-500">否</span>
              )
            }
          />
          <div className="flex items-start justify-between gap-4 py-2.5">
            <span className="shrink-0 text-xs text-mist-500">行业限制</span>
            <span className="flex flex-wrap justify-end gap-1.5">
              {profile.sector_restrictions.length === 0 ? (
                <span className="text-sm text-mist-500">无</span>
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

      {/* 交付物 */}
      <Panel innerClassName="flex flex-col">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
            <Icon name="briefcase" size={15} className="text-gold-400" />
            交付物
          </h3>
          <span className="text-xs text-mist-600">
            {deliverables.length} 份
          </span>
        </div>
        {deliverables.length === 0 ? (
          <EmptyState
            icon="briefcase"
            title="还没有交付物"
            hint="使用上方「生成建议书」或「生成 IPS」为该客户产出第一份交付物。"
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
          返回客户列表
        </ButtonLink>
      </div>
    </div>
  );
}
