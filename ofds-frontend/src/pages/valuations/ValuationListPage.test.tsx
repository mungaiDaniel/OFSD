import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ValuationListPage from "./ValuationListPage";
import { valuationService } from "@/services/valuationService";
import type { NavValuationRunItem } from "@/lib/types";

vi.mock("@/services/valuationService");
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const FUND_RUN: NavValuationRunItem = {
  share_class_id: 1,
  fund_name: "Axiom",
  valuation_date: "2026-09-30",
  nav_per_share: 1.5,
  opening_aum: 100,
  closing_aum: 150,
  profit: 50,
  investors: 2,
  performance_pct: 5,
} as NavValuationRunItem;

const SHARE_RUN: NavValuationRunItem = {
  ...FUND_RUN,
  fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE",
};

function renderWith(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

beforeEach(() => {
  vi.mocked(valuationService.listNavRuns).mockImplementation(async (_limit, product) =>
    product === "SHARES" ? [SHARE_RUN] : [FUND_RUN]
  );
});

describe("Valuation screen — product scoping", () => {
  it("Funds valuations screen requests FUNDS and shows only Funds reports", async () => {
    renderWith(<ValuationListPage product="FUNDS" />);

    await waitFor(() => expect(valuationService.listNavRuns).toHaveBeenCalledWith(100, "FUNDS"));
    expect(await screen.findByText("Axiom")).toBeInTheDocument();
    expect(screen.queryByText(/Dangote/i)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Funds Valuation Statements/i })).toBeInTheDocument();
  });

  it("Shares valuations screen requests SHARES and shows only Shares reports", async () => {
    renderWith(<ValuationListPage product="SHARES" />);

    await waitFor(() => expect(valuationService.listNavRuns).toHaveBeenCalledWith(100, "SHARES"));
    expect(await screen.findByText(/Dangote/i)).toBeInTheDocument();
    expect(screen.queryByText("Axiom")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Shares Valuation Statements/i })).toBeInTheDocument();
  });

  it("defaults to FUNDS when no product is given", async () => {
    renderWith(<ValuationListPage />);
    await waitFor(() => expect(valuationService.listNavRuns).toHaveBeenCalledWith(100, "FUNDS"));
  });
});
