import { cx } from "@/lib/cx";

/** 数据表原语 —— 统一发丝边框与等宽数字。THead 内使用原生 <tr>。 */
export function Table({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cx("overflow-x-auto", className)}>
      <table className="w-full border-collapse text-left text-sm">
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: React.ReactNode }) {
  return (
    <thead className="text-[11px] font-medium tracking-[0.14em] text-mist-500 uppercase">
      {children}
    </thead>
  );
}

export function TH({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return <th className={cx("px-4 py-3 font-medium", className)}>{children}</th>;
}

export function TR({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <tr
      className={cx(
        "border-t border-white/[0.05] transition-colors duration-300 hover:bg-white/[0.02]",
        className
      )}
    >
      {children}
    </tr>
  );
}

export function TD({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <td className={cx("tnum px-4 py-3 text-mist-200", className)}>{children}</td>
  );
}
