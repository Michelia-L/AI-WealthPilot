import { cx } from "@/lib/cx";

interface SectionHeaderProps {
  /** 英文眉标（小药丸） */
  eyebrow: string;
  /** 中文衬线大标题 */
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}

/** 页头 —— 眉标 + 衬线标题 + 可选操作区，全站统一的页面开场。 */
export default function SectionHeader({
  eyebrow,
  title,
  description,
  actions,
  className,
}: SectionHeaderProps) {
  return (
    <div
      className={cx(
        "flex flex-wrap items-end justify-between gap-x-8 gap-y-4",
        className
      )}
    >
      <div>
        <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-gold-500/25 bg-gold-500/[0.07] px-3 py-1 text-[10px] font-medium tracking-[0.22em] text-gold-400 uppercase">
          {eyebrow}
        </div>
        <h1 className="font-display text-3xl leading-tight text-mist-100 md:text-4xl">
          {title}
        </h1>
        {description && (
          <p className="mt-2.5 max-w-2xl text-sm leading-6 text-mist-500">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </div>
  );
}
