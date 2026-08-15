import { expect, test } from "@playwright/test";

/** Client-side validation of the optimizer form — no backend compute. */
test("optimizer: run button guards BL views and the min-2 asset rule", async ({
  page,
}) => {
  await page.goto("/optimizer");

  const run = page.getByRole("button", { name: "Run Optimization" });
  await expect(run).toBeEnabled();

  // Black-Litterman with zero views disables the run button
  await page.getByRole("button", { name: "Black-Litterman" }).click();
  await expect(run).toBeDisabled();

  // Back to classic MVO re-enables it
  await page.getByRole("button", { name: "Classic MVO" }).click();
  await expect(run).toBeEnabled();

  // The asset guard: untoggling is a no-op once only two assets remain —
  // the run button must stay enabled (a valid 2-asset request).
  await page.getByRole("button", { name: "Gold" }).click();
  await page.getByRole("button", { name: "US Aggregate Bonds" }).click();
  await expect(run).toBeEnabled();
  // Two assets left; this click must be rejected by the min-2 guard
  // (selected chips keep their gold style; run stays enabled)
  const intl = page.getByRole("button", {
    name: "International Developed Equities",
  });
  await intl.click();
  await expect(run).toBeEnabled();
  await expect(intl).toHaveClass(/border-gold-500\/50/);
});
