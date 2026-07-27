import { en, type Dictionary } from "./en";
import { zh } from "./zh";
import type { Locale } from "../locale";

/**
 * Locale → dictionary map. Client-safe: pure data modules, no server-only
 * imports — `locale-context.tsx` pulls the active dictionary from here so the
 * RSC boundary only ever carries the `locale` string (dictionary values
 * include interpolation functions, which are not serializable as props).
 */
export const dictionaries: Record<Locale, Dictionary> = { en, zh };

export type { Dictionary };
