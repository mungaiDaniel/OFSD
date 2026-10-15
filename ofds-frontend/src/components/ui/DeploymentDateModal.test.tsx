import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DeploymentDateModal } from "./DeploymentDateModal";
import type { BatchInvestorLight } from "@/lib/types";

const INVESTORS: BatchInvestorLight[] = [
  { id: 1, investor_name: "Alice Johnson", internal_client_code: "INV-001", amount_deposited: 1000, main_balance: 1000, share_class_id: 1, class_code: "CI-USD", class_currency: "USD" },
  { id: 2, investor_name: "Bob Smith", internal_client_code: "INV-002", amount_deposited: 3000, main_balance: 3000, share_class_id: 1, class_code: "CI-USD", class_currency: "USD" },
];

// Date inputs can't be typed into reliably in jsdom — set them directly.
const setDateInput = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });

describe("DeploymentDateModal — manual per-client date + NAV (Deploy stage)", () => {
  it("lists every client with their own date and NAV inputs, blocking confirm until all are filled", async () => {
    const user = userEvent.setup();
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByText("Alice Johnson")).toBeInTheDocument();
    expect(screen.getByText("Bob Smith")).toBeInTheDocument();

    const confirm = screen.getByRole("button", { name: /Deploy & Activate/ });
    await user.type(screen.getByLabelText("NAV per share for Alice Johnson"), "100");
    await user.type(screen.getByLabelText("NAV per share for Bob Smith"), "120");
    // NAVs alone aren't enough — each client also needs a deployment date.
    expect(confirm).toBeDisabled();

    setDateInput(screen.getByLabelText("Deployment date for Alice Johnson"), "2026-10-01");
    expect(confirm).toBeDisabled();
    setDateInput(screen.getByLabelText("Deployment date for Bob Smith"), "2026-10-08");
    expect(confirm).toBeEnabled();
  });

  it("'Apply to all' fills every client's date and NAV", async () => {
    const user = userEvent.setup();
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={vi.fn()} onClose={vi.fn()} />);

    setDateInput(screen.getByLabelText("Deployment date for all clients"), "2026-10-05");
    await user.type(screen.getByPlaceholderText("e.g., 1389.5737"), "250");
    await user.click(screen.getByRole("button", { name: "Apply to all" }));

    for (const name of ["Alice Johnson", "Bob Smith"]) {
      expect((screen.getByLabelText(`NAV per share for ${name}`) as HTMLInputElement).value).toBe("250");
      expect((screen.getByLabelText(`Deployment date for ${name}`) as HTMLInputElement).value).toBe("2026-10-05");
    }
  });

  it("sends each client's date and NAV, per-class totals, and the earliest date as the batch date", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);

    setDateInput(screen.getByLabelText("Deployment date for Alice Johnson"), "2026-10-08");
    setDateInput(screen.getByLabelText("Deployment date for Bob Smith"), "2026-10-01");
    await user.type(screen.getByLabelText("NAV per share for Alice Johnson"), "100");
    await user.type(screen.getByLabelText("NAV per share for Bob Smith"), "120");
    await user.click(screen.getByRole("button", { name: /Deploy & Activate/ }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const payload = onConfirm.mock.calls[0]![0];
    expect(payload.investorNavs).toEqual({ 1: 100, 2: 120 });
    expect(payload.investorDates).toEqual({
      1: new Date("2026-10-08").toISOString(),
      2: new Date("2026-10-01").toISOString(),
    });
    expect(payload.dateString).toBe(new Date("2026-10-01").toISOString());
    // 1000/100 = 10 shares, 3000/120 = 25 shares -> 35 shares, 4000 NAV.
    expect(payload.classes).toHaveLength(1);
    expect(payload.classes[0].totalShares).toBe(35);
    expect(payload.classes[0].totalNav).toBe(4000);
  });

  it("'One NAV for everyone' uses one date and one NAV per class, with no per-client values", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn().mockResolvedValue(undefined);
    render(<DeploymentDateModal open investments={INVESTORS} onConfirm={onConfirm} onClose={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "One NAV for everyone" }));
    expect(screen.queryByLabelText("NAV per share for Alice Johnson")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Deployment date for Alice Johnson")).not.toBeInTheDocument();

    setDateInput(document.querySelector('input[type="date"]') as HTMLElement, "2026-10-01");
    await user.type(screen.getByPlaceholderText("e.g., 1389.5737"), "100");
    await user.click(screen.getByRole("button", { name: /Deploy & Activate/ }));

    const payload = onConfirm.mock.calls[0]![0];
    expect(payload.investorNavs).toBeUndefined();
    expect(payload.investorDates).toBeUndefined();
    expect(payload.dateString).toBe(new Date("2026-10-01").toISOString());
    expect(payload.classes[0]).toMatchObject({ navPerShare: 100, totalShares: 40, totalNav: 4000 });
  });
});
