import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Download, FileText, Loader2, Send } from "lucide-react";
import { fundService } from "@/services/fundService";
import { reportService } from "@/services/reportService";
import { emailService } from "@/services/emailService";
import type { EligibleInvestor, FundSummaryItem } from "@/lib/types";

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

const inputStyle: React.CSSProperties = {
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  color: "var(--color-text-primary)",
  fontSize: "12px",
  padding: "8px 10px",
  outline: "none",
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
  appearance: "none",
  paddingRight: "28px",
  background: `rgba(0,0,0,0.25) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%2394A3B8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat right 8px center`,
};

const btn = (disabled: boolean, variant: "primary" | "ghost" = "ghost"): React.CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 14px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.6 : 1,
  border: variant === "primary" ? "none" : "1px solid rgba(255,255,255,0.1)",
  background: variant === "primary" ? "rgb(26, 69, 255)" : "rgba(255,255,255,0.05)",
  color: variant === "primary" ? "#fff" : "var(--color-text-secondary)",
});

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
  const [downloadProgress, setDownloadProgress] = useState<{ done: number; total: number } | null>(null);

  useEffect(() => {
    fundService.getSummary().then((s) => { if (s) setFunds(s.funds); }).catch(() => {});
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
        const { queued, skipped, not_found } = res.data ?? { queued: [], skipped: [], not_found: [] };
        toast.success(`Queued ${queued.length} statement email(s) for approval`);
        if (skipped.length > 0) {
          toast.info(`${skipped.length} skipped (already queued or pending)`);
        }
        if (not_found.length > 0) {
          toast.error(`${not_found.length} client code(s) not found`);
        }
        setSelectedIds(new Set());
      } else {
        toast.error(res.message || "Failed to queue statements");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to queue statements");
    } finally {
      setQueuing(false);
    }
  };

  return (
    <div>
      <p style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginBottom: "16px" }}>
        Filter investors by the valuation period + fund + share class you just committed, then queue each
        selected investor's overall statement email — their whole portfolio, not just this fund/class — for
        approval. Nothing sends immediately; queued items show up in the Inbox tab.
      </p>

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
              {funds.map((f) => (
                <option key={f.id} value={String(f.id)}>{f.fund_name}</option>
              ))}
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
                Queue {selectedIds.size > 0 ? `${selectedIds.size} ` : ""}for approval
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
