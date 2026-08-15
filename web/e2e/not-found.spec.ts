import { expect, test } from "@playwright/test";

test("unmatched URL renders the root not-found UI", async ({ page }) => {
  await page.goto("/no-such-page");
  await expect(page.getByText("Page not found")).toBeVisible();
  const home = page.getByRole("link", { name: "Back to overview" });
  await expect(home).toBeVisible();
  await home.click();
  await expect(page).toHaveURL(/\/$/);
});
