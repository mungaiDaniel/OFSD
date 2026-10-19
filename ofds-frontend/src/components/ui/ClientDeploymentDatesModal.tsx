import { useEffect, useMemo, useState } from "react";
import type { BatchInvestorLight } from "@/lib/types";

interface ClientDeploymentDatesModalProps {
  open: boolean;
  onClose: () => void;
  investments: BatchInvestorLight[];
  /** Called with only the clients whose date was changed: {investment_id: "YYYY-MM-DD"}. */
  onSave: (dates: Record<number, string>) => Promise<void>;
  isSaving: boolean;
}

/** Super admin: correct each client's own deployment date in an already-deployed batch. */
export function ClientDeploymentDatesModal({ open, onClose, investments, onSave, isSaving }: ClientDeploymentDatesModalProps) {
  const [dates, setDates] = useState<Record<number, string>>({});
  const [applyAll, setApplyAll] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  useEffect(() => {
    if (!open) return;
    const initial: Record<number, string> = {};
    investments.forEach((i) => {
      initial[i.id] = (i.deployment_date ?? "").slice(0, 10);
    });
    setDates(initial);
    setApplyAll("");
  }, [open, investments]);

  const changed = useMemo(() => {
    const out: Record<number, string> = {};
    investments.forEach((i) => {
      const next = dates[i.id];
      if (next && next !== (i.deployment_date ?? "").slice(0, 10)) out[i.id] = next;
    });
    return out;
  }, [dates, investments]);

  const invalid = (i: BatchInvestorLight) => {
    const d = dates[i.id];
    if (!d) return "Required";
    if (d > today) return "In the future";
    if (i.date_deposited && d < i.date_deposited.slice(0, 10)) return "Before deposit date";
    return null;
  };
  const hasInvalid = investments.some((i) => invalid(i));
  const changedCount = Object.keys(changed).length;

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1050 }}
      onClick={() => !isSaving && onClose()}
    >
      <div
        style={{ background: "var(--color-surface, #fff)", color: "var(--color-text-primary, #111)", borderRadius: "10px", padding: "24px", width: "760px", maxWidth: "95vw", maxHeight: "88vh", display: "flex", flexDirection: "column" }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ fontSize: "16px", marginBottom: "4px" }}>Client deployment dates</h3>
        <p style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginBottom: "14px" }}>
          Set the date each client was actually deployed. Statements show these dates; shares, NAV and amounts do not change.
        </p>

        <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "12px" }}>
          <span style={{ fontSize: "12px" }}>Apply one date to all:</span>
          <input type="date" className="form-control form-control-sm" style={{ width: "160px" }} value={applyAll} max={today} onChange={(e) => setApplyAll(e.target.value)} />
          <button
            className="btn btn-sm btn-outline-secondary"
            disabled={!applyAll || isSaving}
            onClick={() => setDates(Object.fromEntries(investments.map((i) => [i.id, applyAll])))}
          >
            Apply
          </button>
        </div>

        <div style={{ overflowY: "auto", border: "1px solid var(--color-border, #ddd)", borderRadius: "6px" }}>
          <table className="table table-sm mb-0" style={{ fontSize: "12px" }}>
            <thead>
              <tr>
                <th>Client</th>
                <th>Code</th>
                <th>Deposited</th>
                <th>Deployment date</th>
              </tr>
            </thead>
            <tbody>
              {investments.map((i) => {
                const err = invalid(i);
                return (
                  <tr key={i.id}>
                    <td>{i.investor_name}</td>
                    <td>{i.internal_client_code}</td>
                    <td>{i.date_deposited ? i.date_deposited.slice(0, 10) : "—"}</td>
                    <td>
                      <input
                        type="date"
                        className="form-control form-control-sm"
                        style={{ width: "160px", borderColor: err ? "var(--color-destructive, #dc3545)" : undefined }}
                        value={dates[i.id] ?? ""}
                        max={today}
                        min={i.date_deposited ? i.date_deposited.slice(0, 10) : undefined}
                        onChange={(e) => setDates((prev) => ({ ...prev, [i.id]: e.target.value }))}
                      />
                      {err && <span style={{ marginLeft: "8px", color: "var(--color-destructive, #dc3545)" }}>{err}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "8px", marginTop: "16px" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginRight: "auto" }}>
            {changedCount} client{changedCount === 1 ? "" : "s"} changed
          </span>
          <button className="btn btn-sm btn-outline-secondary" disabled={isSaving} onClick={onClose}>
            Cancel
          </button>
          <button className="btn btn-sm btn-primary" disabled={isSaving || hasInvalid || changedCount === 0} onClick={() => onSave(changed)}>
            {isSaving ? "Saving..." : "Save dates"}
          </button>
        </div>
      </div>
    </div>
  );
}
