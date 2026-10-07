import { Fragment, useState, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { X, Mail, CheckCircle, XCircle, Loader2, AlertTriangle, Send } from "lucide-react";
import { emailService, type PendingEmail } from "@/services/emailService";
import { toast } from "sonner";

// ─── Email type → human-readable label + badge colour ───────────────────────
const EMAIL_TYPE_META: Record<string, { label: string; color: string; bg: string }> = {
  DEPOSIT_CONFIRMATION:  { label: "Deposit Receipt",      color: "#3DBB78", bg: "rgba(61,187,120,0.12)" },
  OFFSHORE_TRANSFER:     { label: "Offshore Transfer",    color: "#3B6FD4", bg: "rgba(59,111,212,0.12)" },
  INVESTMENT_ACTIVE:     { label: "Account Activation",  color: "#D4940B", bg: "rgba(212,148,11,0.12)"  },
  WITHDRAWAL_RECEIVED:   { label: "Withdrawal Received", color: "#9B6FE3", bg: "rgba(155,111,227,0.12)" },
  WITHDRAWAL_APPROVED:   { label: "Withdrawal Approved", color: "#D44B4B", bg: "rgba(212,75,75,0.12)"   },
};

function EmailTypeBadge({ type }: { type: string }) {
  const meta = EMAIL_TYPE_META[type] ?? { label: type, color: "#94A3B8", bg: "rgba(148,163,184,0.12)" };
  return (
    <span
      style={{
        fontSize: "10px",
        fontWeight: 700,
        padding: "2px 8px",
        borderRadius: "999px",
        color: meta.color,
        background: meta.bg,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        whiteSpace: "nowrap",
      }}
    >
      {meta.label}
    </span>
  );
}

// ─── Props ───────────────────────────────────────────────────────────────────
interface EmailConfirmationModalProps {
  /** When true the modal mounts and fetches pending emails */
  open: boolean;
  /** Called when the modal should close (all handled or user dismissed) */
  onClose: () => void;
  /** Optional: restrict display/actions to a specific batch */
  batchId?: number | null;
}

// ─── Component ───────────────────────────────────────────────────────────────
export function EmailConfirmationModal({ open, onClose, batchId }: EmailConfirmationModalProps) {
  const [emails, setEmails] = useState<PendingEmail[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionInProgress, setActionInProgress] = useState<Set<number>>(new Set());
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [sentIds, setSentIds] = useState<Set<number>>(new Set());
  const [suppressedIds, setSuppressedIds] = useState<Set<number>>(new Set());

  const formatUsd = (value: number) =>
    value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const sanitizeTransferBody = (emailType: string, body: string, email: PendingEmail) => {
    if (emailType !== "OFFSHORE_TRANSFER") return body;

    const hasDbBackedDeductions =
      email.initial_deposit_usd != null ||
      email.transaction_fee_usd != null ||
      email.entry_fee_usd != null ||
      email.main_balance != null;

    // If we do not have persisted values, keep the original body as-is.
    // This avoids introducing incorrect defaults in the preview.
    if (!hasDbBackedDeductions) return body;

    const initialDeposit = email.initial_deposit_usd ?? email.amount ?? 0;
    const transactionFee = email.transaction_fee_usd ?? 0;
    const entryFeeUsd = email.entry_fee_usd ?? 0;
    const netAfterTransaction = Math.max(0, initialDeposit - transactionFee);
    const entryFeePercent =
      email.entry_fee_percent ??
      (netAfterTransaction > 0 ? (entryFeeUsd / netAfterTransaction) * 100 : 0);
    const finalBalance = email.main_balance ?? Math.max(0, netAfterTransaction - entryFeeUsd);

    return [
      "Transaction Status: Successfully Transferred to Fund",
      "",
      `Initial Deposit: $${formatUsd(initialDeposit)}`,
      `Bank Transaction Fee: -$${formatUsd(transactionFee)}`,
      `Fund Entry Fee (${entryFeePercent.toFixed(2)}%): -$${formatUsd(entryFeeUsd)}`,
      `Total Active Principal: $${formatUsd(finalBalance)}`,
    ].join("\n");
  };

  // ── Fetch pending emails on mount / when opened ──────────────────────────
  const fetchPending = useCallback(async () => {
    setLoading(true);
    try {
      const res = await emailService.getPending();
      let data = res.data?.data ?? [];
      if (batchId != null) {
        data = data.filter((e) => e.batch_id === batchId);
      }
      setEmails(data);
    } catch {
      toast.error("Failed to load pending emails");
    } finally {
      setLoading(false);
    }
  }, [batchId]);

  useEffect(() => {
    if (open) {
      fetchPending();
      setPreviewId(null);
      setSentIds(new Set());
      setSuppressedIds(new Set());
    }
  }, [open, fetchPending]);

  // ── Auto-close once all emails are handled ───────────────────────────────
  useEffect(() => {
    if (open && !loading && emails.length === 0 && actionInProgress.size === 0) {
      // Only auto-close if we've already done a fetch (not the very first render)
      // We detect this by checking that we're not still loading
    }
  }, [open, loading, emails, actionInProgress]);

  // ── Confirm single email ─────────────────────────────────────────────────
  // Approving no longer sends immediately — it queues the email, and the
  // throttled send-queue scheduler sends it within a few minutes.
  const handleConfirm = async (id: number) => {
    setActionInProgress((prev) => new Set(prev).add(id));
    try {
      await emailService.confirm(id);
      setSentIds((prev) => new Set(prev).add(id));
      toast.success("Queued for sending");
    } catch (err: any) {
      const msg = err?.response?.data?.message ?? "Failed to queue";
      toast.error(msg);
    } finally {
      setActionInProgress((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  // ── Cancel / suppress single email ──────────────────────────────────────
  const handleCancel = async (id: number) => {
    setActionInProgress((prev) => new Set(prev).add(id));
    try {
      await emailService.cancel(id);
      setSuppressedIds((prev) => new Set(prev).add(id));
      toast.info("Email suppressed");
    } catch (err: any) {
      const msg = err?.response?.data?.message ?? "Suppression failed";
      toast.error(msg);
    } finally {
      setActionInProgress((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  // ── Confirm ALL ──────────────────────────────────────────────────────────
  // One request for the whole batch instead of one request per email — at
  // thousands of emails, awaiting them one at a time in the browser could take
  // hours; this is a single round trip regardless of how many are selected.
  // The send-queue scheduler drains the resulting Queued rows a little at a time.
  const handleConfirmAll = async () => {
    const pendingTargets = emails.filter((e) => !sentIds.has(e.id) && !suppressedIds.has(e.id));
    const ids = pendingTargets.map((e) => e.id);
    if (ids.length === 0) return;

    setActionInProgress(new Set(ids));
    try {
      const res = await emailService.confirmBatch(ids);
      const queued = res.data?.queued ?? [];
      const skipped = res.data?.skipped ?? [];
      setSentIds((prev) => {
        const next = new Set(prev);
        queued.forEach((id) => next.add(id));
        return next;
      });
      if (skipped.length === 0) {
        toast.success(`${queued.length} email${queued.length !== 1 ? "s" : ""} queued for sending`);
      } else {
        toast.warning(`${queued.length} queued, ${skipped.length} could not be queued — check the list`);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message ?? "Failed to queue emails");
    } finally {
      setActionInProgress(new Set());
    }
  };

  // ── Cancel ALL ───────────────────────────────────────────────────────────
  const handleCancelAll = async () => {
    const pendingTargets = emails.filter((e) => !sentIds.has(e.id) && !suppressedIds.has(e.id));
    const ids = pendingTargets.map((e) => e.id);
    if (ids.length === 0) return;

    setActionInProgress(new Set(ids));
    try {
      const res = await emailService.cancelBatch(ids);
      const suppressed = res.data?.suppressed ?? [];
      setSuppressedIds((prev) => {
        const next = new Set(prev);
        suppressed.forEach((id) => next.add(id));
        return next;
      });
      toast.info(`${suppressed.length} email${suppressed.length !== 1 ? "s" : ""} suppressed`);
    } catch (err: any) {
      toast.error(err?.response?.data?.message ?? "Failed to suppress emails");
    } finally {
      setActionInProgress(new Set());
    }
  };

  if (!open) return null;

  const previewedEmail = emails.find((e) => e.id === previewId) ?? null;
  void previewedEmail; // actual preview renders inline per-row, not via this ref
  const totalPending = emails.filter(e => !sentIds.has(e.id) && !suppressedIds.has(e.id)).length;
  const anyInProgress = actionInProgress.size > 0;

  // ── Modal markup — rendered into a portal at document.body ───────────────
  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Email Confirmation"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9998,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "rgba(6, 11, 26, 0.88)",
        backdropFilter: "blur(4px)",
        padding: "16px",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: "#0B1228",
          border: "1px solid rgba(59,111,212,0.25)",
          borderRadius: "16px",
          width: "100%",
          maxWidth: "880px",
          maxHeight: "88vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 24px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(59,111,212,0.15)",
          overflow: "hidden",
        }}
      >
        {/* ─── Header ─────────────────────────────────────────────────── */}
        <div
          style={{
            padding: "20px 24px 16px",
            borderBottom: "1px solid rgba(255,255,255,0.07)",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            gap: "12px",
            flexShrink: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                width: "38px",
                height: "38px",
                borderRadius: "10px",
                background: "rgba(59,111,212,0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <Mail size={18} color="#3B6FD4" />
            </div>
            <div>
              <h2
                style={{
                  margin: 0,
                  fontSize: "16px",
                  fontWeight: 700,
                  color: "#FFFFFF",
                  fontFamily: "var(--font-display)",
                }}
              >
                Email Notification Queue
              </h2>
              <p
                style={{
                  margin: "3px 0 0",
                  fontSize: "12px",
                  color: "#94A3B8",
                  fontFamily: "var(--font-body)",
                }}
              >
                {loading
                  ? "Loading pending emails…"
                  : totalPending === 0
                  ? "No pending emails — all clear."
                  : `${totalPending} email${totalPending !== 1 ? "s" : ""} awaiting approval. Approving queues them to send in the next throttled batch.`}
              </p>
            </div>
          </div>
          <button
            id="email-modal-close"
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#64748B",
              padding: "4px",
              borderRadius: "6px",
              lineHeight: 1,
              flexShrink: 0,
            }}
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* ─── Body ───────────────────────────────────────────────────── */}
        <div style={{ flex: 1, overflowY: "auto", padding: "0" }}>
          {loading ? (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "10px",
                padding: "48px 24px",
                color: "#94A3B8",
                fontSize: "13px",
              }}
            >
              <Loader2 size={18} style={{ animation: "spin 1s linear infinite" }} color="#3B6FD4" />
              Loading pending notifications…
            </div>
          ) : totalPending === 0 ? (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: "10px",
                padding: "48px 24px",
                color: "#64748B",
              }}
            >
              <CheckCircle size={40} color="#3DBB78" strokeWidth={1.5} />
              <p style={{ margin: 0, fontSize: "14px", color: "#94A3B8" }}>
                No pending emails — all done!
              </p>
            </div>
          ) : (
            <>
              {/* Email list */}
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr
                    style={{
                      background: "#0F1833",
                      borderBottom: "1px solid rgba(255,255,255,0.06)",
                    }}
                  >
                    {["Type", "Recipient", "Subject", "Actions"].map((h) => (
                      <th
                        key={h}
                        style={{
                          padding: "10px 16px",
                          fontSize: "10px",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.06em",
                          color: "#64748B",
                          textAlign: "left",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {emails.map((email, idx) => {
                    const busy = actionInProgress.has(email.id);
                    const isPreview = previewId === email.id;
                    return (
                      <Fragment key={email.id}>
                        <tr
                          style={{
                            borderBottom: "1px solid rgba(255,255,255,0.05)",
                            background: isPreview
                              ? "rgba(59,111,212,0.08)"
                              : idx % 2 === 0
                              ? "transparent"
                              : "rgba(255,255,255,0.015)",
                            transition: "background 0.15s ease",
                            opacity: busy ? 0.6 : 1,
                          }}
                        >
                          {/* Type badge */}
                          <td style={{ padding: "12px 16px", verticalAlign: "middle" }}>
                            <EmailTypeBadge type={email.email_type} />
                          </td>

                          {/* Recipient */}
                          <td style={{ padding: "12px 16px", verticalAlign: "middle" }}>
                            <div
                              style={{
                                fontSize: "13px",
                                fontWeight: 600,
                                color: "#FFFFFF",
                              }}
                            >
                              {email.recipient_name ?? "—"}
                            </div>
                            <div
                              style={{
                                fontSize: "11px",
                                color: "#64748B",
                                fontFamily: "var(--font-mono)",
                              }}
                            >
                              {email.recipient_email}
                            </div>
                            {email.amount != null && (
                              <div
                                style={{
                                  fontSize: "11px",
                                  color: "#3DBB78",
                                  fontFamily: "var(--font-mono)",
                                  marginTop: "2px",
                                }}
                              >
                                USD {email.amount.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </div>
                            )}
                            {email.email_type === "OFFSHORE_TRANSFER" && email.main_balance != null && (
                              <div
                                style={{
                                  fontSize: "10px",
                                  color: "#94A3B8",
                                  fontFamily: "var(--font-mono)",
                                  marginTop: "2px",
                                  lineHeight: 1.4,
                                }}
                              >
                                Initial Deposit: USD {(email.initial_deposit_usd ?? email.amount ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })} | Tx Fee: USD {(email.transaction_fee_usd ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })} | Entry Fee ({(email.entry_fee_percent ?? 0).toFixed(2)}%): USD {(email.entry_fee_usd ?? 0).toLocaleString("en-US", { minimumFractionDigits: 2 })} | Active Principal: USD {email.main_balance.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                              </div>
                            )}
                          </td>

                          {/* Subject + preview toggle */}
                          <td style={{ padding: "12px 16px", verticalAlign: "middle", maxWidth: "220px" }}>
                            <div
                              style={{
                                fontSize: "12px",
                                color: "#94A3B8",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {email.subject}
                            </div>
                            <button
                              onClick={() => setPreviewId(isPreview ? null : email.id)}
                              style={{
                                background: "none",
                                border: "none",
                                cursor: "pointer",
                                color: "#3B6FD4",
                                fontSize: "11px",
                                padding: "2px 0",
                                marginTop: "2px",
                                fontFamily: "var(--font-body)",
                              }}
                            >
                              {isPreview ? "Hide preview" : "Preview body"}
                            </button>
                          </td>

                          {/* Actions */}
                          <td style={{ padding: "12px 16px", verticalAlign: "middle", whiteSpace: "nowrap" }}>
                            {busy ? (
                              <Loader2
                                size={16}
                                color="#3B6FD4"
                                style={{ animation: "spin 1s linear infinite" }}
                              />
                            ) : sentIds.has(email.id) ? (
                              <span style={{ color: "#3DBB78", fontSize: "12px", fontWeight: 700, display: "flex", alignItems: "center", gap: "5px" }}>
                                <CheckCircle size={14} /> Queued
                              </span>
                            ) : suppressedIds.has(email.id) ? (
                              <span style={{ color: "#D44B4B", fontSize: "12px", fontWeight: 700, display: "flex", alignItems: "center", gap: "5px" }}>
                                <XCircle size={14} /> Cancelled
                              </span>
                            ) : (
                              <div style={{ display: "flex", gap: "8px" }}>
                                <button
                                  id={`email-confirm-${email.id}`}
                                  onClick={() => handleConfirm(email.id)}
                                  disabled={anyInProgress}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "5px",
                                    padding: "6px 12px",
                                    borderRadius: "8px",
                                    border: "none",
                                    background: "#3B6FD4",
                                    color: "#FFFFFF",
                                    fontSize: "12px",
                                    fontWeight: 600,
                                    cursor: anyInProgress ? "not-allowed" : "pointer",
                                    opacity: anyInProgress ? 0.6 : 1,
                                    transition: "background 0.2s ease, transform 0.1s ease",
                                    fontFamily: "var(--font-body)",
                                  }}
                                  onMouseEnter={(e) => {
                                    if (!anyInProgress) (e.currentTarget as HTMLButtonElement).style.background = "#2A54A0";
                                  }}
                                  onMouseLeave={(e) => {
                                    (e.currentTarget as HTMLButtonElement).style.background = "#3B6FD4";
                                  }}
                                >
                                  <Send size={12} />
                                  Approve
                                </button>
                                <button
                                  id={`email-cancel-${email.id}`}
                                  onClick={() => handleCancel(email.id)}
                                  disabled={anyInProgress}
                                  style={{
                                    display: "flex",
                                    alignItems: "center",
                                    gap: "5px",
                                    padding: "6px 12px",
                                    borderRadius: "8px",
                                    border: "1px solid rgba(212,75,75,0.4)",
                                    background: "transparent",
                                    color: "#D44B4B",
                                    fontSize: "12px",
                                    fontWeight: 600,
                                    cursor: anyInProgress ? "not-allowed" : "pointer",
                                    opacity: anyInProgress ? 0.6 : 1,
                                    transition: "background 0.2s ease",
                                    fontFamily: "var(--font-body)",
                                  }}
                                  onMouseEnter={(e) => {
                                    if (!anyInProgress) (e.currentTarget as HTMLButtonElement).style.background = "rgba(212,75,75,0.08)";
                                  }}
                                  onMouseLeave={(e) => {
                                    (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                                  }}
                                >
                                  <XCircle size={12} />
                                  Cancel
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>

                        {/* Expandable body preview */}
                        {isPreview && (
                          <tr
                            style={{ background: "rgba(59,111,212,0.05)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}
                          >
                            <td colSpan={4} style={{ padding: "12px 24px 16px" }}>
                              <pre
                                style={{
                                  margin: 0,
                                  fontSize: "11px",
                                  color: "#94A3B8",
                                  fontFamily: "var(--font-mono)",
                                  whiteSpace: "pre-wrap",
                                  lineHeight: 1.7,
                                  background: "rgba(6,11,26,0.5)",
                                  padding: "12px 16px",
                                  borderRadius: "8px",
                                  border: "1px solid rgba(255,255,255,0.06)",
                                  maxHeight: "200px",
                                  overflowY: "auto",
                                }}
                              >
                                {sanitizeTransferBody(email.email_type, email.body, email)}
                              </pre>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>

        {/* ─── Footer — bulk actions ─────────────────────────────────── */}
        {totalPending > 0 && (
          <div
            style={{
              padding: "14px 24px",
              borderTop: "1px solid rgba(255,255,255,0.07)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "12px",
              flexShrink: 0,
              background: "#0B1228",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <AlertTriangle size={14} color="#D4940B" />
              <span style={{ fontSize: "12px", color: "#94A3B8" }}>
                {totalPending} notification{totalPending !== 1 ? "s" : ""} pending admin action
              </span>
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <button
                id="email-cancel-all"
                onClick={handleCancelAll}
                disabled={anyInProgress}
                style={{
                  padding: "8px 18px",
                  borderRadius: "8px",
                  border: "1px solid rgba(212,75,75,0.35)",
                  background: "transparent",
                  color: "#D44B4B",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: anyInProgress ? "not-allowed" : "pointer",
                  opacity: anyInProgress ? 0.6 : 1,
                  fontFamily: "var(--font-body)",
                  transition: "background 0.2s ease",
                }}
                onMouseEnter={(e) => {
                  if (!anyInProgress) (e.currentTarget as HTMLButtonElement).style.background = "rgba(212,75,75,0.07)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.background = "transparent";
                }}
              >
                Suppress All
              </button>

              <button
                id="email-confirm-all"
                onClick={handleConfirmAll}
                disabled={anyInProgress}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "7px",
                  padding: "8px 20px",
                  borderRadius: "8px",
                  border: "none",
                  background: "linear-gradient(135deg, #3B6FD4, #2A54A0)",
                  color: "#FFFFFF",
                  fontSize: "12px",
                  fontWeight: 700,
                  cursor: anyInProgress ? "not-allowed" : "pointer",
                  opacity: anyInProgress ? 0.6 : 1,
                  boxShadow: "0 4px 14px rgba(59,111,212,0.35)",
                  fontFamily: "var(--font-body)",
                  transition: "box-shadow 0.2s ease, transform 0.1s ease",
                }}
                onMouseEnter={(e) => {
                  if (!anyInProgress) {
                    (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 6px 20px rgba(59,111,212,0.5)";
                    (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-1px)";
                  }
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 14px rgba(59,111,212,0.35)";
                  (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0)";
                }}
              >
                {anyInProgress ? (
                  <Loader2 size={13} style={{ animation: "spin 1s linear infinite" }} />
                ) : (
                  <Send size={13} />
                )}
                Approve All ({totalPending})
              </button>
            </div>
          </div>
        )}
      </div>

      {/* ── Keyframe for spinner ── */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>,
    document.body
  );
}
