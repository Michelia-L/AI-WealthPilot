import type { Metadata } from "next";
import { getAdvisorReports, getAdvisorStatus, getProfiles } from "@/lib/api";
import { altLocale } from "@/lib/i18n/locale";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import AdvisorWorkspace from "@/components/advisor-workspace";
import SectionHeader from "@/components/ui/section-header";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.advisor.title} · AI WealthPilot` };
}

/**
 * AI Advisor — streaming advisory reports over a selected client profile.
 * List/status fetch server-side; the workspace owns the SSE stream,
 * save-to-library, and the report history.
 */
export default async function AdvisorPage() {
  const [profiles, status, reports, locale] = await Promise.all([
    getProfiles(),
    getAdvisorStatus(),
    getAdvisorReports(),
    getLocale(),
  ]);
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow={alt.advisor.title}
        title={t.advisor.title}
        description={t.advisor.description}
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
