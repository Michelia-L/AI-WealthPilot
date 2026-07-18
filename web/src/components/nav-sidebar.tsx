"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "市场仪表盘", en: "Market Dashboard", icon: "📊" },
  { href: "/optimizer", label: "组合优化器", en: "Portfolio Optimizer", icon: "🧮" },
  { href: "/retirement", label: "退休规划", en: "Retirement", icon: "🎯" },
  { href: "/profiles", label: "客户画像", en: "Profiles", icon: "👤" },
  { href: "/advisor", label: "AI 顾问", en: "AI Advisor", icon: "🤖" },
];

export default function NavSidebar() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1">
      {NAV_ITEMS.map((item) => {
        const active =
          item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors ${
              active
                ? "bg-amber-500/10 font-medium text-amber-300"
                : "text-slate-400 hover:bg-slate-800/60 hover:text-slate-200"
            }`}
          >
            <span aria-hidden>{item.icon}</span>
            <span>{item.label}</span>
            <span className="ml-auto text-[10px] uppercase tracking-wide text-slate-600">
              {item.en}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}
