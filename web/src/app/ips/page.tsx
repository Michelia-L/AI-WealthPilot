import type { Metadata } from "next";
import { getAdvisorStatus, getIpsDocuments, getProfiles } from "@/lib/api";
import { altLocale } from "@/lib/i18n/locale";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import IpsWorkspace from "@/components/ips-workspace";
import SectionHeader from "@/components/ui/section-header";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.ips.title} · AI WealthPilot` };
}

/**
 * IPS generation — LangGraph multi-agent workflow as an async task.
 * The page fetches profiles/documents server-side; the workspace creates
 * the task, follows its SSE progress feed, and browses the document library.
 */
export default async function IpsPage() {
  const [profiles, status, documents, locale] = await Promise.all([
    getProfiles(),
    getAdvisorStatus(),
    getIpsDocuments(),
    getLocale(),
  ]);
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow={alt.ips.title}
        title={t.ips.title}
        description={t.ips.description}
      />

      <IpsWorkspace
        profiles={profiles?.profiles ?? null}
        status={status}
        initialDocuments={documents?.documents ?? []}
      />
    </div>
  );
}
