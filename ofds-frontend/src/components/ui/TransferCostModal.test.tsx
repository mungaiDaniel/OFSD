import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TransferCostModal } from "./TransferCostModal";
import type { BatchInvestorLight } from "@/lib/types";

const INVESTORS: BatchInvestorLight[] = [
  { id: 1, investor_name: "Alice Johnson", internal_client_code: "INV-001", amount_deposited: 2000, main_balance: 2000, share_class_id: 1, class_code: "CI-USD", class_currency: "USD" },
  { id: 2, investor_name: "Bob Smith", internal_client_code: "INV-002", amount_deposited: 3000, main_balance: 3000, share_class_id: 1, class_code: "CI-USD", class_currency: "USD" },
];

describe("TransferCostModal — manual per-client amounts (Transfer stage)", () => {
  it("lists every client, defaulting each input to their full deposited amount", () => {
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByText("Alice Johnson")).toBeInTheDocument();
    expect(screen.getByText("Bob Smith")).toBeInTheDocument();

    const inputs = screen.getAllByRole("spinbutton").filter((el) => el.getAttribute("step") === "0.01" && el.getAttribute("min") === "0") as HTMLInputElement[];
    // First spinbutton is the entry-fee field; the rest are per-client amounts.
    const amountInputs = inputs.slice(1);
    expect(amountInputs.map((i) => i.value)).toEqual(["2000", "3000"]);
  });

  it("recomputes Total Active Principal live as amounts and entry fee change", async () => {
    const user = userEvent.setup();
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const entryFeeInput = inputs[0]!;
    const aliceInput = inputs[1]!;

    // Bank only sent Alice 1800 instead of her full 2000.
    await user.clear(aliceInput);
    await user.type(aliceInput, "1800");
    await user.clear(entryFeeInput);
    await user.type(entryFeeInput, "2");

    // Total received = 1800 + 3000 = 4800; entry fee 2% = 96; net = 4704.00
    expect(screen.getByText("$4,704.00")).toBeInTheDocument();
  });

  it("confirms with an amountsReceived map keyed by investment id, plus the entry fee %", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<TransferCostModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const entryFeeInput = inputs[0]!;
    const aliceInput = inputs[1]!;

    await user.clear(aliceInput);
    await user.type(aliceInput, "1800");
    await user.clear(entryFeeInput);
    await user.type(entryFeeInput, "2");

    await user.click(screen.getByRole("button", { name: "Confirm & Transfer" }));

    expect(onConfirm).toHaveBeenCalledWith({ 1: 1800, 2: 3000 }, 2);
  });
});
