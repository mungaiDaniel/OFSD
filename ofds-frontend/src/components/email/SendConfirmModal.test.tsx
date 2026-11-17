import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SendConfirmModal, { estimateSendTime } from "./SendConfirmModal";

const items = (n: number) => Array.from({ length: n }, (_, i) => ({ primary: `Investor ${i + 1}`, secondary: `i${i + 1}@x.com` }));

describe("SendConfirmModal", () => {
  it("lists the exact emails and sends with one click when the count is small", async () => {
    const onConfirm = vi.fn();
    render(<SendConfirmModal open title="Send these 3?" items={items(3)} count={3} onConfirm={onConfirm} onCancel={vi.fn()} />);
    expect(screen.getByText("Investor 2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /send 3 now/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("makes the admin type the count for larger sends", async () => {
    const onConfirm = vi.fn();
    render(<SendConfirmModal open title="t" items={items(30)} count={30} onConfirm={onConfirm} onCancel={vi.fn()} />);
    const send = screen.getByRole("button", { name: /send 30 now/i });
    expect(send).toBeDisabled();

    const box = screen.getByLabelText("Type the number of emails to confirm");
    await userEvent.type(box, "29");
    expect(send).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, "30");
    expect(send).toBeEnabled();
    await userEvent.click(send);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("can require typing even for a small count", () => {
    render(<SendConfirmModal open title="t" items={[]} count={2} requireTypedCount onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("button", { name: /send 2 now/i })).toBeDisabled();
  });

  it("cannot send nothing, and cancel does not confirm", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<SendConfirmModal open title="t" items={[]} count={0} cancelLabel="Keep in Inbox" onConfirm={onConfirm} onCancel={onCancel} />);
    expect(screen.getByRole("button", { name: /send 0 now/i })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Keep in Inbox" }));
    expect(onCancel).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("renders nothing when closed", () => {
    const { container } = render(<SendConfirmModal open={false} title="t" items={[]} count={1} onConfirm={vi.fn()} onCancel={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("estimateSendTime", () => {
  it("uses the drip rate", () => {
    expect(estimateSendTime(200, { batch_size: 100, interval_minutes: 5 })).toBe("about 10 min");
    expect(estimateSendTime(5000, { batch_size: 100, interval_minutes: 5 })).toBe("about 4.2 hours");
    expect(estimateSendTime(10, null)).toBe("");
  });
});
