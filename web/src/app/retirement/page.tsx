import RetirementWorkspace from "@/components/retirement-workspace";

export const metadata = {
  title: "退休规划 · AI WealthPilot",
};

/**
 * Retirement planner — two-phase Monte Carlo (accumulation → distribution).
 * Pure form → POST → results flow; the workspace owns all interactivity.
 */
export default function RetirementPage() {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold tracking-tight text-slate-50">
          退休规划 <span className="text-base font-normal text-slate-400">Retirement Planner</span>
        </h1>
        <p className="mt-1 text-sm text-slate-400">
          几何布朗运动两阶段蒙特卡洛：积累期储蓄注入 → 支取期通胀调整提款
        </p>
      </header>

      <RetirementWorkspace />
    </div>
  );
}
