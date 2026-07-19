import { cx } from "@/lib/cx";

export type StatTone = "default" | "gold" | "jade" | "cinnabar";

const TONE_CLASS: Record<StatTone, string> = {
  default: "text-mist-100",
  gold: "text-gold-300",
  jade: "text-jade-300",
  cinnabar: "text-cinnabar-300",
};

interface StatTileProps {
  label: string;
  value: string;
  hint?: string;
  tone?: StatTone;
  className?: string;
}

/** 指标瓷贴 —— 收益率、波动率、夏普率等核心数字。 */
export default function StatTile({
  label,
  value,
  hint,
  tone = "default",
  className,
}: StatTileProps) {
  return (
    <div
      className={cx(
        "rounded-xl border border-white/[0.06] bg-ink-850/50 px-4 py-3.5",
        className
      )}
    >
      <div className="text-[11px] font-medium tracking-[0.12em] text-mist-500 uppercase">
        {label}
      </div>
      <div
        className={cx(
          "tnum mt-1.5 font-mono text-xl leading-none",
          TONE_CLASS[tone]
        )}
      >
        {value}
      </div>
      {hint && <div className="mt-1.5 text-[11px] text-mist-600">{hint}</div>}
    </div>
  );
}
