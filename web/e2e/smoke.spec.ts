import { expect, test } from "@playwright/test";

/**
 * Route smoke: every page renders its shell (title/chrome). Data sections may
 * legitimately degrade to the offline/empty state — the contract under test
 * is that pages never crash.
 */
const ROUTES: { path: string; heading: string | RegExp }[] = [
  { path: "/", heading: /Private Wealth Workstation/i },
  { path: "/market", heading: "Market Dashboard" },
  { path: "/optimizer", heading: "Portfolio Optimizer" },
  { path: "/retirement", heading: "Retirement Planner" },
  { path: "/profiles", heading: "Client Profiles" },
  { path: "/advisor", heading: "AI Advisor" },
  { path: "/ips", heading: "IPS Workflow" },
  { path: "/deliverables", heading: "Deliverables" },
  { path: "/monitoring", heading: "Portfolio Monitor" },
  { path: "/settings", heading: "Settings" },
];

for (const { path, heading } of ROUTES) {
  test(`GET ${path} renders`, async ({ page }) => {
    const resp = await page.goto(path);
    expect(resp?.status()).toBe(200);
    await expect(page.getByText(heading).first()).toBeVisible();
  });
}
