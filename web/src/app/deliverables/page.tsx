import type { Metadata } from "next";
import { getAdvisorReports, getIpsDocuments, getProfiles } from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import DeliverablesControls from "@/components/deliverables-controls";
import { ApiOffline } from "@/components/api-offline";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
import {
  Badge,
  ButtonLink,
  EmptyState,
  Panel,
  SectionHeader,
  Table,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.deliverables.title} · AI WealthPilot` };
}

interface DeliverableRow {
  kind: "advisor" | "ips";
  id: string;
  client: string;
  sub: string;
  when: string;
  viewHref: string;
  downloads: Array<{ label: string; href: string }>;
}

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * 交付物中心（P9）—— 建议书与 IPS 文档的统一浏览：
 * URL 驱动的客户/类型筛选，行内查看与多格式导出。
 */
export default async function DeliverablesPage({ searchParams }: PageProps) {
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];
  const sp = await searchParams;
  const clientFilter = typeof sp.client === "string" ? sp.client : "";
  const typeFilter =
    typeof sp.type === "string" && ["all", "advisor", "ips"].includes(sp.type)
      ? sp.type
      : "all";

  const [reportsData, ipsData, profilesData] = await Promise.all([
    getAdvisorReports(),
    getIpsDocuments(),
    getProfiles(),
  ]);

  if (reportsData === null && ipsData === null) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader
          eyebrow={alt.deliverables.title}
          title={t.deliverables.title}
          description={t.deliverables.descriptionOffline}
        />
        <ApiOffline resource={t.deliverables.resourceList} />
      </div>
    );
  }

  const clientNames = (profilesData?.profiles ?? []).map((p) => p.name);

  const rows: DeliverableRow[] = [
    ...(reportsData?.reports ?? []).map((r) => ({
      kind: "advisor" as const,
      id: r.report_id,
      client: r.client_name,
      sub: `${r.model} · ${r.total_tokens.toLocaleString()} tokens`,
      when: r.generated_at,
      viewHref: `/deliverables/advisor/${encodeURIComponent(r.report_id)}`,
      downloads: [
        {
          label: "PDF",
          href: `/api/advisor/reports/${encodeURIComponent(r.report_id)}/pdf`,
        },
        {
          label: "HTML",
          href: `/api/advisor/reports/${encodeURIComponent(r.report_id)}/export?format=html`,
        },
        {
          label: "MD",
          href: `/api/advisor/reports/${encodeURIComponent(r.report_id)}/export?format=markdown`,
        },
      ],
    })),
    ...(ipsData?.documents ?? []).map((d) => ({
      kind: "ips" as const,
      id: d.document_id,
      client: d.client_name,
      sub: t.deliverables.ipsSub(d.version, d.status, d.revision_rounds),
      when: d.saved_at,
      viewHref: `/deliverables/ips/${encodeURIComponent(d.document_id)}`,
      downloads: [
        {
          label: "PDF",
          href: `/api/ips/${encodeURIComponent(d.document_id)}/pdf`,
        },
        {
          label: "MD",
          href: `/api/ips/${encodeURIComponent(d.document_id)}/export`,
        },
      ],
    })),
  ]
    .filter((r) => typeFilter === "all" || r.kind === typeFilter)
    .filter((r) => !clientFilter || r.client === clientFilter)
    .sort((a, b) => (a.when < b.when ? 1 : -1));

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow={alt.deliverables.title}
        title={t.deliverables.title}
        description={t.deliverables.description}
      />

      <DeliverablesControls
        clients={clientNames}
        client={clientFilter}
        type={typeFilter}
        total={rows.length}
      />

      {rows.length === 0 ? (
        <Panel pad={false}>
          <EmptyState
            icon="briefcase"
            title={t.deliverables.emptyTitle}
            hint={t.deliverables.emptyHint}
          />
        </Panel>
      ) : (
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table className="min-w-[720px]">
            <THead>
              <tr>
                <TH>{t.deliverables.colType}</TH>
                <TH>{t.deliverables.colClient}</TH>
                <TH>{t.deliverables.colSummary}</TH>
                <TH>{t.deliverables.colTime}</TH>
                <TH className="text-right">{t.deliverables.colActions}</TH>
              </tr>
            </THead>
            <tbody>
              {rows.map((r) => (
                <TR key={`${r.kind}-${r.id}`}>
                  <TD>
                    <Badge tone={r.kind === "advisor" ? "gold" : "steel"}>
                      {r.kind === "advisor"
                        ? t.deliverables.kindAdvisor
                        : t.deliverables.kindIps}
                    </Badge>
                  </TD>
                  <TD className="font-medium text-mist-100">{r.client}</TD>
                  <TD className="font-mono text-xs text-mist-400">{r.sub}</TD>
                  <TD className="font-mono text-xs text-mist-500">
                    {fmtLocal(r.when)}
                  </TD>
                  <TD>
                    <div className="flex items-center justify-end gap-1">
                      <ButtonLink
                        href={r.viewHref}
                        variant="ghost"
                        size="sm"
                        icon="eye"
                      >
                        {t.common.view}
                      </ButtonLink>
                      {r.downloads.map((d) => (
                        <ButtonLink
                          key={d.label}
                          href={d.href}
                          variant="ghost"
                          size="sm"
                          icon="download"
                        >
                          {d.label}
                        </ButtonLink>
                      ))}
                    </div>
                  </TD>
                </TR>
              ))}
            </tbody>
          </Table>
        </Panel>
      )}
    </div>
  );
}
