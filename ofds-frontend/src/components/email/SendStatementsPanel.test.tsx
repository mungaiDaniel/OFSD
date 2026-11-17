import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SendStatementsPanel from "./SendStatementsPanel";
import { fundService } from "@/services/fundService";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock("@/services/fundService", () => ({ fundService: { getSummary: vi.fn() } }));
vi.mock("@/services/reportService", () => ({ reportService: { getEligibleInvestors: vi.fn() } }));
vi.mock("@/services/batchService", () => ({ batchService: { getAll: vi.fn().mockResolvedValue([]) } }));
vi.mock("@/services/emailService", () => ({
  emailService: {
    getQueueStatus: vi.fn().mockResolvedValue({ data: { batch_size: 100, interval_minutes: 5, queued_count: 0, next_run_at: null } }),
    listStatementDownloads: vi.fn().mockResolvedValue([]),
  },
}));

describe("SendStatementsPanel fund list", () => {
  beforeEach(() => {
    vi.mocked(fundService.getSummary).mockImplementation(async (product: any) =>
      ({
        as_of_date: "2026-11-05",
        funds: product === "SHARES"
          ? [{ id: 9, fund_name: "Dangote Shares", product_type: "SHARES" }]
          : [{ id: 1, fund_name: "Income Fund", product_type: "FUNDS" }],
      }) as any
    );
  });

  it("offers both Funds and Shares, in both statement flows", async () => {
    render(<SendStatementsPanel />);
    // overall flow: the Fund filter lists both products
    await waitFor(() => expect(screen.getByRole("option", { name: "Dangote Shares" })).toBeInTheDocument());
    expect(screen.getByRole("option", { name: "Income Fund" })).toBeInTheDocument();
    expect(fundService.getSummary).toHaveBeenCalledWith("FUNDS");
    expect(fundService.getSummary).toHaveBeenCalledWith("SHARES");

    // typed flow (Transfer confirmation etc.): same list, shares under their own group
    await userEvent.selectOptions(screen.getByLabelText("STATEMENT TYPE"), "transfer");
    const fund = await screen.findByLabelText("Fund");
    const groups = within(fund).getAllByRole("group");
    expect(groups.map((g) => g.getAttribute("label"))).toEqual(["Funds", "Shares"]);
    expect(within(groups[1] as HTMLElement).getByRole("option", { name: "Dangote Shares" })).toBeInTheDocument();
  });
});
