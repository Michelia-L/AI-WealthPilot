import { getAdvisorReports, getIpsDocuments, getProfiles } from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import DeliverablesControls from "@/components/deliverables-controls";
import { ApiOffline } from "@/components/api-offline";
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

export const metadata = {
  title: "交付物中心 · AI WealthPilot",
};

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
          eyebrow="Deliverables"
          title="交付物中心"
          description="AI 建议书与 IPS 文档的统一浏览与导出。"
        />
        <ApiOffline resource="交付物列表" />
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
      sub: `v${d.version} · ${d.status} · 修订 ${d.revision_rounds} 轮`,
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
        eyebrow="Deliverables"
        title="交付物中心"
        description="AI 建议书与 IPS 文档的统一浏览与导出 —— 每一次顾问交付，都留痕可查。"
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
            title="没有符合条件的交付物"
            hint="调整筛选条件，或先到 AI 顾问 / IPS 生成页为客户产出交付物。"
          />
        </Panel>
      ) : (
        <Panel pad={false} innerClassName="overflow-hidden">
          <Table className="min-w-[720px]">
            <THead>
              <tr>
                <TH>类型</TH>
                <TH>客户</TH>
                <TH>摘要</TH>
                <TH>时间</TH>
                <TH className="text-right">操作</TH>
              </tr>
            </THead>
            <tbody>
              {rows.map((r) => (
                <TR key={`${r.kind}-${r.id}`}>
                  <TD>
                    <Badge tone={r.kind === "advisor" ? "gold" : "steel"}>
                      {r.kind === "advisor" ? "AI 建议书" : "IPS"}
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
                        查看
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
