import { expect, test } from "@playwright/test";

for (const locale of ["en", "zh"] as const) {
  test(`ESG and sector preferences are disclosed across the client workflow (${locale})`, async ({ page, request }) => {
    test.setTimeout(90_000);
    const response = await request.post("/api/profiles", { data: {
      name: `Preference Disclosure ${locale}`, age: 40, marital_status: "single", dependents: 0,
      financial: {
        annual_income: 100000, annual_expenses: 60000, investable_assets: 400000,
        total_liabilities: 0, emergency_fund_months: 6,
      },
      goals: [], time_horizon_years: 20, is_multi_stage: false, liquidity_needs: 0,
      tax_status: "taxable", esg_preference: true, sector_restrictions: ["Tobacco", "Defense"], notes: "",
      risk_scores: { ability_score: 3, willingness_score: 3 },
      ability_answers: {}, willingness_answers: {},
    } });
    expect(response.status()).toBe(201);
    const id = (await response.json()).id;
    const zh = locale === "zh";
    const disclosure = zh ? "偏好已记录，尚未执行筛选。" : "Preferences recorded; screening has not been performed.";
    await page.goto(`/profiles/${id}`);
    if (zh) await page.getByRole("button", { name: "中文", exact: true }).first().click();
    await expect(page.getByText(disclosure, { exact: false })).toBeVisible();
    await expect(page.getByText("Tobacco, Defense", { exact: false })).toBeVisible();

    await page.goto("/advisor");
    await page.getByRole("combobox", { name: zh ? "选择客户" : "Client", exact: true }).selectOption(String(id));
    await page.getByRole("button", { name: zh ? "生成建议书" : "Generate Proposal", exact: true }).click();
    await expect(page.getByText(disclosure, { exact: false })).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText("Tobacco, Defense", { exact: false })).toBeVisible();

    await page.goto("/ips");
    await page.getByRole("combobox", { name: zh ? "选择画像" : "Profile", exact: true }).selectOption(String(id));
    await page.getByRole("button", { name: zh ? "生成 IPS" : "Generate IPS", exact: true }).click();
    await page.getByRole("button", { name: zh ? "立即查看" : "View Now", exact: true }).click({ timeout: 30_000 });
    await expect(page.getByText(disclosure, { exact: false })).toBeVisible();
    await expect(page.getByText("Tobacco, Defense", { exact: false })).toBeVisible();
    await expect(page.getByText(zh ? "客户无 ESG 偏好" : "The client has no ESG preferences", { exact: false })).toHaveCount(0);
  });
}
