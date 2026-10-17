import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Slider from "./slider";

describe("Slider accessibility", () => {
  it("associates each visible label with its own slider", () => {
    render(
      <>
        <Slider label="Current Age" value={35} min={18} max={80} onChange={vi.fn()} />
        <Slider label="Retirement Age" value={60} min={19} max={90} onChange={vi.fn()} />
      </>
    );
    expect(screen.getByLabelText("Current Age")).toBe(screen.getByRole("slider", { name: "Current Age" }));
    expect(screen.getByLabelText("Retirement Age")).toBe(screen.getByRole("slider", { name: "Retirement Age" }));
    expect(screen.getByLabelText("Current Age")).toHaveValue("35");
    expect(screen.getByLabelText("Retirement Age")).toHaveValue("60");
  });

  it("names an inline slider without adding a visible label", () => {
    const onChange = vi.fn();
    render(<Slider aria-label="Confidence" value={70} min={10} max={100} onChange={onChange} />);
    const slider = screen.getByRole("slider", { name: "Confidence" });
    fireEvent.change(slider, { target: { value: "80" } });
    expect(onChange).toHaveBeenCalledWith(80);
  });

  it("announces the displayed units with the value", () => {
    render(
      <Slider label="Current Age" value={35} min={18} max={80}
        format={(value) => value + " yrs"} onChange={vi.fn()} />
    );
    expect(screen.getByRole("slider", { name: "Current Age" })).toHaveAttribute("aria-valuetext", "35 yrs");
  });
});
