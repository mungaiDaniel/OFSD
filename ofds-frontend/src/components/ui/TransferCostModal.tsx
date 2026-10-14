import { useState } from "react";
import { createPortal } from "react-dom";
import { DollarSign, X, Check, Loader2 } from "lucide-react";
import type { BatchInvestorLight } from "@/lib/types";

interface TransferCostModalProps {
  open: boolean;
  onClose: () => void;
  investments: BatchInvestorLight[];
  /** amountsReceived is keyed by investment id — the real amount that landed
   * in the bank for that investor, manually entered. */
  onConfirm: (amountsReceived: Record<number, number>, entryFeePercent: number) => Promise<void>;
  isLoading?: boolean;
}

const fmt = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/**
 * Advance-to-Transfer: lists every client in the batch so the admin can type
 * in the amount actually received from the bank for each one (wires rarely
 * arrive as a neat prorated share of one aggregate transaction cost — the
 * bank's own deduction varies per transfer). The entry fee % still applies,
 * now against each investor's real received amount instead of a formula.
 */
export function TransferCostModal({
  open,
  onClose,
  investments,
  onConfirm,
  isLoading = false,
}: TransferCostModalProps) {
  // Defaults every row to the full deposited amount — the common case is the
  // full wire arrived, so the admin only needs to touch the rows that differ.
  const [amounts, setAmounts] = useState<Record<number, string>>(() =>
    Object.fromEntries(investments.map((inv) => [inv.id, String(inv.amount_deposited)]))
  );
  const [entryFeePercent, setEntryFeePercent] = useState<string>("0");

  if (!open) return null;

  const entryFeeRate = (parseFloat(entryFeePercent) || 0) / 100;

  const rows = investments.map((inv) => {
    const received = Math.max(0, parseFloat(amounts[inv.id] ?? "") || 0);
    const bankDeduction = Math.max(0, inv.amount_deposited - received);
    const entryFee = received * entryFeeRate;
    const net = Math.max(0, received - entryFee);
    return { inv, received, bankDeduction, entryFee, net };
  });

  const totalDeposited = rows.reduce((s, r) => s + r.inv.amount_deposited, 0);
  const totalReceived = rows.reduce((s, r) => s + r.received, 0);
  const totalBankDeduction = rows.reduce((s, r) => s + r.bankDeduction, 0);
  const totalEntryFee = rows.reduce((s, r) => s + r.entryFee, 0);
  const totalNet = rows.reduce((s, r) => s + r.net, 0);

  const setAmount = (id: number, value: string) => setAmounts((prev) => ({ ...prev, [id]: value }));

  const handleConfirm = async () => {
    const amountsReceived: Record<number, number> = {};
    for (const inv of investments) {
      amountsReceived[inv.id] = Math.max(0, parseFloat(amounts[inv.id] ?? "") || 0);
    }
    await onConfirm(amountsReceived, parseFloat(entryFeePercent) || 0);
  };

  const overlayStyle: React.CSSProperties = {
    position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
    background: "rgba(0, 0, 0, 0.4)", backdropFilter: "blur(4px)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 9999, padding: "20px",
  };

  const modalStyle: React.CSSProperties = {
    background: "#0B1228", borderRadius: "16px", width: "100%", maxWidth: "820px",
    border: "1px solid rgba(255, 255, 255, 0.08)", boxShadow: "0 24px 48px rgba(0, 0, 0, 0.4)",
    overflow: "hidden auto", display: "flex", flexDirection: "column",
    color: "#fff", fontFamily: "var(--font-sans)", maxHeight: "90vh",
  };

  const headerStyle: React.CSSProperties = {
    padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.06)",
    display: "flex", alignItems: "center", justifyContent: "space-between",
  };

  const contentStyle: React.CSSProperties = { padding: "24px", display: "flex", flexDirection: "column", gap: "16px" };

  const smallInputStyle: React.CSSProperties = {
    width: "130px", background: "rgba(255, 255, 255, 0.05)", border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: "6px", color: "#fff", padding: "6px 10px", fontSize: "12px", outline: "none",
    fontFamily: "var(--font-mono)", colorScheme: "dark", textAlign: "right",
  };

  const inputStyle: React.CSSProperties = {
    width: "100%", background: "rgba(255, 255, 255, 0.05)", border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: "8px", color: "#fff", padding: "12px 16px", fontSize: "14px", outline: "none",
    fontFamily: "var(--font-mono)", colorScheme: "dark",
  };

  return createPortal(
    <div style={overlayStyle} onClick={onClose} className="scale-in">
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div style={headerStyle}>
          <div className="d-flex align-items-center gap-2">
            <div
              style={{
                width: "32px", height: "32px", background: "rgba(59, 111, 212, 0.15)",
                color: "#3B6FD4", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <DollarSign size={16} />
            </div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Advance to Transfer</h3>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            style={{ background: "transparent", border: "none", color: "#94A3B8", cursor: isLoading ? "not-allowed" : "pointer", padding: "4px" }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={contentStyle}>
          <p style={{ margin: 0, fontSize: "14px", color: "rgba(255,255,255,0.7)", lineHeight: 1.5 }}>
            Enter the amount each client's wire actually landed as — defaults to their full deposit. The
            entry fee % below is then taken off each client's real received amount.
          </p>

          <div>
            <label style={{ display: "block", fontSize: "12px", color: "#94A3B8", marginBottom: "6px", fontWeight: 500 }}>
              ENTRY FEE PERCENTAGE (%)
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              max="100"
              style={inputStyle}
              value={entryFeePercent}
              onChange={(e) => setEntryFeePercent(e.target.value)}
              disabled={isLoading}
              placeholder="2.00"
            />
          </div>

          <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", overflow: "hidden" }}>
            <div style={{ maxHeight: "320px", overflowY: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead style={{ position: "sticky", top: 0, background: "#111a33" }}>
                  <tr>
                    {["Client", "Deposited (USD)", "Amount Received (USD)", "Net"].map((h, i) => (
                      <th
                        key={h}
                        style={{ padding: "8px 10px", textAlign: i === 0 ? "left" : "right", color: "#94A3B8", fontWeight: 600, whiteSpace: "nowrap" }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ inv, net }) => (
                    <tr key={inv.id} style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                      <td style={{ padding: "6px 10px" }}>
                        <div style={{ color: "#fff", fontWeight: 500 }}>{inv.investor_name}</div>
                        <div style={{ color: "rgba(255,255,255,0.4)", fontFamily: "var(--font-mono)", fontSize: "10px" }}>
                          {inv.internal_client_code}
                        </div>
                      </td>
                      <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.6)", fontFamily: "var(--font-mono)" }}>
                        {fmt(inv.amount_deposited)}
                      </td>
                      <td style={{ padding: "6px 10px", textAlign: "right" }}>
                        <input
                          type="number"
                          step="0.01"
                          min="0"
                          style={smallInputStyle}
                          value={amounts[inv.id] ?? ""}
                          onChange={(e) => setAmount(inv.id, e.target.value)}
                          disabled={isLoading}
                        />
                      </td>
                      <td style={{ padding: "6px 10px", textAlign: "right", color: "#86EFAC", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                        {fmt(net)}
                      </td>
                    </tr>
                  ))}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={4} style={{ padding: "16px", textAlign: "center", color: "rgba(255,255,255,0.4)" }}>
                        No clients in this batch.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div
            style={{
              background: "rgba(255, 255, 255, 0.04)",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              borderRadius: "10px",
              padding: "12px",
              display: "flex",
              flexDirection: "column",
              gap: "6px",
              fontSize: "12px",
              fontFamily: "var(--font-mono)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", color: "#CBD5E1" }}>
              <span>Initial Batch Total</span>
              <span>${fmt(totalDeposited)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#CBD5E1" }}>
              <span>Total Amount Received</span>
              <span>${fmt(totalReceived)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#FCA5A5" }}>
              <span>Bank Deduction (implied)</span>
              <span>-${fmt(totalBankDeduction)}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#FBBF24" }}>
              <span>Entry Fee ({(parseFloat(entryFeePercent) || 0).toFixed(2)}%)</span>
              <span>-${fmt(totalEntryFee)}</span>
            </div>
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", marginTop: "4px", paddingTop: "8px", display: "flex", justifyContent: "space-between", color: "#86EFAC", fontWeight: 700 }}>
              <span>Total Active Principal</span>
              <span>${fmt(totalNet)}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: "16px 24px", background: "rgba(0,0,0,0.2)", borderTop: "1px solid rgba(255,255,255,0.06)",
          display: "flex", justifyContent: "flex-end", gap: "12px",
        }}>
          <button
            onClick={onClose}
            disabled={isLoading}
            style={{
              background: "transparent", border: "1px solid rgba(255, 255, 255, 0.1)", color: "#fff",
              padding: "8px 16px", borderRadius: "6px", fontSize: "13px", fontWeight: 500,
              cursor: isLoading ? "not-allowed" : "pointer", transition: "all 0.2s",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isLoading}
            style={{
              background: "#3B6FD4", border: "none", color: "#fff", padding: "8px 16px", borderRadius: "6px",
              fontSize: "13px", fontWeight: 500, cursor: isLoading ? "not-allowed" : "pointer",
              opacity: isLoading ? 0.6 : 1, display: "flex", alignItems: "center", gap: "6px", transition: "all 0.2s",
            }}
          >
            {isLoading ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
            Confirm & Transfer
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
