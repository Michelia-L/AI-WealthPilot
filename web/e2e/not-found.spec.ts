import { expect, test } from "./fixtures";

test("unmatched URL renders the root not-found UI", async ({ page }) => {
  await page.goto("/no-such-page");
  const main = page.getByRole("main");
  await expect(main.getByText("Page not found")).toBeVisible();
  const home = main.getByRole("link", { name: "Back to overview" });
  await expect(home).toBeVisible();
  await home.click();
  await expect(page).toHaveURL(/\/$/);
});
