import { getAdvisorStatus, getIpsDocuments, getProfiles } from "@/lib/api";
import IpsWorkspace from "@/components/ips-workspace";
import SectionHeader from "@/components/ui/section-header";

export const metadata = {
  title: "IPS 生成 · AI WealthPilot",
};

/**
 * IPS generation — LangGraph multi-agent workflow as an async task.
 * The page fetches profiles/documents server-side; the workspace creates
 * the task, follows its SSE progress feed, and browses the document library.
 */
export default async function IpsPage() {
  const [profiles, status, documents] = await Promise.all([
    getProfiles(),
    getAdvisorStatus(),
    getIpsDocuments(),
  ]);

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow="IPS Workflow"
        title="IPS 生成"
        description="LangGraph 多智能体工作流：注入资本市场预期后生成初稿，经适当性、合规、一致性三维评审与 SAA 量化验证，自动修订直至定稿入库。"
      />

      <IpsWorkspace
        profiles={profiles?.profiles ?? null}
        status={status}
        initialDocuments={documents?.documents ?? []}
      />
    </div>
  );
}
