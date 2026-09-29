import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import AppShell from "./app-shell";
import { en } from "@/lib/i18n/dictionaries/en";
vi.mock("next/navigation", () => ({ usePathname: () => "/advisor" }));
vi.mock("./locale-context", () => ({ useT: () => en, useLocale: () => ({ locale: "en", setLocale: vi.fn() }) }));
vi.mock("./client-selector", () => ({ default: () => <div>Client picker</div> }));

describe("Advisor Console navigation", () => {
  it("groups existing workflows and hides system settings for advisors on both menus", () => {
    render(<AppShell profiles={[]} healthBadge={null}><p>Content</p></AppShell>);
    const sidebar = screen.getByRole("complementary");
    expect(within(sidebar).getByText("Advisor Console")).toBeVisible();
    expect(within(sidebar).getByText("Advisory", { exact: true })).toBeVisible();
    expect(within(sidebar).getByRole("link", { name: /AI Advisor/ })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: /Settings/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.queryByRole("link", { name: /Settings/ })).toBeNull();
  });
  it("shows settings when the server grants that capability", () => {
    render(<AppShell profiles={[]} healthBadge={null} canManageSettings><p>Content</p></AppShell>);
    expect(screen.getByRole("link", { name: /Settings/ })).toHaveAttribute("href", "/settings");
  });
});
