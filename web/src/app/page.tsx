import Link from "next/link";
import {
  getAdvisorReports,
  getIpsDocuments,
  getMonitoringFleetStatus,
  getProfiles,
  getQuotes,
  type MonitoringFleetResponse,
  type ProfileSummary,
  type Quote,
} from "@/lib/api";
import { cx } from "@/lib/cx";
import { formatAssetPrice, fmtLocal } from "@/lib/format";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
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
    pct === null ? "text-mist-500" : pct > 0 ? "text-rise" : pct < 0 ? "text-fall" : "text-mist-400";
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
// 组合监控告警（Phase 17 — 越带亮灯，懒触发日检）
// ---------------------------------------------------------------------------

async function MonitoringBanner({ fleet }: { fleet: MonitoringFleetResponse }) {
  const t = await getDict();
  const { summary } = fleet;
  const priceAsOf = fleet.price_as_of ?? "—";

  if (summary.breach > 0) {
    const worst = fleet.items
      .filter((i) => i.status === "breach")
      .sort(
        (a, b) => (b.max_abs_drift_pp ?? 0) - (a.max_abs_drift_pp ?? 0)
      );
    const offenders = worst
      .slice(0, 2)
      .map((w) =>
        t.overview.monitoringOffender(
          w.client_name,
          (w.max_abs_drift_pp ?? 0) * 100
        )
      )
      .join(" · ");
    return (
      <Link
        href={`/monitoring?doc=${encodeURIComponent(worst[0].document_id)}`}
        className="group block"
      >
        <div className="flex items-center gap-4 rounded-2xl border border-cinnabar-500/30 bg-cinnabar-500/[0.06] px-5 py-3.5 transition-colors duration-500 ease-luxe hover:border-cinnabar-500/50">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cinnabar-500/30 bg-cinnabar-500/10 text-cinnabar-400">
            <Icon name="warning" size={16} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-sm text-mist-100">
              {t.overview.monitoringBreachTitle(summary.breach)}
              <span className="ml-2 text-xs text-mist-500">{offenders}</span>
            </p>
            <p className="mt-0.5 text-xs text-mist-500">
              {t.overview.monitoringBreachHint(priceAsOf)}
            </p>
          </div>
          <Icon
            name="arrowRight"
            size={15}
            className="shrink-0 text-cinnabar-400/70 transition-transform duration-500 ease-luxe group-hover:translate-x-0.5"
          />
        </div>
      </Link>
    );
  }

  if (summary.ok > 0) {
    return (
      <div className="flex items-center gap-3 rounded-2xl border border-jade-500/20 bg-jade-500/[0.04] px-5 py-2.5">
        <Icon name="shield" size={14} className="shrink-0 text-jade-400" />
        <p className="text-xs text-mist-400">
          {t.overview.monitoringOk(summary.ok)}
          {summary.unknown > 0 && (
            <span className="text-mist-600">
              {t.overview.monitoringUnknown(summary.unknown)}
            </span>
          )}
        </p>
        <span className="tnum ml-auto shrink-0 font-mono text-[11px] text-mist-600">
          {t.overview.monitoringAsOf(priceAsOf)}
        </span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-3 rounded-2xl border border-white/[0.06] bg-ink-900/70 px-5 py-2.5">
      <Icon name="info" size={14} className="shrink-0 text-mist-500" />
      <p className="text-xs text-mist-500">
        {t.overview.monitoringUnavailable}
        {fleet.items[0]?.note ? `：${fleet.items[0].note}` : ""}
      </p>
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

async function ClientsCard({
  profiles,
}: {
  profiles: ProfileSummary[] | null;
}) {
  const t = await getDict();
  return (
    <Panel className="h-full" innerClassName="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="users" size={15} className="text-gold-400" />
          {t.overview.clientsTitle}
        </h3>
        <Link
          href="/profiles"
          className="group flex items-center gap-1 text-xs text-mist-500 transition-colors hover:text-gold-300"
        >
          {t.overview.clientsManage}
          <Icon
            name="arrowUpRight"
            size={12}
            className="transition-transform duration-300 ease-luxe group-hover:-translate-y-px group-hover:translate-x-px"
          />
        </Link>
      </div>
      {profiles === null ? (
        <p className="text-xs leading-5 text-mist-500">{t.overview.clientsOffline}</p>
      ) : profiles.length === 0 ? (
        <EmptyState
          icon="users"
          title={t.overview.clientsEmptyTitle}
          hint={t.overview.clientsEmptyHint}
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
                  <div className="text-xs text-mist-500">{t.overview.clientAge(p.age)}</div>
                </div>
                <Badge tone={riskTone(p.risk_level)}>
                  {p.risk_level.split("/")[0].trim()}
                </Badge>
              </Link>
            ))}
          </div>
          <div className="mt-auto pt-3 text-xs text-mist-600">
            {t.overview.clientsTotal(profiles.length)}
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

const KIND_ICON: Record<Deliverable["kind"], IconName> = {
  advisor: "sparkle",
  ips: "scroll",
};

async function DeliverablesCard({ items }: { items: Deliverable[] | null }) {
  const t = await getDict();
  const kindLabel: Record<Deliverable["kind"], string> = {
    advisor: t.overview.kindAdvisor,
    ips: t.overview.kindIps,
  };
  return (
    <Panel className="h-full" innerClassName="flex h-full flex-col">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-medium text-mist-200">
          <Icon name="briefcase" size={15} className="text-gold-400" />
          {t.overview.deliverablesTitle}
        </h3>
      </div>
      {items === null ? (
        <p className="text-xs leading-5 text-mist-500">{t.overview.deliverablesOffline}</p>
      ) : items.length === 0 ? (
        <EmptyState
          icon="briefcase"
          title={t.overview.deliverablesEmptyTitle}
          hint={t.overview.deliverablesEmptyHint}
          className="py-8"
        />
      ) : (
        <div className="grid gap-x-8 sm:grid-cols-2">
          {items.map((d) => (
            <Link
              key={`${d.kind}-${d.id}`}
              href={`/deliverables/${d.kind}/${encodeURIComponent(d.id)}`}
              className="group flex items-center gap-3 border-b border-white/[0.05] py-3 transition-colors"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/[0.06] bg-ink-850 text-gold-400">
                <Icon name={KIND_ICON[d.kind]} size={14} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm text-mist-100 transition-colors group-hover:text-gold-300">
                  {d.client}
                </span>
                <span className="block truncate text-xs text-mist-500">
                  {kindLabel[d.kind]} · {d.sub}
                </span>
              </span>
              <span className="tnum shrink-0 font-mono text-[11px] text-mist-600">
                {fmtLocal(d.when)}
              </span>
            </Link>
          ))}
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// 模块入口
// ---------------------------------------------------------------------------

interface ModuleEntry {
  href: string;
  icon: IconName;
  title: string;
  /** 另一语言的小字标签（沿用全站双语品牌层）。 */
  alt: string;
  desc: string;
}

function ModuleCard({ mod, index }: { mod: ModuleEntry; index: number }) {
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
              {mod.alt}
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
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];

  const [quotes, profilesData, reportsData, ipsData, fleetData] =
    await Promise.all([
      getQuotes(),
      getProfiles(),
      getAdvisorReports(),
      getIpsDocuments(),
      getMonitoringFleetStatus(locale),
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

  const dateStr = new Date().toLocaleDateString(
    locale === "zh" ? "zh-CN" : "en-US",
    {
      year: "numeric",
      month: "long",
      day: "numeric",
      weekday: "long",
    }
  );

  const modules: ModuleEntry[] = [
    { href: "/market", icon: "chartUp", title: t.overview.modules.market.title, alt: alt.overview.modules.market.title, desc: t.overview.modules.market.desc },
    { href: "/optimizer", icon: "pie", title: t.overview.modules.optimizer.title, alt: alt.overview.modules.optimizer.title, desc: t.overview.modules.optimizer.desc },
    { href: "/retirement", icon: "target", title: t.overview.modules.retirement.title, alt: alt.overview.modules.retirement.title, desc: t.overview.modules.retirement.desc },
    { href: "/profiles", icon: "users", title: t.overview.modules.profiles.title, alt: alt.overview.modules.profiles.title, desc: t.overview.modules.profiles.desc },
    { href: "/advisor", icon: "sparkle", title: t.overview.modules.advisor.title, alt: alt.overview.modules.advisor.title, desc: t.overview.modules.advisor.desc },
    { href: "/ips", icon: "scroll", title: t.overview.modules.ips.title, alt: alt.overview.modules.ips.title, desc: t.overview.modules.ips.desc },
  ];

  const allOffline = !quotes && !profilesData;

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-10">
      {/* 页首 */}
      <header className="animate-fade-up">
        <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-gold-500/25 bg-gold-500/[0.07] px-3 py-1 text-[10px] font-medium tracking-[0.22em] text-gold-400 uppercase">
          Private Wealth Workstation
        </div>
        <h1 className="font-display text-4xl leading-tight text-mist-100 md:text-5xl">
          {t.overview.title}
        </h1>
        <p className="font-display mt-3 text-lg text-gold-400 italic">
          {alt.overview.title}
        </p>
        <p className="mt-3 max-w-xl text-sm leading-6 text-mist-500">
          {t.overview.tagline}
        </p>
        <p className="mt-2 text-xs text-mist-600">{dateStr}</p>
      </header>

      {allOffline && <ApiOffline resource={t.overview.offlineResource} />}

      {/* 市场脉搏 */}
      <PulseTape quotes={quotes?.quotes ?? null} />

      {/* 组合监控告警 */}
      {fleetData !== null && fleetData.summary.total > 0 && (
        <Reveal>
          <MonitoringBanner fleet={fleetData} />
        </Reveal>
      )}

      {/* 客户与交付物 */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Reveal>
          <ClientsCard profiles={profilesData?.profiles ?? null} />
        </Reveal>
        <Reveal delay={60} className="lg:col-span-2">
          <DeliverablesCard items={deliverables} />
        </Reveal>
      </div>

      {/* 模块入口 */}
      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="font-display text-xl text-mist-100">{t.overview.workbenchTitle}</h2>
          <span className="text-[10px] tracking-[0.2em] text-mist-600 uppercase">
            {alt.overview.workbenchTitle}
          </span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {modules.map((mod, i) => (
            <ModuleCard key={mod.href} mod={mod} index={i} />
          ))}
        </div>
      </section>

      <footer className="mt-auto border-t border-white/[0.06] pt-6 text-xs leading-5 text-mist-500">
        {t.overview.disclaimer}
      </footer>
    </div>
  );
}
