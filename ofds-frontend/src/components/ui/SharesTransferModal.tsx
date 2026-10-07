import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Coins, X, Check, Loader2 } from "lucide-react";
import { batchService } from "@/services/batchService";
import type { SharesTransferPreview } from "@/lib/types";

interface SharesTransferModalProps {
  open: boolean;
  onClose: () => void;
  batchId: number;
  onConfirm: (entryFeePercent: number, totalTransactionCostUsd: number) => Promise<void>;
  isLoading?: boolean;
}

const PREVIEW_ROW_LIMIT = 50;

/**
 * SHARES-only Transferred-stage fee form (Task 2): entry fee first, then the
 * transaction cost proportional to the balance AFTER that entry fee — the
 * opposite order from the FUNDS TransferCostModal, which this deliberately
 * does not touch or reuse logic from. Live preview comes straight from the
 * backend (SharesTransferService.preview) so the UI never re-implements the
 * rounding/residual rules itself.
 */
export function SharesTransferModal({ open, onClose, batchId, onConfirm, isLoading = false }: SharesTransferModalProps) {
  const [entryFeePercent, setEntryFeePercent] = useState<string>("0");
  const [transactionCost, setTransactionCost] = useState<string>("0");
  const [preview, setPreview] = useState<SharesTransferPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      setPreviewLoading(true);
      setPreviewError(null);
      batchService
        .previewSharesTransfer(batchId, entryFeePercent || "0", transactionCost || "0")
        .then(setPreview)
        .catch((err) => {
          setPreview(null);
          setPreviewError(err?.response?.data?.message || "Could not compute a preview for these inputs");
        })
        .finally(() => setPreviewLoading(false));
    }, 300);
    return () => clearTimeout(t);
  }, [open, batchId, entryFeePercent, transactionCost]);

  if (!open) return null;

  const canConfirm = !!preview && !previewLoading && !previewError;

  const handleConfirm = async () => {
    if (!canConfirm) return;
    await onConfirm(parseFloat(entryFeePercent) || 0, parseFloat(transactionCost) || 0);
  };

  const overlayStyle: React.CSSProperties = {
    position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
    background: "rgba(0, 0, 0, 0.4)", backdropFilter: "blur(4px)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 9999, padding: "20px",
  };
  const modalStyle: React.CSSProperties = {
    background: "#0B1228", borderRadius: "16px", width: "100%", maxWidth: "680px",
    border: "1px solid rgba(255, 255, 255, 0.08)", boxShadow: "0 24px 48px rgba(0, 0, 0, 0.4)",
    overflow: "hidden auto", display: "flex", flexDirection: "column",
    color: "#fff", fontFamily: "var(--font-sans)", maxHeight: "90vh",
  };
  const headerStyle: React.CSSProperties = {
    padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.06)",
    display: "flex", alignItems: "center", justifyContent: "space-between",
  };
  const contentStyle: React.CSSProperties = { padding: "24px", display: "flex", flexDirection: "column", gap: "16px" };
  const inputStyle: React.CSSProperties = {
    width: "100%", background: "rgba(255, 255, 255, 0.05)", border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: "8px", color: "#fff", padding: "12px 16px", fontSize: "14px", outline: "none",
    fontFamily: "var(--font-mono)", colorScheme: "dark",
  };
  const labelStyle: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", fontWeight: 500, display: "block", marginBottom: "6px" };

  return createPortal(
    <div style={overlayStyle} onClick={onClose} className="scale-in">
      <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div className="d-flex align-items-center gap-2">
            <div style={{ width: "32px", height: "32px", background: "rgba(212, 148, 11, 0.15)", color: "#D4940B", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Coins size={16} />
            </div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Transfer Shares Batch</h3>
          </div>
          <button onClick={onClose} disabled={isLoading} style={{ background: "transparent", border: "none", color: "#94A3B8", cursor: isLoading ? "not-allowed" : "pointer", padding: "4px" }}>
            <X size={18} />
          </button>
        </div>

        <div style={contentStyle}>
          <p style={{ margin: 0, fontSize: "14px", color: "rgba(255,255,255,0.7)", lineHeight: 1.5 }}>
            Entry fee is taken from the raw deposit first; the transaction cost is then split proportionally across what's left — the opposite order from a Funds batch.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={labelStyle}>ENTRY FEE PERCENTAGE (%)</label>
              <input type="number" step="0.01" min="0" max="100" style={inputStyle} value={entryFeePercent} onChange={(e) => setEntryFeePercent(e.target.value)} disabled={isLoading} placeholder="2.00" />
            </div>
            <div>
              <label style={labelStyle}>TOTAL TRANSACTION COST (USD)</label>
              <input type="number" step="0.01" min="0" style={inputStyle} value={transactionCost} onChange={(e) => setTransactionCost(e.target.value)} disabled={isLoading} placeholder="0.00" />
            </div>
          </div>

          {previewError && (
            <div style={{ padding: "10px 12px", borderRadius: "8px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", fontSize: "12px", color: "#EF4444" }}>
              {previewError}
            </div>
          )}

          {preview && !previewError && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
                {[
                  { label: "TOTAL ENTRY FEE", value: preview.totals.entry_fee_usd, color: "#FBBF24" },
                  { label: "TOTAL TRANSACTION COST", value: preview.totals.transaction_cost_usd, color: "#FCA5A5" },
                  { label: "TOTAL NET USD", value: preview.totals.net_usd, color: "#86EFAC" },
                ].map((s) => (
                  <div key={s.label}>
                    <span style={{ fontSize: "10px", color: "#94A3B8" }}>{s.label}</span>
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: "14px", fontWeight: 700, color: s.color }}>
                      {s.value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                  </div>
                ))}
              </div>

              <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", overflow: "hidden" }}>
                <div style={{ maxHeight: "220px", overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                    <thead style={{ position: "sticky", top: 0, background: "#111a33" }}>
                      <tr>
                        {["Client Code", "Deposit", "Entry Fee", "Balance", "Tx Cost", "Net USD"].map((h) => (
                          <th key={h} style={{ padding: "8px 10px", textAlign: h === "Client Code" ? "left" : "right", color: "#94A3B8", fontWeight: 600, whiteSpace: "nowrap" }}>
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.slice(0, PREVIEW_ROW_LIMIT).map((r) => (
                        <tr key={r.investment_id} style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                          <td style={{ padding: "6px 10px", color: "rgba(255,255,255,0.7)", fontFamily: "var(--font-mono)" }}>{r.internal_client_code}</td>
                          <td style={{ padding: "6px 10px", textAlign: "right", color: "#fff" }}>{r.deposit_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                          <td style={{ padding: "6px 10px", textAlign: "right", color: "#FBBF24" }}>{r.entry_fee_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                          <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.7)" }}>{r.balance_after_entry.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                          <td style={{ padding: "6px 10px", textAlign: "right", color: "#FCA5A5" }}>{r.transaction_cost_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                          <td style={{ padding: "6px 10px", textAlign: "right", color: "#86EFAC", fontWeight: 600 }}>{r.net_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {preview.rows.length > PREVIEW_ROW_LIMIT && (
                  <div style={{ padding: "8px 10px", fontSize: "11px", color: "rgba(255,255,255,0.5)", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                    + {preview.rows.length - PREVIEW_ROW_LIMIT} more deposit{preview.rows.length - PREVIEW_ROW_LIMIT === 1 ? "" : "s"}
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <div style={{ padding: "16px 24px", background: "rgba(0,0,0,0.2)", borderTop: "1px solid rgba(255,255,255,0.06)", display: "flex", justifyContent: "flex-end", gap: "12px" }}>
          <button onClick={onClose} disabled={isLoading} style={{ background: "transparent", border: "1px solid rgba(255, 255, 255, 0.1)", color: "#fff", padding: "8px 16px", borderRadius: "6px", fontSize: "13px", fontWeight: 500, cursor: isLoading ? "not-allowed" : "pointer" }}>
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={isLoading || !canConfirm}
            style={{
              background: "#D4940B", border: "none", color: "#fff", padding: "8px 16px", borderRadius: "6px",
              fontSize: "13px", fontWeight: 500, cursor: (isLoading || !canConfirm) ? "not-allowed" : "pointer",
              opacity: (isLoading || !canConfirm) ? 0.6 : 1, display: "flex", alignItems: "center", gap: "6px",
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
