import Link from "next/link";
import {
  getAdvisorReports,
  getIpsDocuments,
  getProfiles,
  getQuotes,
  type ProfileSummary,
  type Quote,
} from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatAssetPrice, fmtLocal } from "@/lib/format";
import { ApiOffline } from "@/components/api-offline";
import { Badge, type BadgeTone } from "@/components/ui/chip";
import EmptyState from "@/components/ui/empty";
import Icon, { type IconName } from "@/components/ui/icon";
import Panel from "@/components/ui/panel";
import Reveal from "@/components/ui/reveal";

// ---------------------------------------------------------------------------
// 市场脉搏跑马灯
// ---------------------------------------------------------------------------

function PulseItem({ quote }: { quote: Quote }) {
  const pct = quote.change_pct;
  const tone =
    pct === null ? "text-mist-500" : pct > 0 ? "text-jade-400" : pct < 0 ? "text-cinnabar-400" : "text-mist-400";
  return (
    <span className="flex shrink-0 items-center gap-2.5 px-6">
      <span className="text-xs text-mist-400">{quote.name}</span>
      <span className="tnum font-mono text-sm text-mist-100">
        {formatAssetPrice(quote.price, quote.currency, quote.symbol, quote.ticker)}
      </span>
      <span className={cx("tnum font-mono text-xs", tone)}>
        {pct === null ? "—" : `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`}
      </span>
    </span>
  );
}

function PulseTape({ quotes }: { quotes: Quote[] | null }) {
  if (!quotes || quotes.length === 0) return null;
  // 首尾相接复制一份，配合 marquee 动画无缝循环
  const loop = [...quotes, ...quotes];
  return (
    <div className="relative overflow-hidden rounded-full border border-white/[0.06] bg-ink-900/70 py-2.5 [mask-image:linear-gradient(90deg,transparent,black_6%,black_94%,transparent)]">
      <div className="animate-marquee flex w-max hover:[animation-play-state:paused]">
        {loop.map((q, i) => (
          <PulseItem key={`${q.ticker}-${i}`} quote={q} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 客户速览
// ---------------------------------------------------------------------------

function riskTone(level: string): BadgeTone {
  if (level.includes("保守")) return "steel";
  if (level.includes("稳健")) return "jade";
  if (level.includes("平衡")) return "gold";
  if (level.includes("成长")) return "gold";
  if (level.includes("进取")) return "cinnabar";
  return "mist";
}

function ClientsCard({
  profiles,
}: {
  profiles: ProfileSummary[] | null;
}) {
  return (
    <Panel className="h-full" innerClassName="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="users" size={15} className="text-gold-400" />
          客户速览
        </h3>
        <Link
          href="/profiles"
          className="group flex items-center gap-1 text-xs text-mist-500 transition-colors hover:text-gold-300"
        >
          管理
          <Icon
            name="arrowUpRight"
            size={12}
            className="transition-transform duration-300 ease-luxe group-hover:-translate-y-px group-hover:translate-x-px"
          />
        </Link>
      </div>
      {profiles === null ? (
        <p className="text-xs leading-5 text-mist-500">API 离线，无法读取客户列表。</p>
      ) : profiles.length === 0 ? (
        <EmptyState
          icon="users"
          title="还没有客户画像"
          hint="建立第一份双轨风险评估画像，开启顾问工作流。"
          className="py-8"
        />
      ) : (
        <>
          <div className="flex flex-col divide-y divide-white/[0.05]">
            {profiles.slice(0, 5).map((p) => (
              <Link
                key={p.id}
                href={`/profiles/${p.id}`}
                className="group flex items-center justify-between gap-3 py-2.5 transition-colors"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm text-mist-100 transition-colors group-hover:text-gold-300">
                    {p.name}
                  </div>
                  <div className="text-xs text-mist-500">{p.age} 岁</div>
                </div>
                <Badge tone={riskTone(p.risk_level)}>
                  {p.risk_level.split("/")[0].trim()}
                </Badge>
              </Link>
            ))}
          </div>
          <div className="mt-auto pt-3 text-xs text-mist-600">
            共 {profiles.length} 位客户
          </div>
        </>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// 最近交付物
// ---------------------------------------------------------------------------

interface Deliverable {
  kind: "advisor" | "ips";
  id: string;
  client: string;
  when: string;
  sub: string;
}

const KIND_META: Record<Deliverable["kind"], { icon: IconName; label: string }> = {
  advisor: { icon: "sparkle", label: "AI 建议书" },
  ips: { icon: "scroll", label: "IPS 文档" },
};

function DeliverablesCard({ items }: { items: Deliverable[] | null }) {
  return (
    <Panel className="h-full lg:col-span-2" innerClassName="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="briefcase" size={15} className="text-gold-400" />
          最近交付物
        </h3>
      </div>
      {items === null ? (
        <p className="text-xs leading-5 text-mist-500">API 离线，无法读取交付物。</p>
      ) : items.length === 0 ? (
        <EmptyState
          icon="briefcase"
          title="暂无交付物"
          hint="在 AI 顾问或 IPS 生成页为客户产出第一份建议书。"
          className="py-8"
        />
      ) : (
        <div className="grid gap-x-8 sm:grid-cols-2">
          {items.map((d) => {
            const meta = KIND_META[d.kind];
            return (
              <Link
                key={`${d.kind}-${d.id}`}
                href={`/deliverables/${d.kind}/${encodeURIComponent(d.id)}`}
                className="group flex items-center gap-3 border-b border-white/[0.05] py-3 transition-colors"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/[0.06] bg-ink-850 text-gold-400">
                  <Icon name={meta.icon} size={14} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-mist-100 transition-colors group-hover:text-gold-300">
                    {d.client}
                  </span>
                  <span className="block truncate text-xs text-mist-500">
                    {meta.label} · {d.sub}
                  </span>
                </span>
                <span className="tnum shrink-0 font-mono text-[11px] text-mist-600">
                  {fmtLocal(d.when)}
                </span>
              </Link>
          );
          })}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// 模块入口
// ---------------------------------------------------------------------------

const MODULES: Array<{
  href: string;
  icon: IconName;
  title: string;
  en: string;
  desc: string;
}> = [
  { href: "/market", icon: "chartUp", title: "市场", en: "Market", desc: "全球行情、跨资产相关性与资本市场预期（CME）" },
  { href: "/optimizer", icon: "pie", title: "组合优化", en: "Optimizer", desc: "MVO · Resampled · Black-Litterman 有效前沿求解" },
  { href: "/retirement", icon: "target", title: "退休规划", en: "Retirement", desc: "GBM 蒙特卡洛两阶段生命周期模拟" },
  { href: "/profiles", icon: "users", title: "客户画像", en: "Profiles", desc: "双轨风险画像与行为金融偏差识别" },
  { href: "/advisor", icon: "sparkle", title: "AI 顾问", en: "Advisor", desc: "DeepSeek 流式生成个性化投资建议书" },
  { href: "/ips", icon: "scroll", title: "IPS 生成", en: "IPS Workflow", desc: "LangGraph 多智能体生成—评审—修订流水线" },
];

function ModuleCard({ mod, index }: { mod: (typeof MODULES)[number]; index: number }) {
  return (
    <Reveal delay={index * 60}>
      <Link href={mod.href} className="group block h-full">
        <Panel
          className="h-full transition-colors duration-500 ease-luxe hover:border-gold-500/30"
          innerClassName="flex h-full flex-col"
        >
          <div className="flex items-start justify-between">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.06] bg-ink-850 text-gold-400 transition-colors duration-500 group-hover:border-gold-500/30">
              <Icon name={mod.icon} size={18} />
            </span>
            <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/[0.06] text-mist-500 transition-all duration-500 ease-luxe group-hover:border-gold-500/40 group-hover:text-gold-300">
              <Icon
                name="arrowUpRight"
                size={13}
                className="transition-transform duration-500 ease-luxe group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
              />
            </span>
          </div>
          <div className="mt-5 font-display text-lg text-mist-100">
            {mod.title}
            <span className="ml-2 align-middle font-sans text-[10px] font-medium tracking-[0.18em] text-mist-600 uppercase">
              {mod.en}
            </span>
          </div>
          <p className="mt-2 text-xs leading-5 text-mist-500">{mod.desc}</p>
        </Panel>
      </Link>
    </Reveal>
  );
}

// ---------------------------------------------------------------------------
// 总览页
// ---------------------------------------------------------------------------

export default async function OverviewPage() {
  const [quotes, profilesData, reportsData, ipsData] = await Promise.all([
    getQuotes(),
    getProfiles(),
    getAdvisorReports(),
    getIpsDocuments(),
  ]);

  const deliverables: Deliverable[] | null =
    reportsData === null && ipsData === null
      ? null
      : [
          ...(reportsData?.reports ?? []).map((r) => ({
            kind: "advisor" as const,
            id: r.report_id,
            client: r.client_name,
            when: r.generated_at,
            sub: `${r.model} · ${r.total_tokens} tokens`,
          })),
          ...(ipsData?.documents ?? []).map((d) => ({
            kind: "ips" as const,
            id: d.document_id,
            client: d.client_name,
            when: d.saved_at,
            sub: `v${d.version} · ${d.status}`,
          })),
        ]
          .sort((a, b) => (a.when < b.when ? 1 : -1))
          .slice(0, 6);

  const dateStr = new Date().toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  });

  const allOffline = !quotes && !profilesData;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-10">
      {/* 页首 */}
      <header className="animate-fade-up">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-gold-500/25 bg-gold-500/[0.07] px-3 py-1 text-[10px] font-medium tracking-[0.22em] text-gold-400 uppercase">
          Private Wealth Workstation
        </div>
        <h1 className="font-display text-4xl leading-tight text-mist-100 md:text-5xl">
          财富驾驶舱
        </h1>
        <p className="font-display mt-3 text-lg text-gold-400 italic">
          The Advisor&apos;s Cockpit
        </p>
        <p className="mt-3 max-w-xl text-sm leading-6 text-mist-500">
          机构级财富管理方法论 × AI
          智能体——从客户画像到投资建议书的完整工作流。
        </p>
        <p className="mt-2 text-xs text-mist-600">{dateStr}</p>
      </header>

      {allOffline && <ApiOffline resource="市场与客户数据" />}

      {/* 市场脉搏 */}
      <PulseTape quotes={quotes?.quotes ?? null} />

      {/* 客户与交付物 */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Reveal>
          <ClientsCard profiles={profilesData?.profiles ?? null} />
        </Reveal>
        <DeliverablesCard items={deliverables} />
      </div>

      {/* 模块入口 */}
      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="font-display text-xl text-mist-100">工作台</h2>
          <span className="text-[10px] tracking-[0.2em] text-mist-600 uppercase">
            Modules
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((mod, i) => (
            <ModuleCard key={mod.href} mod={mod} index={i} />
          ))}
        </div>
      </section>

      <footer className="mt-auto border-t border-white/[0.06] pt-6 text-xs leading-5 text-mist-500">
        AI WealthPilot
        为研究与教育用途的财富管理原型。所有量化输出与 AI
        生成内容基于历史数据与模型假设，不构成投资建议。
      </footer>
    </div>
  );
}
