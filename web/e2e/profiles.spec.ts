import { expect, test } from "@playwright/test";

/** Full CRUD over the real SQLite layer — no external services involved. */
test("profile create → list → delete", async ({ page }) => {
  const name = `E2E Client ${Date.now()}`;

  await page.goto("/profiles");
  await page.getByRole("button", { name: "New Profile" }).click();

  await page.getByLabel("Name").fill(name);

  // Submit and wait for the proxied POST to land before asserting on the list
  const created = page.waitForResponse(
    (r) => r.url().includes("/api/profiles") && r.request().method() === "POST"
  );
  await page.getByRole("button", { name: "New Profile" }).last().click();
  await created;

  // List view re-renders after router.refresh() — allow for slow CI runners
  const row = page.getByRole("link", { name });
  await expect(row).toBeVisible({ timeout: 15_000 });

  // Delete it via the confirm dialog (its confirm button is labeled "Delete")
  await page.getByRole("button", { name: `Delete ${name}` }).click();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Delete" })
    .click();
  await expect(page.getByRole("link", { name })).toHaveCount(0, {
    timeout: 15_000,
  });
});
