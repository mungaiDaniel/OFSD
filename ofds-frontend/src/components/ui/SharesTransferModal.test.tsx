import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SharesTransferModal } from "./SharesTransferModal";
import { batchService } from "@/services/batchService";

vi.mock("@/services/batchService", () => ({
  batchService: { previewSharesTransfer: vi.fn() },
}));

const preview = (pct: number) => ({
  rows: [{ investment_id: 1, internal_client_code: "151202", deposit_usd: 404000, entry_fee_usd: (404000 * pct) / 100, balance_after_entry: 0, transaction_cost_usd: 0, net_usd: 0 }],
  totals: { deposit_usd: 404000, entry_fee_usd: (404000 * pct) / 100, balance_after_entry: 0, transaction_cost_usd: 0, net_usd: 0 },
});

describe("SharesTransferModal — entry fee as percentage or amount", () => {
  beforeEach(() => {
    vi.mocked(batchService.previewSharesTransfer).mockImplementation(async (_id, pct) => preview(parseFloat(String(pct)) || 0) as any);
  });

  it("typing the percentage fills in the amount", async () => {
    render(<SharesTransferModal open batchId={1} onClose={vi.fn()} onConfirm={vi.fn()} />);
    const amount = screen.getByLabelText("Entry fee amount") as HTMLInputElement;
    await waitFor(() => expect(amount).not.toBeDisabled());

    await userEvent.clear(screen.getByLabelText("Entry fee percentage"));
    await userEvent.type(screen.getByLabelText("Entry fee percentage"), "1");
    expect(amount.value).toBe("4040.00");
  });

  it("typing the amount fills in the percentage and sends that percentage", async () => {
    render(<SharesTransferModal open batchId={1} onClose={vi.fn()} onConfirm={vi.fn()} />);
    const amount = screen.getByLabelText("Entry fee amount") as HTMLInputElement;
    await waitFor(() => expect(amount).not.toBeDisabled());

    await userEvent.clear(amount);
    await userEvent.type(amount, "4040");
    expect((screen.getByLabelText("Entry fee percentage") as HTMLInputElement).value).toBe("1");
    await waitFor(() => expect(batchService.previewSharesTransfer).toHaveBeenLastCalledWith(1, "1", "0"));
  });
});
