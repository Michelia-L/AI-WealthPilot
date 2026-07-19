import { getAssetClasses } from "@/lib/api";
import { ApiOffline } from "@/components/api-offline";
import OptimizerWorkspace from "@/components/optimizer-workspace";
import SectionHeader from "@/components/ui/section-header";

export const metadata = {
  title: "组合优化器 · AI WealthPilot",
};

/**
 * Portfolio Optimizer page. The workspace is a client component — form
 * state is inherently interactive, and the run button POSTs through the
 * same-origin proxy route.
 */
export default async function OptimizerPage() {
  const assetClasses = await getAssetClasses();

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <SectionHeader
        eyebrow="Portfolio Optimizer"
        title="组合优化器"
        description="均值-方差优化（MVO）、Michaud 重采样前沿与 Black-Litterman 贝叶斯配置，求解有效前沿上的最优资产组合。"
      />

      {assetClasses ? (
        <OptimizerWorkspace assetClasses={assetClasses.asset_classes} />
      ) : (
        <ApiOffline resource="优化资产宇宙" />
      )}
    </div>
  );
}
