import { expect, test } from "@playwright/test";

const clients: { id: number; age: number }[] = [];
const name = "Client Context Example";

test.beforeAll(async ({ request }) => {
  for (const age of [41, 52]) {
    const response = await request.post("/api/profiles", { data: {
      name, age, marital_status: "single", dependents: 0,
      financial: {
        annual_income: 100000, annual_expenses: 60000, investable_assets: age * 10000,
        total_liabilities: 0, emergency_fund_months: 6,
      },
      goals: [], time_horizon_years: 20, is_multi_stage: false, liquidity_needs: 0,
      tax_status: "taxable", esg_preference: false, sector_restrictions: [], notes: "",
      risk_scores: { ability_score: 3, willingness_score: 3 },
      ability_answers: {}, willingness_answers: {},
    } });
    expect(response.status()).toBe(201);
    clients.push({ id: (await response.json()).id, age });
  }
});

test("retirement follows persisted and sidebar clients while preserving manual mode", async ({ page }) => {
  await page.addInitScript(({ id, name }) => {
    localStorage.setItem("wealthpilot.activeClient", JSON.stringify({ id, name }));
  }, { id: clients[0].id, name });
  await page.goto("/retirement");
  const picker = page.getByRole("combobox", { name: "Client", exact: true });
  await expect(picker).toHaveValue(String(clients[0].id));
  await expect(page.getByRole("spinbutton", { name: "Current Savings" })).toHaveValue("410000");

  await picker.selectOption("");
  await page.getByRole("spinbutton", { name: "Current Savings" }).fill("123456");
  await expect(picker).toHaveValue("");
  await page.locator("aside select").selectOption(String(clients[1].id));
  await expect(picker).toHaveValue(String(clients[1].id));
  await expect(page.getByRole("spinbutton", { name: "Current Savings" })).toHaveValue("520000");
  await page.locator("aside").getByRole("link", { name: /Market/ }).click();
  await page.locator("aside").getByRole("link", { name: /Retirement/ }).click();
  await expect(picker).toHaveValue(String(clients[1].id));
});

test("monitoring filters generated IPS documents by client ID despite duplicate names", async ({ page, request }) => {
  test.setTimeout(90_000);
  const documentIds: string[] = [];
  for (const client of clients) {
    const created = await request.post("/api/ips/generate", { data: { profile_id: client.id } });
    expect(created.status()).toBe(202);
    const taskId = (await created.json()).task_id;
    const events = await request.get(`/api/ips/tasks/${taskId}/events`);
    const done = (await events.text()).split("\n")
      .filter((line) => line.startsWith("data: "))
      .map((line) => JSON.parse(line.slice(6)))
      .find((event) => event.type === "done");
    expect(done?.success).toBe(true);
    documentIds.push(done.document_id);
  }

  await page.addInitScript(({ id, name }) => {
    localStorage.setItem("wealthpilot.activeClient", JSON.stringify({ id, name }));
  }, { id: clients[0].id, name });
  await page.goto("/monitoring");
  const picker = page.getByRole("combobox", { name: "Select an IPS document (source of SAA targets)" });
  await expect(picker.locator(`option[value="${documentIds[0]}"]`)).toHaveCount(1);
  await expect(picker.locator(`option[value="${documentIds[1]}"]`)).toHaveCount(0);
  await page.getByRole("combobox", { name: "Filter by client" }).selectOption("all");
  const labels = await picker.locator("option").allTextContents();
  expect(new Set(labels).size).toBe(labels.length);
  await picker.selectOption(documentIds[1]);
  await expect(page).toHaveURL(new RegExp(`doc=${documentIds[1]}`));
  await expect(picker).toHaveValue(documentIds[1]);
  await page.getByRole("button", { name: "中文", exact: true }).first().click();
  await expect(page.getByRole("combobox", { name: "按客户筛选" })).toHaveValue("all");
});
