import { cx } from "@/lib/cx";

/** 表单分组 —— 小字眉标 + 控件（label 用 div，避免误触发内部按钮控件）。 */
export default function Group({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cx(className)}>
      <div className="mb-2 text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
        {label}
      </div>
      {children}
    </div>
  );
}
