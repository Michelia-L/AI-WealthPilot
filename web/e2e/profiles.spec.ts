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
