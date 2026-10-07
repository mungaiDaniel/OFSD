import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ProductToggle, OVERVIEW_PRODUCT_OPTIONS } from "./ProductToggle";

describe("ProductToggle", () => {
  it("renders Funds and Shares by default, with the given value pressed", () => {
    render(<ProductToggle value="FUNDS" onChange={() => {}} />);

    const funds = screen.getByRole("button", { name: "Funds" });
    const shares = screen.getByRole("button", { name: "Shares" });
    expect(funds).toHaveAttribute("aria-pressed", "true");
    expect(shares).toHaveAttribute("aria-pressed", "false");
    // No "All" option unless explicitly requested via `options`.
    expect(screen.queryByRole("button", { name: "All" })).not.toBeInTheDocument();
  });

  it("calls onChange with the clicked option's value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProductToggle value="FUNDS" onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Shares" }));

    expect(onChange).toHaveBeenCalledWith("SHARES");
  });

  it("supports a 3-way All | Funds | Shares toggle for the Overview filter", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<ProductToggle value="ALL" onChange={onChange} options={OVERVIEW_PRODUCT_OPTIONS} />);

    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Shares" }));
    expect(onChange).toHaveBeenCalledWith("SHARES");
  });

  it("renders an accessible group label when provided", () => {
    render(<ProductToggle value="FUNDS" onChange={() => {}} label="Product" />);
    expect(screen.getByRole("group", { name: "Product" })).toBeInTheDocument();
  });
});
