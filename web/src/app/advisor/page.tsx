import { getAdvisorReports, getAdvisorStatus, getProfiles } from "@/lib/api";
import AdvisorWorkspace from "@/components/advisor-workspace";
import SectionHeader from "@/components/ui/section-header";

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
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow="AI Advisor"
        title="AI 顾问"
        description="基于客户画像，由 DeepSeek 流式逐字生成个性化投资建议书（IPS 框架 · 行为金融 · 资产配置）。"
        className="mb-8"
      />

      <AdvisorWorkspace
        profiles={profiles?.profiles ?? null}
        status={status}
        initialReports={reports?.reports ?? []}
      />
    </div>
  );
}
