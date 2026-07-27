import type { Metadata } from "next";
import { getAdvisorReport, getIpsDocument } from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import Markdown from "@/components/markdown";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
import {
  Badge,
  ButtonLink,
  EmptyState,
  Icon,
  Panel,
  SectionHeader,
} from "@/components/ui";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.deliverableDetail.title} · AI WealthPilot` };
}

interface PageProps {
  params: Promise<{ type: string; id: string }>;
}

function NotFound({
  reason,
  title,
  backLabel,
}: {
  reason: string;
  title: string;
  backLabel: string;
}) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
      <Panel>
        <EmptyState
          icon="warning"
          title={title}
          hint={reason}
          action={<ButtonLink href="/deliverables">{backLabel}</ButtonLink>}
        />
      </Panel>
    </div>
  );
}

/** 元信息行：图标 + 标签 + 值。 */
function MetaItem({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <div className="text-[10px] font-medium tracking-[0.16em] text-mist-600 uppercase">
        {label}
      </div>
      <div className="tnum mt-1 text-sm text-mist-200">{value}</div>
    </div>
  );
}

/**
 * 交付物查看器 —— advisor 建议书与 IPS 文档共用的阅读页，
 * 头部提供多格式导出。
 */
export default async function DeliverableViewerPage({ params }: PageProps) {
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];
  const { type, id } = await params;

  if (type !== "advisor" && type !== "ips") {
    return (
      <NotFound
        reason={t.deliverableDetail.reasonUnknownType}
        title={t.deliverableDetail.notFoundTitle}
        backLabel={t.deliverables.backToCenter}
      />
    );
  }

  if (type === "advisor") {
    const report = await getAdvisorReport(id);
    if (!report) {
      return (
        <NotFound
          reason={t.deliverableDetail.reasonReportMissing}
          title={t.deliverableDetail.notFoundTitle}
          backLabel={t.deliverables.backToCenter}
        />
      );
    }
    const encoded = encodeURIComponent(report.report_id);
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader
          eyebrow={alt.deliverableDetail.reportEyebrow}
          title={report.client_name}
          description={t.deliverableDetail.reportDescription}
          actions={
            <div className="flex items-center gap-2">
              <Badge tone="gold">{t.deliverables.kindAdvisor}</Badge>
              <ButtonLink
                href={`/api/advisor/reports/${encoded}/pdf`}
                icon="download"
              >
                {t.deliverableDetail.downloadPdf}
              </ButtonLink>
              <ButtonLink
                href={`/api/advisor/reports/${encoded}/export?format=html`}
                variant="ghost"
                icon="download"
              >
                HTML
              </ButtonLink>
              <ButtonLink
                href={`/api/advisor/reports/${encoded}/export?format=markdown`}
                variant="ghost"
                icon="download"
              >
                Markdown
              </ButtonLink>
            </div>
          }
        />

        <Panel pad={false}>
          <div className="grid grid-cols-2 gap-4 border-b border-white/[0.06] px-6 py-4 sm:grid-cols-4">
            <MetaItem
              label={t.deliverableDetail.labelGenerated}
              value={fmtLocal(report.generated_at)}
            />
            <MetaItem
              label={t.deliverableDetail.labelModel}
              value={report.model}
            />
            <MetaItem
              label={t.deliverableDetail.labelTokens}
              value={report.total_tokens.toLocaleString()}
            />
            <MetaItem
              label={t.deliverableDetail.labelPromptCompletion}
              value={`${report.prompt_tokens.toLocaleString()} / ${report.completion_tokens.toLocaleString()}`}
            />
          </div>
          {report.notes && (
            <div className="flex items-start gap-2 border-b border-white/[0.06] px-6 py-3 text-xs text-mist-400">
              <Icon name="info" size={13} className="mt-0.5 shrink-0 text-gold-400" />
              {report.notes}
            </div>
          )}
          <div className="px-6 py-6">
            <Markdown>{report.content}</Markdown>
          </div>
        </Panel>

        <div>
          <ButtonLink href="/deliverables" variant="ghost" size="sm">
            {t.deliverables.backToCenter}
          </ButtonLink>
        </div>
      </div>
    );
  }

  const doc = await getIpsDocument(id);
  if (!doc) {
    return (
      <NotFound
        reason={t.deliverableDetail.reasonIpsMissing}
        title={t.deliverableDetail.notFoundTitle}
        backLabel={t.deliverables.backToCenter}
      />
    );
  }
  const encoded = encodeURIComponent(doc.document_id);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow={alt.deliverableDetail.ipsEyebrow}
        title={doc.client_name}
        description={t.deliverableDetail.ipsDescription}
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={doc.status === "approved" ? "jade" : "gold"} dot>
              {doc.status}
            </Badge>
            <ButtonLink href={`/api/ips/${encoded}/pdf`} icon="download">
              {t.deliverableDetail.downloadPdf}
            </ButtonLink>
            <ButtonLink
              href={`/api/ips/${encoded}/export`}
              variant="ghost"
              icon="download"
            >
              Markdown
            </ButtonLink>
          </div>
        }
      />

      <Panel pad={false}>
        <div className="grid grid-cols-2 gap-4 border-b border-white/[0.06] px-6 py-4 sm:grid-cols-4">
          <MetaItem label={t.deliverableDetail.labelVersion} value={`v${doc.version}`} />
          <MetaItem
            label={t.deliverableDetail.labelSaved}
            value={doc.saved_at ? fmtLocal(doc.saved_at) : "—"}
          />
          <MetaItem
            label={t.deliverableDetail.labelRounds}
            value={String(doc.revision_rounds)}
          />
          <MetaItem label={t.deliverableDetail.labelRisk} value={doc.risk_level} />
        </div>
        <div className="px-6 py-6">
          <Markdown>{doc.markdown}</Markdown>
        </div>
      </Panel>

      <div>
        <ButtonLink href="/deliverables" variant="ghost" size="sm">
          {t.deliverables.backToCenter}
        </ButtonLink>
      </div>
    </div>
  );
}
