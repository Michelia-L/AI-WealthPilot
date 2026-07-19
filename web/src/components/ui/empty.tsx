import { cx } from "@/lib/cx";
import Icon, { type IconName } from "./icon";

interface EmptyStateProps {
  icon?: IconName;
  title: string;
  hint?: string;
  action?: React.ReactNode;
  className?: string;
}

/** 空态 —— 图标置于双层 bezel 容器内，保持质感一致。 */
export default function EmptyState({
  icon,
  title,
  hint,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cx(
        "flex flex-col items-center justify-center px-6 py-14 text-center",
        className
      )}
    >
      {icon && (
        <div className="mb-4 rounded-2xl border border-white/[0.06] bg-white/[0.02] p-1.5">
          <div className="flex h-11 w-11 items-center justify-center rounded-[calc(1rem-0.375rem)] border border-white/[0.05] bg-ink-850 text-gold-400">
            <Icon name={icon} size={20} />
          </div>
        </div>
      )}
      <div className="text-sm font-medium text-mist-200">{title}</div>
      {hint && (
        <div className="mt-1.5 max-w-sm text-xs leading-5 text-mist-500">
          {hint}
        </div>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
