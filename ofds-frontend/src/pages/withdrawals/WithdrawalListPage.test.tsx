import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WithdrawalListPage from "./WithdrawalListPage";
import { withdrawalService } from "@/services/withdrawalService";
import { fundService } from "@/services/fundService";
import type { Withdrawal, CoreFund } from "@/lib/types";

vi.mock("@/services/withdrawalService");
vi.mock("@/services/fundService");
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const FUNDS: CoreFund[] = [
  { id: 1, fund_name: "Axiom", fund_code: "AXIOM", product_type: "FUNDS", is_active: true },
];

const REFUND_ROW: Withdrawal = {
  id: 10,
  client_id: "REFUND-C",
  investor_name: "Client C",
  fund_id: 2,
  fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE",
  product_type: "SHARES",
  amount: 2702.0,
  status: "Pending",
  date_withdrawn: "2026-06-01T00:00:00Z",
  approved_at: null,
  note: null,
  source: "oversubscription_refund",
  batch_id: 5,
  batch_name: "DPRP Batch 1",
  rate_used: 1500,
  oversubscription_notice_sent: false,
};

const FUNDS_ROW: Withdrawal = {
  id: 11,
  client_id: "FUNDS-INV",
  investor_name: "Funds Investor",
  fund_id: 1,
  fund_name: "Axiom",
  product_type: "FUNDS",
  amount: 500.0,
  status: "Pending",
  date_withdrawn: "2026-06-02T00:00:00Z",
  approved_at: null,
  note: null,
  source: "investor_request",
  batch_id: null,
  batch_name: null,
  rate_used: null,
};

function mockListResponse(rows: Withdrawal[]) {
  return { data: rows, pagination: { total: rows.length, total_pages: 1 } };
}

beforeEach(() => {
  vi.mocked(fundService.getAll).mockResolvedValue(FUNDS);
  vi.mocked(withdrawalService.getCount).mockResolvedValue(0);
  vi.mocked(withdrawalService.getAll).mockImplementation(async (params) => {
    let rows = [REFUND_ROW, FUNDS_ROW];
    if (params?.source) rows = rows.filter((r) => r.source === params.source);
    if (params?.product) rows = rows.filter((r) => r.product_type === params.product);
    return mockListResponse(rows);
  });
});

describe("WithdrawalListPage — refunds appear inline (Task 11)", () => {
  it("renders the Shares oversubscription refund with its type badge and Product badge", async () => {
    render(<WithdrawalListPage />);

    await screen.findByText("REFUND-C");
    expect(screen.getByText("Oversubscription Refund")).toBeInTheDocument();
    expect(screen.getByText("Investor Request")).toBeInTheDocument();
    expect(screen.getAllByText("Shares").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Funds").length).toBeGreaterThan(0);
  });

  it("shows batch, amount, and rate used for the refund row", async () => {
    render(<WithdrawalListPage />);
    await screen.findByText("REFUND-C");

    expect(screen.getByText("DPRP Batch 1")).toBeInTheDocument();
    expect(screen.getByText(/2,702\.00/)).toBeInTheDocument();
    expect(screen.getByText(/₦1,500/)).toBeInTheDocument();
  });
});

describe("WithdrawalListPage — filters (Task 11)", () => {
  it("Product = Shares requests product=SHARES and shows only the refund", async () => {
    const user = userEvent.setup();
    render(<WithdrawalListPage />);
    await screen.findByText("REFUND-C");

    await user.click(screen.getByRole("button", { name: "Shares" }));

    await waitFor(() =>
      expect(withdrawalService.getAll).toHaveBeenCalledWith(expect.objectContaining({ product: "SHARES" }))
    );
    expect(screen.queryByText("FUNDS-INV")).not.toBeInTheDocument();
  });

  it("Type = Oversubscription Refunds requests source=oversubscription_refund", async () => {
    const user = userEvent.setup();
    render(<WithdrawalListPage />);
    await screen.findByText("REFUND-C");

    await user.click(screen.getByRole("button", { name: "Oversubscription Refunds" }));

    await waitFor(() =>
      expect(withdrawalService.getAll).toHaveBeenCalledWith(
        expect.objectContaining({ source: "oversubscription_refund" })
      )
    );
  });
});

describe("WithdrawalListPage — approval flow unchanged (Task 11)", () => {
  it("Approve button calls withdrawalService.approve for that row's id", async () => {
    const user = userEvent.setup();
    vi.mocked(withdrawalService.approve).mockResolvedValue({ status: 200, message: "ok" });
    render(<WithdrawalListPage />);
    await screen.findByText("REFUND-C");

    const approveButtons = screen.getAllByRole("button", { name: /Approve$/i });
    await user.click(approveButtons[0]!);

    await waitFor(() => expect(withdrawalService.approve).toHaveBeenCalledWith(10));
  });
});
