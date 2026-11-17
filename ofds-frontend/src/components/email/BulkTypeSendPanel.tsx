import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Eye, FileText, Loader2, RotateCcw, Search, Send, X } from "lucide-react";
import { batchService } from "@/services/batchService";
import { emailService, type BulkKind, type BulkPreview, type BulkPreviewRow, type BulkSample, type BulkSelection } from "@/services/emailService";
import type { Batch, FundSummaryItem } from "@/lib/types";
import SendConfirmModal from "./SendConfirmModal";
import { btn, fieldLabel, selectStyle } from "./emailStyles";

// Bulk send of ONE statement type (deposit / transfer / deployment / withdrawal /
// oversubscription) for a fund and/or batch:
//   pick type + fund/batch -> Preview (counts + who) -> Send N -> confirm -> progress.
// The send is scoped to exactly the previewed list; the server re-checks the count and
// refuses if it changed, and sends nothing outside this selection.

export const KIND_LABEL: Record<BulkKind, string> = {
  deposit: "Deposit confirmation",
  transfer: "Transfer confirmation",
  deployment: "Deployment confirmation",
  withdrawal: "Withdrawal notice",
  oversubscription: "Oversubscription / refund notice",
};

const STATE_META: Record<BulkPreviewRow["state"], { label: string; color: string }> = {
  none: { label: "Ready", color: "rgb(74,222,128)" },
  pending: { label: "Waiting in Inbox", color: "rgb(251,191,36)" },
  suppressed: { label: "Suppressed earlier", color: "rgb(248,113,113)" },
  failed: { label: "Failed earlier", color: "rgb(248,113,113)" },
  queued: { label: "Already queued", color: "rgb(96,165,250)" },
  sending: { label: "Sending", color: "rgb(96,165,250)" },
  sent: { label: "Already sent", color: "var(--color-text-tertiary)" },
  no_email: { label: "No email address", color: "rgb(251,191,36)" },
};

const POLL_MS = 4000;

interface Props {
  kind: BulkKind;
  funds: FundSummaryItem[];
}

export default function BulkTypeSendPanel({ kind, funds }: Props) {
  const [fundId, setFundId] = useState("all");
  const [batchId, setBatchId] = useState("all");
  const [includeSent, setIncludeSent] = useState(false);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [preview, setPreview] = useState<BulkPreview | null>(null);
  const [previewSel, setPreviewSel] = useState<BulkSelection | null>(null);
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [rate, setRate] = useState<{ batch_size: number; interval_minutes: number } | null>(null);
  const [progress, setProgress] = useState<{ ids: number[]; counts: Record<string, number> } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Preview of one investor's actual email + attached statement (nothing is sent).
  const [view, setView] = useState<{ row: BulkPreviewRow; tab: "email" | "pdf"; sample?: BulkSample; pdfUrl?: string; error?: string; busy: boolean } | null>(null);
  const [resendRow, setResendRow] = useState<BulkPreviewRow | null>(null);

  useEffect(() => {
    batchService.getAll().then(setBatches).catch(() => {});
    emailService.getQueueStatus().then((r) => r.data && setRate({ batch_size: r.data.batch_size, interval_minutes: r.data.interval_minutes })).catch(() => {});
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // A different type/fund/batch is a different send - never show or act on an old preview.
  useEffect(() => { setPreview(null); setPreviewSel(null); }, [kind, fundId, batchId, includeSent]);

  const fundName = funds.find((f) => String(f.id) === fundId)?.fund_name;
  const batchOptions = useMemo(
    () => (fundId === "all" ? batches : batches.filter((b) => (b.funds ?? []).some((f) => f.fund_name === fundName))),
    [batches, fundId, fundName]
  );
  useEffect(() => {
    if (batchId !== "all" && !batchOptions.some((b) => String(b.id) === batchId)) setBatchId("all");
  }, [batchOptions, batchId]);

  const selection = (): BulkSelection => ({
    kind,
    fundId: fundId === "all" ? undefined : Number(fundId),
    batchId: batchId === "all" ? undefined : Number(batchId),
    includeSent,
  });
  const nothingChosen = fundId === "all" && batchId === "all";

  const runPreview = useCallback(async () => {
    setLoading(true);
    try {
      const sel = selection();
      setPreview(await emailService.bulkSendPreview(sel));
      setPreviewSel(sel);
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to load the list");
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, fundId, batchId, includeSent]);

  const rowSelection = (r: BulkPreviewRow): BulkSelection => ({ ...(previewSel ?? selection()), includeSent: true, clientCode: r.client_code });

  const closeView = () => {
    setView((v) => { if (v?.pdfUrl) URL.revokeObjectURL(v.pdfUrl); return null; });
  };
  const openView = async (row: BulkPreviewRow, tab: "email" | "pdf") => {
    setView((v) => { if (v?.pdfUrl) URL.revokeObjectURL(v.pdfUrl); return { row, tab, busy: true }; });
    const sel = { ...(previewSel ?? selection()), clientCode: row.client_code };
    try {
      const [sample, pdfUrl] = await Promise.all([
        emailService.bulkSample(sel, row.client_code),
        emailService.bulkSamplePdf(sel, row.client_code).then((b) => URL.createObjectURL(b)).catch(() => undefined),
      ]);
      setView({ row, tab, sample, pdfUrl, busy: false });
    } catch (err: any) {
      setView({ row, tab, busy: false, error: err?.response?.data?.message || "Could not load the preview" });
    }
  };

  // Send again to ONE investor who already got this email.
  const confirmResend = async () => {
    if (!resendRow) return;
    setSending(true);
    try {
      const res = await emailService.bulkSend(rowSelection(resendRow), 1);
      setResendRow(null);
      if (res.email_ids.length) {
        toast.success(`Queued again for ${resendRow.name} - sending in the background`);
        startPolling(res.email_ids);
      } else {
        toast.info("Nothing to send");
      }
      await runPreview();
    } catch (err: any) {
      setResendRow(null);
      toast.error(err?.response?.data?.message || "Failed to queue the email");
    } finally {
      setSending(false);
    }
  };

  const willSendRows = useMemo(
    () => (preview?.rows ?? []).filter((r) => ["none", "pending", "suppressed", "failed"].includes(r.state) || (includeSent && r.state === "sent")),
    [preview, includeSent]
  );

  const startPolling = (ids: number[]) => {
    if (pollRef.current) clearInterval(pollRef.current);
    const tick = async () => {
      try {
        const res = await emailService.statusCounts(ids);
        setProgress({ ids, counts: res.counts });
        if ((res.counts.Queued ?? 0) + (res.counts.Sending ?? 0) === 0 && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch {
        /* keep polling; a blip is not fatal */
      }
    };
    tick();
    pollRef.current = setInterval(tick, POLL_MS);
  };

  const confirmSend = async () => {
    if (!preview || !previewSel) return;
    setSending(true);
    try {
      const res = await emailService.bulkSend(previewSel, preview.counts.will_send);
      setConfirmOpen(false);
      if (res.email_ids.length === 0) {
        toast.info("Nothing to send");
      } else {
        toast.success(`${res.email_ids.length} email${res.email_ids.length === 1 ? "" : "s"} queued — sending in the background`);
        startPolling(res.email_ids);
      }
      await runPreview();
    } catch (err: any) {
      setConfirmOpen(false);
      toast.error(err?.response?.data?.message || "Failed to queue emails");
      await runPreview();
    } finally {
      setSending(false);
    }
  };

  const c = progress?.counts ?? {};
  const total = progress?.ids.length ?? 0;
  const sentN = c.Confirmed ?? 0;
  const failedN = c.Failed ?? 0;
  const remaining = (c.Queued ?? 0) + (c.Sending ?? 0);
  const pct = total > 0 ? Math.round(((sentN + failedN) / total) * 100) : 0;

  return (
    <div>
      <div className="ofds-glass" style={{ padding: "16px 20px", marginBottom: "16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr) auto", gap: "12px", alignItems: "end" }}>
          <div>
            <label style={fieldLabel}>FUND</label>
            <select value={fundId} onChange={(e) => setFundId(e.target.value)} style={selectStyle} aria-label="Fund">
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
            <label style={fieldLabel}>BATCH</label>
            <select value={batchId} onChange={(e) => setBatchId(e.target.value)} style={selectStyle} aria-label="Batch">
              <option value="all">All batches</option>
              {batchOptions.map((b) => (
                <option key={b.id} value={String(b.id)}>{b.batch_name}</option>
              ))}
            </select>
          </div>
          <button onClick={runPreview} disabled={loading || nothingChosen} style={btn(loading || nothingChosen, "primary")}>
            {loading ? <Loader2 size={13} className="ss-spin" /> : <Search size={13} />}
            Preview list
          </button>
        </div>
        <div style={{ marginTop: "10px", display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap" }}>
          <label style={{ fontSize: "11px", color: "var(--color-text-secondary)", display: "inline-flex", gap: "6px", alignItems: "center", cursor: "pointer" }}>
            <input type="checkbox" checked={includeSent} onChange={(e) => setIncludeSent(e.target.checked)} />
            Also send again to investors who already received this email
          </label>
          {nothingChosen && <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>Choose a fund or a batch to preview.</span>}
        </div>
      </div>

      {progress && (
        <div className="ofds-glass" style={{ padding: "14px 20px", marginBottom: "16px" }} aria-label="Send progress">
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "var(--color-text-secondary)", marginBottom: "8px" }}>
            <span>
              <strong style={{ color: "#fff" }}>{sentN}</strong> of {total} sent
              {failedN > 0 && <span style={{ color: "rgb(248,113,113)" }}> · {failedN} failed</span>}
              {remaining > 0 && <span> · {remaining} waiting to go out</span>}
            </span>
            <span>{remaining === 0 ? "Done" : `${pct}%`}</span>
          </div>
          <div style={{ height: "6px", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
            <div style={{ width: `${pct}%`, height: "100%", background: failedN > 0 ? "rgb(251,191,36)" : "rgb(34,197,94)", transition: "width .4s" }} />
          </div>
          {failedN > 0 && remaining === 0 && (
            <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "8px" }}>
              Failed emails stay in the Processed tab, where you can retry them one by one.
            </div>
          )}
        </div>
      )}

      {preview && preview.counts.will_send === 0 && preview.counts.already_sent > 0 && !includeSent && (
        <div className="ofds-glass" style={{ padding: "12px 20px", marginBottom: "16px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
            All {preview.counts.already_sent} investors already received this email. Send it again to everyone, or use "Send again" on a single row.
          </span>
          <button onClick={() => setIncludeSent(true)} style={btn(false, "primary")}>
            <RotateCcw size={13} /> Send again to all {preview.counts.already_sent}
          </button>
        </div>
      )}

      {preview && (
        <div className="ofds-glass" style={{ overflow: "hidden" }}>
          <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
            <div style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
              <strong style={{ color: "#fff" }}>{preview.label}</strong> · {preview.counts.total} investor{preview.counts.total === 1 ? "" : "s"}
              {" · "}<span style={{ color: "rgb(74,222,128)" }}>{preview.counts.will_send} will be sent</span>
              {preview.counts.already_sent > 0 && !includeSent && <> · {preview.counts.already_sent} already sent (skipped)</>}
              {preview.counts.in_progress > 0 && <> · {preview.counts.in_progress} already queued (skipped)</>}
              {preview.counts.no_email > 0 && <> · {preview.counts.no_email} without email (skipped)</>}
            </div>
            <button onClick={() => setConfirmOpen(true)} disabled={sending || preview.counts.will_send === 0} style={btn(sending || preview.counts.will_send === 0, "primary")}>
              <Send size={13} /> Send {preview.counts.will_send} email{preview.counts.will_send === 1 ? "" : "s"}…
            </button>
          </div>
          <div style={{ overflowX: "auto", maxHeight: "480px", overflowY: "auto" }}>
            <table className="table table-dark mb-0" style={{ background: "transparent" }}>
              <thead>
                <tr>
                  <th>Investor</th>
                  <th>Client Code</th>
                  <th>Fund</th>
                  <th>Batch</th>
                  <th style={{ textAlign: "right" }}>Amount</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} style={{ padding: "32px 16px", textAlign: "center", color: "var(--color-text-tertiary)" }}>
                      No investors match. {kind === "transfer" && "Only transferred batches are included. "}
                      {kind === "deployment" && "Only deployed batches are included."}
                    </td>
                  </tr>
                ) : (
                  preview.rows.slice(0, 500).map((r, i) => {
                    const m = STATE_META[r.state];
                    return (
                      <tr key={`${r.client_code}-${i}`} style={{ opacity: r.state === "no_email" ? 0.5 : 1 }}>
                        <td style={{ fontSize: "12px" }}>{r.name}<div style={{ fontSize: "10px", color: "var(--color-text-tertiary)" }}>{r.email || "—"}</div></td>
                        <td style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-secondary)" }}>{r.client_code}</td>
                        <td style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>{r.fund_name ?? "—"}</td>
                        <td style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>{r.batch_name ?? "—"}</td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>
                          {r.amount != null ? `${r.currency} ${r.amount.toLocaleString("en-US", { maximumFractionDigits: 2 })}` : "—"}
                        </td>
                        <td style={{ fontSize: "11px", fontWeight: 600, color: m.color }}>{m.label}</td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          <button onClick={() => openView(r, "email")} title="Preview the email" aria-label={`Preview email for ${r.name}`} style={{ ...btn(false, "ghost"), padding: "4px 8px", marginRight: 4 }}>
                            <Eye size={12} /> Email
                          </button>
                          {r.email_type !== "WITHDRAWAL_RECEIVED" && r.email_type !== "WITHDRAWAL_APPROVED" && (
                            <button onClick={() => openView(r, "pdf")} title="Preview the attached statement" aria-label={`Preview statement for ${r.name}`} style={{ ...btn(false, "ghost"), padding: "4px 8px", marginRight: 4 }}>
                              <FileText size={12} /> Statement
                            </button>
                          )}
                          {r.state === "sent" && (
                            <button onClick={() => setResendRow(r)} title="Send this email to this investor again" aria-label={`Send again to ${r.name}`} style={{ ...btn(sending, "ghost"), padding: "4px 8px" }}>
                              <RotateCcw size={12} /> Send again
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
            {preview.rows.length > 500 && (
              <div style={{ padding: "8px 16px", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                Showing the first 500 of {preview.rows.length}. All {preview.counts.will_send} eligible emails will be sent.
              </div>
            )}
          </div>
        </div>
      )}

      {view && (
        <div role="dialog" aria-label="Email preview" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }} onClick={closeView}>
          <div className="ofds-glass" style={{ width: "min(900px, 100%)", height: "min(85vh, 800px)", display: "flex", flexDirection: "column", background: "var(--color-bg-elevated, #0f1530)" }} onClick={(e) => e.stopPropagation()}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.08)", display: "flex", alignItems: "center", gap: 12 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 600 }}>{view.row.name}</div>
                <div style={{ fontSize: 11, color: "var(--color-text-tertiary)" }}>Preview only - nothing is sent</div>
              </div>
              <button onClick={() => setView({ ...view, tab: "email" })} style={btn(false, view.tab === "email" ? "primary" : "ghost")}><Eye size={12} /> Email</button>
              <button onClick={() => setView({ ...view, tab: "pdf" })} disabled={!view.sample?.attachment_name} style={btn(!view.sample?.attachment_name, view.tab === "pdf" ? "primary" : "ghost")}><FileText size={12} /> Attached statement</button>
              <button onClick={closeView} aria-label="Close preview" style={{ ...btn(false, "ghost"), padding: "6px" }}><X size={14} /></button>
            </div>
            <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
              {view.busy && <div style={{ padding: 32, textAlign: "center" }}><Loader2 size={18} className="ss-spin" /> Loading...</div>}
              {!view.busy && view.error && <div style={{ padding: 32, color: "rgb(248,113,113)" }}>{view.error}</div>}
              {!view.busy && view.sample && view.tab === "email" && (
                <div>
                  <div style={{ padding: "12px 16px", fontSize: 12, lineHeight: 1.7, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <div><span style={{ color: "var(--color-text-tertiary)" }}>To:</span> {view.sample.name} &lt;{view.sample.to}&gt;</div>
                    <div><span style={{ color: "var(--color-text-tertiary)" }}>Subject:</span> {view.sample.subject}</div>
                    <div><span style={{ color: "var(--color-text-tertiary)" }}>Attachment:</span> {view.sample.attachment_name ?? "none"}</div>
                  </div>
                  <iframe title="Email body" sandbox="" srcDoc={view.sample.html} style={{ width: "100%", height: 520, border: 0, background: "#fff" }} />
                </div>
              )}
              {!view.busy && view.sample && view.tab === "pdf" && (
                view.pdfUrl
                  ? <iframe title="Attached statement" src={view.pdfUrl} style={{ width: "100%", height: "100%", border: 0, background: "#fff" }} />
                  : <div style={{ padding: 32, color: "var(--color-text-tertiary)" }}>No statement could be generated for this investor.</div>
              )}
            </div>
          </div>
        </div>
      )}

      <SendConfirmModal
        open={resendRow != null}
        title={`Send again to ${resendRow?.name ?? ""}?`}
        description="This investor already received this email. A fresh copy will be queued for just them."
        items={resendRow ? [{ primary: resendRow.name, secondary: resendRow.email, note: "resend" }] : []}
        count={1}
        rate={rate}
        busy={sending}
        onConfirm={confirmResend}
        onCancel={() => setResendRow(null)}
      />

      <SendConfirmModal
        open={confirmOpen}
        title={`Send ${preview?.counts.will_send ?? 0} ${KIND_LABEL[kind].toLowerCase()} email${preview?.counts.will_send === 1 ? "" : "s"}?`}
        description={`${[fundName, batchOptions.find((b) => String(b.id) === batchId)?.batch_name].filter(Boolean).join(" · ") || "Selected fund/batch"} — only the investors listed below.`}
        items={willSendRows.map((r) => ({ primary: r.name, secondary: r.email, note: r.state === "sent" ? "resend" : r.batch_name ?? undefined }))}
        count={preview?.counts.will_send ?? 0}
        rate={rate}
        busy={sending}
        onConfirm={confirmSend}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
