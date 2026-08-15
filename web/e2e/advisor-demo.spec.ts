import { expect, test } from "@playwright/test";

/**
 * Crown-jewel e2e: the advisor SSE pipeline end to end — browser → same-origin
 * proxy → FastAPI (demo fixture replay) → streamed report rendered back in the
 * workspace. No network, no API key.
 *
 * The fixture's fictional client name is substituted with the selected
 * profile's name at replay, so assertions target fixture-invariant text.
 */
test("advisor: demo-mode report streams and renders", async ({ page }) => {
  await page.goto("/advisor");

  // Demo-mode banner is visible
  await expect(page.getByText(/demo mode/i).first()).toBeVisible();

  // Capture the selected client's name — the replayed report carries it
  const clientSelect = page.getByRole("combobox", { name: "Client" });
  const selectedName = (
    (await clientSelect.locator("option:checked").textContent()) ?? ""
  ).split(" (")[0].trim();

  await page.getByRole("button", { name: "Generate Proposal" }).click();

  // The fixture report streams in: heading + demo marker + client name
  // (name appears in the report body; <option> copies stay hidden).
  const report = page.getByRole("heading", { name: "投资咨询建议书" });
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/演示样例，内容为虚构/).first()).toBeVisible();
  if (selectedName) {
    await expect(
      page
        .getByText(new RegExp(selectedName))
        .filter({ visible: true })
        .first()
    ).toBeVisible();
  }
});
