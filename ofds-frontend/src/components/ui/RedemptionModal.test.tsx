import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RedemptionModal } from "./RedemptionModal";
import { withdrawalService } from "@/services/withdrawalService";

vi.mock("@/services/withdrawalService", () => ({
  withdrawalService: { getRedemptionHoldings: vi.fn(), recordRedemption: vi.fn() },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const HOLDING = {
  fund_id: 7, fund_name: "Sample Fund Henderson Horizon Biotechnology", share_class_id: 3,
  class_code: "JH_BIO", currency: "USD", shares_available: 1178.976, lots: 1,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(withdrawalService.getRedemptionHoldings).mockResolvedValue({ investor_name: "Mary Mburu", holdings: [HOLDING] });
  vi.mocked(withdrawalService.recordRedemption).mockResolvedValue({ status: 201, message: "ok" } as never);
});

const fillMarysContractNote = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText("Client code"), "145591");
  await user.click(screen.getByRole("button", { name: /Find/ }));
  await screen.findByText("Mary Mburu");
  await user.type(screen.getByLabelText("Shares redeemed"), "101.423");
  await user.type(screen.getByLabelText("NAV per share"), "37.96");
  await user.type(screen.getByLabelText("Gross amount"), "3850");
  fireEvent.change(screen.getByLabelText("Trade date"), { target: { value: "2026-10-20" } });
  fireEvent.change(screen.getByLabelText("Settlement date"), { target: { value: "2026-10-23" } });
  await user.type(screen.getByLabelText("Transfer agent reference"), "6035089");
};

describe("RedemptionModal — record a redemption from the contract note", () => {
  it("shows shares remaining and sends the contract-note figures", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    render(<RedemptionModal open onClose={vi.fn()} onDone={onDone} />);

    await fillMarysContractNote(user);
    expect(screen.getByText("1,077.553")).toBeInTheDocument(); // 1,178.976 - 101.423

    await user.click(screen.getByRole("button", { name: /Record redemption/ }));
    await waitFor(() => expect(withdrawalService.recordRedemption).toHaveBeenCalledTimes(1));
    expect(withdrawalService.recordRedemption).toHaveBeenCalledWith({
      client_code: "145591", fund_id: 7, share_class_id: 3, shares: 101.423, nav: 37.96,
      trade_date: "2026-10-20", gross_amount: 3850, exit_fee: 0,
      settlement_date: "2026-10-23", ta_reference: "6035089",
    });
    expect(onDone).toHaveBeenCalled();
  });

  it("blocks redeeming more shares than the client holds", async () => {
    const user = userEvent.setup();
    render(<RedemptionModal open onClose={vi.fn()} onDone={vi.fn()} />);
    await fillMarysContractNote(user);
    await user.clear(screen.getByLabelText("Shares redeemed"));
    await user.type(screen.getByLabelText("Shares redeemed"), "2000");
    await user.clear(screen.getByLabelText("Gross amount"));
    expect(screen.getByText(/More shares than the client holds/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record redemption/ })).toBeDisabled();
  });

  it("flags a gross amount that doesn't match shares x NAV", async () => {
    const user = userEvent.setup();
    render(<RedemptionModal open onClose={vi.fn()} onDone={vi.fn()} />);
    await fillMarysContractNote(user);
    await user.clear(screen.getByLabelText("Gross amount"));
    await user.type(screen.getByLabelText("Gross amount"), "5000");
    expect(screen.getByText(/doesn't match shares × NAV/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Record redemption/ })).toBeDisabled();
  });

  it("executing a pending request loads that client and links the withdrawal", async () => {
    const user = userEvent.setup();
    render(<RedemptionModal open onClose={vi.fn()} onDone={vi.fn()} prefill={{ withdrawalId: 42, clientCode: "145591", fundId: 7, amount: 3850 }} />);
    await screen.findByText("Mary Mburu");
    await user.type(screen.getByLabelText("Shares redeemed"), "101.423");
    await user.type(screen.getByLabelText("NAV per share"), "37.96");
    fireEvent.change(screen.getByLabelText("Trade date"), { target: { value: "2026-10-20" } });
    await user.click(screen.getByRole("button", { name: /Record redemption/ }));
    await waitFor(() => expect(withdrawalService.recordRedemption).toHaveBeenCalled());
    expect(vi.mocked(withdrawalService.recordRedemption).mock.calls[0]![0]).toMatchObject({ withdrawal_id: 42, gross_amount: 3850 });
  });
});
