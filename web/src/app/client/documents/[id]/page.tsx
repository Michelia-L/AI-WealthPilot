import { notFound } from "next/navigation";
import AcknowledgeDocument from "@/components/client-portal/acknowledge";
import { Allocation } from "@/components/client-portal/sections";
import ClientUnavailable from "@/components/client-portal/unavailable";
import Markdown from "@/components/markdown";
import { Badge, ButtonLink, Panel, SectionHeader } from "@/components/ui";
import { getClientReport } from "@/lib/api/server";
import { fmtUtc } from "@/lib/format";
import { getDict, getLocale } from "@/lib/i18n/server";

export default async function ClientDocumentPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const t = (await getDict()).clientPortal;
  const { id } = await params;
  const { data: report, status } = await getClientReport(id, await getLocale());
  if (status === 404) notFound();
  if (!report) return <ClientUnavailable />;
  const content = report.content;
  const narratives = [
    { heading: t.summary, text: content.summary },
    { heading: t.recommendation, text: content.recommendation },
    { heading: t.riskExplanation, text: content.risk_explanation },
    { heading: t.riskDisclosure, text: content.risk_disclosure },
    ...content.sections,
  ].filter((section) => section.text);
  return (
    <div className="space-y-6">
      <ButtonLink href="/client/documents" size="sm" variant="ghost">
        {t.backDocuments}
      </ButtonLink>
      <SectionHeader
        eyebrow={t.documentTypes[report.type]}
        title={report.title}
        description={t.version(report.version)}
        actions={
          <Badge tone={report.status === "acknowledged" ? "jade" : "gold"}>
            {t.statuses[report.status]}
          </Badge>
        }
      />
      <p className="text-xs leading-6 text-mist-400">
        {t.publishedAt} · {fmtUtc(report.published_at)}
        {report.acknowledged_at && (
          <>
            <br />
            {t.acknowledgedAt} · {fmtUtc(report.acknowledged_at)}
          </>
        )}
      </p>
      {content.allocation.length > 0 && (
        <Panel>
          <h2 className="mb-4 font-display text-xl">{t.targetAllocation}</h2>
          <Allocation allocation={content.allocation} />
        </Panel>
      )}
      {narratives.map((section, index) => (
        <Panel key={index}>
          <h2 className="mb-4 break-words font-display text-xl">
            {section.heading}
          </h2>
          <div className="break-words">
            <Markdown>{section.text}</Markdown>
          </div>
        </Panel>
      ))}
      <Panel>
        <AcknowledgeDocument
          key={report.id}
          id={report.id}
          acknowledged={report.status === "acknowledged"}
        />
      </Panel>
    </div>
  );
}
