"use client";

import { cx } from "@/lib/cx";

interface TabItem {
  key: string;
  label: React.ReactNode;
}

interface TabsProps {
  tabs: TabItem[];
  active: string;
  onChange: (key: string) => void;
  className?: string;
}

/** 下划线页签 —— 激活态金色刻线 + 微光。 */
export default function Tabs({ tabs, active, onChange, className }: TabsProps) {
  return (
    <div
      role="tablist"
      className={cx("flex items-center gap-1 border-b border-white/[0.07]", className)}
    >
      {tabs.map((t) => (
        <button
          key={t.key}
          role="tab"
          aria-selected={t.key === active}
          onClick={() => onChange(t.key)}
          className={cx(
            "relative px-4 py-2.5 text-sm transition-colors duration-300 ease-luxe",
            t.key === active
              ? "text-gold-300"
              : "text-mist-500 hover:text-mist-200"
          )}
        >
          {t.label}
          {t.key === active && (
            <span className="absolute inset-x-3 -bottom-px h-px bg-gold-400 shadow-[0_0_8px_rgb(201_164_92/0.8)]" />
          )}
        </button>
      ))}
    </div>
  );
}
