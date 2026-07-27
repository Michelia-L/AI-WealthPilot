import { Badge } from "@/components/ui";
import type { BadgeTone } from "@/components/ui";
import type { Locale } from "@/lib/i18n/locale";

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

/**
 * risk_level 为 "English / 中文" 双语数据串，按当前语言取对应一半；
 * 空值或「未评估」回退为本地化的未评估文案。
 */
export function localizedRiskLabel(
  level: string,
  locale: Locale,
  unassessed: string
): string {
  if (!level || level === "未评估") return unassessed;
  return level.split(" / ")[locale === "zh" ? 1 : 0] ?? level;
}

/** 风险等级徽章 —— 空字符串按未评估处理（与原 riskChip 语义一致）。 */
export function RiskBadge({
  level,
  locale,
  unassessed,
}: {
  level: string;
  locale: Locale;
  unassessed: string;
}) {
  return (
    <Badge tone={riskTone(level)}>
      {localizedRiskLabel(level, locale, unassessed)}
    </Badge>
  );
}
