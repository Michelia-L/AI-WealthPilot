import { expect, test } from "./fixtures";

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

test("advisor goal budgets recalculate after a profile edit and localize on reload", async ({
  page,
  request,
}, testInfo) => {
  const payload = {
    name: `Goal Planning E2E ${Date.now()}`,
    age: 40,
    financial: { investable_assets: 400_000, annual_income: 100_000, annual_expenses: 60_000 },
    risk_scores: { ability_score: 3, willingness_score: 3 },
    goals: [
      { name: "Planning retirement", target_amount: 2_000_000, years: 25, priority: "high" },
      { name: "Planning education", target_amount: 200_000, years: 10, priority: "low" },
    ],
  };
  const created = await request.post("/api/profiles", { data: payload });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  try {
    await page.goto(`/profiles/${id}`);
    const retirement = page.getByRole("article", { name: "Planning retirement" });
    const education = page.getByRole("article", { name: "Planning education" });
    await expect(retirement.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "15.0%");
    await expect(education.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "50.0%");
    await expect(retirement).toContainText("300,000");
    await expect(education).toContainText("10,000");
    await expect(page.getByRole("table", { name: "Goal feasibility within the risk budget" })).toContainText("Planning education");
    await page.screenshot({ path: testInfo.outputPath("advisor-goal-funding.png"), fullPage: true });

    payload.goals[1].target_amount = 400_000;
    expect((await request.put(`/api/profiles/${id}`, { data: payload })).status()).toBe(200);
    await page.reload();
    await expect(education.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "25.0%");
    await page.getByRole("button", { name: "中文", exact: true }).click();
    await expect(page.getByRole("heading", { name: "目标资金规划" })).toBeVisible();
    await expect(education).toContainText("所需年化收益率");
    await expect(education.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "25.0%");
  } finally {
    expect((await request.delete(`/api/profiles/${id}`)).status()).toBe(204);
  }
});

test("manual goal budgets validate, persist and return to priority allocation", async ({ page, request }, testInfo) => {
  const payload = {
    name: `Manual Goal E2E ${Date.now()}`, age: 40,
    financial: { investable_assets: 400_000, annual_income: 100_000, annual_expenses: 60_000 },
    goals: [
      { name: "Manual retirement", target_amount: 2_000_000, years: 25, priority: "high" },
      { name: "Manual education", target_amount: 200_000, years: 10, priority: "low" },
    ],
  };
  const created = await request.post("/api/profiles", { data: payload });
  expect(created.status()).toBe(201);
  const { id } = await created.json();
  try {
    await page.goto(`/profiles?edit=${id}`);
    const goal = page.getByRole("group", { name: "Goal 2", exact: true });
    await goal.getByRole("switch", { name: "Set a manual budget" }).click();
    await goal.getByLabel("Planning budget", { exact: true }).fill("400001");
    await goal.getByLabel("Annual contribution budget").fill("15000");
    const rejected = page.waitForResponse((r) => r.url().endsWith(`/api/profiles/${id}`) && r.request().method() === "PUT");
    await page.getByRole("button", { name: "Save Changes" }).click();
    expect((await rejected).status()).toBe(422);
    await expect(page.getByRole("main").getByRole("alert")).toContainText("exceed the recorded investable assets");
    await goal.getByLabel("Planning budget", { exact: true }).fill("80000");
    const saved = page.waitForResponse((r) => r.url().endsWith(`/api/profiles/${id}`) && r.request().method() === "PUT");
    await page.getByRole("button", { name: "Save Changes" }).click();
    expect((await saved).status()).toBe(200);
    await expect(page.getByRole("link", { name: payload.name })).toBeVisible();

    await page.goto(`/profiles/${id}`);
    const education = page.getByRole("article", { name: "Manual education" });
    await expect(education).toContainText("Manually set");
    await expect(education).toContainText("8 years");
    await expect(education.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "40.0%");
    await expect(page.getByRole("article", { name: "Manual retirement" })).toContainText("320,000");
    await page.reload();
    await expect(education).toContainText("Manually set");

    await page.getByRole("button", { name: "中文", exact: true }).click();
    await expect(education).toContainText("手动指定");
    await expect(education).toContainText("零收益下的达标年限");
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await education.screenshot({ path: testInfo.outputPath("manual-goal-mobile-zh.png") });

    await page.goto(`/profiles?edit=${id}`);
    const edited = page.getByRole("group", { name: "目标 2", exact: true });
    await expect(edited.getByLabel("规划资金预算", { exact: true })).toHaveValue("80000");
    await edited.screenshot({ path: testInfo.outputPath("manual-goal-editor-mobile-zh.png") });
    await edited.getByRole("switch", { name: "手动设置预算" }).click();
    const reset = page.waitForResponse((r) => r.url().endsWith(`/api/profiles/${id}`) && r.request().method() === "PUT");
    await page.getByRole("button", { name: "保存修改" }).click();
    expect((await reset).status()).toBe(200);
    await page.goto(`/profiles/${id}`);
    await expect(education).toContainText("按优先级分配");
    await expect(education.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "50.0%");
    await expect(education.getByText("零收益下的达标年限", { exact: true }).locator("..").locator("dd")).toHaveText("10 年");
  } finally {
    expect((await request.delete(`/api/profiles/${id}`)).status()).toBe(204);
  }
});
