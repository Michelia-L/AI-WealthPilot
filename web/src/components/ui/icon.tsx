import { cx } from "@/lib/cx";

/**
 * 细线图标体系 —— 取代 emoji。
 * 24×24 viewBox，stroke=currentColor，圆角端点，视觉线宽约 1.4。
 */

export type IconName =
  | "gauge"
  | "chartUp"
  | "pie"
  | "target"
  | "users"
  | "sparkle"
  | "scroll"
  | "arrowUpRight"
  | "arrowRight"
  | "chevronDown"
  | "chevronRight"
  | "plus"
  | "pencil"
  | "trash"
  | "x"
  | "check"
  | "download"
  | "upload"
  | "warning"
  | "info"
  | "menu"
  | "refresh"
  | "clock"
  | "banknote"
  | "shield"
  | "layers"
  | "globe"
  | "briefcase"
  | "sliders"
  | "eye"
  | "dot";

const PATHS: Record<IconName, React.ReactNode> = {
  gauge: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 12l4.2-4.2" />
      <path d="M12 6.6v1.4M6.6 12H8M16 12h1.4" />
    </>
  ),
  chartUp: (
    <>
      <path d="M3.5 16.5l5-5 3.5 3.5 8-8.5" />
      <path d="M14.5 6.5H20V12" />
    </>
  ),
  pie: (
    <>
      <path d="M21 12a9 9 0 1 1-9-9v9h9z" />
      <path d="M14.5 2.6A9 9 0 0 1 21.4 9.5H14.5V2.6z" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.5" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.4" />
      <path d="M2.8 20c.7-3.3 3.2-5.2 6.2-5.2s5.5 1.9 6.2 5.2" />
      <path d="M15.8 4.9a3.4 3.4 0 0 1 0 6.4" />
      <path d="M17.8 15.2c2 .8 3.3 2.4 3.8 4.8" />
    </>
  ),
  sparkle: (
    <>
      <path d="M11 4l1.7 4.8 4.8 1.7-4.8 1.7L11 17l-1.7-4.8-4.8-1.7 4.8-1.7L11 4z" />
      <path d="M18.5 15l.9 2.6 2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6z" />
    </>
  ),
  scroll: (
    <>
      <path d="M7 3.5h10.5v17l-2.6-1.7-2.6 1.7-2.6-1.7L7 20.5v-17z" />
      <path d="M10 8h4.5M10 11.5h4.5M10 15h2.5" />
    </>
  ),
  arrowUpRight: (
    <>
      <path d="M7 17L17 7" />
      <path d="M9 7h8v8" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M4 12h16" />
      <path d="M13 5.5l6.5 6.5-6.5 6.5" />
    </>
  ),
  chevronDown: <path d="M6 9.5l6 6 6-6" />,
  chevronRight: <path d="M9.5 6l6 6-6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  pencil: (
    <path d="M16.8 4a2.1 2.1 0 0 1 3 3L8.5 18.3 4 19.5l1.2-4.5L16.8 4z" />
  ),
  trash: (
    <>
      <path d="M4.5 7h15" />
      <path d="M9.5 7V5.2A1.2 1.2 0 0 1 10.7 4h2.6a1.2 1.2 0 0 1 1.2 1.2V7" />
      <path d="M6.5 7l.9 12a2 2 0 0 0 2 1.9h5.2a2 2 0 0 0 2-1.9l.9-12" />
      <path d="M10.2 11v5.5M13.8 11v5.5" />
    </>
  ),
  x: <path d="M6 6l12 12M18 6L6 18" />,
  check: <path d="M4.5 12.5l5 5 10-11" />,
  download: (
    <>
      <path d="M12 4v11" />
      <path d="M6.5 10.5L12 16l5.5-5.5" />
      <path d="M4 20h16" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15V4" />
      <path d="M6.5 8.5L12 3l5.5 5.5" />
      <path d="M4 20h16" />
    </>
  ),
  warning: (
    <>
      <path d="M12 3.8L21.5 20h-19L12 3.8z" />
      <path d="M12 10v4.5" />
      <path d="M12 17.4h.01" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.2" />
      <path d="M12 7.6h.01" />
    </>
  ),
  menu: <path d="M4 7.5h16M4 16.5h16" />,
  refresh: (
    <>
      <path d="M20 12a8 8 0 1 1-2.34-5.66" />
      <path d="M20 3.5V8h-4.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3.5 2" />
    </>
  ),
  banknote: (
    <>
      <rect x="2.5" y="7" width="19" height="10" rx="2" />
      <circle cx="12" cy="12" r="2.6" />
      <path d="M6 12h.01M18 12h.01" />
    </>
  ),
  shield: (
    <>
      <path d="M12 2.8l7.5 2.8v5.7c0 4.7-3.2 7.9-7.5 9.7-4.3-1.8-7.5-5-7.5-9.7V5.6L12 2.8z" />
      <path d="M9 11.8l2.2 2.2 4-4.2" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3.2l8.8 4.9-8.8 4.9L3.2 8.1 12 3.2z" />
      <path d="M3.2 13.4l8.8 4.9 8.8-4.9" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17" />
      <path d="M12 3.5c2.4 2.3 3.7 5.2 3.7 8.5s-1.3 6.2-3.7 8.5c-2.4-2.3-3.7-5.2-3.7-8.5s1.3-6.2 3.7-8.5z" />
    </>
  ),
  briefcase: (
    <>
      <rect x="3" y="7.5" width="18" height="12.5" rx="2.5" />
      <path d="M9 7.5V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.5" />
      <path d="M3 12.5h18" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7.5h16M4 16.5h16" />
      <circle cx="9.5" cy="7.5" r="2" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="16.5" r="2" fill="currentColor" stroke="none" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  dot: <circle cx="12" cy="12" r="4" fill="currentColor" stroke="none" />,
};

interface IconProps {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
}

export default function Icon({
  name,
  size = 16,
  strokeWidth = 1.4,
  className,
}: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className={cx("shrink-0", className)}
    >
      {PATHS[name]}
    </svg>
  );
}
