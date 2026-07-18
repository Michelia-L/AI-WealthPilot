import { getAdvisorReports, getAdvisorStatus, getProfiles } from "@/lib/api";
import AdvisorWorkspace from "@/components/advisor-workspace";

export const metadata = {
  title: "AI 顾问 · AI WealthPilot",
};

/**
 * AI Advisor — streaming advisory reports over a selected client profile.
 * List/status fetch server-side; the workspace owns the SSE stream,
 * save-to-library, and the report history.
 */
export default async function AdvisorPage() {
  const [profiles, status, reports] = await Promise.all([
    getProfiles(),
    getAdvisorStatus(),
    getAdvisorReports(),
  ]);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">
          AI 顾问 <span className="text-base font-normal text-slate-400">AI Advisor</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          基于客户画像的流式投资建议书（IPS 框架 · 行为金融 · 资产配置）
        </p>
      </header>

      <AdvisorWorkspace
        profiles={profiles?.profiles ?? null}
        status={status}
        initialReports={reports?.reports ?? []}
      />
    </div>
  );
}
