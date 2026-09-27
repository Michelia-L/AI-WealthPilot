import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/components/locale-context";
import DeleteDeliverableButton from "./delete-deliverable-button";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const fetchMock = vi.fn();

beforeEach(() => {
  refresh.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

function renderButton(kind: "ips" | "advisor" = "ips", locale: "en" | "zh" = "en") {
  const onDeleted = vi.fn();
  render(
    <LocaleProvider locale={locale}>
      <DeleteDeliverableButton kind={kind} id="ips_测试 #1" clientName="Jane" onDeleted={onDeleted} />
    </LocaleProvider>
  );
  return onDeleted;
}

it("cancels without deleting", () => {
  renderButton();
  fireEvent.click(screen.getByRole("button", { name: "Delete document for Jane" }));
  expect(screen.getByRole("dialog")).toHaveTextContent("client acknowledgements");
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

it.each(["ips", "advisor"] as const)("deletes %s once and refreshes after success", async (kind) => {
  let finish!: (response: Response) => void;
  fetchMock.mockReturnValue(new Promise<Response>((resolve) => { finish = resolve; }));
  const onDeleted = renderButton(kind);
  const trigger = screen.getByRole("button", { name: "Delete document for Jane" });
  fireEvent.click(trigger);
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
  expect(trigger).toBeDisabled();
  fireEvent.click(trigger);
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith(
    `${kind === "ips" ? "/api/ips" : "/api/advisor/reports"}/${encodeURIComponent("ips_测试 #1")}`,
    { method: "DELETE" }
  );
  expect(refresh).not.toHaveBeenCalled();
  await act(async () => finish(new Response(null, { status: 204 })));
  expect(onDeleted).toHaveBeenCalledOnce();
  expect(refresh).toHaveBeenCalledOnce();
});

it.each([
  ["en", "Delete document for Jane", "Delete", "Could not delete the document. Please try again."],
  ["zh", "删除 Jane 的文档", "删除", "无法删除文档，请重试。"],
] as const)("shows a localized fallback and allows retry (%s)", async (locale, label, confirm, message) => {
  fetchMock.mockResolvedValue(new Response("unavailable", { status: 502 }));
  const onDeleted = renderButton("ips", locale);
  fireEvent.click(screen.getByRole("button", { name: label }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: confirm }));
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(onDeleted).not.toHaveBeenCalled();
  expect(refresh).not.toHaveBeenCalled();
  await waitFor(() => expect(screen.getByRole("button", { name: label })).not.toBeDisabled());
});

it("shows the API error and keeps the document", async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "IPS document not found." }), { status: 404 }));
  const onDeleted = renderButton();
  fireEvent.click(screen.getByRole("button", { name: "Delete document for Jane" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("IPS document not found.");
  expect(onDeleted).not.toHaveBeenCalled();
});
