"use client";

import { cx } from "@/lib/cx";

interface SegmentedOption<T> {
  value: T;
  label: React.ReactNode;
}

interface SegmentedProps<T extends string | number> {
  options: ReadonlyArray<SegmentedOption<T>>;
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
  className?: string;
}

/** 分段选择器 —— 周期、方法、目标函数等短选项切换。 */
export default function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  size = "md",
  className,
}: SegmentedProps<T>) {
  return (
    <div
      className={cx(
        "inline-flex items-center gap-0.5 rounded-full border border-white/[0.08] bg-ink-850/80 p-1",
        className
      )}
    >
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          onClick={() => onChange(o.value)}
          className={cx(
            "rounded-full font-medium transition-all duration-300 ease-luxe",
            size === "sm"
              ? "px-3 py-1 text-[11px]"
              : "px-3.5 py-1.5 text-xs",
            o.value === value
              ? "bg-gold-500/15 text-gold-300 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]"
              : "text-mist-500 hover:text-mist-200"
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
