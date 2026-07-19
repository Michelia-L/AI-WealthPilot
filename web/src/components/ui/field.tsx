import { cx } from "@/lib/cx";
import Icon from "./icon";

const INPUT_BASE =
  "w-full rounded-lg border border-white/[0.08] bg-ink-850/70 px-3 py-2 text-sm text-mist-100 outline-none transition-all duration-300 ease-luxe placeholder:text-mist-600 focus:border-gold-500/45 focus:bg-ink-850 focus:shadow-[0_0_0_3px_rgb(201_164_92/0.12)]";

/** 表单字段容器：标签 + 控件 + 提示。 */
export function Field({
  label,
  hint,
  className,
  children,
}: {
  label?: string;
  hint?: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className={cx("block", className)}>
      {label && (
        <span className="mb-1.5 block text-xs font-medium text-mist-400">
          {label}
        </span>
      )}
      {children}
      {hint && (
        <span className="mt-1 block text-[11px] text-mist-600">{hint}</span>
      )}
    </label>
  );
}

export function Input({
  className,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(INPUT_BASE, className)} {...rest} />;
}

/** 数字输入 —— 等宽数字对齐。 */
export function NumInput({
  className,
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      type="number"
      inputMode="decimal"
      className={cx(INPUT_BASE, "tnum font-mono", className)}
      {...rest}
    />
  );
}

export function Select({
  className,
  children,
  ...rest
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className="relative">
      <select
        className={cx(INPUT_BASE, "appearance-none pr-9", className)}
        {...rest}
      >
        {children}
      </select>
      <Icon
        name="chevronDown"
        size={13}
        className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-mist-500"
      />
    </div>
  );
}

export function Textarea({
  className,
  ...rest
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea className={cx(INPUT_BASE, "min-h-20", className)} {...rest} />
  );
}
