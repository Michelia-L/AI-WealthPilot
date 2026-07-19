"use client";

import { cx } from "@/lib/cx";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label?: string;
  className?: string;
}

/** 开关 —— allow_short、ESG 偏好等布尔选项。 */
export default function Toggle({
  checked,
  onChange,
  label,
  className,
}: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={cx("group inline-flex items-center gap-2.5", className)}
    >
      <span
        className={cx(
          "relative h-5 w-9 rounded-full border transition-all duration-300 ease-luxe",
          checked
            ? "border-gold-500/60 bg-gold-500/25"
            : "border-white/15 bg-ink-700/60"
        )}
      >
        <span
          className={cx(
            "absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 rounded-full transition-all duration-300 ease-luxe",
            checked ? "left-[18px] bg-gold-400" : "left-[3px] bg-mist-500"
          )}
        />
      </span>
      {label && (
        <span className="text-xs text-mist-400 transition-colors duration-300 group-hover:text-mist-200">
          {label}
        </span>
      )}
    </button>
  );
}
