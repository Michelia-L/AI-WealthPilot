"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, useMemo } from "react";
import { dictionaries, type Dictionary } from "@/lib/i18n/dictionaries";
import type { Locale } from "@/lib/i18n/locale";

interface LocaleContextValue {
  locale: Locale;
  /** Dictionary of the active locale. */
  t: Dictionary;
  /** Persist a new locale (cookie via route handler) and re-render the tree. */
  setLocale: (locale: Locale) => void;
}

const LocaleContext = createContext<LocaleContextValue | null>(null);

/**
 * Locale provider — the active locale comes from the root layout (cookie,
 * server-resolved), so first paint and hydration always agree. The dictionary
 * itself is imported here (client-safe module): it contains interpolation
 * functions, which cannot cross the RSC props boundary.
 */
export function LocaleProvider({
  locale,
  children,
}: {
  locale: Locale;
  children: React.ReactNode;
}) {
  const router = useRouter();

  const value = useMemo<LocaleContextValue>(
    () => ({
      locale,
      t: dictionaries[locale],
      setLocale: (next: Locale) => {
        if (next === locale) return;
        void fetch("/api/locale", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ locale: next }),
        }).then(() => router.refresh());
      },
    }),
    [locale, router]
  );

  return (
    <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
  );
}

export function useT(): Dictionary {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useT must be used within LocaleProvider");
  return ctx.t;
}

export function useLocale(): Pick<LocaleContextValue, "locale" | "setLocale"> {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return { locale: ctx.locale, setLocale: ctx.setLocale };
}
