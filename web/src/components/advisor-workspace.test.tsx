import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdvisorStatusResponse, ProfileSummary, ReportSummary } from "@/lib/api";
import { advisor } from "@/lib/i18n/dictionaries/en/advisor";
import { common } from "@/lib/i18n/dictionaries/en/common";
import AdvisorWorkspace from "./advisor-workspace";

// Real English dictionary for copy; heavy children stubbed out.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ advisor, common }),
  useLocale: () => ({ locale: "en" }),
}));
vi.mock("@/components/client-context", () => ({
  useClient: () => ({ clientId: null, clientName: null, select: vi.fn() }),
}));
const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: refreshMock }),
}));
vi.mock("@/components/markdown", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="markdown">{children}</div>
  ),
}));
vi.mock("@/components/reasoning-section", () => ({
  default: ({ text }: { text: string }) => (
    <div data-testid="reasoning">{text}</div>
  ),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const PROFILES = [
  { id: 1, name: "Jane Doe", age: 40, risk_level: "Balanced / 平衡型" } as ProfileSummary,
];
const STATUS = {
  configured: true,
  demo: false,
  model: "deepseek-reasoner",
} as AdvisorStatusResponse;
const REPORTS = [
  {
    report_id: "r-1",
    client_name: "Jane Doe",
    model: "deepseek-reasoner",
    generated_at: "2026-08-14T10:00:00",
    total_tokens: 1500,
  } as ReportSummary,
];

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

/** A real SSE body — exercises the actual readSseStream parsing chain. */
function sseResponse(events: Record<string, unknown>[], status = 200): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    }),
    { status }
  );
}

const DONE_EVENT = {
  type: "done",
  success: true,
  model: "deepseek-reasoner",
  prompt_tokens: 100,
  completion_tokens: 50,
  reasoning_tokens: 20,
  total_tokens: 150,
};

beforeEach(() => {
  fetchMock.mockReset();
  refreshMock.mockClear();
});

describe("AdvisorWorkspace streaming", () => {
  it("streams reasoning + tokens, then saves the report to the library", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/advisor/report/stream")) {
        return Promise.resolve(
          sseResponse([
            { type: "reasoning", text: "thinking…" },
            { type: "token", text: "Hello " },
            { type: "token", text: "world" },
            DONE_EVENT,
          ])
        );
      }
      if (url.includes("/advisor/reports")) {
        return Promise.resolve(jsonResponse({ report_id: "r-2" }, 201));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    render(
      <AdvisorWorkspace profiles={PROFILES} status={STATUS} initialReports={[]} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate Proposal" }));

    // reasoning streams into the reasoning section, tokens into the body
    expect(await screen.findByTestId("reasoning")).toHaveTextContent("thinking…");
    expect((await screen.findByTestId("markdown")).textContent).toBe("Hello world");
    // token summary + save form appear on done
    expect(await screen.findByText(/150/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save to Report Library" }));
    expect(await screen.findByText("Saved to report library")).toBeInTheDocument();

    const saveCall = fetchMock.mock.calls.find(
      ([url, init]) =>
        (url as string) === "/api/advisor/reports" &&
        (init as RequestInit)?.method === "POST"
    )!;
    const body = JSON.parse((saveCall[1] as RequestInit).body as string);
    expect(body).toMatchObject({
      client_name: "Jane Doe",
      content: "Hello world",
      model: "deepseek-reasoner",
    });
    expect(refreshMock).toHaveBeenCalled();
  });

  it("shows an error event and re-arms the generate button", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/advisor/report/stream")) {
        return Promise.resolve(
          sseResponse([
            { type: "token", text: "partial" },
            { type: "error", message: "upstream timeout" },
          ])
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    render(
      <AdvisorWorkspace profiles={PROFILES} status={STATUS} initialReports={[]} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate Proposal" }));

    expect(await screen.findByText("upstream timeout")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Generate Proposal" })
    ).not.toBeDisabled();
  });

  it("flags an unsuccessful done event as a validation failure", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/advisor/report/stream")) {
        return Promise.resolve(
          sseResponse([
            { type: "token", text: "draft" },
            { ...DONE_EVENT, success: false, error_message: "schema mismatch" },
          ])
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    render(
      <AdvisorWorkspace profiles={PROFILES} status={STATUS} initialReports={[]} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate Proposal" }));

    expect(await screen.findByText("schema mismatch")).toBeInTheDocument();
    // no save form for a failed generation
    expect(
      screen.queryByRole("button", { name: "Save to Report Library" })
    ).not.toBeInTheDocument();
  });
});

describe("AdvisorWorkspace report library", () => {
  it("deletes a report through the confirm dialog", async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes("/advisor/reports/") && init?.method === "DELETE") {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    render(
      <AdvisorWorkspace profiles={PROFILES} status={STATUS} initialReports={REPORTS} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete report" }));
    // ConfirmDialog opens
    expect(screen.getByText("Delete this report?")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url, init]) =>
            (url as string) === "/api/advisor/reports/r-1" &&
            (init as RequestInit)?.method === "DELETE"
        )
      ).toBe(true)
    );
    expect(refreshMock).toHaveBeenCalled();
  });

  it("loads a report into the viewer", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/advisor/reports/r-1")) {
        return Promise.resolve(
          jsonResponse({
            client_name: "Jane Doe",
            generated_at: "2026-08-14T10:00:00",
            content: "stored proposal",
          })
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    render(
      <AdvisorWorkspace profiles={PROFILES} status={STATUS} initialReports={REPORTS} />
    );
    fireEvent.click(screen.getByRole("button", { name: "View report" }));
    expect(await screen.findByTestId("markdown")).toHaveTextContent(
      "stored proposal"
    );
  });
});

describe("AdvisorWorkspace guards", () => {
  it("renders the empty-profiles hint and no generate button", () => {
    render(<AdvisorWorkspace profiles={[]} status={STATUS} initialReports={[]} />);
    expect(screen.getByText(/No client profiles/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Generate Proposal" })
    ).not.toBeInTheDocument();
  });

  it("disables generation when the LLM is not configured", () => {
    render(
      <AdvisorWorkspace
        profiles={PROFILES}
        status={{ configured: false, demo: false, model: "—" } as AdvisorStatusResponse}
        initialReports={[]}
      />
    );
    expect(screen.getByRole("button", { name: "Generate Proposal" })).toBeDisabled();
  });
});
