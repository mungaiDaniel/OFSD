import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { MailCheck, Inbox, CheckCheck, FileText, Send, Ban, Search, ChevronLeft, ChevronRight, MailSearch } from "lucide-react";
import { emailService } from "@/services/emailService";
import type { PendingEmail, PendingEmailStatus } from "@/lib/types";
import SendStatementsPanel from "@/components/email/SendStatementsPanel";
import SendConfirmModal from "@/components/email/SendConfirmModal";
import { selectStyle } from "@/components/email/emailStyles";

type Tab = "inbox" | "processed" | "statements";

const EMAIL_TYPE_LABEL: Record<string, string> = {
  INVESTOR_STATEMENT: "Overall statement",
  DEPOSIT_CONFIRMATION: "Deposit",
  OFFSHORE_TRANSFER: "Transfer",
  INVESTMENT_ACTIVE: "Deployment",
  INVESTMENT_ACTIVE_OVERSUBSCRIBED: "Deployment (oversubscribed)",
  OVERSUBSCRIPTION_REFUND_NOTICE: "Oversubscription / refund",
  WITHDRAWAL_RECEIVED: "Withdrawal received",
  WITHDRAWAL_APPROVED: "Withdrawal approved",
  BATCH_UPLOAD: "Batch upload",
};
const typeLabel = (t: string) => EMAIL_TYPE_LABEL[t] ?? t;

const STATUS_META: Record<string, { bg: string; border: string; color: string; label: string }> = {
  Pending_Confirmation: { bg: "rgba(245, 158, 11, 0.1)", border: "rgba(245, 158, 11, 0.25)", color: "rgb(251, 191, 36)", label: "Pending" },
  Queued: { bg: "rgba(96, 165, 250, 0.1)", border: "rgba(96, 165, 250, 0.25)", color: "rgb(96, 165, 250)", label: "Queued" },
  Suppressed: { bg: "rgba(239, 68, 68, 0.1)", border: "rgba(239, 68, 68, 0.25)", color: "rgb(248, 113, 113)", label: "Suppressed" },
  Confirmed: { bg: "rgba(34, 197, 94, 0.1)", border: "rgba(34, 197, 94, 0.25)", color: "rgb(74, 222, 128)", label: "Confirmed" },
  Failed: { bg: "rgba(239, 68, 68, 0.1)", border: "rgba(239, 68, 68, 0.25)", color: "rgb(248, 113, 113)", label: "Failed" },
};

function StatusBadge({ status }: { status: PendingEmailStatus | null }) {
  const meta = (status && STATUS_META[status]) || { bg: "rgba(255,255,255,0.05)", border: "rgba(255,255,255,0.1)", color: "var(--color-text-secondary)", label: status || "—" };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "4px 10px",
        borderRadius: "999px",
        background: meta.bg,
        border: `1px solid ${meta.border}`,
        color: meta.color,
        fontSize: "11px",
        fontWeight: 700,
      }}
    >
      {meta.label}
    </span>
  );
}

function formatCreated(d: string | null): string {
  if (!d) return "—";
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return "—";
  const date = dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  const time = dt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  return `${date} ${time}`;
}

function formatAmount(email: PendingEmail): string {
  if (email.amount == null) return "—";
  return `${email.currency_type || "USD"} ${email.amount.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

const tabBtnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  padding: "8px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  cursor: "pointer",
  fontSize: "12px",
  fontWeight: 600,
};

const countChip: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  padding: "4px 10px",
  borderRadius: "100px",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  background: "rgba(255, 255, 255, 0.05)",
  color: "var(--color-text-secondary)",
  fontSize: "11px",
  fontWeight: 600,
};

const actionBtnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "6px 10px",
  borderRadius: "8px",
  fontSize: "11px",
  fontWeight: 600,
};

function formatNextRun(iso: string | null): string {
  if (!iso) return "—";
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return "—";
  const mins = Math.max(0, Math.round((dt.getTime() - Date.now()) / 60000));
  if (mins <= 0) return "any moment";
  return `~${mins} min`;
}

const PER_PAGE = 50;

const INBOX_STATUS_ORDER: PendingEmailStatus[] = ["Pending_Confirmation", "Queued", "Suppressed"];
const PROCESSED_STATUS_ORDER: PendingEmailStatus[] = ["Confirmed", "Failed"];

export default function PendingEmailsPage() {
  const [tab, setTab] = useState<Tab>("inbox");
  const [emails, setEmails] = useState<PendingEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [matchedTotal, setMatchedTotal] = useState<number | null>(null);
  const [typeFilter, setTypeFilter] = useState("");
  const [typeCounts, setTypeCounts] = useState<Record<string, number>>({});
  const [pendingMatch, setPendingMatch] = useState(0);
  const [confirmAllOpen, setConfirmAllOpen] = useState(false);
  const [busyIds, setBusyIds] = useState<Set<number>>(new Set());
  const [confirmingAll, setConfirmingAll] = useState(false);
  const [suppressingAll, setSuppressingAll] = useState(false);
  const [queueStatus, setQueueStatus] = useState<{ next_run_at: string | null; queued_count: number; batch_size: number; interval_minutes: number } | null>(null);

  // Debounce search so we're not hitting the server on every keystroke; resets to page 1.
  useEffect(() => {
    const t = setTimeout(() => setPage(1), 300);
    return () => clearTimeout(t);
  }, [search]);

  const trimmedSearch = search.trim();

  const loadEmails = useCallback(async () => {
    if (tab === "statements") return;
    setLoading(true);
    try {
      // With no search term, the backend never builds the (expensive) row list
      // at all — it only returns per-status counts. This is what keeps the
      // Email page fast once thousands of rows accumulate over time.
      const fn = tab === "inbox" ? emailService.getInbox : emailService.getProcessed;
      const params: { search?: string; page?: number; per_page?: number; email_type?: string } = {};
      if (trimmedSearch) Object.assign(params, { search: trimmedSearch, page, per_page: PER_PAGE });
      if (tab === "inbox" && typeFilter) params.email_type = typeFilter;
      const res = await fn(Object.keys(params).length ? params : undefined);
      if (res.status === 200) {
        setEmails(trimmedSearch ? ((res.data as PendingEmail[]) || []) : []);
        setStatusCounts(res.status_counts ?? {});
        setTypeCounts(res.type_counts ?? {});
        setPendingMatch(res.pending_match ?? 0);
        setTotalPages(res.pagination?.total_pages ?? 1);
        setMatchedTotal(res.pagination?.total ?? null);
      } else {
        toast.error(res.message || "Failed to load emails");
      }
    } catch {
      toast.error("Failed to load emails");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, trimmedSearch, page, typeFilter]);

  useEffect(() => {
    let alive = true;
    loadEmails().then(() => { if (!alive) return; });
    return () => { alive = false; };
  }, [loadEmails]);

  const loadQueueStatus = useCallback(async () => {
    if (tab !== "inbox") return;
    try {
      const qs = await emailService.getQueueStatus();
      setQueueStatus(qs.data ?? null);
    } catch {
      // Non-critical — leave the indicator hidden if this fails.
    }
  }, [tab]);

  useEffect(() => { loadQueueStatus(); }, [loadQueueStatus]);

  useEffect(() => {
    setSearch("");
    setPage(1);
    setTypeFilter("");
  }, [tab]);

  useEffect(() => { setPage(1); }, [typeFilter]);

  const totalForTab = Object.values(statusCounts).reduce((sum, n) => sum + n, 0);
  const statusOrder = tab === "inbox" ? INBOX_STATUS_ORDER : PROCESSED_STATUS_ORDER;

  const runAction = async (id: number, action: "confirm" | "cancel") => {
    setBusyIds((prev) => new Set(prev).add(id));
    try {
      const res = action === "confirm" ? await emailService.confirm(id) : await emailService.cancel(id);
      if (res.status === 200) {
        toast.success(action === "confirm" ? "Queued for sending" : "Email suppressed");
        setEmails((prev) => prev.filter((e) => e.id !== id));
        setStatusCounts((prev) => {
          const email = emails.find((e) => e.id === id);
          if (!email?.status) return prev;
          const next = { ...prev, [email.status]: Math.max(0, (prev[email.status] || 1) - 1) };
          const newStatus = action === "confirm" ? "Queued" : "Suppressed";
          next[newStatus] = (next[newStatus] || 0) + 1;
          return next;
        });
      } else {
        toast.error(res.message || "Action failed");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Action failed");
    } finally {
      setBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  };

  // Exactly the emails "Confirm All" will approve under the current filters (type + search):
  // Pending only. The server returns this count and re-checks it when the admin confirms.
  const pendingCount = pendingMatch;

  // Suppressable = Pending_Confirmation + Queued (same set cancel_pending_email
  // allows for a single row) — matches matchedTotal (all statuses in the
  // search results) as an approximation when searching, same simplification
  // pendingCount above already makes for Confirm All.
  const suppressibleCount = trimmedSearch
    ? (matchedTotal ?? 0)
    : (statusCounts.Pending_Confirmation ?? 0) + (statusCounts.Queued ?? 0);

  // Step 1: just open the confirmation dialog (it shows the scope and makes the admin type the count).
  const confirmAllPending = () => {
    if (pendingCount === 0) return;
    setConfirmAllOpen(true);
  };

  // Step 2: the admin typed the count. The server re-counts and refuses if it differs.
  const runConfirmAll = async () => {
    setConfirmingAll(true);
    try {
      const res = await emailService.confirmAll(pendingCount, {
        search: trimmedSearch || undefined,
        emailType: typeFilter || undefined,
      });
      setConfirmAllOpen(false);
      if (res.status === 200) {
        toast.success(`${res.data?.queued ?? 0} email(s) queued for sending`);
      } else {
        toast.error(res.message || "Confirm all failed");
      }
    } catch (err: any) {
      setConfirmAllOpen(false);
      toast.error(err?.response?.data?.message || "Confirm all failed");
    } finally {
      setConfirmingAll(false);
      await loadEmails();
      await loadQueueStatus();
    }
  };

  const suppressAllPending = async () => {
    if (suppressibleCount === 0) return;
    const scopeNote = trimmedSearch ? ` matching "${trimmedSearch}"` : "";
    const confirmed = window.confirm(
      `Suppress all ${suppressibleCount.toLocaleString()} email(s)${scopeNote}?\n\n` +
      `This stops them from sending — they will NOT be delivered unless confirmed again later.`
    );
    if (!confirmed) return;

    setSuppressingAll(true);
    try {
      const res = await emailService.suppressAll(trimmedSearch || undefined, typeFilter || undefined);
      if (res.status === 200) {
        toast.success(`${res.data?.suppressed ?? 0} email(s) suppressed`);
        await loadEmails();
        await loadQueueStatus();
      } else {
        toast.error(res.message || "Suppress all failed");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Suppress all failed");
    } finally {
      setSuppressingAll(false);
    }
  };

  return (
    <div className="ofds-page">
      <div>
        {/* Header */}
        <div className="page-header-row" style={{ marginBottom: "24px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <MailCheck size={18} style={{ color: "rgb(96, 165, 250)" }} />
            <div>
              <h1 className="ofds-page-title">Email</h1>
              <p className="ofds-page-subtitle">
                {tab === "inbox"
                  ? "Awaiting approval, or approved and queued to send"
                  : tab === "processed"
                  ? "Emails already sent or failed"
                  : "Filter investors and queue overall statement emails for approval"}
              </p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {queueStatus && queueStatus.queued_count > 0 && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "6px 12px",
                  borderRadius: "999px",
                  background: "rgba(96, 165, 250, 0.1)",
                  border: "1px solid rgba(96, 165, 250, 0.25)",
                  color: "rgb(96, 165, 250)",
                  fontSize: "11px",
                  fontWeight: 600,
                }}
                title="Approved emails are sent in throttled batches, not immediately"
              >
                {queueStatus.queued_count} queued — next batch in {formatNextRun(queueStatus.next_run_at)}
              </span>
            )}
            {tab !== "statements" && (
              <div style={{ position: "relative" }}>
                <Search
                  size={12}
                  style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-tertiary)", pointerEvents: "none" }}
                />
                <input
                  placeholder="Search by client code, email, or phone…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  style={{
                    background: "rgba(255, 255, 255, 0.04)",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                    borderRadius: "8px",
                    padding: "6px 12px 6px 30px",
                    fontSize: "12px",
                    color: "var(--color-text-primary)",
                    width: "260px",
                    outline: "none",
                  }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: "flex", gap: "10px", marginBottom: "14px" }}>
          <button
            type="button"
            onClick={() => setTab("inbox")}
            style={{
              ...tabBtnBase,
              background: tab === "inbox" ? "rgba(0, 102, 255, 0.14)" : "rgba(255, 255, 255, 0.05)",
              color: tab === "inbox" ? "rgb(255, 255, 255)" : "var(--color-text-secondary)",
            }}
          >
            <Inbox size={16} /> Pending / Suppressed
          </button>
          <button
            type="button"
            onClick={() => setTab("processed")}
            style={{
              ...tabBtnBase,
              background: tab === "processed" ? "rgba(0, 102, 255, 0.14)" : "rgba(255, 255, 255, 0.05)",
              color: tab === "processed" ? "rgb(255, 255, 255)" : "var(--color-text-secondary)",
            }}
          >
            <CheckCheck size={16} /> Processed
          </button>
          <button
            type="button"
            onClick={() => setTab("statements")}
            style={{
              ...tabBtnBase,
              background: tab === "statements" ? "rgba(0, 102, 255, 0.14)" : "rgba(255, 255, 255, 0.05)",
              color: tab === "statements" ? "rgb(255, 255, 255)" : "var(--color-text-secondary)",
            }}
          >
            <FileText size={16} /> Send Statements
          </button>
        </div>

        <SendConfirmModal
          open={confirmAllOpen}
          title={`Confirm ${pendingCount.toLocaleString()} pending email${pendingCount === 1 ? "" : "s"}?`}
          description={[
            typeFilter ? `Type: ${typeLabel(typeFilter)}` : "All types",
            trimmedSearch ? `matching "${trimmedSearch}"` : null,
          ].filter(Boolean).join(" · ") + ". Only Pending emails are included — Suppressed and Failed ones are left alone."}
          items={[]}
          count={pendingCount}
          rate={queueStatus}
          requireTypedCount
          confirmLabel={`Send ${pendingCount.toLocaleString()}`}
          busy={confirmingAll}
          onConfirm={runConfirmAll}
          onCancel={() => setConfirmAllOpen(false)}
        />

        {tab === "statements" ? (
          <SendStatementsPanel />
        ) : (
          <>
        {/* Status count chips — always cheap SQL counts, never a full row load */}
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "8px", marginBottom: "14px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
            <span style={countChip}>Total: {totalForTab.toLocaleString()}</span>
            {statusOrder.map((s) => (
              <span key={s} style={countChip}>
                {STATUS_META[s]?.label ?? s}: {(statusCounts[s] ?? 0).toLocaleString()}
              </span>
            ))}
            {tab === "inbox" && (Object.keys(typeCounts).length > 0 || typeFilter) && (
              <select
                value={typeFilter}
                onChange={(e) => setTypeFilter(e.target.value)}
                aria-label="Filter by email type"
                style={{ ...selectStyle, padding: "4px 28px 4px 10px", borderRadius: "100px", fontSize: "11px" }}
              >
                <option value="">All types</option>
                {Object.entries(typeCounts).map(([t, n]) => (
                  <option key={t} value={t}>{typeLabel(t)} ({n.toLocaleString()})</option>
                ))}
                {typeFilter && !(typeFilter in typeCounts) && <option value={typeFilter}>{typeLabel(typeFilter)} (0)</option>}
              </select>
            )}
          </div>
          {tab === "inbox" && (
            <button
              type="button"
              onClick={confirmAllPending}
              disabled={confirmingAll || pendingCount === 0}
              title={pendingCount === 0 ? "No pending emails in this scope" : `Confirm all ${pendingCount.toLocaleString()} pending email(s)${trimmedSearch ? ` matching "${trimmedSearch}"` : ""}`}
              style={{
                ...actionBtnBase,
                border: "1px solid rgba(34,197,94,0.35)",
                background: "rgba(34,197,94,0.1)",
                color: "rgb(74,222,128)",
                cursor: confirmingAll || pendingCount === 0 ? "not-allowed" : "pointer",
                opacity: confirmingAll || pendingCount === 0 ? 0.5 : 1,
              }}
            >
              <CheckCheck size={13} />
              {confirmingAll ? "Confirming…" : `Confirm All Pending${pendingCount ? ` (${pendingCount.toLocaleString()})` : ""}`}
            </button>
          )}
          {tab === "inbox" && (
            <button
              type="button"
              onClick={suppressAllPending}
              disabled={suppressingAll || suppressibleCount === 0}
              title={suppressibleCount === 0 ? "No suppressible emails in this scope" : `Suppress all ${suppressibleCount.toLocaleString()} email(s)${trimmedSearch ? ` matching "${trimmedSearch}"` : ""}`}
              style={{
                ...actionBtnBase,
                border: "1px solid rgba(239,68,68,0.35)",
                background: "rgba(239,68,68,0.1)",
                color: "rgb(248,113,113)",
                cursor: suppressingAll || suppressibleCount === 0 ? "not-allowed" : "pointer",
                opacity: suppressingAll || suppressibleCount === 0 ? 0.5 : 1,
              }}
            >
              <Ban size={13} />
              {suppressingAll ? "Suppressing…" : `Suppress All${suppressibleCount ? ` (${suppressibleCount.toLocaleString()})` : ""}`}
            </button>
          )}
        </div>

        {/* Table */}
        <div className="ofds-glass" style={{ overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table className="table table-dark mb-0" style={{ background: "transparent" }}>
              <thead>
                <tr>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Recipient</th>
                  <th>Subject</th>
                  <th>Amount</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {!trimmedSearch ? (
                  <tr>
                    <td colSpan={7} style={{ padding: "48px 16px", textAlign: "center" }}>
                      <MailSearch size={28} style={{ color: "var(--color-text-tertiary)", marginBottom: "10px" }} />
                      <div style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "4px" }}>
                        {totalForTab.toLocaleString()} email{totalForTab === 1 ? "" : "s"} on file
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>
                        Search by client code, email, or phone number to find one.
                      </div>
                    </td>
                  </tr>
                ) : loading ? (
                  <tr>
                    <td colSpan={7} style={{ padding: "32px 16px", textAlign: "center", color: "var(--color-text-tertiary)" }}>
                      Loading…
                    </td>
                  </tr>
                ) : emails.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ padding: "32px 16px", textAlign: "center", color: "var(--color-text-tertiary)" }}>
                      No emails found for "{trimmedSearch}".
                    </td>
                  </tr>
                ) : (
                  emails.map((email) => {
                    const busy = busyIds.has(email.id);
                    const canConfirm = email.status !== "Confirmed" && email.status !== "Queued";
                    const canSuppress = email.status === "Pending_Confirmation" || email.status === "Queued";
                    return (
                      <tr key={email.id} style={{ cursor: "default" }}>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>{email.email_type}</td>
                        <td>
                          <StatusBadge status={email.status} />
                        </td>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                            <span style={{ fontSize: "12px", color: "var(--color-text-primary)" }}>{email.recipient_name || "—"}</span>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-tertiary)" }}>{email.recipient_email}</span>
                          </div>
                        </td>
                        <td style={{ fontSize: "12px", color: "var(--color-text-secondary)", maxWidth: "520px" }}>{email.subject}</td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>{formatAmount(email)}</td>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-tertiary)" }}>{formatCreated(email.created_at)}</td>
                        <td style={{ textAlign: "right" }}>
                          <div style={{ display: "inline-flex", gap: "8px" }}>
                            <button
                              onClick={() => runAction(email.id, "confirm")}
                              disabled={busy || !canConfirm}
                              style={{
                                ...actionBtnBase,
                                border: "1px solid rgba(34, 197, 94, 0.25)",
                                background: "rgba(34, 197, 94, 0.1)",
                                color: "rgb(34, 197, 94)",
                                cursor: busy || !canConfirm ? "not-allowed" : "pointer",
                                opacity: busy || !canConfirm ? 0.5 : 1,
                              }}
                            >
                              <Send size={14} /> {email.status === "Queued" ? "Queued" : "Approve"}
                            </button>
                            <button
                              onClick={() => runAction(email.id, "cancel")}
                              disabled={busy || !canSuppress}
                              style={{
                                ...actionBtnBase,
                                border: "1px solid rgba(239, 68, 68, 0.25)",
                                background: "rgba(239, 68, 68, 0.1)",
                                color: "rgb(248, 113, 113)",
                                cursor: busy || !canSuppress ? "not-allowed" : "pointer",
                                opacity: busy || !canSuppress ? 0.5 : 1,
                              }}
                            >
                              <Ban size={14} /> Suppress
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {trimmedSearch && totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "14px" }}>
            <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
              Page {page} of {totalPages}
            </span>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                style={{
                  display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
                  borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                  color: "var(--color-text-secondary)", fontSize: "12px", cursor: (page <= 1 || loading) ? "not-allowed" : "pointer",
                  opacity: (page <= 1 || loading) ? 0.5 : 1,
                }}
              >
                <ChevronLeft size={14} /> Prev
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || loading}
                style={{
                  display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
                  borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                  color: "var(--color-text-secondary)", fontSize: "12px", cursor: (page >= totalPages || loading) ? "not-allowed" : "pointer",
                  opacity: (page >= totalPages || loading) ? 0.5 : 1,
                }}
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
          </>
        )}
      </div>
    </div>
  );
}
