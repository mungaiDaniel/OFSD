import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X } from "lucide-react";

interface CurrencyOverrideDialogProps {
  open: boolean;
  className: string;
  reasons: string[];
  onConfirm: () => void;
  onClose: () => void;
}

/**
 * Task 12: explicit confirmation before a super_admin unlocks a share class
 * currency that already has deposits/batches/valuations. Styled like the
 * other OFDS modals (TransferCostModal). The server still requires
 * `confirm_currency_override: true` and audit-logs the override.
 */
export function CurrencyOverrideDialog({ open, className, reasons, onConfirm, onClose }: CurrencyOverrideDialogProps) {
  const [acknowledged, setAcknowledged] = useState(false);

  useEffect(() => {
    if (open) setAcknowledged(false);
  }, [open]);

  if (!open) return null;

  return createPortal(
    <div
      role="presentation"
      onClick={onClose}
      className="scale-in"
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.4)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: "20px",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="currency-override-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0B1228",
          borderRadius: "16px",
          width: "100%",
          maxWidth: "460px",
          border: "1px solid rgba(255,255,255,0.08)",
          boxShadow: "0 24px 48px rgba(0,0,0,0.4)",
          color: "#fff",
          fontFamily: "var(--font-sans)",
        }}
      >
        <div
          style={{
            padding: "20px 24px",
            borderBottom: "1px solid rgba(255,255,255,0.06)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div className="d-flex align-items-center gap-2">
            <div
              style={{
                width: "32px",
                height: "32px",
                background: "rgba(245,158,11,0.15)",
                color: "#fbbf24",
                borderRadius: "8px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <AlertTriangle size={16} />
            </div>
            <h3 id="currency-override-title" style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
              Override locked currency?
            </h3>
          </div>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            style={{ background: "transparent", border: "none", color: "#94A3B8", cursor: "pointer", padding: "4px" }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: "24px", display: "flex", flexDirection: "column", gap: "14px" }}>
          <p style={{ margin: 0, fontSize: "14px", color: "rgba(255,255,255,0.75)", lineHeight: 1.5 }}>
            <strong>{className}</strong> already has {reasons.length ? reasons.join(", ") : "financial records"}.
          </p>
          <div
            style={{
              background: "rgba(245,158,11,0.08)",
              border: "1px solid rgba(245,158,11,0.3)",
              borderRadius: "10px",
              padding: "12px 14px",
              fontSize: "13px",
              color: "#fcd34d",
              lineHeight: 1.5,
            }}
          >
            Existing figures will <strong>not</strong> be converted. Deposits, NAVs and valuations keep their
            current numbers and will simply be labelled with the new currency. This override is recorded in the
            audit log under your name.
          </div>
          <label style={{ display: "flex", gap: "10px", alignItems: "flex-start", fontSize: "13px", color: "#cbd5e1" }}>
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              style={{ marginTop: "3px" }}
            />
            I understand existing figures will not be converted.
          </label>
        </div>

        <div
          style={{
            padding: "16px 24px",
            borderTop: "1px solid rgba(255,255,255,0.06)",
            display: "flex",
            justifyContent: "flex-end",
            gap: "12px",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: "10px 20px",
              borderRadius: "8px",
              border: "1px solid rgba(255,255,255,0.15)",
              background: "transparent",
              color: "var(--color-text-secondary)",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={!acknowledged}
            style={{
              padding: "10px 20px",
              borderRadius: "8px",
              border: "1px solid rgba(245,158,11,0.5)",
              background: "rgba(245,158,11,0.15)",
              color: "#fbbf24",
              fontSize: "13px",
              fontWeight: 600,
              cursor: acknowledged ? "pointer" : "not-allowed",
              opacity: acknowledged ? 1 : 0.5,
            }}
          >
            Unlock currency
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}

export default CurrencyOverrideDialog;
