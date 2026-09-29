import { expect, test, demoLogin } from "./fixtures";

const clients: { id: number; age: number }[] = [];
const name = "Client Context Example";

test.beforeAll(async ({ request, baseURL }) => {
  await demoLogin(request, baseURL!);
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

test("retirement requires a client and follows the shared selection", async ({ page }) => {
  await page.goto("/retirement");
  await page.getByRole("combobox", { name: "Current client", exact: true }).selectOption(String(clients[0].id));
  await page.reload();
  const picker = page.getByRole("combobox", { name: "Client", exact: true });
  await expect(picker).toHaveValue(String(clients[0].id));
  await expect(page.getByRole("spinbutton", { name: "Current Savings" })).toHaveValue("410000");

  await picker.selectOption("");
  await expect(page.getByRole("button", { name: "Run Simulation" })).toBeDisabled();
  await expect(page.getByRole("combobox", { name: "Current client", exact: true })).toHaveValue("");
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

  await page.goto("/profiles");
  await page.getByRole("combobox", { name: "Current client", exact: true }).selectOption(String(clients[0].id));
  await page.locator("aside").getByRole("link", { name: /Monitor/ }).click();
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
  await page.getByRole("button", { name: "EN", exact: true }).first().click();
  await page.goto("/ips");
  const sidebar = page.getByRole("combobox", { name: "Current client", exact: true });
  const firstDocument = page.getByRole("row").filter({ has: page.locator(`a[href="/api/ips/${documentIds[0]}/pdf"]`) });
  const secondDocument = page.getByRole("row").filter({ has: page.locator(`a[href="/api/ips/${documentIds[1]}/pdf"]`) });
  await expect(firstDocument).toHaveCount(1);
  await expect(secondDocument).toHaveCount(0);
  await sidebar.selectOption(String(clients[1].id));
  await expect(firstDocument).toHaveCount(0);
  await expect(secondDocument).toHaveCount(1);
  await sidebar.selectOption("");
  await expect(firstDocument).toHaveCount(0);
  await expect(secondDocument).toHaveCount(0);
});

test("advisor and IPS follow sidebar changes, profile links and reloads", async ({ page }) => {
  await page.goto("/advisor");
  const sidebar = page.getByRole("combobox", { name: "Current client", exact: true });
  const advisor = page.getByRole("combobox", { name: "Client", exact: true });
  await expect(page.getByRole("button", { name: "Generate Proposal" })).toBeDisabled();
  await advisor.selectOption(String(clients[0].id));
  await expect(sidebar).toHaveValue(String(clients[0].id));
  await sidebar.selectOption(String(clients[1].id));
  await expect(advisor).toHaveValue(String(clients[1].id));
  await page.locator("aside").getByRole("link", { name: /IPS/ }).click();
  const ips = page.getByRole("combobox", { name: "Profile", exact: true });
  await expect(ips).toHaveValue(String(clients[1].id));
  await sidebar.selectOption(String(clients[0].id));
  await expect(ips).toHaveValue(String(clients[0].id));
  await page.reload();
  await expect(ips).toHaveValue(String(clients[0].id));
  await page.goto(`/profiles/${clients[1].id}`);
  await expect(sidebar).toHaveValue(String(clients[1].id));
  await sidebar.selectOption(String(clients[0].id));
  await expect(page).toHaveURL(new RegExp(`/profiles/${clients[0].id}$`));
  await page.locator("aside").getByRole("link", { name: /Optimizer/ }).click();
  await expect(sidebar).toHaveValue(String(clients[0].id));
  await expect(page.getByRole("status")).toContainText(name);
  await page.goto(`/profiles/${clients[1].id}`);
  await sidebar.selectOption("");
  await expect(page).toHaveURL(/\/profiles$/);
  await expect(sidebar).toHaveValue("");
  expect(await page.evaluate(() => Object.keys(sessionStorage).filter((key) => key.startsWith("wealthpilot.activeClient:")))).toHaveLength(0);
  await page.reload();
  await expect(sidebar).toHaveValue("");
  await sidebar.selectOption(String(clients[0].id));
  await page.getByRole("button", { name: "中文", exact: true }).first().click();
  await expect(page.getByRole("combobox", { name: "当前客户", exact: true })).toHaveValue(String(clients[0].id));
});

test("IPS resumes only the selected client's saved task", async ({ page, request }) => {
  test.setTimeout(60_000);
  const created = await request.post("/api/ips/generate", { data: { profile_id: clients[0].id } });
  expect(created.status()).toBe(202);
  const { task_id: taskId } = await created.json();
  await page.goto("/profiles");
  await page.getByRole("combobox", { name: "Current client", exact: true }).selectOption(String(clients[1].id));
  await page.evaluate(({ taskId, id }) => {
    const clientKey = Object.keys(sessionStorage).find((key) => key.startsWith("wealthpilot.activeClient:"))!;
    const scope = clientKey.slice("wealthpilot.activeClient:".length);
    sessionStorage.setItem(`wealthpilot:active-task:ips:${scope}:${id}`, taskId);
  }, { taskId, id: clients[0].id });
  const taskRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes(`/api/ips/tasks/${taskId}/events`)) taskRequests.push(request.url());
  });
  await page.locator("aside").getByRole("link", { name: /IPS/ }).click();
  await expect(page.getByRole("combobox", { name: "Profile", exact: true })).toHaveValue(String(clients[1].id));
  await expect(page.getByRole("button", { name: "Generate IPS", exact: true })).toBeEnabled();
  expect(taskRequests).toHaveLength(0);
  await page.getByRole("combobox", { name: "Current client", exact: true }).selectOption(String(clients[0].id));
  await expect(page.getByText(/IPS generated and archived/).first()).toBeVisible({ timeout: 30_000 });
  expect(taskRequests).toHaveLength(1);
});


test("optimizer replay rejects a task handle copied into another client's scope", async ({ page, request }) => {
  test.setTimeout(90_000);
  const created = await request.post("/api/portfolio/optimize/async", { data: {
    context_profile_id: clients[0].id,
    assets: ["US_EQUITY", "US_BOND"], method: "mvo", risk_free_rate: 0.03,
  } });
  expect(created.status()).toBe(202);
  const { task_id: taskId } = await created.json();
  const eventsPath = `/api/portfolio/tasks/${taskId}/events`;
  expect((await request.get(eventsPath)).status()).toBe(422);
  expect((await request.get(`${eventsPath}?context_profile_id=${clients[1].id}`)).status()).toBe(404);

  await page.goto("/profiles");
  await page.getByRole("combobox", { name: "Current client", exact: true }).selectOption(String(clients[1].id));
  await page.evaluate(({ taskId, ids }) => {
    const clientKey = Object.keys(sessionStorage).find((key) => key.startsWith("wealthpilot.activeClient:"))!;
    const scope = clientKey.slice("wealthpilot.activeClient:".length);
    for (const id of ids) sessionStorage.setItem(`wealthpilot:active-task:portfolio:${scope}:${id}`, taskId);
  }, { taskId, ids: clients.map((client) => client.id) });

  const rejected = page.waitForResponse((response) => response.url().endsWith(`${eventsPath}?context_profile_id=${clients[1].id}`));
  await page.locator("aside").getByRole("link", { name: /Optimizer/ }).click();
  expect((await rejected).status()).toBe(404);
  await expect.poll(() => page.evaluate((id) => Object.keys(sessionStorage)
    .filter((key) => key.startsWith("wealthpilot:active-task:portfolio:") && key.endsWith(`:${id}`)).length,
  clients[1].id)).toBe(0);

  const resumed = page.waitForResponse((response) => response.url().endsWith(`${eventsPath}?context_profile_id=${clients[0].id}`));
  await page.getByRole("combobox", { name: "Current client", exact: true }).selectOption(String(clients[0].id));
  const response = await resumed;
  expect(response.status()).toBe(200);
  expect(await response.text()).toContain('"type": "done"');
  await expect(page.getByText("Annualized Return", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Optimization" })).toBeEnabled();
});

test("advisor library isolates reports for same-named clients and clears old previews", async ({ page, request }) => {
  const reports: string[] = [];
  try {
    for (let i = 0; i < clients.length; i++) {
      const saved = await request.post("/api/advisor/reports", { data: {
        profile_id: clients[i].id, client_name: name,
        model: `context-report-${i}`, content: `Client report body ${i}`,
      } });
      expect(saved.status()).toBe(201);
      const summary = await saved.json();
      expect(summary.profile_id).toBe(clients[i].id);
      reports.push(summary.report_id);
    }
    await page.goto("/advisor");
    const sidebar = page.getByRole("combobox", { name: "Current client", exact: true });
    await sidebar.selectOption(String(clients[0].id));
    const first = page.getByRole("row").filter({ hasText: "context-report-0" });
    const second = page.getByRole("row").filter({ hasText: "context-report-1" });
    await expect(first).toHaveCount(1);
    await expect(second).toHaveCount(0);
    await first.getByRole("button", { name: "View report", exact: true }).click();
    await expect(page.getByText("Client report body 0", { exact: true })).toBeVisible();
    await sidebar.selectOption(String(clients[1].id));
    await expect(first).toHaveCount(0);
    await expect(second).toHaveCount(1);
    await expect(page.getByText("Client report body 0", { exact: true })).toHaveCount(0);
    await sidebar.selectOption("");
    await expect(first).toHaveCount(0);
    await expect(second).toHaveCount(0);
  } finally {
    for (const id of reports) await request.delete(`/api/advisor/reports/${id}`);
  }
});
