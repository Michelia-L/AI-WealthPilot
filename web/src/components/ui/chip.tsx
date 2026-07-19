import { cx } from "@/lib/cx";

/** 可选中 Chip —— 表单里的单选/多选标签。 */
export function Chip({
  selected,
  className,
  children,
  type = "button",
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  return (
    <button
      type={type}
      className={cx(
        "rounded-full border px-3.5 py-1.5 text-xs font-medium transition-all duration-300 ease-luxe active:scale-95",
        selected
          ? "border-gold-500/50 bg-gold-500/[0.12] text-gold-300 shadow-[0_0_18px_-6px_rgb(201_164_92/0.45)]"
          : "border-white/10 bg-white/[0.03] text-mist-400 hover:border-white/20 hover:text-mist-200",
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export type BadgeTone = "gold" | "jade" | "cinnabar" | "steel" | "mist";

const TONES: Record<BadgeTone, string> = {
  gold: "border-gold-500/30 bg-gold-500/10 text-gold-300",
  jade: "border-jade-500/30 bg-jade-500/10 text-jade-300",
  cinnabar: "border-cinnabar-500/30 bg-cinnabar-500/10 text-cinnabar-300",
  steel: "border-steel-500/30 bg-steel-500/10 text-steel-300",
  mist: "border-white/10 bg-white/[0.04] text-mist-300",
};

/** 状态徽章 —— 风险等级、缓存状态、文档状态等。 */
export function Badge({
  tone = "mist",
  dot = false,
  className,
  children,
}: {
  tone?: BadgeTone;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium",
        TONES[tone],
        className
      )}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}
