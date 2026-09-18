import { test as base, expect, type APIRequestContext } from "@playwright/test";

export async function demoLogin(request: APIRequestContext, baseURL: string) {
  const response = await request.post("/api/session", { headers: { Origin: baseURL }, data: { action: "demo" } });
  expect(response.status()).toBe(200);
}

/** Existing flows run through explicit demo sign-in for browser and request contexts. */
export const test = base.extend<{ workspaceLogin: void }>({
  workspaceLogin: [async ({ context, request, baseURL }, provide) => {
    await demoLogin(context.request, baseURL!);
    await demoLogin(request, baseURL!);
    await provide();
  }, { auto: true }],
});
export { expect };
