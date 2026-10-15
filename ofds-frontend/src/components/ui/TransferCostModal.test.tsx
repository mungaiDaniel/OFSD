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
  it("lists every client, with each amount received starting at 0", () => {
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByText("Alice Johnson")).toBeInTheDocument();
    expect(screen.getByText("Bob Smith")).toBeInTheDocument();

    const inputs = screen.getAllByRole("spinbutton").filter((el) => el.getAttribute("step") === "0.01" && el.getAttribute("min") === "0") as HTMLInputElement[];
    // First spinbutton is the entry-fee field; the rest are per-client amounts.
    const amountInputs = inputs.slice(1);
    expect(amountInputs.map((i) => i.value)).toEqual(["0", "0"]);
  });

  it("re-seeds a 0 amount for every client once the real list arrives after the modal first mounts empty", () => {
    // Reproduces the production bug: the modal is in the tree before the
    // investor list has loaded (investments=[]), then `open` flips true once
    // the real list is ready. A one-time useState initializer would freeze
    // on the empty list; the useEffect keyed on `open` must re-seed instead.
    const { rerender } = render(<TransferCostModal open={false} investments={[]} onConfirm={vi.fn()} onClose={vi.fn()} />);
    rerender(<TransferCostModal open={false} investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);
    rerender(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    const inputs = screen.getAllByRole("spinbutton").filter((el) => el.getAttribute("step") === "0.01" && el.getAttribute("min") === "0") as HTMLInputElement[];
    const amountInputs = inputs.slice(1);
    expect(amountInputs.map((i) => i.value)).toEqual(["0", "0"]);
  });

  it("recomputes Total Active Principal live as amounts and entry fee change", async () => {
    const user = userEvent.setup();
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const entryFeeInput = inputs[0]!;
    const aliceInput = inputs[1]!;

    // Bank only sent Alice 1800 instead of her full 2000; Bob's 3000 arrived in full.
    await user.clear(aliceInput);
    await user.type(aliceInput, "1800");
    await user.clear(inputs[2]!);
    await user.type(inputs[2]!, "3000");
    await user.clear(entryFeeInput);
    await user.type(entryFeeInput, "2");

    // Total received = 1800 + 3000 = 4800; entry fee 2% = 96; net = 4704.00
    expect(screen.getByText("$4,704.00")).toBeInTheDocument();
  });

  it("confirms in manual mode with an amountsReceived map, null transaction cost, plus the entry fee %", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<TransferCostModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const entryFeeInput = inputs[0]!;
    const aliceInput = inputs[1]!;

    await user.clear(aliceInput);
    await user.type(aliceInput, "1800");
    await user.clear(inputs[2]!);
    await user.type(inputs[2]!, "3000");
    await user.clear(entryFeeInput);
    await user.type(entryFeeInput, "2");

    await user.click(screen.getByRole("button", { name: "Confirm & Transfer" }));

    expect(onConfirm).toHaveBeenCalledWith("manual", { 1: 1800, 2: 3000 }, null, 2);
  });
});

describe("TransferCostModal — per-client Transfer Amount and Entry Fee columns", () => {
  it("shows each client's transfer amount (deposited − received) and entry fee (on received)", async () => {
    const user = userEvent.setup();
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByText("Transfer Amount")).toBeInTheDocument();
    expect(screen.getByText("Entry Fee")).toBeInTheDocument();

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    await user.clear(inputs[0]!);
    await user.type(inputs[0]!, "10");
    const aliceInput = screen.getByLabelText("Amount received for Alice Johnson");
    await user.clear(aliceInput);
    await user.type(aliceInput, "1900");

    const aliceRow = aliceInput.closest("tr")!;
    // Transfer amount 2000 - 1900 = 100.00; entry fee 10% of 1900 = 190.00; net 1710.00
    expect(aliceRow).toHaveTextContent("100.00");
    expect(aliceRow).toHaveTextContent("190.00");
    expect(aliceRow).toHaveTextContent("1,710.00");

    // Bob still at 0 received: his whole 3000 deposit shows as the transfer amount.
    const bobRow = screen.getByLabelText("Amount received for Bob Smith").closest("tr")!;
    expect(bobRow).toHaveTextContent("3,000.00");
  });
});

describe("TransferCostModal — whole batch at once (aggregate mode)", () => {
  it("switches to the aggregate view and hides the per-client table", async () => {
    const user = userEvent.setup();
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Whole batch at once" }));

    expect(screen.queryByText("Alice Johnson")).not.toBeInTheDocument();
    expect(screen.getByText("TOTAL TRANSACTION COST (USD)", { exact: false })).toBeInTheDocument();
  });

  it("computes Total Active Principal as deposit minus transaction cost minus entry fee", async () => {
    const user = userEvent.setup();
    render(<TransferCostModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Whole batch at once" }));

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const entryFeeInput = inputs[0]!;
    const costInput = inputs[1]!;

    await user.clear(costInput);
    await user.type(costInput, "100");
    await user.clear(entryFeeInput);
    await user.type(entryFeeInput, "2");

    // Deposited 5000 - cost 100 = 4900; entry fee 2% of 4900 = 98; net = 4802.00
    expect(screen.getByText("$4,802.00")).toBeInTheDocument();
  });

  it("confirms in aggregate mode with a transactionCostUsd, null amountsReceived, plus the entry fee %", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<TransferCostModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Whole batch at once" }));

    const inputs = screen.getAllByRole("spinbutton") as HTMLInputElement[];
    const entryFeeInput = inputs[0]!;
    const costInput = inputs[1]!;

    await user.clear(costInput);
    await user.type(costInput, "100");
    await user.clear(entryFeeInput);
    await user.type(entryFeeInput, "2");

    await user.click(screen.getByRole("button", { name: "Confirm & Transfer" }));

    expect(onConfirm).toHaveBeenCalledWith("aggregate", null, 100, 2);
  });
});
