import { getAssetClasses } from "@/lib/api";
import { ApiOffline } from "@/components/api-offline";
import OptimizerWorkspace from "@/components/optimizer-workspace";

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
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">
          组合优化器 <span className="text-base font-normal text-slate-400">Portfolio Optimizer</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          均值-方差优化 · 重采样前沿（Michaud）· Black-Litterman 贝叶斯配置
        </p>
      </header>

      {assetClasses ? (
        <OptimizerWorkspace assetClasses={assetClasses.asset_classes} />
      ) : (
        <ApiOffline resource="优化资产宇宙" />
      )}
    </div>
  );
}
