import { cookies } from "next/headers";
import { dictionaries, type Dictionary } from "./dictionaries";
import { DEFAULT_LOCALE, isLocale, LOCALE_COOKIE, type Locale } from "./locale";

export { dictionaries };

/**
 * Active UI locale from the request cookie. Server components and route
 * handlers only — client components must use `useT()`/`useLocale()` from
 * `components/locale-context` (or import the dictionaries directly).
 */
export async function getLocale(): Promise<Locale> {
  const store = await cookies();
  const value = store.get(LOCALE_COOKIE)?.value;
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

/** Dictionary for the active locale (server components). */
export async function getDict(): Promise<Dictionary> {
  return dictionaries[await getLocale()];
}
