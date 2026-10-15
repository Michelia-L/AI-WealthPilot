import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  getClientAdvisors,
  getClientGoals,
  getClientIdentity,
  getClientPortfolio,
  getClientProfile,
  getClientReport,
  getClientReports,
  getClientRisk,
} from "./client-portal-server";
import { POST as ask } from "@/app/api/me/assistant/route";
import { POST as acknowledge } from "@/app/api/me/reports/[id]/acknowledge/route";
import { NextRequest } from "next/server";
import { en } from "@/lib/i18n/dictionaries/en";

vi.mock("../session", () => ({
  API_ORIGIN: "http://backend.invalid",
  getSessionHeaders: async () => ({
    Authorization: "Bearer fixture",
    "X-Organization-ID": "workspace",
  }),
}));
vi.mock("@/lib/i18n/server", () => ({
  getLocale: async () => "zh",
  getDict: async () => en,
}));
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

describe("client reads", () => {
  it.each([
    [getClientIdentity, ""],
    [getClientProfile, "/profile"],
    [getClientPortfolio, "/portfolio"],
    [getClientGoals, "/goals"],
    [getClientRisk, "/risk-profile"],
    [getClientAdvisors, "/advisor"],
  ] as const)(
    "uses the authenticated scope and explicit locale (%s)",
    async (read, suffix) => {
      fetchMock.mockResolvedValue(
        new Response(JSON.stringify({ allowed: true })),
      );
      expect((await read("zh")).data).toEqual({ allowed: true });
      expect(fetchMock).toHaveBeenCalledWith(
        `http://backend.invalid/api/me${suffix}`,
        {
          cache: "no-store",
          headers: {
            Authorization: "Bearer fixture",
            "X-Organization-ID": "workspace",
            "X-Locale": "zh",
          },
        },
      );
    },
  );
  it("preserves document pagination and encodes version IDs", async () => {
    fetchMock.mockImplementation(async () => new Response("{}"));
    await getClientReports("en", 20, 20);
    expect(fetchMock.mock.calls[0][0]).toBe(
      "http://backend.invalid/api/me/reports?limit=20&offset=20",
    );
    await getClientReport("version?client_id=foreign/1", "en");
    expect(fetchMock.mock.calls[1][0]).toBe(
      `http://backend.invalid/api/me/reports/${encodeURIComponent("version?client_id=foreign/1")}`,
    );
  });
  it.each([401, 404, 409, 503])(
    "preserves HTTP %s without forwarding upstream error text",
    async (status) => {
      fetchMock.mockResolvedValue(
        new Response(JSON.stringify({ detail: "private upstream context" }), {
          status,
        }),
      );
      expect(await getClientReport("missing", "en")).toEqual({
        data: null,
        status,
      });
    },
  );
  it("distinguishes network failure from a missing document", async () => {
    fetchMock.mockRejectedValue(new TypeError("private upstream context"));
    expect(await getClientReport("missing", "en")).toEqual({
      data: null,
      status: 502,
    });
  });
});

describe("client mutations", () => {
  it("forwards questions through the existing session and locale proxy", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ answer: "Reply", demo: false })),
    );
    const response = await ask(
      new NextRequest("http://localhost/api/me/assistant", {
        method: "POST",
        body: JSON.stringify({ message: "My plan" }),
      }),
    );
    expect(response.status).toBe(200);
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/me\/assistant$/);
    expect(options.headers.Authorization).toBe("Bearer fixture");
    expect(options.headers["X-Locale"]).toBe("zh");
    expect(JSON.parse(options.body)).toEqual({ message: "My plan" });
    expect(response.headers.get("cache-control")).toBe("no-store");
  });
  it("rejects malformed JSON without sending a request to the backend", async () => {
    const response = await ask(
      new NextRequest("http://localhost/api/me/assistant", {
        method: "POST",
        body: "{",
      }),
    );
    expect(response.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("cannot turn a document ID into a different endpoint or forward a forged selector", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
    );
    const id = "version?client_id=foreign/1";
    const response = await acknowledge(
      new Request(
        "http://localhost/api/me/reports/1/acknowledge?client_id=foreign",
        { method: "POST", body: JSON.stringify({ client_id: "foreign" }) },
      ),
      { params: Promise.resolve({ id }) },
    );
    expect(response.status).toBe(404);
    expect(fetchMock.mock.calls[0][0]).toMatch(
      `/api/me/reports/${encodeURIComponent(id)}/acknowledge`,
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
  });
});
