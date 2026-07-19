import { cx } from "@/lib/cx";

interface PanelProps {
  className?: string;
  /** 内芯容器类名（控制内边距、布局） */
  innerClassName?: string;
  /** 是否使用默认内边距（默认 p-6） */
  pad?: boolean;
  children: React.ReactNode;
}

/**
 * Double-Bezel 双层卡片：外壳托盘（发丝边框 + 微弱底）包裹内芯
 * （曜石面 + 顶部内高光），同心圆角，呈现"玻璃板置于金属托盘"的质感。
 */
export default function Panel({
  className,
  innerClassName,
  pad = true,
  children,
}: PanelProps) {
  return (
    <div
      className={cx(
        "rounded-[1.4rem] border border-white/[0.06] bg-white/[0.02] p-1.5",
        className
      )}
    >
      <div
        className={cx(
          "h-full rounded-[calc(1.4rem-0.375rem)] border border-white/[0.04] bg-ink-900/80 shadow-[inset_0_1px_0_rgb(255_255_255/0.05)]",
          pad && "p-6",
          innerClassName
        )}
      >
        {children}
      </div>
    </div>
  );
}
