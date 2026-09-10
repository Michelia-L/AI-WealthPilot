import { expect, test } from "@playwright/test";

test("actual holdings: entry, persisted drift, JSON import, history and Chinese errors", async ({ page, request }) => {
  test.setTimeout(120_000);
  // Create an isolated synthetic client/document, avoiding another test's positions.
  const profile = await request.post("/api/profiles", { data: {
    name: "Holdings Example", age: 45, marital_status: "single", dependents: 0,
    financial: { annual_income: 100000, annual_expenses: 60000, investable_assets: 1000000, total_liabilities: 0, emergency_fund_months: 6 },
    goals: [], time_horizon_years: 20, is_multi_stage: false, liquidity_needs: 0,
    tax_status: "taxable", esg_preference: false, sector_restrictions: [], notes: "",
    risk_scores: { ability_score: 3, willingness_score: 3 }, ability_answers: {}, willingness_answers: {},
  } });
  expect(profile.status()).toBe(201);
  const profileId = (await profile.json()).id;
  const created = await request.post("/api/ips/generate", { data: { profile_id: profileId } });
  expect(created.status()).toBe(202);
  const events = await request.get(`/api/ips/tasks/${(await created.json()).task_id}/events`);
  const done = (await events.text()).split("\n").filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice(6))).find((event) => event.type === "done");
  expect(done?.success).toBe(true);
  await page.addInitScript((id) => localStorage.setItem("wealthpilot.activeClient", JSON.stringify({ id, name: "Holdings Example" })), profileId);
  await page.goto(`/monitoring?doc=${done.document_id}`);
  await expect(page.getByRole("heading", { name: "Actual Holdings", exact: true })).toBeVisible();
  await page.getByLabel("Valuation date", { exact: true }).fill("2026-06-10");
  const asset = await page.getByRole("combobox", { name: "Asset class", exact: true }).inputValue();
  const currency = await page.getByLabel("Base currency", { exact: true }).inputValue();
  await page.getByRole("spinbutton", { name: "Market value", exact: true }).fill("1000");
  await page.getByRole("spinbutton", { name: "Cost basis (optional)" }).fill("900");
  await page.getByLabel("Cost basis date", { exact: true }).fill("2026-01-01");
  await page.getByRole("button", { name: "Save new snapshot" }).click();
  await expect(page.getByRole("status")).toContainText("Snapshot saved");
  await expect(page.getByText("Actual holdings snapshot · 2026-06-10", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "View snapshot", exact: true }).locator("option")).toHaveCount(1);
  await page.reload();
  await expect(page.getByText("Actual holdings snapshot · 2026-06-10", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "100.0%", exact: true })).toBeVisible();

  await page.getByText("Import JSON snapshot", { exact: true }).click();
  await page.getByRole("textbox", { name: "Snapshot JSON", exact: true }).fill(JSON.stringify({
    as_of: "2026-06-11", base_currency: currency, holdings: [{ asset_class: asset, quantity: 20, unit_price: 100 }],
  }));
  await page.getByRole("button", { name: "Import and save snapshot" }).click();
  await expect(page.getByRole("combobox", { name: "View snapshot", exact: true }).locator("option")).toHaveCount(2);
  await expect(page.getByText("Actual holdings snapshot · 2026-06-11", { exact: true })).toBeVisible();
  await expect(page.getByText(/Compared with previous snapshot: 2026-06-10/)).toBeVisible();
  const oldId = await page.getByRole("combobox", { name: "View snapshot", exact: true }).locator("option").nth(1).getAttribute("value");
  await page.getByRole("combobox", { name: "View snapshot", exact: true }).selectOption(oldId!);
  await expect(page.getByRole("cell", { name: "900", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "中文", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "实际持仓", exact: true })).toBeVisible();
  // This error can only be localized by the same-origin proxy forwarding X-Locale.
  const details = page.locator("details").filter({ has: page.getByText("导入 JSON 快照", { exact: true }) });
  if (await details.getAttribute("open") === null) await page.getByText("导入 JSON 快照", { exact: true }).click();
  await page.getByRole("textbox", { name: "快照 JSON", exact: true }).fill(JSON.stringify({
    as_of: "2999-01-01", base_currency: currency, holdings: [{ asset_class: asset, market_value: 1 }],
  }));
  await page.getByRole("button", { name: "导入并保存快照" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "估值日期不能晚于今天。" })).toHaveText("估值日期不能晚于今天。");
  await expect(page.getByRole("combobox", { name: "查看快照", exact: true }).locator("option")).toHaveCount(2);
});
