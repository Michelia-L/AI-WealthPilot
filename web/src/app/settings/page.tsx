import type { Metadata } from "next";
import { getLlmSettings } from "@/lib/api";
import { altLocale } from "@/lib/i18n/locale";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { ApiOffline } from "@/components/api-offline";
import SettingsForm from "@/components/settings-form";
import SectionHeader from "@/components/ui/section-header";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.settings.title} · AI WealthPilot` };
}

/**
 * Settings — user-defined OpenAI-compatible LLM endpoint. The current
 * effective config is fetched server-side; the form owns fetch-models and
 * save mutations through the same-origin proxy.
 */
export default async function SettingsPage() {
  const [settings, locale] = await Promise.all([getLlmSettings(), getLocale()]);
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow={alt.settings.title}
        title={t.settings.title}
        description={t.settings.description}
        className="mb-8"
      />

      {settings === null ? (
        <ApiOffline resource={t.settings.apiOfflineResource} />
      ) : (
        <SettingsForm initial={settings} />
      )}
    </div>
  );
}
