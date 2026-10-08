import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ValuationCreatePage from "./ValuationCreatePage";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";

vi.mock("@/services/fundService");
vi.mock("@/services/batchService");
vi.mock("@/services/valuationService");
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

function renderWith(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(batchService.getAll).mockResolvedValue([]);
});

describe("Valuation entry screen — product scoping", () => {
  it("Funds valuation entry loads the FUNDS summary and shows KES/USD groups", async () => {
    vi.mocked(fundService.getSummary).mockImplementation(async (product) =>
      product === "SHARES"
        ? null
        : {
            as_of_date: "2026-09-30",
            funds: [
              {
                fund_name: "Axiom",
                classes: [
                  { id: 1, class_name: "Class A", class_code: "KES_A", currency: "KES", is_active: true, current_nav: 1 },
                  { id: 2, class_name: "Class B", class_code: "USD_B", currency: "USD", is_active: true, current_nav: 1 },
                ],
              },
            ],
          }
    );

    renderWith(<ValuationCreatePage product="FUNDS" />);

    await waitFor(() => expect(fundService.getSummary).toHaveBeenCalledWith("FUNDS"));
    expect(await screen.findByText("KES_A")).toBeInTheDocument();
    expect(screen.getByText("USD_B")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Monthly Fund Valuation/i })).toBeInTheDocument();
  });

  it("Shares valuation entry loads the SHARES summary and shows an NGN group only", async () => {
    vi.mocked(fundService.getSummary).mockImplementation(async (product) =>
      product === "SHARES"
        ? {
            as_of_date: "2026-09-30",
            funds: [
              {
                fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE",
                classes: [
                  { id: 3, class_name: "DPRP Class", class_code: "NGN_A", currency: "NGN", is_active: true, current_nav: 1 },
                ],
              },
            ],
          }
        : null
    );

    renderWith(<ValuationCreatePage product="SHARES" />);

    await waitFor(() => expect(fundService.getSummary).toHaveBeenCalledWith("SHARES"));
    expect(await screen.findByText("NGN_A")).toBeInTheDocument();
    expect(screen.queryByText("KES_A")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Monthly Shares Valuation/i })).toBeInTheDocument();
  });

  it("Shares empty state points back to Shares management", async () => {
    vi.mocked(fundService.getSummary).mockResolvedValue(null);
    vi.mocked(fundService.getAll).mockResolvedValue([]);

    renderWith(<ValuationCreatePage product="SHARES" />);

    expect(await screen.findByText(/No active share classes/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Go to Shares Management/i })).toBeInTheDocument();
  });
});
