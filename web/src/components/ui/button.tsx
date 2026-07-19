import Link from "next/link";
import { cx } from "@/lib/cx";
import Icon, { type IconName } from "./icon";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  /** button-in-button：尾部图标嵌在独立圆形内 */
  trailingIcon?: IconName;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-gold-500 text-ink-950 hover:bg-gold-400 shadow-[0_10px_28px_-12px_rgb(201_164_92/0.55)]",
  secondary:
    "border border-white/10 bg-white/[0.04] text-mist-200 hover:border-white/20 hover:bg-white/[0.07]",
  ghost: "text-mist-400 hover:bg-white/[0.05] hover:text-mist-100",
  danger:
    "border border-cinnabar-500/30 bg-cinnabar-500/10 text-cinnabar-300 hover:bg-cinnabar-500/20",
};

const SIZES: Record<Size, string> = {
  sm: "gap-1.5 px-3.5 py-1.5 text-xs",
  md: "gap-2 px-5 py-2.5 text-sm",
  lg: "gap-2.5 px-7 py-3 text-[15px]",
};

export default function Button({
  variant = "primary",
  size = "md",
  icon,
  trailingIcon,
  className,
  children,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cx(
        "group inline-flex items-center justify-center rounded-full font-medium transition-all duration-300 ease-luxe select-none active:scale-[0.97] disabled:pointer-events-none disabled:opacity-45",
        VARIANTS[variant],
        SIZES[size],
        className
      )}
      {...rest}
    >
      {icon && <Icon name={icon} size={size === "sm" ? 13 : 15} />}
      {children}
      {trailingIcon && (
        <span
          className={cx(
            "flex items-center justify-center rounded-full transition-transform duration-300 ease-luxe group-hover:-translate-y-px group-hover:translate-x-0.5",
            size === "sm" ? "h-5 w-5" : "h-6 w-6",
            variant === "primary" ? "bg-ink-950/15" : "bg-white/10"
          )}
        >
          <Icon name={trailingIcon} size={12} />
        </span>
      )}
    </button>
  );
}

interface ButtonLinkProps {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  trailingIcon?: IconName;
  className?: string;
  children: React.ReactNode;
}

/** 链接版按钮 —— 与 Button 同视觉，用于导航场景。 */
export function ButtonLink({
  href,
  variant = "secondary",
  size = "md",
  icon,
  trailingIcon,
  className,
  children,
}: ButtonLinkProps) {
  return (
    <Link
      href={href}
      className={cx(
        "group inline-flex items-center justify-center rounded-full font-medium transition-all duration-300 ease-luxe select-none active:scale-[0.97]",
        VARIANTS[variant],
        SIZES[size],
        className
      )}
    >
      {icon && <Icon name={icon} size={size === "sm" ? 13 : 15} />}
      {children}
      {trailingIcon && (
        <span
          className={cx(
            "flex items-center justify-center rounded-full transition-transform duration-300 ease-luxe group-hover:-translate-y-px group-hover:translate-x-0.5",
            size === "sm" ? "h-5 w-5" : "h-6 w-6",
            variant === "primary" ? "bg-ink-950/15" : "bg-white/10"
          )}
        >
          <Icon name={trailingIcon} size={12} />
        </span>
      )}
    </Link>
  );
}
