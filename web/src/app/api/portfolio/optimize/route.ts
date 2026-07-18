import { NextResponse } from "next/server";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

/**
 * Same-origin proxy for the optimization endpoint. The browser only talks
 * to the Next.js server; API_ORIGIN stays server-side (no CORS, no leaked
 * internal URLs).
 */
export async function POST(request: Request) {
  const body = await request.json();
  try {
    const res = await fetch(`${API_ORIGIN}/api/portfolio/optimize`, {
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
