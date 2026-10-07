import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { MailCheck, Inbox, CheckCheck, FileText, Send, Ban, Search, ChevronLeft, ChevronRight, MailSearch } from "lucide-react";
import { emailService } from "@/services/emailService";
import type { PendingEmail, PendingEmailStatus } from "@/lib/types";
import SendStatementsPanel from "@/components/email/SendStatementsPanel";

type Tab = "inbox" | "processed" | "statements";

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
      const res = await fn(trimmedSearch ? { search: trimmedSearch, page, per_page: PER_PAGE } : undefined);
      if (res.status === 200) {
        setEmails(trimmedSearch ? ((res.data as PendingEmail[]) || []) : []);
        setStatusCounts(res.status_counts ?? {});
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
  }, [tab, trimmedSearch, page]);

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
  }, [tab]);

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

  // Pending-only count (not Suppressed/Failed) for the button label/dialog —
  // matches what most admins mean by "confirm all pending", though the
  // backend also sweeps up Suppressed/Failed (same set a single Confirm
  // click already allows) since those are just as resendable.
  const pendingCount = trimmedSearch ? (matchedTotal ?? 0) : (statusCounts.Pending_Confirmation ?? 0);

  // Suppressable = Pending_Confirmation + Queued (same set cancel_pending_email
  // allows for a single row) — matches matchedTotal (all statuses in the
  // search results) as an approximation when searching, same simplification
  // pendingCount above already makes for Confirm All.
  const suppressibleCount = trimmedSearch
    ? (matchedTotal ?? 0)
    : (statusCounts.Pending_Confirmation ?? 0) + (statusCounts.Queued ?? 0);

  const estimateSendTime = (count: number): string => {
    if (!queueStatus || count <= 0) return "";
    const { batch_size, interval_minutes } = queueStatus;
    if (!batch_size || !interval_minutes) return "";
    const totalMinutes = Math.ceil(count / batch_size) * interval_minutes;
    if (totalMinutes < 60) return `~${totalMinutes} min`;
    const hours = totalMinutes / 60;
    if (hours < 48) return `~${hours.toFixed(1)} hours`;
    return `~${(hours / 24).toFixed(1)} days`;
  };

  const confirmAllPending = async () => {
    if (pendingCount === 0) return;
    const scopeNote = trimmedSearch ? ` matching "${trimmedSearch}"` : "";
    const timeEstimate = estimateSendTime(pendingCount);
    const confirmed = window.confirm(
      `Queue all ${pendingCount.toLocaleString()} pending email(s)${scopeNote} for sending?\n\n` +
      `This queues them immediately, but they're SENT at the throttled rate below to avoid tripping ` +
      `the mail provider's spam/rate limits${timeEstimate ? ` — at the current rate (${queueStatus?.batch_size}/${queueStatus?.interval_minutes} min), that's ${timeEstimate} to finish sending all of them.` : "."}`
    );
    if (!confirmed) return;

    setConfirmingAll(true);
    try {
      const res = await emailService.confirmAll(trimmedSearch || undefined);
      if (res.status === 200) {
        toast.success(`${res.data?.queued ?? 0} email(s) queued for sending`);
        await loadEmails();
        await loadQueueStatus();
      } else {
        toast.error(res.message || "Confirm all failed");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Confirm all failed");
    } finally {
      setConfirmingAll(false);
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
      const res = await emailService.suppressAll(trimmedSearch || undefined);
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
