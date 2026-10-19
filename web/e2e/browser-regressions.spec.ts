import { expect, test } from "./fixtures";
import { en } from "../src/lib/i18n/dictionaries/en";
import { zh } from "../src/lib/i18n/dictionaries/zh";

for (const locale of ["en", "zh"] as const) {
  const t = locale === "en" ? en : zh;

  test("market: synthetic data is disclosed and controls fit mobile screens (" + locale + ")", async ({
    page, context, baseURL,
  }) => {
    await context.addCookies([{ name: "wp_locale", value: locale, url: baseURL! }]);
    await page.goto("/market");
    await expect(page.getByText(t.market.demoDescription, { exact: true })).toBeVisible();
    await expect(page.locator("footer")).toHaveText(t.market.demoFooterDisclaimer);
    await expect(page.getByText(t.market.description, { exact: true })).toHaveCount(0);
    await expect(page.getByText(t.market.footerDisclaimer, { exact: true })).toHaveCount(0);
    await expect(page.locator(".js-plotly-plot").first()).toBeVisible();

    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth))
        .toBeLessThanOrEqual(width);
      await expect(page.getByRole("button", { name: "5Y", exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: "3M", exact: true }).click();
    await expect(page).toHaveURL(/period=3mo/);
  });

  test("retirement: default and optional sliders expose localized names (" + locale + ")", async ({
    page, context, baseURL,
  }) => {
    await context.addCookies([{ name: "wp_locale", value: locale, url: baseURL! }]);
    await page.goto("/retirement");
    await page.getByRole("combobox", { name: t.clientSelector.label, exact: true })
      .selectOption({ index: 1 });
    for (const name of [
      t.retirement.currentAge, t.retirement.retirementAge, t.retirement.lifeExpectancy,
      t.retirement.expectedReturn, t.retirement.volatility, t.retirement.inflationRate,
    ]) {
      await expect(page.getByRole("slider", { name, exact: true })).toBeVisible();
    }
    await page.getByRole("button", { name: t.retirement.strategyGuardrails, exact: true }).click();
    await expect(page.getByRole("slider", { name: t.retirement.guardrailBand, exact: true })).toBeVisible();
    await expect(page.getByRole("slider", { name: t.retirement.guardrailAdjust, exact: true })).toBeVisible();
    await page.getByRole("button", { name: t.retirement.inflationPresetCustom, exact: true }).click();
    await expect(page.getByRole("slider", { name: t.retirement.distributionInflationRate, exact: true })).toBeVisible();
  });
}

test("optimizer: refreshing a running resampled task restores the result", async ({ page }) => {
  test.setTimeout(90_000);
  await page.goto("/optimizer");
  await page.getByRole("combobox", { name: "Current client", exact: true })
    .selectOption({ index: 1 });
  await page.getByRole("button", { name: "Resampled MVO", exact: true }).click();
  const created = page.waitForResponse((response) =>
    response.url().endsWith("/api/portfolio/optimize/async")
      && response.request().method() === "POST"
  );
  const progress = page.waitForResponse((response) =>
    /\/api\/portfolio\/tasks\/[^/]+\/events\?/.test(response.url())
  );
  await page.getByRole("button", { name: "Run Optimization", exact: true }).click();
  const response = await created;
  expect(response.status()).toBe(202);
  const { task_id: taskId } = await response.json();
  await page.waitForFunction((id) =>
    Object.values(sessionStorage).some((value) => value.includes(id)), taskId
  );
  expect((await progress).status()).toBe(200);
  await expect(page.getByText(/Running resampled optimization/)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Weight σ", exact: true }))
    .toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Backtest This Portfolio", exact: true })).toBeVisible();
});
