import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { DollarSign, X, Check, Loader2 } from "lucide-react";
import type { BatchInvestorLight } from "@/lib/types";

export type TransferMode = "manual" | "aggregate";

interface TransferCostModalProps {
  open: boolean;
  onClose: () => void;
  investments: BatchInvestorLight[];
  /**
   * mode="manual": amountsReceived is the real amount typed in per investor
   * (keyed by investment id), transactionCostUsd is null.
   * mode="aggregate": transactionCostUsd is one lump-sum transaction cost for
   * the whole batch (split pro-rata server-side, same as before this
   * feature existed), amountsReceived is null.
   */
  onConfirm: (
    mode: TransferMode,
    amountsReceived: Record<number, number> | null,
    transactionCostUsd: number | null,
    entryFeePercent: number
  ) => Promise<void>;
  isLoading?: boolean;
}

const fmt = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function seedAmounts(investments: BatchInvestorLight[]): Record<number, string> {
  return Object.fromEntries(investments.map((inv) => [inv.id, String(inv.amount_deposited)]));
}

/**
 * Advance-to-Transfer: two ways to tell the system what actually landed in
 * the bank —
 * - Manual (per client): type in the real amount received for each investor
 *   (wires rarely arrive as a neat prorated share of one aggregate cost).
 * - Whole batch at once: the original single Transaction Cost (USD), split
 *   pro-rata across investors server-side — unchanged from before.
 * Either way the entry fee % applies afterward, same as always.
 */
export function TransferCostModal({
  open,
  onClose,
  investments,
  onConfirm,
  isLoading = false,
}: TransferCostModalProps) {
  const [mode, setMode] = useState<TransferMode>("manual");
  const [amounts, setAmounts] = useState<Record<number, string>>({});
  const [transactionCost, setTransactionCost] = useState<string>("0");
  const [entryFeePercent, setEntryFeePercent] = useState<string>("0");

  // Re-seed every time the modal is freshly opened — `investments` can still
  // be an empty placeholder on the very first render (it loads just before
  // this modal opens), so seeding once via a useState initializer left every
  // row stuck blank/zero. Re-seeding on `open` instead means it always picks
  // up whatever investments list is current at the moment it's shown.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (open) setAmounts(seedAmounts(investments));
  }, [open]);

  if (!open) return null;

  const entryFeeRate = (parseFloat(entryFeePercent) || 0) / 100;

  // ── Manual mode math ──
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
  const totalEntryFeeManual = rows.reduce((s, r) => s + r.entryFee, 0);
  const totalNetManual = rows.reduce((s, r) => s + r.net, 0);

  // ── Aggregate (whole batch at once) mode math — same formula as before
  // this feature existed: one transaction cost off the top, then entry fee
  // on what's left. The actual per-investor split still happens server-side.
  const transactionCostUsd = parseFloat(transactionCost) || 0;
  const netAfterTransactionCost = Math.max(0, totalDeposited - transactionCostUsd);
  const entryFeeAggregate = Math.max(0, netAfterTransactionCost * entryFeeRate);
  const totalNetAggregate = Math.max(0, netAfterTransactionCost - entryFeeAggregate);

  const setAmount = (id: number, value: string) => setAmounts((prev) => ({ ...prev, [id]: value }));

  const handleConfirm = async () => {
    const entryFee = parseFloat(entryFeePercent) || 0;
    if (mode === "manual") {
      const amountsReceived: Record<number, number> = {};
      for (const inv of investments) {
        amountsReceived[inv.id] = Math.max(0, parseFloat(amounts[inv.id] ?? "") || 0);
      }
      await onConfirm("manual", amountsReceived, null, entryFee);
    } else {
      await onConfirm("aggregate", null, transactionCostUsd, entryFee);
    }
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

  const tabStyle = (active: boolean): React.CSSProperties => ({
    flex: 1,
    padding: "9px 12px",
    borderRadius: "8px",
    border: active ? "1px solid rgba(59,111,212,0.5)" : "1px solid rgba(255,255,255,0.08)",
    background: active ? "rgba(59,111,212,0.15)" : "transparent",
    color: active ? "#93B4F5" : "#94A3B8",
    fontSize: "12px",
    fontWeight: 600,
    cursor: isLoading ? "not-allowed" : "pointer",
    transition: "all 0.15s",
  });

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
          <div style={{ display: "flex", gap: "8px" }}>
            <button type="button" style={tabStyle(mode === "manual")} disabled={isLoading} onClick={() => setMode("manual")}>
              Manual — per client
            </button>
            <button type="button" style={tabStyle(mode === "aggregate")} disabled={isLoading} onClick={() => setMode("aggregate")}>
              Whole batch at once
            </button>
          </div>

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

          {mode === "manual" ? (
            <>
              <p style={{ margin: 0, fontSize: "13px", color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>
                Enter the amount each client's wire actually landed as — defaults to their full deposit.
              </p>

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
                  background: "rgba(255, 255, 255, 0.04)", border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "10px", padding: "12px", display: "flex", flexDirection: "column", gap: "6px",
                  fontSize: "12px", fontFamily: "var(--font-mono)",
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
                  <span>-${fmt(totalEntryFeeManual)}</span>
                </div>
                <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", marginTop: "4px", paddingTop: "8px", display: "flex", justifyContent: "space-between", color: "#86EFAC", fontWeight: 700 }}>
                  <span>Total Active Principal</span>
                  <span>${fmt(totalNetManual)}</span>
                </div>
              </div>
            </>
          ) : (
            <>
              <p style={{ margin: 0, fontSize: "13px", color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>
                Apply deductions in order: Transaction Cost (USD), then Entry Fee (%) — split pro-rata across
                every client's deposit share.
              </p>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94A3B8", marginBottom: "6px", fontWeight: 500 }}>
                  TOTAL TRANSACTION COST (USD)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  style={inputStyle}
                  value={transactionCost}
                  onChange={(e) => setTransactionCost(e.target.value)}
                  disabled={isLoading}
                  placeholder="0.00"
                />
              </div>

              <div
                style={{
                  background: "rgba(255, 255, 255, 0.04)", border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "10px", padding: "12px", display: "flex", flexDirection: "column", gap: "6px",
                  fontSize: "12px", fontFamily: "var(--font-mono)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", color: "#CBD5E1" }}>
                  <span>Initial Batch Total</span>
                  <span>${fmt(totalDeposited)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: "#FCA5A5" }}>
                  <span>Bank Transaction Fee</span>
                  <span>-${fmt(transactionCostUsd)}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", color: "#FBBF24" }}>
                  <span>Entry Fee ({(parseFloat(entryFeePercent) || 0).toFixed(2)}%)</span>
                  <span>-${fmt(entryFeeAggregate)}</span>
                </div>
                <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", marginTop: "4px", paddingTop: "8px", display: "flex", justifyContent: "space-between", color: "#86EFAC", fontWeight: 700 }}>
                  <span>Total Active Principal</span>
                  <span>${fmt(totalNetAggregate)}</span>
                </div>
              </div>
            </>
          )}
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
