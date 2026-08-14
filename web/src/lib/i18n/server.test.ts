import { beforeEach, describe, expect, it, vi } from "vitest";
import { getDict, getLocale } from "./server";

// next/headers cookies() is the only server-only dependency — mock it so the
// cookie contract can be tested without a request context.
const cookieGet = vi.fn();
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: cookieGet })),
}));

beforeEach(() => {
  cookieGet.mockReset();
});

describe("getLocale", () => {
  it("defaults to English for new visitors (no cookie)", async () => {
    cookieGet.mockReturnValue(undefined);
    await expect(getLocale()).resolves.toBe("en");
  });

  it("honors a valid wp_locale cookie", async () => {
    cookieGet.mockReturnValue({ value: "zh" });
    await expect(getLocale()).resolves.toBe("zh");
    expect(cookieGet).toHaveBeenCalledWith("wp_locale");
  });

  it("falls back to English for unknown cookie values", async () => {
    cookieGet.mockReturnValue({ value: "fr" });
    await expect(getLocale()).resolves.toBe("en");
  });
});

describe("getDict", () => {
  it("returns the dictionary of the active locale", async () => {
    cookieGet.mockReturnValue({ value: "zh" });
    const t = await getDict();
    expect(t.optimizer.run).toBe("运行优化");

    cookieGet.mockReturnValue(undefined);
    const tEn = await getDict();
    expect(tEn.optimizer.run).toBe("Run Optimization");
  });
});
