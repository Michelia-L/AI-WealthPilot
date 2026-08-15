import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { LlmSettingsResponse } from "@/lib/api";
import { common } from "@/lib/i18n/dictionaries/en/common";
import { settings } from "@/lib/i18n/dictionaries/en/settings";
import SettingsForm from "./settings-form";

vi.mock("@/components/locale-context", () => ({
  useT: () => ({ settings, common }),
}));
const refreshMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: refreshMock }),
}));

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

const DB_INITIAL: LlmSettingsResponse = {
  source: "db",
  base_url: "https://api.deepseek.com",
  api_key_masked: "sk-****abcd",
  model: "deepseek-chat",
  demo: false,
} as LlmSettingsResponse;

const ENV_INITIAL: LlmSettingsResponse = {
  source: "env",
  base_url: "https://api.deepseek.com",
  api_key_masked: "sk-****env0",
  model: "deepseek-reasoner",
  demo: false,
} as LlmSettingsResponse;

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status });
}

/** Fill endpoint + key + model so the action buttons become enabled. */
function fillForm() {
  fireEvent.change(screen.getByPlaceholderText("https://api.deepseek.com"), {
    target: { value: "https://api.example.com" },
  });
  fireEvent.change(screen.getByPlaceholderText("sk-..."), {
    target: { value: "sk-test-key" },
  });
  fireEvent.change(
    screen.getByPlaceholderText("Enter manually, or fetch the model list first"),
    { target: { value: "my-model" } }
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  refreshMock.mockClear();
});

describe("SettingsForm current configuration", () => {
  it("echoes the active config with the masked key and source badge", () => {
    render(<SettingsForm initial={DB_INITIAL} />);
    expect(screen.getByText("Active Configuration")).toBeInTheDocument();
    expect(screen.getByText("Custom Endpoint")).toBeInTheDocument();
    expect(screen.getByText("sk-****abcd")).toBeInTheDocument();
    expect(screen.getByText("deepseek-chat")).toBeInTheDocument();
    // db-sourced config pre-fills endpoint/model and offers the clear action
    expect(
      screen.getByPlaceholderText("https://api.deepseek.com")
    ).toHaveValue("https://api.deepseek.com");
    expect(
      screen.getByRole("button", { name: "Clear Custom" })
    ).toBeInTheDocument();
  });

  it("hides the clear action for env-sourced config", () => {
    render(<SettingsForm initial={ENV_INITIAL} />);
    expect(screen.getByText("Environment")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Clear Custom" })
    ).not.toBeInTheDocument();
    // env config does not leak into the form fields
    expect(screen.getByPlaceholderText("https://api.deepseek.com")).toHaveValue("");
  });
});

describe("SettingsForm model fetching", () => {
  it("fetches models and switches the model field to a select", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ models: ["m-a", "m-b"] }))
    );
    render(<SettingsForm initial={ENV_INITIAL} />);
    fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Fetch Model List" }));
    expect(await screen.findByText("Fetched 2 available models")).toBeInTheDocument();

    // model input became a select with the fetched options, first selected
    const select = screen.getByRole("combobox");
    expect(select).toHaveValue("m-a");
    expect(screen.getByRole("option", { name: "m-b" })).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/settings/llm/models");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      base_url: "https://api.example.com",
      api_key: "sk-test-key",
    });
  });

  it("surfaces fetch failures and empty model lists as errors", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: "connection refused" }, 502))
    );
    render(<SettingsForm initial={ENV_INITIAL} />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Fetch Model List" }));
    expect(await screen.findByText("connection refused")).toBeInTheDocument();

    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ models: [] }))
    );
    fireEvent.click(screen.getByRole("button", { name: "Fetch Model List" }));
    expect(
      await screen.findByText("The endpoint returned no available models")
    ).toBeInTheDocument();
  });
});

describe("SettingsForm saving", () => {
  it("saves the custom endpoint and refreshes", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ ok: true }))
    );
    render(<SettingsForm initial={ENV_INITIAL} />);
    fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Save Configuration" }));
    expect(
      await screen.findByText("Saved — all AI features now use the custom endpoint.")
    ).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/settings/llm");
    expect((init as RequestInit).method).toBe("PUT");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      base_url: "https://api.example.com",
      api_key: "sk-test-key",
      model: "my-model",
    });
    expect(refreshMock).toHaveBeenCalled();
    // key field cleared after a successful save
    expect(screen.getByPlaceholderText("sk-...")).toHaveValue("");
  });

  it("clearing sends empty fields (delete row, fall back to env)", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ ok: true }))
    );
    render(<SettingsForm initial={DB_INITIAL} />);

    fireEvent.click(screen.getByRole("button", { name: "Clear Custom" }));
    expect(
      await screen.findByText(
        "Custom configuration cleared — falling back to environment variables."
      )
    ).toBeInTheDocument();

    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      base_url: "",
      api_key: "",
      model: "",
    });
  });

  it("shows save errors from the API", async () => {
    fetchMock.mockImplementation(() =>
      Promise.resolve(jsonResponse({ detail: "invalid base_url" }, 422))
    );
    render(<SettingsForm initial={ENV_INITIAL} />);
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "Save Configuration" }));
    expect(await screen.findByText("invalid base_url")).toBeInTheDocument();
  });
});
