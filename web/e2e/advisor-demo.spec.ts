import { expect, test } from "@playwright/test";

/**
 * Crown-jewel e2e: the advisor SSE pipeline end to end — browser → same-origin
 * proxy → FastAPI (demo fixture replay) → streamed report rendered back in the
 * workspace. No network, no API key.
 *
 * Demo fixtures are locale-aware: the default English locale replays the
 * English fixture; after switching to 中文 the Chinese fixture replays. The
 * fixture's fictional client name is substituted with the selected profile's
 * name at replay, so name assertions target fixture-invariant text.
 */
test("advisor: demo-mode report streams in English under the default locale", async ({
  page,
}) => {
  await page.goto("/advisor");

  // Demo-mode banner is visible
  await expect(page.getByText(/demo mode/i).first()).toBeVisible();

  // Capture the selected client's name — the replayed report carries it
  const clientSelect = page.getByRole("combobox", { name: "Client" });
  const selectedName = (
    (await clientSelect.locator("option:checked").textContent()) ?? ""
  ).split(" (")[0].trim();

  await page.getByRole("button", { name: "Generate Proposal" }).click();

  // The English fixture report streams in: heading + demo marker + client
  // name (name appears in the report body; <option> copies stay hidden).
  const report = page.getByRole("heading", {
    name: "Investment Advisory Report",
  });
  await expect(report).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByText(/demonstration sample; all content is fictional/).first()
  ).toBeVisible();
  // The Chinese fixture must not leak into the default en locale.
  await expect(
    page.getByRole("heading", { name: "投资咨询建议书" })
  ).toHaveCount(0);
  if (selectedName) {
    await expect(
      page
        .getByText(new RegExp(selectedName))
        .filter({ visible: true })
        .first()
    ).toBeVisible();
  }
});

test("advisor: demo-mode report streams in Chinese after switching to zh", async ({
  page,
}) => {
  await page.goto("/advisor");

  // Switch the sidebar locale toggle to Chinese
  await page.getByRole("button", { name: "中文" }).first().click();
  const generateButton = page.getByRole("button", { name: "生成建议书" });
  await expect(generateButton).toBeVisible();

  await generateButton.click();

  // The Chinese fixture report streams in: heading + demo marker.
  await expect(
    page.getByRole("heading", { name: "投资咨询建议书" })
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/演示样例，内容为虚构/).first()).toBeVisible();
});
