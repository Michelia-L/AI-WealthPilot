import { beforeEach, describe, expect, it, vi } from "vitest";
import { proxyDelete, proxyGet, proxyPost, proxyStream } from "./proxy";

// The proxy module resolves locale/dictionaries via next/headers — mock the
// whole server module so tests stay request-context free.
vi.mock("@/lib/i18n/server", () => ({
  getLocale: vi.fn(async () => "zh"),
  getDict: vi.fn(async () => ({
    errors: {
      apiUnreachable: "API 服务不可达",
      upstreamError: (status: number) => `上游服务错误（HTTP ${status}）`,
    },
  })),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
});

describe("proxyJson", () => {
  it("forwards the JSON body and injects X-Locale", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }, 201));
    const res = await proxyPost("/api/profiles", { name: "Jane" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/profiles");
    expect(init.method).toBe("POST");
    expect(init.headers["X-Locale"]).toBe("zh");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ name: "Jane" });

    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ ok: true });
  });

  it("omits Content-Type on bodyless GET but keeps X-Locale", async () => {
    fetchMock.mockResolvedValue(jsonResponse([1, 2]));
    await proxyGet("/api/profiles");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers["X-Locale"]).toBe("zh");
    expect(init.headers["Content-Type"]).toBeUndefined();
  });

  it("returns the localized 502 when the API is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await proxyGet("/api/health");
    expect(res.status).toBe(502);
    expect(await res.json()).toEqual({ detail: "API 服务不可达" });
  });

  it("passes a 204 delete through with no body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await proxyDelete("/api/profiles/1");
    expect(res.status).toBe(204);
  });
});

describe("proxyStream", () => {
  it("pipes the upstream body through as text/event-stream", async () => {
    const sseBody = new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode('data: {"a":1}\n\n'));
        c.close();
      },
    });
    fetchMock.mockResolvedValue(new Response(sseBody, { status: 200 }));
    const res = await proxyStream("/api/advisor/stream", { q: 1 });
    expect(res.status).toBe(200);
    expect(res.headers.get("Content-Type")).toBe("text/event-stream");
    expect(await res.text()).toBe('data: {"a":1}\n\n');
  });

  it("forwards upstream errors as JSON instead of streaming", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "bad request" }, 422));
    const res = await proxyStream("/api/advisor/stream", {});
    expect(res.status).toBe(422);
    expect(await res.json()).toEqual({ detail: "bad request" });
  });

  it("falls back to a localized message for non-JSON error bodies", async () => {
    fetchMock.mockResolvedValue(new Response("boom", { status: 500 }));
    const res = await proxyStream("/api/advisor/stream", {});
    expect(res.status).toBe(500);
    expect(await res.json()).toEqual({ detail: "上游服务错误（HTTP 500）" });
  });
});
