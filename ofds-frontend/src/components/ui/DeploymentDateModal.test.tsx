import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeploymentDateModal } from "./DeploymentDateModal";
import type { BatchInvestorLight } from "@/lib/types";

const INVESTORS: BatchInvestorLight[] = [
  { id: 1, investor_name: "Alice Johnson", internal_client_code: "INV-001", amount_deposited: 1000, main_balance: 1000, share_class_id: 1, class_code: "CI-USD", class_currency: "USD" },
  { id: 2, investor_name: "Bob Smith", internal_client_code: "INV-002", amount_deposited: 3000, main_balance: 3000, share_class_id: 1, class_code: "CI-USD", class_currency: "USD" },
];

const setDate = () => {
  const dateInput = document.querySelector('input[type="date"]') as HTMLInputElement;
  fireEvent.change(dateInput, { target: { value: "2026-10-01" } });
};

describe("DeploymentDateModal — manual per-client NAV (Deploy stage)", () => {
  it("lists every client with their own NAV input and blocks confirm until all are priced", async () => {
    const user = userEvent.setup();
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);
    setDate();

    expect(screen.getByText("Alice Johnson")).toBeInTheDocument();
    expect(screen.getByText("Bob Smith")).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: /Deploy & Activate/ });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText("NAV per share for Alice Johnson"), "100");
    expect(confirm).toBeDisabled();
    await user.type(screen.getByLabelText("NAV per share for Bob Smith"), "120");
    expect(confirm).toBeEnabled();
  });

  it("'Apply to all' fills every client's NAV", async () => {
    const user = userEvent.setup();
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    await user.type(screen.getByPlaceholderText("e.g., 1389.5737"), "250");
    await user.click(screen.getByRole("button", { name: "Apply to all" }));

    expect((screen.getByLabelText("NAV per share for Alice Johnson") as HTMLInputElement).value).toBe("250");
    expect((screen.getByLabelText("NAV per share for Bob Smith") as HTMLInputElement).value).toBe("250");
  });

  it("sends each client's NAV plus per-class totals on confirm", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);
    setDate();

    await user.type(screen.getByLabelText("NAV per share for Alice Johnson"), "100");
    await user.type(screen.getByLabelText("NAV per share for Bob Smith"), "120");
    await user.click(screen.getByRole("button", { name: /Deploy & Activate/ }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const payload = onConfirm.mock.calls[0]![0];
    expect(payload.investorNavs).toEqual({ 1: 100, 2: 120 });
    // 1000/100 = 10 shares, 3000/120 = 25 shares -> 35 shares, 4000 NAV.
    expect(payload.classes).toHaveLength(1);
    expect(payload.classes[0].totalShares).toBe(35);
    expect(payload.classes[0].totalNav).toBe(4000);
  });

  it("'One NAV for everyone' mode still uses a single NAV per class and sends no per-client NAVs", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);
    setDate();

    await user.click(screen.getByRole("button", { name: "One NAV for everyone" }));
    expect(screen.queryByLabelText("NAV per share for Alice Johnson")).not.toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("e.g., 1389.5737"), "100");
    await user.click(screen.getByRole("button", { name: /Deploy & Activate/ }));

    const payload = onConfirm.mock.calls[0]![0];
    expect(payload.investorNavs).toBeUndefined();
    expect(payload.classes[0]).toMatchObject({ navPerShare: 100, totalShares: 40, totalNav: 4000 });
  });
});
