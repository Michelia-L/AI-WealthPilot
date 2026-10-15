import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/components/locale-context";
import ClientAssistant from "./assistant";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
const fetchMock = vi.fn();
beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

it("sends a single question through the client endpoint and identifies a demo answer", async () => {
  let complete!: (response: Response) => void;
  fetchMock.mockReturnValue(
    new Promise<Response>((resolve) => {
      complete = resolve;
    }),
  );
  render(
    <LocaleProvider locale="en">
      <ClientAssistant />
    </LocaleProvider>,
  );
  const submit = screen.getByRole("button", { name: "Ask WealthPilot" });
  expect(submit).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Your question" }), {
    target: { value: "  Explain my plan  " },
  });
  fireEvent.click(submit);
  fireEvent.click(submit);
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock).toHaveBeenCalledWith("/api/me/assistant", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: "Explain my plan" }),
  });
  expect(screen.getByRole("status")).toHaveTextContent("Preparing your answer");
  await act(async () =>
    complete(
      new Response(
        JSON.stringify({ answer: "Your suggested allocation", demo: true }),
      ),
    ),
  );
  expect(await screen.findByText("Your suggested allocation")).toBeVisible();
  expect(screen.getByText("Demo response")).toBeVisible();
});

it.each([
  ["en", "Your question", "Ask WealthPilot", "The assistant could not answer."],
  ["zh", "您的问题", "询问 WealthPilot", "助手暂时无法回答"],
] as const)(
  "retains the question and permits retry after a failure (%s)",
  async (locale, label, action, error) => {
    fetchMock.mockRejectedValueOnce(new TypeError("network"));
    render(
      <LocaleProvider locale={locale}>
        <ClientAssistant />
      </LocaleProvider>,
    );
    fireEvent.change(screen.getByRole("textbox", { name: label }), {
      target: { value: "My question" },
    });
    fireEvent.click(screen.getByRole("button", { name: action }));
    expect(await screen.findByRole("alert")).toHaveTextContent(error);
    expect(screen.getByRole("textbox")).toHaveValue("My question");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: action })).toBeEnabled(),
    );
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({ answer: "Answer after retry", demo: false }),
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: action }));
    expect(await screen.findByText("Answer after retry")).toBeVisible();
    expect(screen.queryByRole("alert")).toBeNull();
  },
);
