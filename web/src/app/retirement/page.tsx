import RetirementWorkspace from "@/components/retirement-workspace";
import { SectionHeader } from "@/components/ui";

export const metadata = {
  title: "退休规划 · AI WealthPilot",
};

/**
 * Retirement planner — two-phase Monte Carlo (accumulation → distribution).
 * Pure form → POST → results flow; the workspace owns all interactivity.
 */
export default function RetirementPage() {
  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <SectionHeader
        eyebrow="Retirement Planner"
        title="退休规划"
        description="几何布朗运动两阶段蒙特卡洛：积累期持续储蓄注入，支取期按通胀调整提款，评估退休资金的存续概率。"
      />

      <div className="mt-10">
        <RetirementWorkspace />
      </div>
    </div>
  );
}
