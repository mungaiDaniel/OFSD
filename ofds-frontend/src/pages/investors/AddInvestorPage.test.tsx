import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AddInvestorPage from "./AddInvestorPage";
import { fundService } from "@/services/fundService";
import { investmentService } from "@/services/investmentService";
import type { CoreFund } from "@/lib/types";

vi.mock("@/services/fundService");
vi.mock("@/services/investmentService");
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const FUNDS: CoreFund[] = [
  { id: 1, fund_name: "Axiom", fund_code: "AXIOM", product_type: "FUNDS", is_active: true },
  { id: 2, fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE", fund_code: "DPRP", product_type: "SHARES", is_active: true },
];

function renderPage(initialPath = "/investors/add") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AddInvestorPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(fundService.getAll).mockResolvedValue(FUNDS);
  vi.mocked(investmentService.getInvestorDirectory).mockResolvedValue({ status: 200, message: "ok", data: [] });
});

describe("AddInvestorPage — Product selector", () => {
  it("defaults to Funds and offers only Funds in the dropdown", async () => {
    renderPage();

    await waitFor(() => expect(screen.getByRole("button", { name: "Funds" })).toHaveAttribute("aria-pressed", "true"));

    const fundSelect = screen.getByRole("combobox", { name: "Fund" });
    expect(within(fundSelect).getByText("Axiom (AXIOM)")).toBeInTheDocument();
    expect(within(fundSelect).queryByText(/Dangote/i)).not.toBeInTheDocument();
  });

  it("switching to Shares scopes the Fund dropdown to Shares funds only", async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => screen.getByRole("button", { name: "Funds" }));

    await user.click(screen.getByRole("button", { name: "Shares" }));

    expect(screen.getByRole("button", { name: "Shares" })).toHaveAttribute("aria-pressed", "true");
    const fundSelect = screen.getByRole("combobox", { name: "Fund" });
    expect(within(fundSelect).getByText(/Dangote/i)).toBeInTheDocument();
    expect(within(fundSelect).queryByText("Axiom (AXIOM)")).not.toBeInTheDocument();
  });

  it("reads the initial product from a ?product= query param (e.g. navigated from Shares > Investors)", async () => {
    renderPage("/investors/add?product=SHARES");

    await waitFor(() => expect(screen.getByRole("button", { name: "Shares" })).toHaveAttribute("aria-pressed", "true"));
    const fundSelect = screen.getByRole("combobox", { name: "Fund" });
    expect(within(fundSelect).getByText(/Dangote/i)).toBeInTheDocument();
  });
});
