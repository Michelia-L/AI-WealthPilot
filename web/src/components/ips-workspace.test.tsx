import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AdvisorStatusResponse, ProfileSummary } from "@/lib/api";
import { common } from "@/lib/i18n/dictionaries/en/common";
import { ips } from "@/lib/i18n/dictionaries/en/ips";
import IpsWorkspace from "./ips-workspace";

// Real English dictionary for copy; heavy/irrelevant children stubbed out.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ ips, common }),
  useLocale: () => ({ locale: "en" }),
}));
vi.mock("@/components/client-context", () => ({
  useClient: () => ({ clientId: null, clientName: null, select: vi.fn() }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));
vi.mock("@/components/markdown", () => ({
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="markdown">{children}</div>
  ),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const PROFILES = [
  { id: 1, name: "Jane Doe", age: 40, risk_level: "Balanced / 平衡型" } as ProfileSummary,
];
const STATUS = { configured: true, demo: false } as AdvisorStatusResponse;

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

function mockGenerateFlow(events: Record<string, unknown>[]) {
  fetchMock.mockImplementation((url: string) => {
    if (url.includes("/ips/generate")) {
      return Promise.resolve(jsonResponse({ task_id: "t-1" }, 202));
    }
    if (url.includes("/ips/tasks/")) {
      return Promise.resolve(sseResponse(events));
    }
    if (url.includes("/api/ips/")) {
      return Promise.resolve(jsonResponse({ markdown: "# IPS body" }));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  sessionStorage.clear();
});

describe("IpsWorkspace generation flow", () => {
  it("runs the workflow: node steps, done card, task handle released", async () => {
    mockGenerateFlow([
      { type: "node", node: "profiler", label: "Client Profiling" },
      { type: "node", node: "cme", label: "Capital Market Expectations" },
      {
        type: "done",
        document_id: "ips_abc",
        status: "draft",
        revision_count: 1,
      },
    ]);
    render(
      <IpsWorkspace profiles={PROFILES} status={STATUS} initialDocuments={[]} />
    );

    fireEvent.click(screen.getByRole("button", { name: "Generate IPS" }));

    expect(await screen.findByText("Client Profiling")).toBeInTheDocument();
    expect(screen.getByText("Capital Market Expectations")).toBeInTheDocument();
    expect(await screen.findByText(/ips_abc/)).toBeInTheDocument();
    // done releases the sessionStorage handle
    expect(sessionStorage.getItem("wealthpilot:active-task:ips")).toBeNull();

    // View Now loads the document into the viewer panel
    fireEvent.click(screen.getByRole("button", { name: "View Now" }));
    expect(await screen.findByTestId("markdown")).toHaveTextContent("IPS body");
  });

  it("shows the error message and re-arms the form on an error event", async () => {
    mockGenerateFlow([
      { type: "node", node: "profiler", label: "Client Profiling" },
      { type: "error", message: "LLM exploded" },
    ]);
    render(
      <IpsWorkspace profiles={PROFILES} status={STATUS} initialDocuments={[]} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate IPS" }));

    expect(await screen.findByText("LLM exploded")).toBeInTheDocument();
    // running released — the generate button is clickable again
    expect(
      screen.getByRole("button", { name: "Generate IPS" })
    ).not.toBeDisabled();
  });

  it("surfaces a 503 from task creation without opening an SSE stream", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/ips/generate")) {
        return Promise.resolve(jsonResponse({ detail: "no api key" }, 503));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });
    render(
      <IpsWorkspace profiles={PROFILES} status={STATUS} initialDocuments={[]} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate IPS" }));

    expect(await screen.findByText("no api key")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) => (url as string).includes("/tasks/"))
    ).toBe(false);
  });
});

describe("IpsWorkspace task resume", () => {
  it("reconnects to a stored task on mount and replays its progress", async () => {
    sessionStorage.setItem("wealthpilot:active-task:ips", "t-9");
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/ips/tasks/t-9/events")) {
        return Promise.resolve(
          sseResponse([
            { type: "node", node: "draft", label: "Drafting" },
            {
              type: "done",
              document_id: "ips_9",
              status: "approved",
              revision_count: 0,
            },
          ])
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    render(
      <IpsWorkspace profiles={PROFILES} status={STATUS} initialDocuments={[]} />
    );

    expect(await screen.findByText("Drafting")).toBeInTheDocument();
    expect(await screen.findByText(/ips_9/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([url]) =>
        (url as string).includes("/ips/tasks/t-9/events")
      )
    ).toBe(true);
  });
});

describe("IpsWorkspace guards", () => {
  it("renders the empty-profiles hint and no generate button", () => {
    render(<IpsWorkspace profiles={[]} status={STATUS} initialDocuments={[]} />);
    expect(screen.getByText(/No client profiles yet/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Generate IPS" })
    ).not.toBeInTheDocument();
  });

  it("warns when the profile list is unreachable", () => {
    render(<IpsWorkspace profiles={null} status={STATUS} initialDocuments={[]} />);
    expect(screen.getByText(/make sure the API service is running/)).toBeInTheDocument();
  });

  it("shows the not-configured banner and disables generation", () => {
    render(
      <IpsWorkspace
        profiles={PROFILES}
        status={{ configured: false, demo: false } as AdvisorStatusResponse}
        initialDocuments={[]}
      />
    );
    expect(screen.getByText(/not configured/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generate IPS" })).toBeDisabled();
  });
});
