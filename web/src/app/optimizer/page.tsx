import type { Metadata } from "next";
import { getAssetClasses } from "@/lib/api";
import { ApiOffline } from "@/components/api-offline";
import OptimizerWorkspace from "@/components/optimizer-workspace";
import SectionHeader from "@/components/ui/section-header";
import { dictionaries, getDict, getLocale } from "@/lib/i18n/server";
import { altLocale } from "@/lib/i18n/locale";
import { parseOptimizerDeepLink } from "@/lib/optimizer-link";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getDict();
  return { title: `${t.optimizer.title} · AI WealthPilot` };
}

interface PageProps {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}

/**
 * Portfolio Optimizer page. The workspace is a client component — form
 * state is inherently interactive, and the run button POSTs through the
 * same-origin proxy route.
 * ?assets=KEY1,KEY2（如从监控页联动跳入）预填资产选择；
 * ?method=surplus&source=retirement&ytr=…&dy=…&income=…（退休页 LDI 联动）
 * 预填盈余优化退休收入流通道。
 */
export default async function OptimizerPage({ searchParams }: PageProps) {
  const sp = await searchParams;
  const assetClasses = await getAssetClasses();
  const locale = await getLocale();
  const t = dictionaries[locale];
  const alt = dictionaries[altLocale(locale)];

  const initialAssets =
    assetClasses && typeof sp.assets === "string"
      ? sp.assets
          .split(",")
          .filter((k) => k in assetClasses.asset_classes)
      : undefined;
  const deepLink = parseOptimizerDeepLink(sp);

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow={alt.optimizer.title}
        title={t.optimizer.title}
        description={t.optimizer.description}
      />

      {assetClasses ? (
        <OptimizerWorkspace
          assetClasses={assetClasses.asset_classes}
          initialAssets={
            initialAssets && initialAssets.length >= 2 ? initialAssets : undefined
          }
          deepLink={deepLink}
        />
      ) : (
        <ApiOffline resource={t.optimizer.assetUniverse} />
      )}
    </div>
  );
}
