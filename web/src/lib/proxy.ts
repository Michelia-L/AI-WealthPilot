import { NextResponse } from "next/server";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

/**
 * Shared same-origin proxy for POST mutations. The browser only talks to
 * the Next.js server; API_ORIGIN stays server-side (no CORS, no leaked
 * internal URLs).
 */
export async function proxyPost(path: string, body: unknown) {
  try {
    const res = await fetch(`${API_ORIGIN}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "API 服务不可达，请确认后端已启动。" },
      { status: 502 }
    );
  }
}
