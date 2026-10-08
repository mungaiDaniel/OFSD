import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import FundListPage from "./FundListPage";
import SharesListPage from "@/pages/shares/SharesListPage";
import { fundService } from "@/services/fundService";
import type { CoreFund } from "@/lib/types";

vi.mock("@/services/fundService");
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const FUNDS: CoreFund[] = [
  { id: 1, fund_name: "Axiom", fund_code: "AXIOM", product_type: "FUNDS", is_active: true },
];
const SHARES: CoreFund[] = [
  {
    id: 2,
    fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE",
    fund_code: "DPRP",
    product_type: "SHARES",
    is_active: true,
  },
];

function renderWith(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(fundService.getAll).mockImplementation(async (product) =>
    product === "SHARES" ? SHARES : FUNDS
  );
});

describe("Funds page (/funds)", () => {
  it("lists only FUNDS, requesting the FUNDS-scoped endpoint", async () => {
    renderWith(<FundListPage />);

    await waitFor(() => expect(fundService.getAll).toHaveBeenCalledWith("FUNDS"));
    expect(await screen.findByText("Axiom")).toBeInTheDocument();
    expect(screen.queryByText(/Dangote/i)).not.toBeInTheDocument();
  });

  it("uses Fund wording and offers KES/USD as share class currencies", async () => {
    renderWith(<FundListPage />);
    await waitFor(() => expect(fundService.getAll).toHaveBeenCalled());

    expect(screen.getByRole("heading", { name: "Funds" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New fund/i })).toBeInTheDocument();
  });
});

describe("Shares page (/shares)", () => {
  it("lists only SHARES (the Dangote card), requesting the SHARES-scoped endpoint", async () => {
    renderWith(<SharesListPage />);

    await waitFor(() => expect(fundService.getAll).toHaveBeenCalledWith("SHARES"));
    expect(await screen.findByText(/Dangote/i)).toBeInTheDocument();
    expect(screen.queryByText("Axiom")).not.toBeInTheDocument();
  });

  it("uses Share wording and the required subtitle copy", async () => {
    renderWith(<SharesListPage />);
    await waitFor(() => expect(fundService.getAll).toHaveBeenCalled());

    expect(screen.getByRole("heading", { name: "Shares" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New share/i })).toBeInTheDocument();
    expect(
      screen.getByText("Shares: core shares used for performance tracking and valuation")
    ).toBeInTheDocument();
  });

  it("offers NGN as the only share class currency", async () => {
    const user = userEvent.setup();
    renderWith(<SharesListPage />);
    await screen.findByText(/Dangote/i);

    await user.click(screen.getByRole("button", { name: /Add Share Class/i }));

    // The form has two <select>s: Fund (first), Currency (second) — neither
    // has an aria-label, so select by position within the form.
    const selects = screen.getAllByRole("combobox");
    const currencySelect = selects[selects.length - 1] as HTMLSelectElement;
    const options = within(currencySelect)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["NGN"]);
  });
});
