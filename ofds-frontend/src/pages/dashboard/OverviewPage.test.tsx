import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import OverviewPage from "./OverviewPage";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { dashboardService } from "@/services/dashboardService";
import type { Batch, FundsSummaryResponse } from "@/lib/types";

vi.mock("@/services/fundService");
vi.mock("@/services/batchService");
vi.mock("@/services/dashboardService");

function makeBatch(overrides: Partial<Batch>): Batch {
  return {
    id: 1,
    batch_name: "Batch 1",
    certificate_number: null,
    total_principal: 0,
    total_capital: 0,
    date_deployed: null,
    duration_days: 30,
    expected_close_date: null,
    date_closed: null,
    is_active: true,
    is_transferred: true,
    deployment_confirmed: true,
    stage: 4,
    status: "Active",
    investors_count: 1,
    funds: [],
    created_at: null,
    product_type: "FUNDS",
    ...overrides,
  };
}

const FUNDS_SUMMARY: FundsSummaryResponse = {
  as_of_date: "2026-09-30",
  funds: [
    {
      id: 1,
      fund_name: "Axiom",
      investors_count: 5,
      classes: [
        {
          id: 1,
          class_name: "Class A",
          class_code: "KES_A",
          currency: "KES",
          current_nav: 105,
          total_nav: 10500,
          performance_pct: 5,
          is_valued: true,
        },
      ],
      totals_by_currency: { KES: 10500 },
      gain_by_currency: { KES: 500 },
      gross_deposited_by_currency: { KES: 10000 },
      net_holdings_by_currency: { KES: 10000 },
      withdrawals_by_currency: {},
      refunds_by_currency: {},
    },
  ],
};

const SHARES_SUMMARY: FundsSummaryResponse = {
  as_of_date: "2026-09-30",
  funds: [
    {
      id: 2,
      fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE",
      investors_count: 3,
      classes: [
        {
          id: 2,
          class_name: "DPRP Class",
          class_code: "NGN_A",
          currency: "USD",
          valuation_currency: "NGN",
          current_nav: 525,
          total_nav: 15_750_000,
          performance_pct: 5,
          is_valued: true,
        },
      ],
      totals_by_currency: { NGN: 15_750_000 },
      gain_by_currency: { NGN: 750_000 },
      gross_deposited_by_currency: { USD: 10_000 },
      net_holdings_by_currency: { USD: 10_000 },
      withdrawals_by_currency: {},
      refunds_by_currency: {},
    },
  ],
};

const BATCHES: Batch[] = [
  makeBatch({ id: 1, batch_name: "Funds Batch", product_type: "FUNDS", share_class_id: 1, class_currency: "KES" }),
  makeBatch({ id: 2, batch_name: "Shares Batch", product_type: "SHARES", share_class_id: 2, class_currency: "NGN" }),
];

// The Fund/Share entity dropdown (the NGN card also has a "View in" select).
const entityCombo = () => screen.getByRole("combobox", { name: /^(Fund|Share|Fund \/ Share)$/ });

function renderPage(initialPath = "/overview") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <OverviewPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.mocked(fundService.getSummary).mockImplementation(async (product) =>
    product === "SHARES" ? SHARES_SUMMARY : FUNDS_SUMMARY
  );
  vi.mocked(batchService.getAll).mockResolvedValue(BATCHES);
  vi.mocked(dashboardService.getOverviewStats).mockResolvedValue({
    total_aum: 10500,
    total_aum_kes: 10500,
    total_aum_usd: 0,
    gain_kes: 500,
    gain_usd: 0,
    total_ngn: 15_750_000,
    gain_ngn: 750_000,
    total_investors: 8,
    performance_pct: 5,
    active_batches: 2,
  });
});

describe("Overview — card visibility per product (Task 10)", () => {
  it("Product = Funds shows only KES/USD totals, no NGN", async () => {
    renderPage("/overview?product=FUNDS");
    await screen.findByText("Axiom");

    expect(screen.getAllByText("KES").length).toBeGreaterThan(0);
    expect(screen.getAllByText("USD").length).toBeGreaterThan(0);
    expect(screen.queryAllByText("NGN")).toHaveLength(0);
  });

  it("Product = Shares shows only the NGN total, no KES/USD", async () => {
    renderPage("/overview?product=SHARES");
    await waitFor(() => expect(screen.getAllByText("NGN").length).toBeGreaterThan(0));

    expect(screen.queryAllByText("KES")).toHaveLength(0);
    // No KES/USD total cards (the NGN card's "View in" dropdown has a USD option).
    expect(screen.queryAllByText("USD").filter((el) => el.tagName !== "OPTION")).toHaveLength(0);
  });

  it("Product = All shows KES, USD and NGN together", async () => {
    renderPage("/overview");
    await waitFor(() => expect(screen.getAllByText("NGN").length).toBeGreaterThan(0));

    expect(screen.getAllByText("KES").length).toBeGreaterThan(0);
    expect(screen.getAllByText("USD").length).toBeGreaterThan(0);
    expect(screen.getAllByText("NGN").length).toBeGreaterThan(0);
  });
});

describe("Overview — dropdown / Product tab sync (Task 10)", () => {
  it("groups the dropdown into Funds and Shares optgroups", async () => {
    renderPage("/overview");
    await screen.findByText("Axiom");

    const combo = entityCombo() as HTMLSelectElement;
    const groups = within(combo).getAllByRole("group") as HTMLOptGroupElement[];
    const groupLabels = groups.map((g) => g.label);
    expect(groupLabels).toEqual(["Funds", "Shares"]);
    expect(within(combo).getByText("Axiom")).toBeInTheDocument();
    expect(within(combo).getByText(/Dangote/i)).toBeInTheDocument();
  });

  it("choosing a share switches the Product tab to Shares", async () => {
    const user = userEvent.setup();
    renderPage("/overview");
    await screen.findByText("Axiom");

    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");

    const combo = entityCombo();
    await user.selectOptions(combo, "2");

    await waitFor(() => expect(screen.getByRole("button", { name: "Shares" })).toHaveAttribute("aria-pressed", "true"));
  });

  it("choosing the Shares tab narrows the dropdown to shares only", async () => {
    const user = userEvent.setup();
    renderPage("/overview");
    await screen.findByText("Axiom");

    await user.click(screen.getByRole("button", { name: "Shares" }));

    const combo = entityCombo();
    expect(within(combo).queryByText("Axiom")).not.toBeInTheDocument();
    expect(within(combo).getByText(/Dangote/i)).toBeInTheDocument();
  });
});

describe("Overview — NGN totals for a seeded share holding (Task 10)", () => {
  it("shows Net Holdings / Gross Invested / Gain for the selected share from its own summary data", async () => {
    const user = userEvent.setup();
    renderPage("/overview");
    await screen.findByText("Axiom");

    const combo = entityCombo();
    await user.selectOptions(combo, "2");

    await waitFor(() => expect(screen.getByRole("button", { name: "Shares" })).toHaveAttribute("aria-pressed", "true"));
    await waitFor(() => expect(screen.getAllByText("NGN").length).toBeGreaterThan(0));

    expect(screen.getByText(/₦ 15,750,000\.00/)).toBeInTheDocument();
    // Deposit-side lines are the USD deposits; value/gain are NGN.
    expect(screen.getByText(/Net Holdings:/).parentElement).toHaveTextContent("$ 10,000.00");
    expect(screen.getByText(/Gross Invested:/).parentElement).toHaveTextContent("$ 10,000.00");
    expect(screen.getByText(/Gain\/Loss:/).parentElement).toHaveTextContent("+₦ 750,000.00");
  });
});

describe("Overview — no remaining AUM strings in the UI (Task 10)", () => {
  it("renders no 'AUM' text in any product view", async () => {
    const { unmount } = renderPage("/overview");
    await waitFor(() => expect(screen.getAllByText("NGN").length).toBeGreaterThan(0));
    expect(screen.queryByText(/AUM/i)).not.toBeInTheDocument();
    unmount();

    renderPage("/overview?product=FUNDS");
    await waitFor(() => expect(screen.getAllByText("KES").length).toBeGreaterThan(0));
    expect(screen.queryByText(/AUM/i)).not.toBeInTheDocument();
  });
});
