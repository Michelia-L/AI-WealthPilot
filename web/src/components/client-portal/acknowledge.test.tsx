import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/components/locale-context";
import AcknowledgeDocument from "./acknowledge";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const fetchMock = vi.fn();
beforeEach(() => {
  refresh.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

it("confirms only once through the scoped endpoint and refreshes after success", async () => {
  let complete!: (response: Response) => void;
  fetchMock.mockReturnValue(
    new Promise<Response>((resolve) => {
      complete = resolve;
    }),
  );
  render(
    <LocaleProvider locale="en">
      <AcknowledgeDocument id="version 测试/1" acknowledged={false} />
    </LocaleProvider>,
  );
  const button = screen.getByRole("button", {
    name: "Confirm I have read this document",
  });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(fetchMock).toHaveBeenCalledOnce();
  expect(fetchMock).toHaveBeenCalledWith(
    `/api/me/reports/${encodeURIComponent("version 测试/1")}/acknowledge`,
    { method: "POST" },
  );
  expect(refresh).not.toHaveBeenCalled();
  await act(async () =>
    complete(new Response(JSON.stringify({ status: "acknowledged" }))),
  );
  expect(await screen.findByRole("status")).toHaveTextContent("Read confirmed");
  expect(refresh).toHaveBeenCalledOnce();
  expect(screen.queryByRole("button")).toBeNull();
});

it("does not claim success after a rejected acknowledgement", async () => {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ detail: "Document not found." }), {
      status: 404,
    }),
  );
  render(
    <LocaleProvider locale="en">
      <AcknowledgeDocument id="missing" acknowledged={false} />
    </LocaleProvider>,
  );
  fireEvent.click(screen.getByRole("button"));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Document not found.",
  );
  expect(screen.queryByRole("status")).toBeNull();
  expect(refresh).not.toHaveBeenCalled();
  expect(screen.getByRole("button")).toBeEnabled();
});

it("renders existing confirmation without a mutation", () => {
  render(
    <LocaleProvider locale="zh">
      <AcknowledgeDocument id="read" acknowledged />
    </LocaleProvider>,
  );
  expect(screen.getByRole("status")).toHaveTextContent("已确认阅读");
  expect(screen.queryByRole("button")).toBeNull();
  expect(fetchMock).not.toHaveBeenCalled();
});
