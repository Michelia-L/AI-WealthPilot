import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { monitoring } from "@/lib/i18n/dictionaries/en/monitoring";
import RebalanceAdvice from "./rebalance-advice";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ monitoring }),
}));
vi.mock("@/components/client-context", () => ({
  useClient: () => ({ clientId: 42, clientName: "Jane" }),
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

beforeEach(() => {
  fetchMock.mockReset();
});

describe("RebalanceAdvice", () => {
  it("starts from the empty state and streams reasoning + advice + usage", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        sseResponse([
          { type: "reasoning", text: "checking drift…" },
          { type: "token", text: "Rebalance " },
          { type: "token", text: "bonds now." },
          {
            type: "done",
            model: "deepseek-reasoner",
            prompt_tokens: 120,
            completion_tokens: 30,
            total_tokens: 150,
            reasoning_tokens: 45,
          },
        ])
      )
    );

    render(<RebalanceAdvice documentId="doc-1" />);
    expect(
      screen.getByText("Let AI interpret this monitoring snapshot")
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Generate Advice" }));

    expect(await screen.findByTestId("reasoning")).toHaveTextContent(
      "checking drift…"
    );
    expect((await screen.findByTestId("markdown")).textContent).toBe(
      "Rebalance bonds now."
    );
    // usage line: model · prompt + completion = total tokens
    expect(
      await screen.findByText(/deepseek-reasoner · 120 \+ 30 = 150 tokens/)
    ).toBeInTheDocument();
    // done → the button switches to regenerate
    expect(
      screen.getByRole("button", { name: "Regenerate" })
    ).toBeInTheDocument();

    // request carries the document and the global client id
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/monitoring/advice");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      document_id: "doc-1",
      profile_id: 42,
    });
  });

  it("shows an error event and re-arms the button", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(
        sseResponse([
          { type: "token", text: "partial" },
          { type: "error", message: "stream broke" },
        ])
      )
    );
    render(<RebalanceAdvice documentId="doc-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Generate Advice" }));

    expect(await screen.findByText("stream broke")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Regenerate" })
    ).toBeInTheDocument();
  });

  it("surfaces a non-OK response as an error", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: "monitoring unavailable" }, 503))
    );
    render(<RebalanceAdvice documentId="doc-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Generate Advice" }));

    expect(
      await screen.findByText("monitoring unavailable")
    ).toBeInTheDocument();
  });
});
