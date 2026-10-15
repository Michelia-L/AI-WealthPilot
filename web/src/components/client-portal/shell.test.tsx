import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { LocaleProvider } from "@/components/locale-context";
import ClientPortalShell from "./shell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/client/documents/report-1",
  useRouter: () => ({ refresh: vi.fn() }),
}));

describe("client navigation", () => {
  it.each(["en", "zh"] as const)(
    "exposes only the six client routes (%s)",
    (locale) => {
      render(
        <LocaleProvider locale={locale}>
          <ClientPortalShell
            isDemo={false}
            sessionControls={<button>Session</button>}
          >
            <p>Personal content</p>
          </ClientPortalShell>
        </LocaleProvider>,
      );
      const nav = screen.getByRole("navigation");
      const links = within(nav).getAllByRole("link");
      expect(links.map((link) => link.getAttribute("href"))).toEqual([
        "/client",
        "/client/portfolio",
        "/client/goals",
        "/client/risk-profile",
        "/client/documents",
        "/client/ai",
      ]);
      expect(
        within(nav).getByRole("link", {
          name: locale === "en" ? "Documents" : "文档",
        }),
      ).toHaveAttribute("aria-current", "page");
      expect(screen.queryByRole("combobox")).toBeNull();
      expect(screen.getByRole("main")).toHaveTextContent("Personal content");
      expect(
        screen.queryByText("Demo workspace with fictional data."),
      ).toBeNull();
    },
  );
});
