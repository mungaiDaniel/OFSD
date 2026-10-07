import { useState } from "react";
import { createPortal } from "react-dom";
import { DollarSign, X, Check, Loader2 } from "lucide-react";

interface TransferCostModalProps {
  open: boolean;
  onClose: () => void;
  totalBatchDeposit: number;
  onConfirm: (transactionCostUsd: number, entryFeePercent: number) => Promise<void>;
  isLoading?: boolean;
}

export function TransferCostModal({
  open,
  onClose,
  totalBatchDeposit,
  onConfirm,
  isLoading = false,
}: TransferCostModalProps) {
  const [transactionCost, setTransactionCost] = useState<string>("0");
  const [entryFeePercent, setEntryFeePercent] = useState<string>("0");

  if (!open) return null;

  const transactionCostUsd = parseFloat(transactionCost) || 0;
  const entryFeeRate = (parseFloat(entryFeePercent) || 0) / 100;
  const netAfterTransactionCost = Math.max(0, totalBatchDeposit - transactionCostUsd);
  const entryFeeUsd = Math.max(0, netAfterTransactionCost * entryFeeRate);
  const finalDeployedPrincipal = Math.max(0, netAfterTransactionCost - entryFeeUsd);

  const handleConfirm = async () => {
    await onConfirm(transactionCostUsd, parseFloat(entryFeePercent) || 0);
  };

  const overlayStyle: React.CSSProperties = {
    position: "fixed",
    top: 0, left: 0, right: 0, bottom: 0,
    background: "rgba(0, 0, 0, 0.4)",
    backdropFilter: "blur(4px)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 9999,
    padding: "20px"
  };

  const modalStyle: React.CSSProperties = {
    background: "#0B1228",
    borderRadius: "16px",
    width: "100%",
    maxWidth: "450px",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    boxShadow: "0 24px 48px rgba(0, 0, 0, 0.4)",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    color: "#fff",
    fontFamily: "var(--font-sans)"
  };

  const headerStyle: React.CSSProperties = {
    padding: "20px 24px",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between"
  };

  const contentStyle: React.CSSProperties = {
    padding: "24px",
    display: "flex",
    flexDirection: "column",
    gap: "16px"
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    background: "rgba(255, 255, 255, 0.05)",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: "8px",
    color: "#fff",
    padding: "12px 16px",
    fontSize: "14px",
    outline: "none",
    fontFamily: "var(--font-mono)",
    colorScheme: "dark"
  };

  return createPortal(
    <div style={overlayStyle} onClick={onClose} className="scale-in">
      <div style={modalStyle} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={headerStyle}>
          <div className="d-flex align-items-center gap-2">
            <div
              style={{
                width: "32px", height: "32px",
                background: "rgba(59, 111, 212, 0.15)",
                color: "#3B6FD4",
                borderRadius: "8px",
                display: "flex", alignItems: "center", justifyContent: "center"
              }}
            >
              <DollarSign size={16} />
            </div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Advance to Transfer</h3>
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            style={{
              background: "transparent",
              border: "none",
              color: "#94A3B8",
              cursor: isLoading ? "not-allowed" : "pointer",
              padding: "4px"
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={contentStyle}>
          <p style={{ margin: 0, fontSize: "14px", color: "rgba(255,255,255,0.7)", lineHeight: 1.5 }}>
            Apply deductions in order: Transaction Cost (USD), then Entry Fee (%). Preview updates in real-time before confirmation.
          </p>

          <div style={{ marginTop: "8px" }}>
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

          <div
            style={{
              marginTop: "4px",
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
              <span>${totalBatchDeposit.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#FCA5A5" }}>
              <span>Bank Transaction Fee</span>
              <span>-${transactionCostUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#FBBF24" }}>
              <span>Entry Fee ({(parseFloat(entryFeePercent) || 0).toFixed(2)}%)</span>
              <span>-${entryFeeUsd.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.08)", marginTop: "4px", paddingTop: "8px", display: "flex", justifyContent: "space-between", color: "#86EFAC", fontWeight: 700 }}>
              <span>Total Active Principal</span>
              <span>${finalDeployedPrincipal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          padding: "16px 24px",
          background: "rgba(0,0,0,0.2)",
          borderTop: "1px solid rgba(255,255,255,0.06)",
          display: "flex",
          justifyContent: "flex-end",
          gap: "12px"
        }}>
          <button
            onClick={onClose}
            disabled={isLoading}
            style={{
              background: "transparent",
              border: "1px solid rgba(255, 255, 255, 0.1)",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: 500,
              cursor: isLoading ? "not-allowed" : "pointer",
              transition: "all 0.2s"
            }}
            onMouseOver={e => e.currentTarget.style.background = "rgba(255, 255, 255, 0.05)"}
            onMouseOut={e => e.currentTarget.style.background = "transparent"}
          >
            Cancel
          </button>

          <button
            onClick={handleConfirm}
            disabled={isLoading}
            style={{
              background: "#3B6FD4",
              border: "none",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: 500,
              cursor: isLoading ? "not-allowed" : "pointer",
              opacity: isLoading ? 0.6 : 1,
              display: "flex",
              alignItems: "center",
              gap: "6px",
              transition: "all 0.2s"
            }}
            onMouseOver={e => !isLoading && (e.currentTarget.style.background = "#2D5BB8")}
            onMouseOut={e => e.currentTarget.style.background = "#3B6FD4"}
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