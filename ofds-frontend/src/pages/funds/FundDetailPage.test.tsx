import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import FundDetailPage from "./FundDetailPage";
import ShareDetailPage from "@/pages/shares/ShareDetailPage";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { reportService } from "@/services/reportService";
import type { CoreFund, FundEditContext } from "@/lib/types";

vi.mock("@/services/fundService");
vi.mock("@/services/batchService");
vi.mock("@/services/reportService");
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
// Charts need a canvas — irrelevant to the edit flow.
vi.mock("@/components/charts/ChartCard", () => ({ ChartCard: ({ children }: any) => <div>{children}</div> }));
vi.mock("@/components/charts/DepositsWithdrawalsBarChart", () => ({ DepositsWithdrawalsBarChart: () => null }));
vi.mock("@/components/charts/NAVLineChart", () => ({ NAVLineChart: () => null }));

const AXIOM: CoreFund = { id: 1, fund_name: "Axiom", fund_code: "AXM", product_type: "FUNDS", is_active: true };
const DPRP: CoreFund = {
  id: 2,
  fund_name: "Dangote Petroleum Refinery and Petrochemicals FZE",
  fund_code: "DPRP",
  product_type: "SHARES",
  is_active: true,
};

function ctxFor(fund: CoreFund, locked: boolean): FundEditContext {
  const isShares = fund.product_type === "SHARES";
  return {
    fund: {
      id: fund.id,
      fund_name: fund.fund_name,
      fund_code: fund.fund_code,
      description: null,
      product_type: fund.product_type!,
      is_active: true,
      version: "v1",
    },
    allowed_currencies: isShares ? ["NGN"] : ["KES", "USD"],
    can_override_currency: true,
    open_batches: [],
    rename_locked: false,
    share_classes: [
      {
        id: 10,
        core_fund_id: fund.id,
        class_name: "Class I",
        class_code: isShares ? "DPRP-NGN" : "AXM-USD",
        currency: isShares ? "NGN" : "USD",
        product_type: fund.product_type!,
        is_active: true,
        version: "c1",
        currency_locked: locked,
        currency_lock_reasons: locked ? ["3 deposits"] : [],
        open_batches: [],
      },
    ],
  };
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/funds/:id" element={<FundDetailPage />} />
        <Route path="/shares/:id" element={<ShareDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.setItem("ofds_user_role", "super_admin");
  vi.mocked(batchService.getAll).mockResolvedValue([]);
  vi.mocked(reportService.getAll).mockResolvedValue([]);
  vi.mocked(fundService.getSummary).mockResolvedValue(null);
  vi.mocked(fundService.getById).mockImplementation(async (id) => (id === 2 ? DPRP : AXIOM));
  vi.mocked(fundService.getClasses).mockImplementation(async (id) => [
    {
      id: 10,
      class_name: "Class I",
      class_code: id === 2 ? "DPRP-NGN" : "AXM-USD",
      currency: id === 2 ? "NGN" : "USD",
    },
  ]);
});

describe("Edit fund / share (Task 12)", () => {
  it("shows 'Edit fund' next to Delete on /funds/:id and saves through PATCH with the version", async () => {
    const user = userEvent.setup();
    vi.mocked(fundService.getEditContext).mockResolvedValue(ctxFor(AXIOM, false));
    vi.mocked(fundService.updateFund).mockResolvedValue({ ...ctxFor(AXIOM, false).fund, fund_name: "Axiom Global" });
    renderAt("/funds/1");

    const editBtn = await screen.findByRole("button", { name: /Edit fund/i });
    expect(screen.getByRole("button", { name: /^Delete$/ })).toBeInTheDocument();
    await user.click(editBtn);

    const name = await screen.findByLabelText(/Fund Name/i);
    expect(name).toHaveValue("Axiom");
    expect(screen.getByLabelText(/Fund Code/i)).toHaveValue("AXM");

    await user.clear(name);
    await user.type(name, "Axiom Global");
    await user.click(screen.getByRole("button", { name: /Save changes/i }));

    await waitFor(() =>
      expect(fundService.updateFund).toHaveBeenCalledWith(1, { version: "v1", fund_name: "Axiom Global" }, "FUNDS")
    );
  });

  it("shows 'Edit share' on /shares/:id and uses the SHARES product", async () => {
    const user = userEvent.setup();
    vi.mocked(fundService.getEditContext).mockResolvedValue(ctxFor(DPRP, false));
    renderAt("/shares/2");

    await user.click(await screen.findByRole("button", { name: /Edit share/i }));
    expect(fundService.getEditContext).toHaveBeenCalledWith(2, "SHARES");
    expect(await screen.findByLabelText(/Share Name/i)).toHaveValue(DPRP.fund_name);
    // Product is shown read-only, never as an editable control.
    expect(screen.getByDisplayValue("Shares")).toHaveAttribute("readonly");
  });

  it("hides Edit and Delete for non super admins", async () => {
    localStorage.setItem("ofds_user_role", "admin");
    renderAt("/funds/1");
    await screen.findByRole("heading", { name: /Axiom/i });
    expect(screen.queryByRole("button", { name: /Edit fund/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete$/ })).not.toBeInTheDocument();
  });

  it("shows Delete for super admins", async () => {
    renderAt("/funds/1");
    expect(await screen.findByRole("button", { name: /^Delete$/ })).toBeInTheDocument();
  });

  it("shows a reload prompt on a version conflict", async () => {
    const user = userEvent.setup();
    vi.mocked(fundService.getEditContext).mockResolvedValue(ctxFor(AXIOM, false));
    vi.mocked(fundService.updateFund).mockRejectedValue({
      response: { status: 409, data: { code: "VERSION_CONFLICT", message: "This record was changed by someone else." } },
    });
    renderAt("/funds/1");
    await user.click(await screen.findByRole("button", { name: /Edit fund/i }));
    const desc = await screen.findByLabelText(/Description/i);
    await user.type(desc, "New text");
    await user.click(screen.getByRole("button", { name: /Save changes/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed by someone else/i);
    expect(screen.getByRole("button", { name: /Reload latest/i })).toBeInTheDocument();
  });
});

describe("Edit share class currency lock (Task 12)", () => {
  it("currency is editable while the class is empty", async () => {
    const user = userEvent.setup();
    vi.mocked(fundService.getEditContext).mockResolvedValue(ctxFor(AXIOM, false));
    vi.mocked(fundService.updateClass).mockResolvedValue(ctxFor(AXIOM, false).share_classes[0]!);
    renderAt("/funds/1");

    await screen.findByText("Class I");
    await user.click(screen.getAllByRole("button", { name: /^Edit$/ })[0]!);
    const currency = await screen.findByLabelText(/Currency \*/i);
    expect(currency.tagName).toBe("SELECT");
    await user.selectOptions(currency, "KES");
    await user.click(screen.getByRole("button", { name: /Save changes/i }));
    await waitFor(() =>
      expect(fundService.updateClass).toHaveBeenCalledWith(1, 10, { version: "c1", currency: "KES" }, "FUNDS")
    );
  });

  it("currency is read-only with an explanation once locked, and the override needs explicit confirmation", async () => {
    const user = userEvent.setup();
    vi.mocked(fundService.getEditContext).mockResolvedValue(ctxFor(AXIOM, true));
    vi.mocked(fundService.updateClass).mockResolvedValue(ctxFor(AXIOM, true).share_classes[0]!);
    renderAt("/funds/1");

    await screen.findByText("Class I");
    await user.click(screen.getAllByRole("button", { name: /^Edit$/ })[0]!);
    const locked = await screen.findByLabelText(/Currency \*/i);
    expect(locked).toHaveAttribute("readonly");
    expect(screen.getByText(/Currency is locked because this has deposits\/valuations/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Override \(super admin\)/i }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent(/will not be converted/i);
    const unlock = screen.getByRole("button", { name: /Unlock currency/i });
    expect(unlock).toBeDisabled();
    await user.click(screen.getByRole("checkbox"));
    await user.click(unlock);

    const select = await screen.findByLabelText(/Currency \*/i);
    expect(select.tagName).toBe("SELECT");
    await user.selectOptions(select, "KES");
    await user.click(screen.getByRole("button", { name: /Save changes/i }));
    await waitFor(() =>
      expect(fundService.updateClass).toHaveBeenCalledWith(
        1,
        10,
        { version: "c1", currency: "KES", confirm_currency_override: true },
        "FUNDS"
      )
    );
  });
});
