"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import type { ProfileSummary } from "@/lib/api";
import { cx } from "@/lib/cx";
import ClientSelector from "./client-selector";
import Icon, { type IconName } from "./ui/icon";

const NAV_ITEMS: Array<{
  href: string;
  label: string;
  en: string;
  icon: IconName;
}> = [
  { href: "/", label: "总览", en: "Overview", icon: "gauge" },
  { href: "/market", label: "市场", en: "Market", icon: "chartUp" },
  { href: "/optimizer", label: "组合优化", en: "Optimizer", icon: "pie" },
  { href: "/retirement", label: "退休规划", en: "Retirement", icon: "target" },
  { href: "/profiles", label: "客户画像", en: "Profiles", icon: "users" },
  { href: "/advisor", label: "AI 顾问", en: "Advisor", icon: "sparkle" },
  { href: "/ips", label: "IPS 生成", en: "IPS", icon: "scroll" },
  { href: "/deliverables", label: "交付物", en: "Deliverables", icon: "briefcase" },
  { href: "/monitoring", label: "组合监控", en: "Monitor", icon: "eye" },
];

function Brand() {
  return (
    <Link href="/" className="group flex items-center gap-3">
      <span className="relative flex h-9 w-9 shrink-0 items-center justify-center">
        <span className="absolute inset-0 rotate-45 rounded-[10px] border border-gold-500/40 bg-gradient-to-br from-gold-500/25 to-transparent transition-transform duration-700 ease-luxe group-hover:rotate-[135deg]" />
        <span className="h-1.5 w-1.5 rotate-45 bg-gold-400 shadow-[0_0_10px_rgb(201_164_92/0.9)]" />
      </span>
      <span>
        <span className="block font-display text-[17px] leading-none tracking-wide text-mist-100">
          WealthPilot
        </span>
        <span className="mt-1.5 block text-[9px] font-medium tracking-[0.28em] text-gold-500/80 uppercase">
          AI · Private Wealth
        </span>
      </span>
    </Link>
  );
}

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: (typeof NAV_ITEMS)[number];
  active: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className={cx(
        "group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-300 ease-luxe",
        active
          ? "bg-gold-500/10 text-gold-300"
          : "text-mist-400 hover:bg-white/[0.04] hover:text-mist-100"
      )}
    >
      <Icon
        name={item.icon}
        size={17}
        className={
          active
            ? "text-gold-400"
            : "text-mist-500 transition-colors duration-300 group-hover:text-mist-300"
        }
      />
      <span className="font-medium">{item.label}</span>
      <span
        className={cx(
          "ml-auto text-[9px] tracking-[0.16em] uppercase",
          active ? "text-gold-500/70" : "text-mist-600"
        )}
      >
        {item.en}
      </span>
    </Link>
  );
}

/**
 * 应用外壳 —— 桌面固定侧边栏 + 移动顶栏/抽屉。
 * healthBadge 为服务端渲染插槽，profiles 由根布局注入。
 */
export default function AppShell({
  profiles,
  healthBadge,
  children,
}: {
  profiles: ProfileSummary[];
  healthBadge: React.ReactNode;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // 路由变化时收起移动抽屉（渲染期调整态，React 推荐模式）
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (prevPathname !== pathname) {
    setPrevPathname(pathname);
    setOpen(false);
  }

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <div className="relative z-[1] flex min-h-screen">
      {/* 桌面侧边栏 */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-white/[0.06] bg-ink-950/70 px-5 py-7 backdrop-blur-xl lg:flex">
        <Brand />
        <div className="mt-8">
          <ClientSelector profiles={profiles} />
        </div>
        <nav className="mt-6 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.href} item={item} active={isActive(item.href)} />
          ))}
        </nav>
        <div className="mt-auto pt-6">{healthBadge}</div>
      </aside>

      {/* 移动顶栏（z-50 保持于抽屉之上，汉堡键形变为 X） */}
      <div className="fixed inset-x-0 top-0 z-50 flex h-14 items-center justify-between border-b border-white/[0.06] bg-ink-950/80 px-4 backdrop-blur-xl lg:hidden">
        <Brand />
        <button
          aria-label={open ? "关闭菜单" : "打开菜单"}
          onClick={() => setOpen((v) => !v)}
          className="relative flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-mist-200"
        >
          <span
            className={cx(
              "absolute h-px w-4 bg-current transition-all duration-300 ease-luxe",
              open ? "rotate-45" : "-translate-y-[3.5px]"
            )}
          />
          <span
            className={cx(
              "absolute h-px w-4 bg-current transition-all duration-300 ease-luxe",
              open ? "-rotate-45" : "translate-y-[3.5px]"
            )}
          />
        </button>
      </div>

      {/* 移动抽屉 —— 全屏玻璃覆盖 + 交错入场 */}
      {open && (
        <div className="animate-fade-in fixed inset-0 z-40 bg-ink-950/95 backdrop-blur-2xl lg:hidden">
          <div className="flex h-full flex-col overflow-y-auto px-6 pt-20 pb-8">
            <ClientSelector profiles={profiles} />
            <nav className="mt-6 flex flex-col gap-1.5">
              {NAV_ITEMS.map((item, i) => (
                <div
                  key={item.href}
                  className="animate-fade-up"
                  style={{ animationDelay: `${60 + i * 55}ms` }}
                >
                  <NavLink
                    item={item}
                    active={isActive(item.href)}
                    onNavigate={() => setOpen(false)}
                  />
                </div>
              ))}
            </nav>
            <div className="mt-auto pt-8">{healthBadge}</div>
          </div>
        </div>
      )}

      <main className="min-w-0 flex-1 pt-14 lg:pt-0">{children}</main>
    </div>
  );
}
