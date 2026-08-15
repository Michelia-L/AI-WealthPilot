import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { errors } from "@/lib/i18n/dictionaries/en/errors";
import ErrorPage from "./error";
import Loading from "./loading";
import NotFound from "./not-found";

// Real English dictionary for copy; locale context stubbed out.
vi.mock("@/components/locale-context", () => ({
  useT: () => ({ errors }),
}));

// not-found.tsx is an async server component reading the dictionary via
// getDict(); loading.tsx is a plain server component.
vi.mock("@/lib/i18n/server", () => ({
  getDict: async () => ({ errors }),
}));

describe("app/error.tsx", () => {
  it("renders the error copy and calls unstable_retry on retry", () => {
    const retry = vi.fn();
    render(<ErrorPage error={new Error("boom")} unstable_retry={retry} />);

    expect(screen.getByText(errors.page.errorTitle)).toBeInTheDocument();
    expect(screen.getByText(errors.page.errorHint)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: errors.page.retry }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("shows the digest when present", () => {
    const err = Object.assign(new Error("boom"), { digest: "abc123" });
    render(<ErrorPage error={err} unstable_retry={vi.fn()} />);
    expect(screen.getByText(/abc123/)).toBeInTheDocument();
  });
});

describe("app/loading.tsx", () => {
  it("renders skeleton blocks", () => {
    const { container } = render(<Loading />);
    expect(container.querySelectorAll(".animate-shimmer").length).toBe(3);
  });
});

describe("app/not-found.tsx", () => {
  it("renders the not-found copy and a home link", async () => {
    render(await NotFound());
    expect(screen.getByText(errors.page.notFoundTitle)).toBeInTheDocument();
    expect(screen.getByText(errors.page.notFoundHint)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: errors.page.backHome })
    ).toHaveAttribute("href", "/");
  });
});
