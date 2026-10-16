import { execFileSync } from "node:child_process";
import path from "node:path";
import { test, expect, type BrowserContext } from "@playwright/test";

// All data lives in Playwright's throwaway database. Session tokens are issued
// at runtime and retained in memory only; no real client records are used.
let accounts: Record<
  string,
  { token: string; organization: string; userId: string }
>;
let reports: Record<string, string>;

test.beforeAll(() => {
  const database = process.env.AIWP_E2E_DB_FILE;
  if (!database) throw new Error("Missing isolated E2E database");
  const seeded = execFileSync(
    "python",
    [
      "-c",
      `
import json
from uuid import uuid4
from sqlmodel import Session
from api import db, documents
from api.auth import issue_session
from api.ownership import create_client, set_membership
from api.profile_convert import payload_to_data
from api.schemas import ClientDocumentContent, ProfilePayload

with Session(db.engine) as session:
    org = db.OrganizationRecord(name="Portal E2E")
    session.add(org)
    session.flush()
    staff = db.UserRecord(email=f"{uuid4()}@example.invalid")
    session.add(staff)
    session.flush()
    set_membership(session, org.id, staff.id, "advisor")
    clients, accounts, reports = {}, {}, {}
    for name in ("Alice", "Bob", "Empty", "Ambiguous", "Revoked"):
        user = db.UserRecord(email=f"{uuid4()}@example.invalid")
        session.add(user)
        session.flush()
        set_membership(session, org.id, user.id, "client")
        owner = create_client(session, org.id, user_id=user.id)
        clients[name] = owner
        payload = ProfilePayload(
            name=f"Portal {name}", age=40,
            financial={"investable_assets": 420000, "total_liabilities": 20000, "annual_income": 120000, "annual_expenses": 60000},
            risk_scores={"ability_score": 3, "willingness_score": 3} if name != "Empty" else {},
            goals=([
                {"name": f"{name} retirement", "target_amount": 1500000, "years": 20, "priority": "high"},
                *([
                    {"name": "Alice education", "target_amount": 210000, "years": 7, "priority": "low"},
                    {"name": "Needs details"},
                ] if name == "Alice" else []),
            ] if name != "Empty" else []),
            notes="PORTAL_STAFF_ONLY_SYNTHETIC",
        )
        session.add(db.ProfileRecord(client_id=owner.id, name=payload.name, age=40, data=payload_to_data(payload, "2026-10-01")))
        session.add(db.AdvisorClientAssignmentRecord(organization_id=org.id, advisor_user_id=staff.id, client_id=owner.id))
        if name == "Ambiguous":
            create_client(session, org.id, user_id=user.id)
        session.flush()
        accounts[name] = {"token": issue_session(session, user).access_token, "organization": org.id, "userId": user.id}

    def publish(owner, title, kind="ips", published_at="2026-10-15T01:00:00+00:00"):
        content = ClientDocumentContent(
            title=title, summary=f"Published plan for {title}",
            recommendation="Discuss this suggested allocation with your advisor.",
            risk_explanation="Market values may fall.", risk_disclosure="Returns are not guaranteed.",
            allocation=[{"asset_class": "Global equities", "weight": 0.5}, {"asset_class": "Bonds", "weight": 0.5}] if kind == "ips" else [],
            sections=[{"heading": "Review schedule", "text": "Review with your advisor every year."}],
        )
        record = documents.create_draft(session, organization_id=org.id, client_id=owner.id, created_by=staff.id, type=kind, content=content)
        documents.change(session, record, "draft", "en", status="in_review", submitted_at=published_at)
        documents.change(session, record, "in_review", "en", status="approved", reviewed_by=staff.id, approved_by=staff.id, approved_at=published_at)
        documents.validate_publishable(record, "en")
        documents.change(session, record, "approved", "en", status="published", published_by=staff.id, published_at=published_at)
        return record

    for name in ("Alice", "Bob"):
        record = publish(clients[name], f"{name} investment policy")
        reports[name] = record.id
        draft = documents.revise(session, record, staff.id, ClientDocumentContent(title=f"{name} UNPUBLISHED revision", summary="PRIVATE_DRAFT_CONTENT"), "en")
        reports[f"{name}Draft"] = draft.id
    for number in range(21):
        publish(clients["Alice"], f"Alice portfolio note {number}", "portfolio_review", "2026-10-01T01:00:00+00:00")
    session.commit()
    print(json.dumps({"accounts": accounts, "reports": reports}))
`,
    ],
    {
      cwd: path.resolve(__dirname, "../.."),
      env: { ...process.env, AIWP_DB_URL: `sqlite:///${database}` },
      encoding: "utf8",
    },
  );
  ({ accounts, reports } = JSON.parse(seeded));
});

async function signIn(
  context: BrowserContext,
  baseURL: string,
  name = "Alice",
) {
  await context.addCookies([
    {
      name: "wp_session",
      value: accounts[name].token,
      url: baseURL,
      httpOnly: true,
    },
    {
      name: "wp_organization",
      value: accounts[name].organization,
      url: baseURL,
      httpOnly: true,
    },
  ]);
}

test("client pages have independent navigation and only show the client's information", async ({
  page,
  context,
  baseURL,
}, testInfo) => {
  await signIn(context, baseURL!);
  await page.goto("/");
  await expect(page).toHaveURL(/\/client$/);
  await expect(
    page.getByRole("heading", { name: "Welcome, Portal Alice" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("client-overview.png"),
    fullPage: true,
  });
  const routes = [
    ["/client", "Overview"],
    ["/client/portfolio", "Portfolio"],
    ["/client/goals", "Goals"],
    ["/client/risk-profile", "Risk Profile"],
    ["/client/documents", "Documents"],
    ["/client/ai", "WealthPilot AI"],
  ];
  for (const [route, heading] of routes) {
    await page.goto(route);
    await expect(
      page.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
    const nav = page.getByRole("navigation", { name: "Client navigation" });
    expect(
      await nav
        .getByRole("link")
        .evaluateAll((links) => links.map((link) => link.getAttribute("href"))),
    ).toEqual(routes.map(([href]) => href));
    await expect(
      nav.getByRole("link", { name: heading, exact: true }),
    ).toHaveAttribute("aria-current", "page");
    await expect(
      page.getByRole("combobox", { name: "Current client", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByRole("main")).not.toContainText("Portal Bob");
    await expect(page.getByRole("main")).not.toContainText(
      "PORTAL_STAFF_ONLY_SYNTHETIC",
    );
  }
});

test("goal funding budgets stay scoped and display planning coverage in both locales", async ({
  page,
  context,
  baseURL,
}, testInfo) => {
  await signIn(context, baseURL!);
  await page.goto("/client/goals?client_id=Bob");
  const retirement = page.getByRole("article", { name: "Alice retirement" });
  const education = page.getByRole("article", { name: "Alice education" });
  await expect(retirement.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "21.0%");
  await expect(education.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "50.0%");
  await expect(retirement).toContainText("315,000");
  await expect(retirement).toContainText("45,000");
  await expect(education).toContainText("Covered with planned savings at 0% return");
  await expect(page.getByRole("article", { name: "Needs details" })).toContainText("Add a positive target");
  await expect(page.getByText("Planning estimates; actual balances", { exact: false })).toBeVisible();
  await expect(page.getByRole("main")).not.toContainText("Bob retirement");
  await page.screenshot({ path: testInfo.outputPath("goal-funding-desktop.png"), fullPage: true });

  await page.getByRole("button", { name: "中文", exact: true }).click();
  await expect(retirement).toContainText("年度投入预算");
  await expect(retirement.getByRole("progressbar")).toHaveAccessibleName("Alice retirement · 规划资金覆盖率");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(education).toContainText("按零收益及计划结余可覆盖");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("goal-funding-mobile-zh.png"), fullPage: true });

  await signIn(context, baseURL!, "Bob");
  await page.goto("/client/goals");
  await expect(page.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "28.0%");
  await expect(page.getByRole("article", { name: "Alice education" })).toHaveCount(0);
});

test("a published policy can be read and acknowledged without implying execution", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!);
  await page.goto("/client/portfolio");
  await expect(page.getByRole("table")).toContainText("Global equities");
  await expect(page.getByRole("table")).toContainText("50.0%");
  await expect(
    page.getByText("Actual investment performance is not available.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Read the investment policy" }).click();
  await expect(page).toHaveURL(`/client/documents/${reports.Alice}`);
  await expect(
    page.getByRole("heading", { name: "Alice investment policy" }),
  ).toBeVisible();
  await expect(
    page.getByText("It does not approve or execute any transactions.", {
      exact: false,
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Confirm I have read this document" })
    .click();
  await expect(page.getByRole("status")).toHaveText("Read confirmed");
  await page.reload();
  await expect(page.getByRole("status")).toHaveText("Read confirmed");
  await expect(
    page.getByRole("button", { name: "Confirm I have read this document" }),
  ).toHaveCount(0);
  const repeated = await context.request.post(
    `/api/me/reports/${reports.Alice}/acknowledge`,
  );
  expect(repeated.status()).toBe(200);
  expect(repeated.headers()["cache-control"]).toBe("no-store");
});

test("document pagination lists published versions and hides private revisions", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!);
  const response = await page.goto("/client/documents");
  await expect(
    page.getByRole("link", { name: /Alice investment policy/ }),
  ).toBeVisible();
  expect(await response!.text()).not.toContain("PRIVATE_DRAFT_CONTENT");
  await expect(page.getByRole("main")).not.toContainText("UNPUBLISHED");
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(page).toHaveURL(/offset=20$/);
  await expect(page.getByRole("link", { name: "Previous page" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Next page" })).toHaveCount(0);
});

test("forged selectors and copied document links cannot cross clients", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!);
  await page.goto(`/client?client_id=Bob&report_id=${reports.Bob}`);
  await expect(
    page.getByRole("heading", { name: "Welcome, Portal Alice" }),
  ).toBeVisible();
  for (const id of [reports.Bob, reports.AliceDraft]) {
    await page.goto(`/client/documents/${id}`);
    await expect(
      page.getByText("Document not available", { exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("main")).not.toContainText(
      "Bob investment policy",
    );
    expect(
      (
        await context.request.post(`/api/me/reports/${id}/acknowledge`, {
          data: { client_id: "Bob" },
        })
      ).status(),
    ).toBe(404);
  }
  await signIn(context, baseURL!, "Bob");
  await page.goto(`/client/documents/${reports.Bob}`);
  await expect(
    page.getByRole("heading", { name: "Bob investment policy" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Confirm I have read this document" }),
  ).toBeVisible();
  await page.goto(`/client/documents/${reports.Alice}`);
  await expect(
    page.getByText("Document not available", { exact: true }),
  ).toBeVisible();
});

test("advisor controls stay inaccessible and client mutations require the same origin", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!);
  for (const route of ["/optimizer", "/settings", "/profiles"]) {
    await page.goto(route);
    await expect(page).toHaveURL(/\/client$/);
  }
  for (const endpoint of [
    "/api/settings/llm",
    "/api/profiles/1",
    "/api/ips/not-accessible",
  ]) {
    expect((await context.request.get(endpoint)).status()).toBe(403);
  }
  expect(
    (
      await context.request.post(
        `/api/me/reports/${reports.Alice}/acknowledge`,
        { headers: { Origin: "https://foreign.invalid" } },
      )
    ).status(),
  ).toBe(403);
  expect(
    (
      await context.request.post("/api/me/assistant", {
        data: { message: "Read Bob's plan", client_id: "Bob" },
      })
    ).status(),
  ).toBe(422);
});

test("the client assistant uses the scoped demo endpoint and supports locale switching", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!);
  await page.goto("/client/ai");
  await page
    .getByRole("textbox", { name: "Your question" })
    .fill("Explain my own plan");
  const requested = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/me/assistant") &&
      request.method() === "POST",
  );
  await page.getByRole("button", { name: "Ask WealthPilot" }).click();
  expect((await requested).postDataJSON()).toEqual({
    message: "Explain my own plan",
  });
  await expect(page.getByText("Demo response", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Demo response: your assistant can explain", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "中文", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "您的问题" })).toBeVisible();
  await page
    .getByRole("textbox", { name: "您的问题" })
    .fill("请解读我的投资计划");
  await page.getByRole("button", { name: "询问 WealthPilot" }).click();
  await expect(page.getByText("演示回答", { exact: true })).toBeVisible();
  await expect(
    page.getByText("助手可解读您自己的画像", { exact: false }),
  ).toBeVisible();
});

test("empty goals, absent plans and incomplete risk assessments have explicit states", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!, "Empty");
  for (const [route, message] of [
    ["/client/portfolio", "No published investment plan yet"],
    ["/client/goals", "No goals recorded yet"],
    ["/client/risk-profile", "Assessment incomplete"],
  ]) {
    await page.goto(route);
    await expect(page.getByText(message, { exact: true })).toBeVisible();
  }
  await page.goto("/client/documents");
  await expect(
    page.getByText("No published documents yet", { exact: true }),
  ).toBeVisible();
});

test("mobile navigation and the selected locale persist across reloads", async ({
  page,
  context,
  baseURL,
}, testInfo) => {
  await signIn(context, baseURL!);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/client");
  await page.getByRole("button", { name: "中文", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "总览", exact: true }),
  ).toBeVisible();
  const documents = page
    .getByRole("navigation", { name: "客户导航" })
    .getByRole("link", { name: "文档", exact: true });
  await documents.scrollIntoViewIfNeeded();
  await documents.click();
  await expect(
    page.getByRole("heading", { name: "文档", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("navigation", { name: "客户导航" }),
  ).toBeVisible();
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "wp_locale")
      ?.value,
  ).toBe("zh");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("client-mobile-zh.png"),
    fullPage: true,
  });
});

test("an ambiguous client link does not choose or expose a profile", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!, "Ambiguous");
  await page.goto("/client");
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "Your client workspace is unavailable." }),
  ).toContainText("check your account link");
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(
    page.getByText("Portal Ambiguous", { exact: false }),
  ).toHaveCount(0);
});

test("membership removal closes an already-open client workspace", async ({
  page,
  context,
  baseURL,
}) => {
  await signIn(context, baseURL!, "Revoked");
  await page.goto("/client");
  await expect(
    page.getByRole("heading", { name: "Welcome, Portal Revoked" }),
  ).toBeVisible();
  execFileSync(
    "python",
    [
      "-c",
      `
import sys
from sqlmodel import Session, select
from api import db
with Session(db.engine) as session:
    membership = session.exec(select(db.OrganizationMembershipRecord).where(db.OrganizationMembershipRecord.user_id == sys.argv[1], db.OrganizationMembershipRecord.organization_id == sys.argv[2])).one()
    session.delete(membership)
    session.commit()
`,
      accounts.Revoked.userId,
      accounts.Revoked.organization,
    ],
    {
      cwd: path.resolve(__dirname, "../.."),
      env: {
        ...process.env,
        AIWP_DB_URL: `sqlite:///${process.env.AIWP_E2E_DB_FILE}`,
      },
    },
  );
  await page.reload();
  await expect(
    page.getByText("No workspace access. Contact your administrator.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByRole("navigation")).toHaveCount(0);
  await expect(page.getByText("Portal Revoked", { exact: false })).toHaveCount(
    0,
  );
});
