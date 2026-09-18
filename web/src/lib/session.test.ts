import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { getSessionHeaders, getWorkspaceSession } from "./session";
import { POST } from "@/app/api/session/route";
import { proxy } from "@/proxy";

const { cookieValues } = vi.hoisted(() => ({ cookieValues: new Map<string, string>() }));
vi.mock("next/headers", () => ({ cookies: async () => ({ get: (name: string) => cookieValues.has(name) ? { value: cookieValues.get(name) } : undefined }) }));
vi.mock("@/lib/i18n/server", () => ({ getLocale: async () => "en", getDict: async () => ({ auth: { failed: "Request failed" } }) }));
const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);
function request(body: unknown, origin = "http://localhost:3000") {
  return new NextRequest("http://localhost:3000/api/session", { method: "POST", headers: { origin, "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function json(body: unknown, status = 200) { return new Response(JSON.stringify(body), { status }); }
beforeEach(() => { cookieValues.clear(); fetchMock.mockReset(); });

describe("server sessions", () => {
  it("forwards only session and workspace cookies", async () => {
    expect(await getSessionHeaders()).toEqual({});
    cookieValues.set("wp_session", "test-session");
    cookieValues.set("wp_organization", "a");
    expect(await getSessionHeaders()).toEqual({ Authorization: "Bearer test-session", "X-Organization-ID": "a" });
  });
  it("resolves scope from current memberships, never an unvalidated cookie", async () => {
    cookieValues.set("wp_session", "test-session");
    cookieValues.set("wp_organization", "foreign");
    fetchMock.mockResolvedValueOnce(json({ organizations: [{ id: "a", name: "A", role: "client" }, { id: "b", name: "B", role: "advisor" }] }));
    expect((await getWorkspaceSession())?.organizationId).toBeNull();
    expect(fetchMock.mock.calls[0][1].cache).toBe("no-store");
    fetchMock.mockResolvedValueOnce(json({}, 401));
    expect(await getWorkspaceSession()).toBeNull();
  });
  it("keeps login bearer tokens out of the response body and client-readable cookies", async () => {
    fetchMock.mockResolvedValueOnce(json({ access_token: "test-session", expires_at: "2030-01-01T00:00:00Z" }));
    const response = await POST(request({ action: "login", email: "fixture@example.invalid", password: "test-password" }));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ ok: true });
    expect(response.cookies.get("wp_session")?.httpOnly).toBe(true);
    expect(response.cookies.get("wp_session")?.sameSite).toBe("lax");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(fetchMock.mock.calls[0][0]).toBe("http://localhost:8000/api/auth/login");
  });
  it("does not relay an upstream error or submitted password", async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: "private input" }, 422));
    const response = await POST(request({ action: "login", password: "private input" }));
    expect(response.status).toBe(422);
    expect(await response.text()).not.toContain("private input");
    expect(response.cookies.get("wp_session")).toBeUndefined();
  });
  it("rejects foreign workspace selection", async () => {
    cookieValues.set("wp_session", "test-session");
    fetchMock.mockResolvedValueOnce(json({ organizations: [{ id: "a", name: "A", role: "admin" }] }));
    const response = await POST(request({ action: "organization", organization_id: "b" }));
    expect(response.status).toBe(403);
    expect(response.cookies.get("wp_organization")).toBeUndefined();
  });
  it("compares against Host when Next normalizes loopback URLs", () => {
    const normalized = new NextRequest("http://localhost:3300/api/profiles", {
      method: "POST", headers: { host: "127.0.0.1:3300", origin: "http://127.0.0.1:3300" },
    });
    expect(proxy(normalized).status).toBe(200);
    normalized.headers.set("origin", "http://localhost:3300");
    expect(proxy(normalized).status).toBe(403);
  });
  it("rejects missing or foreign origins before issuing credentials", async () => {
    for (const origin of ["", "https://foreign.invalid", "null"]) {
      expect((await POST(request({ action: "demo" }, origin))).status).toBe(403);
      expect(proxy(request({ action: "demo" }, origin)).status).toBe(403);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("revokes before clearing cookies, and retains the cookie if revocation fails", async () => {
    cookieValues.set("wp_session", "test-session");
    fetchMock.mockResolvedValueOnce(json({}, 503));
    const failed = await POST(request({ action: "logout" }));
    expect(failed.cookies.get("wp_session")).toBeUndefined();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    const response = await POST(request({ action: "logout" }));
    expect(response.cookies.get("wp_session")?.maxAge).toBe(0);
    expect(response.cookies.get("wp_organization")?.maxAge).toBe(0);
    expect(fetchMock.mock.calls[1][1].headers.Authorization).toBe("Bearer test-session");
  });
});
