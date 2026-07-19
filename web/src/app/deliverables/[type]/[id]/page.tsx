import { getAdvisorReport, getIpsDocument } from "@/lib/api";
import { fmtLocal } from "@/lib/format";
import Markdown from "@/components/markdown";
import {
  Badge,
  ButtonLink,
  EmptyState,
  Icon,
  Panel,
  SectionHeader,
} from "@/components/ui";

export const metadata = {
  title: "交付物详情 · AI WealthPilot",
};

interface PageProps {
  params: Promise<{ type: string; id: string }>;
}

function NotFound({ reason }: { reason: string }) {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
      <Panel>
        <EmptyState
          icon="warning"
          title="无法打开交付物"
          hint={reason}
          action={<ButtonLink href="/deliverables">返回交付物中心</ButtonLink>}
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
  const { type, id } = await params;

  if (type !== "advisor" && type !== "ips") {
    return <NotFound reason="未知的交付物类型。" />;
  }

  if (type === "advisor") {
    const report = await getAdvisorReport(id);
    if (!report) {
      return <NotFound reason="建议书不存在，或 API 服务离线。" />;
    }
    const encoded = encodeURIComponent(report.report_id);
    return (
      <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
        <SectionHeader
          eyebrow="Advisory Report"
          title={report.client_name}
          description="AI 投资建议书"
          actions={
            <div className="flex items-center gap-2">
              <Badge tone="gold">AI 建议书</Badge>
              <ButtonLink
                href={`/api/advisor/reports/${encoded}/export?format=html`}
                icon="download"
              >
                导出 HTML
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
            <MetaItem label="生成时间" value={fmtLocal(report.generated_at)} />
            <MetaItem label="AI 模型" value={report.model} />
            <MetaItem
              label="Token 用量"
              value={report.total_tokens.toLocaleString()}
            />
            <MetaItem
              label="输入 / 输出"
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
            返回交付物中心
          </ButtonLink>
        </div>
      </div>
    );
  }

  const doc = await getIpsDocument(id);
  if (!doc) {
    return <NotFound reason="IPS 文档不存在，或 API 服务离线。" />;
  }
  const encoded = encodeURIComponent(doc.document_id);

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow="Investment Policy Statement"
        title={doc.client_name}
        description="投资政策声明书（含审计追踪）"
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={doc.status === "approved" ? "jade" : "gold"} dot>
              {doc.status}
            </Badge>
            <ButtonLink href={`/api/ips/${encoded}/pdf`} icon="download">
              下载 PDF
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
          <MetaItem label="版本" value={`v${doc.version}`} />
          <MetaItem
            label="保存时间"
            value={doc.saved_at ? fmtLocal(doc.saved_at) : "—"}
          />
          <MetaItem label="修订轮次" value={String(doc.revision_rounds)} />
          <MetaItem label="风险等级" value={doc.risk_level} />
        </div>
        <div className="px-6 py-6">
          <Markdown>{doc.markdown}</Markdown>
        </div>
      </Panel>

      <div>
        <ButtonLink href="/deliverables" variant="ghost" size="sm">
          返回交付物中心
        </ButtonLink>
      </div>
    </div>
  );
}
