import { test, expect } from "@playwright/test";

test("sign-in protects API, forwards an HttpOnly session, and sign-out revokes it", async ({ page, context, request }) => {
  expect((await request.get("/api/settings/llm")).status()).toBe(401);
  expect((await request.post("/api/session", { headers: { Origin: "https://foreign.invalid" }, data: { action: "demo" } })).status()).toBe(403);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Sign in to AI WealthPilot" })).toBeVisible();
  await page.getByRole("button", { name: "Try demo", exact: true }).click();
  await expect(page.getByRole("button", { name: "Sign out", exact: true }).first()).toBeVisible();
  const cookie = (await context.cookies()).find((item) => item.name === "wp_session");
  expect(cookie?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("wp_session");
  const settings = await context.request.get("/api/settings/llm");
  expect(settings.status()).toBe(200);
  expect(settings.headers()["cache-control"]).toBe("no-store");
  expect((await settings.json()).demo).toBe(true);
  expect((await context.request.post("/api/session", { data: { action: "organization", organization_id: "local" } })).status()).toBe(403);
  expect((await context.request.put("/api/settings/llm", { data: { model: "unauthorized" } })).status()).toBe(403);
  await page.getByRole("button", { name: "Sign out", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "Sign in to AI WealthPilot" })).toBeVisible();
  expect((await context.request.get("/api/settings/llm")).status()).toBe(401);
  // Reusing the captured cookie cannot restore a revoked backend session.
  await context.addCookies([cookie!]);
  expect((await context.request.get("/api/settings/llm")).status()).toBe(401);
});
