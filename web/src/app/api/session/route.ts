import { hasSameOrigin } from "@/lib/request-origin";
import { NextRequest, NextResponse } from "next/server";
import { API_ORIGIN, SESSION_COOKIE, ORGANIZATION_COOKIE, getSessionHeaders, getWorkspaceSession } from "@/lib/session";
import { getDict, getLocale } from "@/lib/i18n/server";

export async function POST(request: NextRequest) {
  const t = await getDict();
  const fail = (status: number) => NextResponse.json({ detail: t.auth.failed }, { status, headers: { "Cache-Control": "no-store" } });
  // Also checked by Proxy; keep the credential-setting handler safe in isolation.
  if (!hasSameOrigin(request)) return fail(403);
  let body;
  try { body = await request.json(); } catch { return fail(400); }
  if (!body || typeof body !== "object") return fail(400);
  const response = NextResponse.json({ ok: true }, { headers: { "Cache-Control": "no-store" } });
  const options = { httpOnly: true, secure: new URL(request.url).protocol === "https:", sameSite: "lax" as const, path: "/" };
  try {
    if (body.action === "organization") {
      const session = await getWorkspaceSession();
      if (!session) return fail(401);
      if (!session.organizations.some((org) => org.id === body.organization_id)) return fail(403);
      response.cookies.set(ORGANIZATION_COOKIE, body.organization_id, options);
    } else if (body.action === "logout") {
      const upstream = await fetch(`${API_ORIGIN}/api/auth/logout`, { method: "POST", headers: await getSessionHeaders(), cache: "no-store" });
      if (!upstream.ok && upstream.status !== 401) return fail(upstream.status);
      response.cookies.set(SESSION_COOKIE, "", { ...options, maxAge: 0 });
      response.cookies.set(ORGANIZATION_COOKIE, "", { ...options, maxAge: 0 });
    } else if (body.action === "login" || body.action === "demo") {
      const upstream = await fetch(`${API_ORIGIN}/api/auth/${body.action}`, {
        method: "POST", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-Locale": await getLocale() },
        body: body.action === "login" ? JSON.stringify({ email: body.email, password: body.password }) : undefined,
      });
      if (!upstream.ok) return fail(upstream.status);
      const data = await upstream.json();
      response.cookies.set(SESSION_COOKIE, data.access_token, { ...options, expires: new Date(data.expires_at) });
      response.cookies.set(ORGANIZATION_COOKIE, "", { ...options, maxAge: 0 });
    } else return fail(400);
    return response;
  } catch { return fail(502); }
}
