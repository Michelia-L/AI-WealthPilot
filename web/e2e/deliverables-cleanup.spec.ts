import type { APIRequestContext, Page } from "@playwright/test";
import { expect, test } from "./fixtures";

async function generateIps(page: Page, request: APIRequestContext) {
  await page.goto("/ips");
  const picker = page.getByRole("combobox", { name: "Profile" });
  const profileId = Number(await picker.inputValue());
  const name = ((await picker.locator("option:checked").textContent()) ?? "").split(" (")[0].trim();
  const created = await request.post("/api/ips/generate", { data: { profile_id: profileId } });
  expect(created.status()).toBe(202);
  const { task_id: taskId } = await created.json();
  const stream = await request.get(`/api/ips/tasks/${taskId}/events`);
  const events = (await stream.text()).split("\n")
    .filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice(6)));
  const done = events.find((event) => event.type === "done");
  expect(done?.document_id).toBeTruthy();
  return { id: done.document_id as string, name };
}

test("IPS library: cancel preserves the document; confirmed deletion clears the viewer", async ({ page, request }) => {
  const doc = await generateIps(page, request);
  const url = `/api/ips/${encodeURIComponent(doc.id)}`;
  try {
    await page.goto("/ips");
    const row = page.getByRole("row").filter({ has: page.locator(`a[href="${url}/pdf"]`) });
    await row.getByRole("button", { name: "View", exact: true }).click();
    await expect(page.getByRole("button", { name: "Close", exact: true })).toBeVisible();
    await row.getByRole("button", { name: `Delete document for ${doc.name}` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
    expect((await request.get(url)).status()).toBe(200);
    await row.getByRole("button", { name: `Delete document for ${doc.name}` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await expect(row).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Close", exact: true })).toHaveCount(0);
    expect((await request.get(url)).status()).toBe(404);
    await page.reload();
    await expect(row).toHaveCount(0);
  } finally {
    await request.delete(url);
  }
});

test("deliverables: delete an IPS from a filtered list and preserve the filters", async ({ page, request }) => {
  const doc = await generateIps(page, request);
  const url = `/api/ips/${encodeURIComponent(doc.id)}`;
  const filter = new URLSearchParams({ client: doc.name, type: "ips" });
  try {
    await page.goto(`/deliverables?${filter}`);
    const row = page.getByRole("row").filter({ has: page.locator(`a[href="${url}/pdf"]`) });
    await expect(row).toBeVisible();
    await row.getByRole("button", { name: `Delete document for ${doc.name}` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Delete", exact: true }).click();
    await expect(row).toHaveCount(0);
    expect(new URL(page.url()).searchParams.get("client")).toBe(doc.name);
    expect(new URL(page.url()).searchParams.get("type")).toBe("ips");
    expect((await request.get(url)).status()).toBe(404);
    await page.reload();
    await expect(row).toHaveCount(0);
  } finally {
    await request.delete(url);
  }
});
