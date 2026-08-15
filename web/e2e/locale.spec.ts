import { expect, test } from "@playwright/test";

test("locale switcher toggles zh/en and persists via cookie", async ({
  page,
  context,
}) => {
  await page.goto("/");
  // Default locale is English
  await expect(
    page.getByRole("link", { name: "Overview" }).first()
  ).toBeVisible();

  // Switch to Chinese via the sidebar segmented control
  await page.getByRole("button", { name: "中文" }).first().click();
  await expect(page.getByRole("link", { name: "总览" }).first()).toBeVisible();

  const cookies = await context.cookies();
  expect(cookies.find((c) => c.name === "wp_locale")?.value).toBe("zh");

  // Persists across reload
  await page.reload();
  await expect(page.getByRole("link", { name: "总览" }).first()).toBeVisible();

  // Switch back to English
  await page.getByRole("button", { name: "EN" }).first().click();
  await expect(
    page.getByRole("link", { name: "Overview" }).first()
  ).toBeVisible();
});
