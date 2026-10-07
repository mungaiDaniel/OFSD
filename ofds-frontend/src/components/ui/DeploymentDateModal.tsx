import { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { Calendar, X, Check, Loader2, AlertTriangle } from "lucide-react";

interface DeploymentInvestment {
  id?: number;
  internal_client_code?: string;
  investor_name?: string;
  amount_deposited?: number | null;
  share_class_id?: number | null;
  class_code?: string | null;
  class_currency?: string | null;
  main_balance?: number | null;
}

export interface DeploymentClassBreakdown {
  share_class_id: number | null;
  class_code: string | null;
  navPerShare: number;
  totalShares: number;
  totalNav: number;
}

export interface DeploymentOversubscription {
  isOversubscribed: boolean;
  allocationRate: number; // percentage, e.g. 60 = 60%
}

export interface DeploymentConfirmPayload {
  dateString: string;
  classes: DeploymentClassBreakdown[];
  oversubscription?: DeploymentOversubscription;
}

interface DeploymentDateModalProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (payload: DeploymentConfirmPayload) => Promise<void>;
  isLoading?: boolean;
  investments: DeploymentInvestment[];
  /** Only DPRP batches (a direct share purchase, not a pooled NAV fund) can be
   * oversubscribed — the toggle below is hidden entirely otherwise. */
  isDprpFund?: boolean;
}

interface ClassGroup {
  key: string;
  share_class_id: number | null;
  class_code: string | null;
  class_currency: string | null;
  netDeployedAmount: number;
}

function groupByClass(investments: DeploymentInvestment[]): ClassGroup[] {
  const groups = new Map<string, ClassGroup>();
  for (const inv of investments) {
    const key = inv.share_class_id != null ? String(inv.share_class_id) : `code-${inv.class_code ?? "unknown"}`;
    const existing = groups.get(key);
    const amount = inv.main_balance ?? 0;
    if (existing) {
      existing.netDeployedAmount += amount;
    } else {
      groups.set(key, {
        key,
        share_class_id: inv.share_class_id ?? null,
        class_code: inv.class_code ?? null,
        class_currency: inv.class_currency ?? null,
        netDeployedAmount: amount,
      });
    }
  }
  return [...groups.values()];
}

const PREVIEW_ROW_LIMIT = 50;

export function DeploymentDateModal({ open, onClose, onConfirm, isLoading = false, investments, isDprpFund = false }: DeploymentDateModalProps) {
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [navByClass, setNavByClass] = useState<Record<string, string>>({});

  // ── DPRP oversubscription pro-rata allocation ──
  const [isOversubscribed, setIsOversubscribed] = useState(false);
  const [rateMode, setRateMode] = useState<"rate" | "amount">("rate");
  const [rateInput, setRateInput] = useState("");
  const [amountInput, setAmountInput] = useState("");

  const classGroups = useMemo(() => groupByClass(investments), [investments]);

  const totalPreAllocationNet = useMemo(
    () => classGroups.reduce((sum, g) => sum + g.netDeployedAmount, 0),
    [classGroups]
  );

  const allocationRate = useMemo(() => {
    if (!isOversubscribed) return 100;
    if (rateMode === "rate") return Number(rateInput) || 0;
    const amt = Number(amountInput) || 0;
    return totalPreAllocationNet > 0 ? (amt / totalPreAllocationNet) * 100 : 0;
  }, [isOversubscribed, rateMode, rateInput, amountInput, totalPreAllocationNet]);

  const allocationRateValid = !isOversubscribed || (allocationRate > 0 && allocationRate <= 100);
  const allocationFraction = isOversubscribed && allocationRateValid ? allocationRate / 100 : 1;

  if (!open) return null;

  const validCount = classGroups.filter((g) => Number(navByClass[g.key]) > 0).length;
  const allValid = classGroups.length > 0 && validCount === classGroups.length && allocationRateValid;

  const sumTotalShares = classGroups.reduce((sum, g) => {
    const nav = Number(navByClass[g.key]);
    const deployedAmount = g.netDeployedAmount * allocationFraction;
    return sum + (nav > 0 ? deployedAmount / nav : 0);
  }, 0);
  const sumTotalNav = classGroups.reduce((sum, g) => {
    const nav = Number(navByClass[g.key]);
    return sum + (nav > 0 ? g.netDeployedAmount * allocationFraction : 0);
  }, 0);

  const totalDeployedPreview = totalPreAllocationNet * allocationFraction;
  const totalRefundPreview = totalPreAllocationNet - totalDeployedPreview;

  const handleConfirm = async () => {
    if (!selectedDate || !allValid) return;
    const classes: DeploymentClassBreakdown[] = classGroups.map((g) => {
      const nav = Number(navByClass[g.key]);
      const deployedAmount = g.netDeployedAmount * allocationFraction;
      const totalShares = nav > 0 ? Number((deployedAmount / nav).toFixed(4)) : 0;
      return {
        share_class_id: g.share_class_id,
        class_code: g.class_code,
        navPerShare: nav,
        totalShares,
        totalNav: Number(deployedAmount.toFixed(2)),
      };
    });
    await onConfirm({
      dateString: new Date(selectedDate).toISOString(),
      classes,
      oversubscription: isOversubscribed ? { isOversubscribed: true, allocationRate: Number(allocationRate.toFixed(4)) } : undefined,
    });
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
    maxWidth: "680px",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    boxShadow: "0 24px 48px rgba(0, 0, 0, 0.4)",
    overflow: "hidden auto",
    display: "flex",
    flexDirection: "column",
    color: "#fff",
    fontFamily: "var(--font-sans)",
    maxHeight: "90vh",
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
    gap: "20px"
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

  const readonlyInputStyle: React.CSSProperties = {
    ...inputStyle,
    background: "rgba(255, 255, 255, 0.08)",
  };

  const labelStyle: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", fontWeight: 500 };
  const classCardStyle: React.CSSProperties = {
    padding: "18px",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "14px",
    background: "rgba(255,255,255,0.02)",
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
              <Calendar size={16} />
            </div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Deploy Batch to Active</h3>
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
            Configure deployment details. This marks the batch as Active and stores NAV totals for each share class.
          </p>

          {/* Deployment Date */}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ display: "block", ...labelStyle }}>
              DEPLOYMENT DATE <span style={{ color: "#EF4444" }}>*</span>
            </label>
            <input
              type="date"
              style={inputStyle}
              value={selectedDate}
              onChange={(e) => setSelectedDate(e.target.value)}
              disabled={isLoading}
            />
            <p style={{ margin: 0, fontSize: "12px", color: "rgba(255,255,255,0.5)" }}>
              Official date when funds are deployed and active
            </p>
          </div>

          {/* DPRP oversubscription pro-rata allocation */}
          {isDprpFund && (
            <div style={classCardStyle}>
              <label style={{ display: "flex", alignItems: "center", gap: "10px", cursor: isLoading ? "not-allowed" : "pointer" }}>
                <input
                  type="checkbox"
                  checked={isOversubscribed}
                  onChange={(e) => setIsOversubscribed(e.target.checked)}
                  disabled={isLoading}
                  style={{ width: "16px", height: "16px", accentColor: "#D4940B" }}
                />
                <span style={{ fontSize: "14px", fontWeight: 600, color: "#fff" }}>
                  Oversubscribed — apply pro-rata allocation
                </span>
              </label>
              <p style={{ margin: "6px 0 0 26px", fontSize: "12px", color: "rgba(255,255,255,0.5)" }}>
                Total deposits exceeded what can actually be deployed into DPRP shares. Every
                investor gets the same allocation rate applied to their own deposit; the
                remainder is queued as a pending refund.
              </p>

              {isOversubscribed && (
                <div style={{ marginTop: "16px" }}>
                  <div style={{ display: "flex", gap: "10px", marginBottom: "12px" }}>
                    <button
                      type="button"
                      onClick={() => setRateMode("rate")}
                      disabled={isLoading}
                      style={{
                        flex: 1, padding: "8px", borderRadius: "8px", fontSize: "12px", fontWeight: 600, cursor: "pointer",
                        border: rateMode === "rate" ? "1px solid #D4940B" : "1px solid rgba(255,255,255,0.1)",
                        background: rateMode === "rate" ? "rgba(212,148,11,0.12)" : "transparent",
                        color: rateMode === "rate" ? "#D4940B" : "rgba(255,255,255,0.7)",
                      }}
                    >
                      Enter allocation rate
                    </button>
                    <button
                      type="button"
                      onClick={() => setRateMode("amount")}
                      disabled={isLoading}
                      style={{
                        flex: 1, padding: "8px", borderRadius: "8px", fontSize: "12px", fontWeight: 600, cursor: "pointer",
                        border: rateMode === "amount" ? "1px solid #D4940B" : "1px solid rgba(255,255,255,0.1)",
                        background: rateMode === "amount" ? "rgba(212,148,11,0.12)" : "transparent",
                        color: rateMode === "amount" ? "#D4940B" : "rgba(255,255,255,0.7)",
                      }}
                    >
                      Enter amount deployed
                    </button>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      <label style={labelStyle}>
                        {rateMode === "rate" ? "ALLOCATION RATE (%)" : "TOTAL AMOUNT DEPLOYED"}
                        <span style={{ color: "#EF4444" }}> *</span>
                      </label>
                      {rateMode === "rate" ? (
                        <input
                          type="number"
                          step="0.01"
                          placeholder="e.g., 60"
                          style={inputStyle}
                          value={rateInput}
                          onChange={(e) => setRateInput(e.target.value)}
                          disabled={isLoading}
                        />
                      ) : (
                        <input
                          type="number"
                          step="0.01"
                          placeholder="e.g., 600000"
                          style={inputStyle}
                          value={amountInput}
                          onChange={(e) => setAmountInput(e.target.value)}
                          disabled={isLoading}
                        />
                      )}
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      <label style={labelStyle}>DERIVED ALLOCATION RATE</label>
                      <input
                        readOnly
                        disabled
                        type="text"
                        style={readonlyInputStyle}
                        value={`${allocationRate.toLocaleString("en-US", { maximumFractionDigits: 4 })}%`}
                      />
                    </div>
                  </div>

                  {!allocationRateValid && (
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", marginTop: "10px", padding: "8px 10px", borderRadius: "8px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)" }}>
                      <AlertTriangle size={14} style={{ color: "#EF4444", flexShrink: 0 }} />
                      <span style={{ fontSize: "12px", color: "#EF4444" }}>
                        Allocation rate must be greater than 0% and no more than 100%.
                      </span>
                    </div>
                  )}

                  {allocationRateValid && totalPreAllocationNet > 0 && (
                    <>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px", marginTop: "14px" }}>
                        <div>
                          <span style={{ fontSize: "11px", color: "#94A3B8" }}>TOTAL NET DEPOSITS</span>
                          <div style={{ fontSize: "14px", fontWeight: 700, color: "#fff" }}>
                            {totalPreAllocationNet.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                        </div>
                        <div>
                          <span style={{ fontSize: "11px", color: "#94A3B8" }}>TOTAL TO DEPLOY</span>
                          <div style={{ fontSize: "14px", fontWeight: 700, color: "#22c55e" }}>
                            {totalDeployedPreview.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                        </div>
                        <div>
                          <span style={{ fontSize: "11px", color: "#94A3B8" }}>TOTAL TO REFUND</span>
                          <div style={{ fontSize: "14px", fontWeight: 700, color: "#D4940B" }}>
                            {totalRefundPreview.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </div>
                        </div>
                      </div>

                      {/* Live per-investor preview */}
                      <div style={{ marginTop: "14px", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", overflow: "hidden" }}>
                        <div style={{ maxHeight: "220px", overflowY: "auto" }}>
                          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                            <thead style={{ position: "sticky", top: 0, background: "#111a33" }}>
                              <tr>
                                {["Investor", "Client Code", "Deposit", "To Deploy", "To Refund"].map((h) => (
                                  <th key={h} style={{ padding: "8px 10px", textAlign: h === "Investor" || h === "Client Code" ? "left" : "right", color: "#94A3B8", fontWeight: 600, whiteSpace: "nowrap" }}>
                                    {h}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {investments.slice(0, PREVIEW_ROW_LIMIT).map((inv, i) => {
                                const netPrincipal = inv.main_balance ?? 0;
                                const deployed = netPrincipal * allocationFraction;
                                const refund = netPrincipal - deployed;
                                return (
                                  <tr key={inv.id ?? i} style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                                    <td style={{ padding: "6px 10px", color: "#fff" }}>{inv.investor_name ?? "—"}</td>
                                    <td style={{ padding: "6px 10px", color: "rgba(255,255,255,0.6)", fontFamily: "var(--font-mono)" }}>{inv.internal_client_code ?? "—"}</td>
                                    <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.7)" }}>
                                      {(inv.amount_deposited ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </td>
                                    <td style={{ padding: "6px 10px", textAlign: "right", color: "#22c55e" }}>
                                      {deployed.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </td>
                                    <td style={{ padding: "6px 10px", textAlign: "right", color: "#D4940B" }}>
                                      {refund.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        {investments.length > PREVIEW_ROW_LIMIT && (
                          <div style={{ padding: "8px 10px", fontSize: "11px", color: "rgba(255,255,255,0.5)", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                            + {investments.length - PREVIEW_ROW_LIMIT} more investor{investments.length - PREVIEW_ROW_LIMIT === 1 ? "" : "s"} (same {allocationRate.toLocaleString("en-US", { maximumFractionDigits: 2 })}% rate applied to each)
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Per-class NAV entry */}
          {classGroups.map((g) => {
            const nav = Number(navByClass[g.key]) || 0;
            const deployedAmount = g.netDeployedAmount * allocationFraction;
            const totalShares = nav > 0 ? deployedAmount / nav : 0;
            return (
              <div key={g.key} style={classCardStyle}>
                <div style={{ fontSize: "14px", fontWeight: 600, color: "#fff", marginBottom: "4px" }}>
                  {g.class_code ?? "Unassigned"} {g.class_currency ? `(${g.class_currency})` : ""}
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    <label style={labelStyle}>NAV PER SHARE <span style={{ color: "#EF4444" }}>*</span></label>
                    <input
                      type="number"
                      step="0.0001"
                      placeholder="e.g., 1389.5737"
                      style={inputStyle}
                      value={navByClass[g.key] ?? ""}
                      onChange={(e) => setNavByClass((prev) => ({ ...prev, [g.key]: e.target.value }))}
                      disabled={isLoading}
                    />
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    <label style={labelStyle}>NET DEPLOYED AMOUNT{isOversubscribed ? " (ALLOCATED)" : ""}</label>
                    <input
                      readOnly
                      disabled
                      type="text"
                      style={readonlyInputStyle}
                      value={deployedAmount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    />
                  </div>
                </div>
                <div style={{ marginTop: "12px" }}>
                  <label style={labelStyle}>TOTAL SHARES (CALCULATED)</label>
                  <input
                    readOnly
                    disabled
                    type="text"
                    style={readonlyInputStyle}
                    value={totalShares.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                  />
                </div>
              </div>
            );
          })}

          {/* Summary */}
          {classGroups.length > 0 && (
            <div style={classCardStyle}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", ...labelStyle }}>
                <span>Total across all classes</span>
                <span>{validCount}/{classGroups.length} valid</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "11px", color: "#94A3B8" }}>SUM TOTAL SHARES</span>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff" }}>
                    {sumTotalShares.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
                  <span style={{ fontSize: "11px", color: "#94A3B8" }}>SUM TOTAL NAV</span>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff" }}>
                    {sumTotalNav.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                </div>
              </div>
            </div>
          )}
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
            disabled={isLoading || !selectedDate || !allValid}
            style={{
              background: "#3B6FD4",
              border: "none",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: 500,
              cursor: (isLoading || !selectedDate || !allValid) ? "not-allowed" : "pointer",
              opacity: (!selectedDate || !allValid || isLoading) ? 0.6 : 1,
              display: "flex",
              alignItems: "center",
              gap: "6px",
              transition: "all 0.2s"
            }}
            onMouseOver={e => !isLoading && selectedDate && allValid && (e.currentTarget.style.background = "#2D5BB8")}
            onMouseOut={e => e.currentTarget.style.background = "#3B6FD4"}
          >
            {isLoading ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
            Deploy &amp; Activate
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
