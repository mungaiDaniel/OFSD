import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BulkTypeSendPanel from "./BulkTypeSendPanel";
import { emailService } from "@/services/emailService";
import { batchService } from "@/services/batchService";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() } }));
vi.mock("@/services/batchService", () => ({ batchService: { getAll: vi.fn() } }));
vi.mock("@/services/emailService", () => ({
  emailService: {
    getQueueStatus: vi.fn(),
    bulkSendPreview: vi.fn(),
    bulkSend: vi.fn(),
    statusCounts: vi.fn(),
  },
}));

const funds = [{ id: 7, fund_name: "Dangote Shares" }] as any;
const row = (name: string, state: string) => ({
  client_code: name, name, email: `${name}@x.com`, fund_name: "Dangote Shares", batch_name: "Batch 1",
  amount: 1000, currency: "USD", email_type: "OFFSHORE_TRANSFER", state,
});
const preview = (rows: any[], will_send: number) => ({
  kind: "transfer", label: "Transfer confirmation", rows,
  counts: { total: rows.length, no_email: 0, ready: will_send, in_progress: 0, already_sent: rows.length - will_send, will_send },
});

describe("BulkTypeSendPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(batchService.getAll).mockResolvedValue([{ id: 3, batch_name: "Batch 1", funds: [{ fund_name: "Dangote Shares" }] }] as any);
    vi.mocked(emailService.getQueueStatus).mockResolvedValue({ data: { batch_size: 100, interval_minutes: 5, queued_count: 0, next_run_at: null } } as any);
    vi.mocked(emailService.statusCounts).mockResolvedValue({ total: 2, counts: { Confirmed: 2 } });
  });

  it("needs a fund or batch before it can preview", async () => {
    render(<BulkTypeSendPanel kind="transfer" funds={funds} />);
    expect(screen.getByRole("button", { name: /preview list/i })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Fund"), "7");
    expect(screen.getByRole("button", { name: /preview list/i })).toBeEnabled();
  });

  it("previews, confirms, then sends exactly the previewed count", async () => {
    vi.mocked(emailService.bulkSendPreview).mockResolvedValue(preview([row("Ann", "none"), row("Bob", "pending"), row("Cy", "sent")], 2) as any);
    vi.mocked(emailService.bulkSend).mockResolvedValue({ email_ids: [11, 12], created: 1, requeued: 1 });

    render(<BulkTypeSendPanel kind="transfer" funds={funds} />);
    await userEvent.selectOptions(screen.getByLabelText("Fund"), "7");
    await userEvent.click(screen.getByRole("button", { name: /preview list/i }));

    expect(emailService.bulkSendPreview).toHaveBeenCalledWith(expect.objectContaining({ kind: "transfer", fundId: 7 }));
    expect(await screen.findByText("Already sent")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /send 2 emails/i }));
    // the dialog lists only the two that will go out
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Ann");
    expect(dialog).toHaveTextContent("Bob");
    expect(dialog).not.toHaveTextContent("Cy@x.com");

    await userEvent.click(screen.getByRole("button", { name: /send 2 now/i }));
    await waitFor(() => expect(emailService.bulkSend).toHaveBeenCalledWith(expect.objectContaining({ kind: "transfer", fundId: 7 }), 2));
    await waitFor(() => expect(emailService.statusCounts).toHaveBeenCalledWith([11, 12]));
    expect(await screen.findByLabelText("Send progress")).toHaveTextContent("2 of 2 sent");
  });

  it("clears the preview when the selection changes, so an old list can never be sent", async () => {
    vi.mocked(emailService.bulkSendPreview).mockResolvedValue(preview([row("Ann", "none")], 1) as any);
    render(<BulkTypeSendPanel kind="transfer" funds={funds} />);
    await userEvent.selectOptions(screen.getByLabelText("Fund"), "7");
    await userEvent.click(screen.getByRole("button", { name: /preview list/i }));
    expect(await screen.findByRole("button", { name: /send 1 email/i })).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("Batch"), "3");
    expect(screen.queryByRole("button", { name: /send 1 email/i })).not.toBeInTheDocument();
  });
});
