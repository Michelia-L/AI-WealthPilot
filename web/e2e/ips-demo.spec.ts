import { expect, test } from "@playwright/test";

/**
 * IPS LangGraph workflow e2e in demo mode: task creation → SSE progress →
 * done event → generated document listed in the library.
 *
 * The replayed fixture takes the selected profile's name, so the library
 * assertion uses the name captured from the picker.
 */
test("ips: demo-mode generation completes and lands in the library", async ({
  page,
}) => {
  await page.goto("/ips");

  // Client picker: capture the selected client's name
  const picker = page.getByRole("combobox", { name: "Profile" });
  const selectedName = (
    (await picker.locator("option:checked").textContent()) ?? ""
  ).split(" (")[0].trim();
  expect(selectedName).toBeTruthy();

  await page.getByRole("button", { name: "Generate IPS" }).click();

  // done event surfaces the archived document banner
  await expect(
    page.getByText(/IPS generated and archived/).first()
  ).toBeVisible({ timeout: 30_000 });

  // …and a row for this client shows up in the library table
  await expect(
    page.getByRole("cell", { name: selectedName }).first()
  ).toBeVisible({ timeout: 15_000 });
});
