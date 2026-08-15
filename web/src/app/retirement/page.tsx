import type { Metadata } from "next";
import RetirementWorkspace from "@/components/retirement-workspace";
import { SectionHeader } from "@/components/ui";
import { getProfiles } from "@/lib/api";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.retirement.title} · AI WealthPilot` };
}

/**
 * Retirement planner — two-phase Monte Carlo (accumulation → distribution).
 * Form → POST → results flow; the workspace owns all interactivity. The
 * profiles list feeds the optional client channel (prefill + risk-level
 * CME suggestion); when the API is unreachable the workspace falls back
 * to the pure manual form.
 */
export default async function RetirementPage() {
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];
  const profiles = await getProfiles();

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow={alt.retirement.title}
        title={t.retirement.title}
        description={t.retirement.description}
      />

      <div className="mt-10">
        <RetirementWorkspace profiles={profiles?.profiles ?? null} />
      </div>
    </div>
  );
}
