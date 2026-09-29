import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect } from "@playwright/test";

// Provision only in the throwaway Playwright database. Sessions are generated
// at runtime, held in memory, and never committed or written to a fixture file.
let identities: Record<string, { token: string; organization: string }>;
let profileIds: Record<string, number>;
test.beforeAll(() => {
  const database = process.env.AIWP_E2E_DB_FILE;
  if (!database) throw new Error("Missing isolated E2E database");
  const seeded = execFileSync("python", ["-c", `
import json
from uuid import uuid4
from sqlmodel import Session
from api import db
from api.auth import issue_session
from api.ownership import set_membership, create_client
with Session(db.engine) as session:
    org = db.OrganizationRecord(name="Console E2E")
    session.add(org)
    session.flush()
    users = {}
    for role in ("advisor", "client", "admin"):
        user = db.UserRecord(email=f"{uuid4()}@example.invalid")
        session.add(user)
        session.flush()
        set_membership(session, org.id, user.id, role)
        users[role] = user
    profiles = {}
    for kind in ("assigned", "unassigned"):
        client = create_client(session, org.id, user_id=users["client"].id if kind == "assigned" else None)
        profile = db.ProfileRecord(client_id=client.id, name=f"Console {kind}", age=40, data={})
        session.add(profile)
        session.flush()
        profiles[kind] = profile.id
        if kind == "assigned":
            session.add(db.AdvisorClientAssignmentRecord(organization_id=org.id, advisor_user_id=users["advisor"].id, client_id=client.id))
    session.commit()
    identities = {role: {"token": issue_session(session, user).access_token, "organization": org.id} for role, user in users.items()}
    print(json.dumps({"identities": identities, "profiles": profiles}))
`], {
    cwd: path.resolve(__dirname, "../.."),
    env: { ...process.env, AIWP_DB_URL: `sqlite:///${database}` },
    encoding: "utf8",
  });
  ({ identities, profiles: profileIds } = JSON.parse(seeded));
});

for (const role of ["advisor", "client", "admin"]) {
  test(`${role}: console and APIs enforce the selected membership`, async ({ page, context, baseURL }) => {
    await context.addCookies([
      { name: "wp_session", value: identities[role].token, url: baseURL!, httpOnly: true },
      { name: "wp_organization", value: identities[role].organization, url: baseURL!, httpOnly: true },
    ]);
    await page.goto("/ips");
    if (role === "client") {
      await expect(page.getByRole("alert").filter({ hasText: "requires advisor or administrator access" })).toBeVisible();
      await expect(page.getByRole("navigation")).toHaveCount(0);
      for (const endpoint of ["/api/ips/not-accessible", "/api/advisor/reports/not-accessible", "/api/settings/llm", `/api/profiles/${profileIds.assigned}`]) {
        expect((await context.request.get(endpoint)).status()).toBe(403);
      }
      return;
    }
    const selector = page.getByRole("combobox", { name: "Current client", exact: true });
    await expect(selector.locator(`option[value="${profileIds.assigned}"]`)).toHaveCount(1);
    await expect(selector.locator(`option[value="${profileIds.unassigned}"]`)).toHaveCount(role === "admin" ? 1 : 0);
    await expect(page.getByRole("link", { name: /Settings/ })).toHaveCount(0);
    if (role === "advisor") {
      expect((await context.request.get(`/api/profiles/${profileIds.unassigned}`)).status()).toBe(404);
    }
    await page.goto("/settings");
    await expect(page.getByRole("alert").filter({ hasText: "require administrator access" })).toBeVisible();
    expect((await context.request.get("/api/settings/llm")).status()).toBe(403);
  });
}
