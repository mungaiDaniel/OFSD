import { useEffect, useState } from "react";
import { Loader2, Send, X } from "lucide-react";

// One confirmation dialog for every "send these emails" action on the Email page.
// It always names the exact emails (or the exact count) about to be approved, and for
// larger sends makes the admin type the number - so an approval can never be a blind
// click, and can never apply to anything that is not on this list.

export interface ConfirmItem {
  primary: string;
  secondary?: string;
  note?: string;
}

/** Sends go out `batchSize` at a time every `intervalMinutes` - say how long that takes. */
export function estimateSendTime(count: number, rate?: { batch_size: number; interval_minutes: number } | null): string {
  if (!rate || !rate.batch_size || !rate.interval_minutes || count <= 0) return "";
  const minutes = Math.ceil(count / rate.batch_size) * rate.interval_minutes;
  if (minutes < 60) return `about ${minutes} min`;
  const hours = minutes / 60;
  return hours < 48 ? `about ${hours.toFixed(1)} hours` : `about ${(hours / 24).toFixed(1)} days`;
}

/** Above this many emails the admin must type the number to confirm. */
export const TYPE_TO_CONFIRM_ABOVE = 25;

interface Props {
  open: boolean;
  title: string;
  description?: string;
  items: ConfirmItem[];
  count: number;
  rate?: { batch_size: number; interval_minutes: number } | null;
  requireTypedCount?: boolean;
  confirmLabel?: string;
  cancelLabel?: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function SendConfirmModal({
  open, title, description, items, count, rate, requireTypedCount, confirmLabel, cancelLabel, busy, onConfirm, onCancel,
}: Props) {
  const [typed, setTyped] = useState("");
  useEffect(() => { if (open) setTyped(""); }, [open]);
  if (!open) return null;

  const mustType = requireTypedCount ?? count > TYPE_TO_CONFIRM_ABOVE;
  const typedOk = !mustType || typed.trim() === String(count);
  const eta = estimateSendTime(count, rate);
  const shown = items.slice(0, 200);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      style={{ position: "fixed", inset: 0, zIndex: 10000, background: "rgba(0,0,0,0.65)", display: "flex", alignItems: "center", justifyContent: "center", padding: "16px" }}
      onClick={() => { if (!busy) onCancel(); }}
    >
      <div
        className="ofds-glass"
        style={{ width: "min(640px, 100%)", maxHeight: "86vh", display: "flex", flexDirection: "column", background: "#0B1228", border: "1px solid rgba(255,255,255,0.12)", borderRadius: "14px" }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ padding: "16px 20px", borderBottom: "1px solid rgba(255,255,255,0.08)", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "12px" }}>
          <div>
            <div style={{ fontSize: "15px", fontWeight: 700, color: "#fff" }}>{title}</div>
            {description && <div style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginTop: "4px" }}>{description}</div>}
          </div>
          <button onClick={onCancel} disabled={busy} aria-label="Close" style={{ background: "transparent", border: "none", color: "var(--color-text-secondary)", cursor: "pointer" }}>
            <X size={16} />
          </button>
        </div>

        {items.length > 0 && (
          <div style={{ overflowY: "auto", padding: "4px 20px", flex: 1, minHeight: 0 }}>
            {shown.map((it, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "7px 0", borderBottom: "1px solid rgba(255,255,255,0.05)", fontSize: "12px" }}>
                <span style={{ color: "#fff" }}>
                  {it.primary}
                  {it.secondary && <span style={{ color: "var(--color-text-tertiary)", marginLeft: "8px" }}>{it.secondary}</span>}
                </span>
                {it.note && <span style={{ color: "var(--color-text-tertiary)", whiteSpace: "nowrap" }}>{it.note}</span>}
              </div>
            ))}
            {items.length > shown.length && (
              <div style={{ padding: "8px 0", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                …and {(items.length - shown.length).toLocaleString()} more
              </div>
            )}
          </div>
        )}

        <div style={{ padding: "14px 20px", borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <div style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginBottom: "10px" }}>
            <strong style={{ color: "#fff" }}>{count.toLocaleString()}</strong> email{count === 1 ? "" : "s"} will be sent
            {eta ? <> — emails go out {rate?.batch_size} every {rate?.interval_minutes} min, so this takes {eta}.</> : "."} Nothing else is touched.
          </div>
          {mustType && (
            <div style={{ marginBottom: "10px" }}>
              <label style={{ display: "block", fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
                Type <strong style={{ color: "#fff" }}>{count}</strong> to confirm
              </label>
              <input
                autoFocus
                inputMode="numeric"
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                aria-label="Type the number of emails to confirm"
                style={{ background: "rgba(0,0,0,0.25)", border: "1px solid rgba(255,255,255,0.15)", borderRadius: "8px", color: "#fff", fontSize: "13px", padding: "8px 10px", width: "140px", outline: "none" }}
              />
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
            <button
              onClick={onCancel}
              disabled={busy}
              style={{ padding: "8px 14px", borderRadius: "8px", fontSize: "12px", fontWeight: 600, border: "1px solid rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.05)", color: "var(--color-text-secondary)", cursor: busy ? "not-allowed" : "pointer" }}
            >
              {cancelLabel ?? "Cancel"}
            </button>
            <button
              onClick={onConfirm}
              disabled={busy || !typedOk || count === 0}
              style={{ display: "inline-flex", alignItems: "center", gap: "6px", padding: "8px 14px", borderRadius: "8px", fontSize: "12px", fontWeight: 600, border: "none", background: "rgb(26, 69, 255)", color: "#fff", cursor: busy || !typedOk || count === 0 ? "not-allowed" : "pointer", opacity: busy || !typedOk || count === 0 ? 0.5 : 1 }}
            >
              {busy ? <Loader2 size={13} className="ss-spin" /> : <Send size={13} />}
              {confirmLabel ?? `Send ${count.toLocaleString()} now`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
