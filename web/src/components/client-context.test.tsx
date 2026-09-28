import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ProfileSummary } from "@/lib/api";
import { ClientProvider, useClient } from "./client-context";
import ClientWorkspace from "./client-workspace";
import { useState } from "react";
import { en } from "@/lib/i18n/dictionaries/en";

const route = vi.hoisted(() => ({ pathname: "/advisor" }));
vi.mock("next/navigation", () => ({ usePathname: () => route.pathname }));
vi.mock("./locale-context", () => ({ useT: () => en }));
const profiles = [1, 2].map((id) => ({ id, name: "Same name", age: 40, risk_level: "", updated_at: "" } as ProfileSummary));
function Probe() {
  const { clientId, clientName, select, clear } = useClient();
  return <>
    <output data-testid="client">{clientId}:{clientName}</output>
    <button onClick={() => select(1, "Untrusted name")}>First</button>
    <button onClick={() => select(2, "Untrusted name")}>Second</button>
    <button onClick={() => select(999, "Foreign")}>Foreign</button>
    <button onClick={clear}>Clear</button>
  </>;
}
function Result() {
  const [value, setValue] = useState("");
  return <input aria-label="Result" value={value} onChange={(e) => setValue(e.target.value)} />;
}
function tree(scope = "user:org", allowed = profiles) {
  return <ClientProvider profiles={allowed} scope={scope}><Probe /><ClientWorkspace><Result /></ClientWorkspace></ClientProvider>;
}
beforeEach(() => { sessionStorage.clear(); localStorage.clear(); route.pathname = "/advisor"; });

describe("authorized current client", () => {
  it("ignores legacy cached names and unauthorized IDs, persists an ID only", () => {
    localStorage.setItem("wealthpilot.activeClient", JSON.stringify({ id: 999, name: "Foreign" }));
    sessionStorage.setItem("wealthpilot.activeClient:user:org", "999");
    render(tree());
    expect(screen.getByTestId("client")).toHaveTextContent(/^:$/);
    fireEvent.click(screen.getByText("Foreign"));
    expect(screen.getByTestId("client")).toHaveTextContent(/^:$/);
    fireEvent.click(screen.getByText("Second"));
    expect(screen.getByTestId("client")).toHaveTextContent("2:Same name");
    expect(sessionStorage.getItem("wealthpilot.activeClient:user:org")).toBe("2");
  });
  it("restores after remount and isolates users and organizations", () => {
    const view = render(tree());
    fireEvent.click(screen.getByText("First"));
    view.rerender(tree("user:other"));
    expect(screen.getByTestId("client")).toHaveTextContent(/^:$/);
    view.rerender(tree("other:org"));
    expect(screen.getByTestId("client")).toHaveTextContent(/^:$/);
    view.unmount();
    render(tree());
    expect(screen.getByTestId("client")).toHaveTextContent("1:Same name");
  });
  it("discards revoked/deleted clients and resets results even for duplicate names", () => {
    const view = render(tree());
    fireEvent.click(screen.getByText("First"));
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "First client's result" } });
    fireEvent.click(screen.getByText("Second"));
    expect(screen.getByLabelText("Result")).toHaveValue("");
    view.rerender(tree("user:org", [profiles[0]]));
    expect(screen.getByTestId("client")).toHaveTextContent(/^:$/);
    expect(sessionStorage.getItem("wealthpilot.activeClient:user:org")).toBeNull();
  });
  it("uses an authorized profile deep link and keeps it after navigation", () => {
    route.pathname = "/profiles/2";
    const view = render(tree());
    expect(screen.getByTestId("client")).toHaveTextContent("2:Same name");
    route.pathname = "/ips";
    view.rerender(tree());
    expect(screen.getByTestId("client")).toHaveTextContent("2:Same name");
    fireEvent.click(screen.getByText("Clear"));
    expect(screen.getByTestId("client")).toHaveTextContent(/^:$/);
  });
});
