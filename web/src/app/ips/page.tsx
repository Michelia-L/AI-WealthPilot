import { getAdvisorStatus, getIpsDocuments, getProfiles } from "@/lib/api";
import IpsWorkspace from "@/components/ips-workspace";

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
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">
          IPS 生成 <span className="text-base font-normal text-slate-400">Investment Policy Statement</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          多智能体工作流：CME 注入 → 初稿 → 适当性/合规/一致性三维评审 → SAA 量化验证 → 修订定稿
        </p>
      </header>

      <IpsWorkspace
        profiles={profiles?.profiles ?? null}
        status={status}
        initialDocuments={documents?.documents ?? []}
      />
    </div>
  );
}
