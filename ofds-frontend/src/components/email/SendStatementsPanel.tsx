import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Loader2, RefreshCw, Send } from "lucide-react";
import { fundService } from "@/services/fundService";
import { reportService } from "@/services/reportService";
import { emailService, type BulkKind, type QueuedStatementEmail, type StatementDownloadJob } from "@/services/emailService";
import type { EligibleInvestor, FundSummaryItem } from "@/lib/types";
import BulkTypeSendPanel, { KIND_LABEL } from "./BulkTypeSendPanel";
import SendConfirmModal from "./SendConfirmModal";
import { btn, inputStyle, selectStyle } from "./emailStyles";

// ═══════════════════════════════════════════════════════════════════════════
// SEND STATEMENTS — Email page tab.
//
// Filter investors by valuation period + fund + share class (the same
// eligibility check already used elsewhere), pick who to send to, and queue
// each selected client's OVERALL statement email (whole portfolio, not just
// the filtered fund/class) for admin approval. Queued items land in the
// Inbox tab like anything else — nothing here sends immediately.
// ═══════════════════════════════════════════════════════════════════════════

function getDefaultPeriod(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 7);
}

const TYPE_OPTIONS: { value: "overall" | BulkKind; label: string }[] = [
  { value: "overall", label: "Overall statement (whole portfolio)" },
  ...(Object.keys(KIND_LABEL) as BulkKind[]).map((k) => ({ value: k, label: KIND_LABEL[k] })),
];

function EmailStatusBadge({ status }: { status: EligibleInvestor["email_status"] }) {
  const cfg = {
    ready: { label: "Ready", bg: "rgba(34,197,94,0.12)", color: "rgb(74,222,128)" },
    no_email: { label: "Missing email", bg: "rgba(245,158,11,0.12)", color: "rgb(251,191,36)" },
    already_sent: { label: "Ready", bg: "rgba(34,197,94,0.12)", color: "rgb(74,222,128)" },
  }[status] ?? { label: "Ready", bg: "rgba(34,197,94,0.12)", color: "rgb(74,222,128)" };
  return (
    <span style={{ display: "inline-flex", padding: "2px 8px", borderRadius: "999px", fontSize: "10px", fontWeight: 700, background: cfg.bg, color: cfg.color }}>
      {cfg.label}
    </span>
  );
}

export default function SendStatementsPanel() {
  const [period, setPeriod] = useState(getDefaultPeriod());
  const [funds, setFunds] = useState<FundSummaryItem[]>([]);
  const [fundId, setFundId] = useState<string>("all");
  const [shareClassId, setShareClassId] = useState<string>("all");

  const [eligible, setEligible] = useState<EligibleInvestor[]>([]);
  const [loadingEligible, setLoadingEligible] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [queuing, setQueuing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [recent, setRecent] = useState<StatementDownloadJob[]>([]);
  const [savingJobId, setSavingJobId] = useState<string | null>(null);
  const [transferStage, setTransferStage] = useState<"undeployed" | "all">("undeployed");
  const [transferDownloading, setTransferDownloading] = useState(false);
  const [transferProgress, setTransferProgress] = useState<{ done: number; total: number } | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{ done: number; total: number } | null>(null);
  const [statementType, setStatementType] = useState<"overall" | BulkKind>("overall");
  // Emails created by the last "Queue" click. Only these may be sent from the dialog that follows.
  const [justQueued, setJustQueued] = useState<QueuedStatementEmail[] | null>(null);
  const [sendingQueued, setSendingQueued] = useState(false);
  const [rate, setRate] = useState<{ batch_size: number; interval_minutes: number } | null>(null);

  useEffect(() => {
    // Funds AND Shares are separate products: getSummary() alone returns only Funds, which
    // is why share funds (e.g. Dangote) were missing from every fund dropdown on this tab.
    Promise.all([
      fundService.getSummary("FUNDS").catch(() => null),
      fundService.getSummary("SHARES").catch(() => null),
    ]).then(([fundsSummary, sharesSummary]) => {
      const merged = [
        ...(fundsSummary?.funds ?? []).map((f) => ({ ...f, product_type: f.product_type ?? ("FUNDS" as const) })),
        ...(sharesSummary?.funds ?? []).map((f) => ({ ...f, product_type: f.product_type ?? ("SHARES" as const) })),
      ];
      setFunds(merged.filter((f, i) => merged.findIndex((x) => x.id === f.id && x.product_type === f.product_type) === i));
    });
    emailService.getQueueStatus().then((r) => r.data && setRate({ batch_size: r.data.batch_size, interval_minutes: r.data.interval_minutes })).catch(() => {});
  }, []);

  const availableClasses = useMemo(() => {
    if (fundId === "all") return funds.flatMap((f) => f.classes ?? []);
    const found = funds.find((f) => String(f.id) === fundId);
    return found ? (found.classes ?? []) : [];
  }, [funds, fundId]);

  const handleLoad = async () => {
    setLoadingEligible(true);
    setSelectedIds(new Set());
    try {
      const params: { period: string; fund_id?: number; share_class_id?: number } = { period };
      if (fundId !== "all") params.fund_id = Number(fundId);
      if (shareClassId !== "all") params.share_class_id = Number(shareClassId);
      const data = await reportService.getEligibleInvestors(params);
      setEligible(data);
      setHasLoaded(true);
    } catch {
      toast.error("Failed to load eligible investors");
    } finally {
      setLoadingEligible(false);
    }
  };

  const readyRows = eligible.filter((i) => i.email_status !== "no_email");
  const noEmailCount = eligible.filter((i) => i.email_status === "no_email").length;

  const toggleOne = (id: number) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const selectAllReady = () => setSelectedIds(new Set(readyRows.map((i) => i.id)));
  const deselectAll = () => setSelectedIds(new Set());

  // Download PDFs: the ticked investors, or every investor in the list when none are
  // ticked. No email address is needed, so investors without one are included.
  const handleDownloadZip = async () => {
    const rows = selectedIds.size > 0 ? eligible.filter((i) => selectedIds.has(i.id)) : eligible;
    if (rows.length === 0) {
      toast.error("No investors to download");
      return;
    }
    setDownloading(true);
    setDownloadProgress({ done: 0, total: rows.length });
    try {
      const codes = Array.from(new Set(rows.map((i) => i.internal_client_code)));
      const fundIds = fundId !== "all" ? [Number(fundId)] : undefined;
      const { total, failed } = await emailService.downloadStatementsZip(codes, fundIds, (done, t) =>
        setDownloadProgress({ done, total: t })
      );
      if (failed.length > 0) {
        toast.warning(`Downloaded ${total - failed.length} of ${total} statements — ${failed.length} failed (listed in _FAILED.txt inside the zip)`);
      } else {
        toast.success(`Downloaded ${total} statement${total === 1 ? "" : "s"}`);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || err?.message || "Failed to download statements");
    } finally {
      setDownloading(false);
      setDownloadProgress(null);
    }
  };

  // Transfer statements need no deployment: every investor in the chosen fund (or all funds)
  // whose batch has been transferred. One zip, a folder per batch, plus summary.csv.
  const handleDownloadTransferZip = async () => {
    const fundIds = fundId !== "all" ? [Number(fundId)] : funds.map((f) => f.id).filter((x): x is number => typeof x === "number");
    if (fundIds.length === 0) {
      toast.error("No funds loaded");
      return;
    }
    setTransferDownloading(true);
    setTransferProgress({ done: 0, total: 0 });
    try {
      const { total, failed } = await emailService.downloadTransferStatementsZip(
        { fundIds, stage: transferStage },
        (done, t) => setTransferProgress({ done, total: t })
      );
      if (failed.length > 0) {
        toast.warning(`Downloaded ${total - failed.length} of ${total} transfer statements — ${failed.length} failed (listed in _FAILED.txt inside the zip)`);
      } else {
        toast.success(`Downloaded ${total} transfer statement${total === 1 ? "" : "s"}`);
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || err?.message || "Failed to download transfer statements");
    } finally {
      setTransferDownloading(false);
      setTransferProgress(null);
    }
  };

  const loadRecent = async () => {
    try {
      setRecent(await emailService.listStatementDownloads());
    } catch {
      /* the list is a convenience; ignore failures */
    }
  };
  useEffect(() => {
    loadRecent();
  }, []);
  // Keep the list fresh while a build is running, and refresh when one finishes.
  useEffect(() => {
    if (!downloading && !transferDownloading && !recent.some((j) => j.state === "running")) return;
    const t = setInterval(loadRecent, 4000);
    return () => clearInterval(t);
  }, [downloading, transferDownloading, recent]);
  useEffect(() => {
    if (!downloading && !transferDownloading) loadRecent();
  }, [downloading, transferDownloading]);

  const saveRecent = async (job: StatementDownloadJob) => {
    setSavingJobId(job.job_id);
    try {
      await emailService.saveFinishedDownload(job.job_id, `${job.label}.zip`);
    } catch (err: any) {
      toast.error(err?.response?.status === 404 ? "That download has expired (kept for 24 hours)" : err?.message || "Failed to download");
    } finally {
      setSavingJobId(null);
    }
  };

  const handleQueue = async () => {
    const selected = eligible.filter((i) => selectedIds.has(i.id) && i.email_status !== "no_email");
    if (selected.length === 0) {
      toast.error("Select at least one investor with an email address");
      return;
    }
    setQueuing(true);
    try {
      const clientCodes = selected.map((i) => i.internal_client_code);
      // Filtered to one fund ("Fund = X") -> every recipient gets THAT fund's
      // fund-scoped statement, not their full portfolio. "All funds" -> full
      // consolidated statement per recipient (fundIds omitted).
      const fundIds = fundId !== "all" ? [Number(fundId)] : undefined;
      const res = await emailService.queueStatementsBatch(clientCodes, fundIds);
      if (res.status === 200) {
        const { queued, skipped, not_found, emails } = res.data ?? { queued: [], skipped: [], not_found: [], emails: [] };
        toast.success(`Queued ${queued.length} statement email(s) for approval`);
        if (skipped.length > 0) {
          toast.info(`${skipped.length} skipped (already queued or pending)`);
        }
        if (not_found.length > 0) {
          toast.error(`${not_found.length} client code(s) not found`);
        }
        setSelectedIds(new Set());
        // Offer to send exactly the emails this click created - nothing else in the Inbox.
        if (emails && emails.length > 0) setJustQueued(emails);
      } else {
        toast.error(res.message || "Failed to queue statements");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to queue statements");
    } finally {
      setQueuing(false);
    }
  };

  // "Send these N now": approves ONLY the ids the last queue call returned.
  const sendJustQueued = async () => {
    if (!justQueued) return;
    setSendingQueued(true);
    try {
      const res = await emailService.confirmBatch(justQueued.map((e) => e.id));
      const n = res.data?.queued?.length ?? 0;
      toast.success(`${n} statement email${n === 1 ? "" : "s"} queued for sending`);
      setJustQueued(null);
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to send");
    } finally {
      setSendingQueued(false);
    }
  };

  const typePicker = (
    <div className="ofds-glass" style={{ padding: "14px 20px", marginBottom: "16px", display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
      <label htmlFor="statement-type" style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>STATEMENT TYPE</label>
      <select id="statement-type" value={statementType} onChange={(e) => setStatementType(e.target.value as "overall" | BulkKind)} style={selectStyle}>
        {TYPE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {statementType !== "overall" && (
        <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
          Pick a fund or batch, preview who gets it, then send. Only that list is sent.
        </span>
      )}
    </div>
  );

  if (statementType !== "overall") {
    return (
      <div>
        {typePicker}
        <BulkTypeSendPanel kind={statementType} funds={funds} />
        <style>{`
          .ss-spin { animation: ss-spin-kf 0.8s linear infinite; }
          @keyframes ss-spin-kf { to { transform: rotate(360deg); } }
        `}</style>
      </div>
    );
  }

  return (
    <div>
      {typePicker}
      <p style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginBottom: "16px" }}>
        Filter investors by the valuation period + fund + share class you just committed, then queue each
        selected investor's overall statement email — their whole portfolio, not just this fund/class. After
        queuing you choose whether to send exactly those emails now; anything else in the Inbox is never touched.
      </p>

      <SendConfirmModal
        open={justQueued !== null}
        title={`Send these ${justQueued?.length ?? 0} statement${justQueued?.length === 1 ? "" : "s"} now?`}
        description="Only the emails you just queued are listed. Choose 'Keep in Inbox' to review them later."
        items={(justQueued ?? []).map((e) => ({ primary: e.recipient_name || e.client_code, secondary: e.recipient_email ?? undefined, note: e.client_code }))}
        count={justQueued?.length ?? 0}
        rate={rate}
        busy={sendingQueued}
        cancelLabel="Keep in Inbox"
        onConfirm={sendJustQueued}
        onCancel={() => {
          if (justQueued) toast.info(`${justQueued.length} email(s) left in the Inbox — not sent`);
          setJustQueued(null);
        }}
      />

      {/* Filters */}
      <div className="ofds-glass" style={{ padding: "16px 20px", marginBottom: "16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr) auto", gap: "12px", alignItems: "end" }}>
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
              VALUATION PERIOD
            </label>
            <input type="month" value={period} onChange={(e) => setPeriod(e.target.value)} style={inputStyle} />
          </div>
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
              FUND
            </label>
            <select
              value={fundId}
              onChange={(e) => { setFundId(e.target.value); setShareClassId("all"); }}
              style={selectStyle}
            >
              <option value="all">All funds</option>
              <optgroup label="Funds">
                {funds.filter((f) => f.product_type !== "SHARES").map((f) => (
                  <option key={f.id} value={String(f.id)}>{f.fund_name}</option>
                ))}
              </optgroup>
              <optgroup label="Shares">
                {funds.filter((f) => f.product_type === "SHARES").map((f) => (
                  <option key={f.id} value={String(f.id)}>{f.fund_name}</option>
                ))}
              </optgroup>
            </select>
          </div>
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
              SHARE CLASS
            </label>
            <select value={shareClassId} onChange={(e) => setShareClassId(e.target.value)} style={selectStyle}>
              <option value="all">All classes</option>
              {availableClasses.map((c) => (
                <option key={c.id} value={String(c.id)}>{c.class_code ?? c.class_name}</option>
              ))}
            </select>
          </div>
          <button onClick={handleLoad} disabled={loadingEligible} style={btn(loadingEligible, "primary")}>
            {loadingEligible ? <Loader2 size={13} className="ss-spin" /> : <FileText size={13} />}
            Load investors
          </button>
        </div>
      </div>

      {/* Recent downloads: a finished zip stays available for 24 hours */}
      {recent.length > 0 && (
        <div className="ofds-glass" style={{ padding: "14px 20px", marginBottom: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "8px" }}>
            <div style={{ fontSize: "12px", color: "#fff", fontWeight: 600 }}>Recent downloads <span style={{ color: "var(--color-text-tertiary)", fontWeight: 400 }}>(kept for 24 hours)</span></div>
            <button onClick={loadRecent} title="Refresh" style={{ background: "transparent", border: "none", color: "var(--color-text-secondary)", cursor: "pointer", padding: 4 }}>
              <RefreshCw size={13} />
            </button>
          </div>
          {recent.map((j) => (
            <div key={j.job_id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", padding: "6px 0", borderTop: "1px solid rgba(255,255,255,0.05)", fontSize: "12px", color: "var(--color-text-secondary)" }}>
              <span>
                {j.label} · {j.created_at ? new Date(j.created_at * 1000).toLocaleString() : ""} ·{" "}
                {j.state === "completed" && `${j.total} PDF${j.total === 1 ? "" : "s"}${j.failed_count ? ` (${j.failed_count} failed)` : ""}`}
                {j.state === "running" && `building ${j.done}/${j.total}…`}
                {j.state === "interrupted" && "cut off by a server restart — start it again"}
                {j.state === "failed" && "failed"}
              </span>
              {j.ready && (
                <button onClick={() => saveRecent(j)} disabled={savingJobId === j.job_id} style={btn(savingJobId === j.job_id)}>
                  {savingJobId === j.job_id ? <Loader2 size={13} className="ss-spin" /> : <Download size={13} />} Download
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Transfer statements (available before deployment) */}
      <div className="ofds-glass" style={{ padding: "14px 20px", marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
        <div style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
          <strong style={{ color: "#fff" }}>Transfer statements</strong> — {fundId === "all" ? "all funds" : "the selected fund"}, one zip with a folder per batch and a summary.csv. No deployment needed.
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <select value={transferStage} onChange={(e) => setTransferStage(e.target.value as "undeployed" | "all")} style={selectStyle}>
            <option value="undeployed">Transferred, not yet deployed</option>
            <option value="all">All transferred batches</option>
          </select>
          <button onClick={handleDownloadTransferZip} disabled={transferDownloading} style={btn(transferDownloading)}>
            {transferDownloading ? <Loader2 size={13} className="ss-spin" /> : <Download size={13} />}
            {transferDownloading && transferProgress && transferProgress.total > 0
              ? `Building ${transferProgress.done}/${transferProgress.total}…`
              : "Download transfer statements (zip)"}
          </button>
        </div>
      </div>

      {/* Results */}
      {hasLoaded && (
        <div className="ofds-glass" style={{ overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
            <div style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
              {eligible.length} investor{eligible.length === 1 ? "" : "s"} found for {period}
              {noEmailCount > 0 && <span style={{ color: "var(--color-text-tertiary)" }}> ({noEmailCount} missing email, not selectable)</span>}
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button onClick={selectAllReady} style={btn(readyRows.length === 0)} disabled={readyRows.length === 0}>Select all</button>
              <button onClick={deselectAll} style={btn(selectedIds.size === 0)} disabled={selectedIds.size === 0}>Deselect all</button>
              <button onClick={handleDownloadZip} disabled={downloading || eligible.length === 0} style={btn(downloading || eligible.length === 0)}>
                {downloading ? <Loader2 size={13} className="ss-spin" /> : <Download size={13} />}
                {downloading && downloadProgress
                  ? `Building ${downloadProgress.done}/${downloadProgress.total}…`
                  : `Download ${selectedIds.size > 0 ? selectedIds.size : eligible.length} PDF${(selectedIds.size > 0 ? selectedIds.size : eligible.length) === 1 ? "" : "s"} (zip)`}
              </button>
              <button onClick={handleQueue} disabled={queuing || selectedIds.size === 0} style={btn(queuing || selectedIds.size === 0, "primary")}>
                {queuing ? <Loader2 size={13} className="ss-spin" /> : <Send size={13} />}
                Queue {selectedIds.size > 0 ? `${selectedIds.size} ` : ""}to send
              </button>
            </div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table table-dark mb-0" style={{ background: "transparent" }}>
              <thead>
                <tr>
                  <th style={{ width: "36px" }}></th>
                  <th>Investor</th>
                  <th>Client Code</th>
                  <th>Fund / Class</th>
                  <th style={{ textAlign: "right" }}>Closing Balance</th>
                  <th>Last Statement</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {eligible.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ padding: "32px 16px", textAlign: "center", color: "var(--color-text-tertiary)" }}>
                      No investors found for this period/fund/class combination.
                    </td>
                  </tr>
                ) : (
                  eligible.map((inv) => {
                    const disabled = inv.email_status === "no_email";
                    return (
                      <tr key={inv.id} style={{ opacity: disabled ? 0.5 : 1 }}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedIds.has(inv.id)}
                            onChange={() => toggleOne(inv.id)}
                            disabled={disabled}
                          />
                        </td>
                        <td style={{ fontSize: "12px" }}>{inv.investor_name}</td>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-secondary)" }}>
                          {inv.internal_client_code}
                        </td>
                        <td style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
                          {inv.fund_name} <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px" }}>({inv.class_code})</span>
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
                          {inv.currency} {inv.closing_balance.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                        </td>
                        <td style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                          {inv.last_statement_date ? new Date(inv.last_statement_date).toLocaleDateString("en-GB") : "—"}
                        </td>
                        <td><EmailStatusBadge status={inv.email_status} /></td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <style>{`
        .ss-spin { animation: ss-spin-kf 0.8s linear infinite; }
        @keyframes ss-spin-kf { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
