import { cx } from "@/lib/cx";

/** 骨架屏 —— 曜石灰渐变微光扫过。 */
export default function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cx(
        "animate-shimmer rounded-lg bg-[linear-gradient(110deg,var(--color-ink-850)_8%,var(--color-ink-800)_18%,var(--color-ink-850)_33%)] bg-[length:200%_100%]",
        className
      )}
    />
  );
}
