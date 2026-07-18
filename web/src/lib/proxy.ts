import { NextResponse } from "next/server";

const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8000";

/**
 * Shared same-origin proxy for mutations. The browser only talks to the
 * Next.js server; API_ORIGIN stays server-side (no CORS, no leaked
 * internal URLs).
 */
export async function proxyJson(
  path: string,
  method: "GET" | "POST" | "PUT" | "DELETE",
  body?: unknown
) {
  try {
    const res = await fetch(`${API_ORIGIN}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    // 204 No Content (deletes) has no body to parse.
    if (res.status === 204) return new NextResponse(null, { status: 204 });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch {
    return NextResponse.json(
      { detail: "API 服务不可达，请确认后端已启动。" },
      { status: 502 }
    );
  }
}

export const proxyGet = (path: string) => proxyJson(path, "GET");
export const proxyPost = (path: string, body: unknown) => proxyJson(path, "POST", body);
export const proxyPut = (path: string, body: unknown) => proxyJson(path, "PUT", body);
export const proxyDelete = (path: string) => proxyJson(path, "DELETE");

/**
 * Streaming proxy for SSE endpoints. Unlike proxyJson this never buffers:
 * the upstream body is piped straight through so tokens reach the browser
 * as they arrive. Error responses (JSON) are forwarded as usual.
 */
export async function proxyStream(path: string, body: unknown) {
  try {
    const res = await fetch(`${API_ORIGIN}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!res.ok || !res.body) {
      const data = await res
        .json()
        .catch(() => ({ detail: `上游服务错误（HTTP ${res.status}）` }));
      return NextResponse.json(data, { status: res.status });
    }
    return new Response(res.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "API 服务不可达，请确认后端已启动。" },
      { status: 502 }
    );
  }
}

/** Streaming proxy for GET SSE endpoints (task progress feeds). */
export async function proxyStreamGet(path: string) {
  try {
    const res = await fetch(`${API_ORIGIN}${path}`, { cache: "no-store" });
    if (!res.ok || !res.body) {
      const data = await res
        .json()
        .catch(() => ({ detail: `上游服务错误（HTTP ${res.status}）` }));
      return NextResponse.json(data, { status: res.status });
    }
    return new Response(res.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "API 服务不可达，请确认后端已启动。" },
      { status: 502 }
    );
  }
}

/**
 * Binary download proxy (PDF export). Streams the upstream body through
 * untouched — parsing it as JSON (proxyGet) would corrupt the file.
 * Content-Type / Content-Disposition are forwarded from the API.
 */
export async function proxyFile(path: string) {
  try {
    const res = await fetch(`${API_ORIGIN}${path}`, { cache: "no-store" });
    if (!res.ok || !res.body) {
      const data = await res
        .json()
        .catch(() => ({ detail: `上游服务错误（HTTP ${res.status}）` }));
      return NextResponse.json(data, { status: res.status });
    }
    return new Response(res.body, {
      status: 200,
      headers: {
        "Content-Type": res.headers.get("Content-Type") ?? "application/octet-stream",
        "Content-Disposition": res.headers.get("Content-Disposition") ?? "attachment",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: "API 服务不可达，请确认后端已启动。" },
      { status: 502 }
    );
  }
}
