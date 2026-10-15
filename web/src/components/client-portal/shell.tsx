"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useT } from "@/components/locale-context";
import LocaleSwitcher from "@/components/locale-switcher";
import Icon, { type IconName } from "@/components/ui/icon";
import { cx } from "@/lib/cx";

const links: {
  href: string;
  key: "overview" | "portfolio" | "goals" | "risk" | "documents" | "ai";
  icon: IconName;
}[] = [
  { href: "/client", key: "overview", icon: "gauge" },
  { href: "/client/portfolio", key: "portfolio", icon: "pie" },
  { href: "/client/goals", key: "goals", icon: "target" },
  { href: "/client/risk-profile", key: "risk", icon: "shield" },
  { href: "/client/documents", key: "documents", icon: "scroll" },
  { href: "/client/ai", key: "ai", icon: "sparkle" },
];

export default function ClientPortalShell({
  children,
  sessionControls,
  isDemo,
}: {
  children: React.ReactNode;
  sessionControls: React.ReactNode;
  isDemo: boolean;
}) {
  const pathname = usePathname();
  const t = useT().clientPortal;
  return (
    <div className="relative z-[1] flex min-h-screen flex-col">
      <header className="border-b border-white/[0.06] bg-ink-950/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-5 py-5 sm:px-8">
          <Link
            href="/client"
            className="flex items-center gap-3 text-gold-300"
          >
            <Icon name="shield" size={25} />
            <span>
              <span className="block font-display text-xl text-mist-100">
                WealthPilot
              </span>
              <span className="text-xs tracking-widest">{t.name}</span>
            </span>
          </Link>
          <div className="flex flex-wrap items-center gap-5">
            <LocaleSwitcher />
            {sessionControls}
          </div>
        </div>
        <nav
          aria-label={t.navLabel}
          className="mx-auto grid max-w-6xl grid-cols-3 gap-1 px-4 sm:flex sm:overflow-x-auto sm:px-7"
        >
          {links.map(({ href, key, icon }) => {
            const active =
              href === "/client"
                ? pathname === href
                : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cx(
                    "flex shrink-0 items-center justify-center gap-1.5 border-b-2 px-1 py-3 text-xs whitespace-nowrap transition-colors sm:justify-start sm:gap-2 sm:px-4 sm:py-4 sm:text-sm",
                  active
                    ? "border-gold-400 text-gold-300"
                    : "border-transparent text-mist-400 hover:text-mist-100",
                )}
              >
                <Icon name={icon} size={16} />
                {t.nav[key]}
              </Link>
            );
          })}
        </nav>
      </header>
      {isDemo && (
        <p className="border-b border-gold-500/20 bg-gold-500/[0.06] px-5 py-2 text-center text-xs text-gold-300">
          {t.demo}
        </p>
      )}
      <main
        id="client-content"
        className="mx-auto w-full max-w-6xl flex-1 px-5 py-8 sm:px-8 sm:py-12"
      >
        {children}
      </main>
      <footer className="mx-auto w-full max-w-6xl border-t border-white/[0.06] px-5 py-6 text-xs leading-6 text-mist-400 sm:px-8">
        {t.disclaimer}
      </footer>
    </div>
  );
}
