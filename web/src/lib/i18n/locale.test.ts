import { describe, expect, it } from "vitest";
import {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_COOKIE,
  altLocale,
  isLocale,
} from "./locale";

describe("locale primitives", () => {
  it("declares en/zh with English as the default for new visitors", () => {
    expect(LOCALES).toEqual(["en", "zh"]);
    expect(DEFAULT_LOCALE).toBe("en");
    expect(LOCALE_COOKIE).toBe("wp_locale");
  });

  it("isLocale narrows valid values only", () => {
    expect(isLocale("en")).toBe(true);
    expect(isLocale("zh")).toBe(true);
    expect(isLocale("fr")).toBe(false);
    expect(isLocale("")).toBe(false);
    expect(isLocale(undefined)).toBe(false);
    expect(isLocale(null)).toBe(false);
  });

  it("altLocale flips between the two locales", () => {
    expect(altLocale("en")).toBe("zh");
    expect(altLocale("zh")).toBe("en");
  });
});
