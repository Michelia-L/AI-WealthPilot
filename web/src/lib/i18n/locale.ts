/** Shared primitives for the self-hosted i18n layer (zero-dependency). */
export const LOCALES = ["en", "zh"] as const;
export type Locale = (typeof LOCALES)[number];

/** New visitors land on English; the choice persists in a cookie. */
export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "wp_locale";

export function isLocale(value: unknown): value is Locale {
  return value === "en" || value === "zh";
}

export function altLocale(locale: Locale): Locale {
  return locale === "en" ? "zh" : "en";
}
