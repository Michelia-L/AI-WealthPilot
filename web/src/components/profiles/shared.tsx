import { Badge } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";

/** 对比选择上限 —— 与 API 的 2–6 限制一致。 */
export const MAX_COMPARE = 6;

/** 风险等级（中英双语字符串）→ Badge 色调：包含匹配，未评估为 mist。 */
export function riskTone(level: string): BadgeTone {
  if (level.includes("保守")) return "steel";
  if (level.includes("稳健")) return "jade";
  if (level.includes("平衡")) return "gold";
  if (level.includes("成长")) return "gold";
  if (level.includes("进取")) return "cinnabar";
  return "mist";
}

/** 风险等级徽章 —— 空字符串按未评估处理（与原 riskChip 语义一致）。 */
export function RiskBadge({ level }: { level: string }) {
  return <Badge tone={riskTone(level)}>{level || "未评估"}</Badge>;
}
