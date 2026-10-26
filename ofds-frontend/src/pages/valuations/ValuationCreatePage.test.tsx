import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ValuationCreatePage from "./ValuationCreatePage";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { valuationService } from "@/services/valuationService";

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

describe("Valuation scope — all vs selected batches", () => {
  const summary = {
    as_of_date: "2026-10-20",
    funds: [
      {
        fund_name: "Axiom",
        classes: [{ id: 1, class_name: "Class I", class_code: "KES_I", currency: "KES", is_active: true, current_nav: 1 }],
      },
    ],
  };

  beforeEach(() => {
    vi.mocked(fundService.getSummary).mockResolvedValue(summary as any);
    vi.mocked(batchService.getAll).mockResolvedValue([
      { id: 10, batch_name: "Batch A", is_active: true, share_class_id: 1, class_code: "KES_I", investors_count: 3 },
      { id: 11, batch_name: "Batch B", is_active: true, share_class_id: 1, class_code: "KES_I", investors_count: 2 },
    ] as any);
    vi.mocked(valuationService.preview).mockResolvedValue({ valuation_date: "2026-10-20", batch_ids: [10], classes: [] } as any);
  });

  async function fillAndPreview() {
    await screen.findByText("KES_I");
    const inputs = screen.getAllByPlaceholderText(/e\.g\./);
    fireEvent.change(inputs[0]!, { target: { value: "1362.3460" } });
    fireEvent.change(inputs[1]!, { target: { value: "100000" } });
    fireEvent.click(screen.getByRole("button", { name: /Ready to preview|Preview/i }));
  }

  it("defaults to all batches: no batch_ids are sent", async () => {
    renderWith(<ValuationCreatePage product="FUNDS" />);
    await fillAndPreview();
    await waitFor(() => expect(valuationService.preview).toHaveBeenCalled());
    expect(vi.mocked(valuationService.preview).mock.calls[0]![0]).not.toHaveProperty("batch_ids");
  });

  it("selected batches: sends only the ticked batch ids and blocks preview with none ticked", async () => {
    renderWith(<ValuationCreatePage product="FUNDS" />);
    await screen.findByText("KES_I");
    fireEvent.click(screen.getByLabelText("Selected batches"));
    const inputs = screen.getAllByPlaceholderText(/e\.g\./);
    fireEvent.change(inputs[0]!, { target: { value: "1362.3460" } });
    fireEvent.change(inputs[1]!, { target: { value: "100000" } });
    const previewBtn = screen.getByRole("button", { name: /Preview/i });
    expect(previewBtn).toBeDisabled();

    fireEvent.click(screen.getByLabelText(/Batch A/));
    expect(previewBtn).not.toBeDisabled();
    fireEvent.click(previewBtn);

    await waitFor(() => expect(valuationService.preview).toHaveBeenCalled());
    expect(vi.mocked(valuationService.preview).mock.calls.at(-1)![0]).toMatchObject({ batch_ids: [10] });
  });
});
