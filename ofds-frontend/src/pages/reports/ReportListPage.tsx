/**
 * ReportListPage — Generate & Send monthly investor statements.
 *
 * Production-faithful implementation:
 *  • "Generate & Send" panel: period / fund / share-class selectors,
 *    load-investors button, investor table with checkboxes, status badges,
 *    individual PDF download, "Download all as ZIP", "Send to N selected"
 *  • "Recent Report Runs" panel: shows actual report runs when available,
 *    falls back to NAV valuation run history when none exist yet.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { useReport } from "@/context/ReportContext";
import { reportService } from "@/services/reportService";
import { fundService } from "@/services/fundService";
import { valuationService } from "@/services/valuationService";
import { ROUTES } from "@/lib/constants";
import type { EligibleInvestor, NavValuationRunItem, FundSummaryItem } from "@/lib/types";

// ── Style helpers ─────────────────────────────────────────────────────────────

const glass: React.CSSProperties = {
  background: "rgba(16,24,45,0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "12px",
};

const inputBase: React.CSSProperties = {
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  color: "#FFFFFF",
  fontFamily: "var(--font-sans)",
  fontSize: "12px",
  padding: "8px 10px",
  outline: "none",
};

const selectStyle: React.CSSProperties = {
  ...inputBase,
  cursor: "pointer",
  appearance: "none",
  paddingRight: "28px",
  background: `rgba(0,0,0,0.25) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%2394A3B8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat right 8px center`,
};

// ── Utility helpers ───────────────────────────────────────────────────────────

function getDefaultPeriod(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return d.toISOString().slice(0, 7);
}

function periodLabel(period: string): string {
  const [year, month] = period.split("-");
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${months[Number(month) - 1]} ${year}`;
}

function periodEndDate(period: string): string {
  const [year, month] = period.split("-").map(Number);
  if (!year || !month) return new Date().toISOString().slice(0, 10);
  return new Date(year, month, 0).toISOString().slice(0, 10);
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return (
    d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) +
    " " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
  );
}

function initials(name: string): string {
  return name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase();
}

// ── Sub-components ────────────────────────────────────────────────────────────

function EmailStatusBadge({ status }: { status: EligibleInvestor["email_status"] }) {
  const cfg = {
    ready: { label: "Ready", bg: "rgba(16,185,129,0.12)", color: "#10B981", dot: "#10B981" },
    no_email: { label: "Missing email", bg: "rgba(245,158,11,0.12)", color: "#F59E0B", dot: "#F59E0B" },
    already_sent: { label: "Already sent", bg: "rgba(96,165,250,0.12)", color: "#60A5FA", dot: "#60A5FA" },
  }[status] ?? { label: "Ready", bg: "rgba(16,185,129,0.12)", color: "#10B981", dot: "#10B981" };

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "2px 8px", borderRadius: "100px", fontSize: "10px", fontWeight: 600, background: cfg.bg, color: cfg.color }}>
      <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: cfg.dot }} />
      {cfg.label}
    </span>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { label: string; bg: string; color: string }> = {
    sent: { label: "Sent", bg: "rgba(16,185,129,0.12)", color: "#10B981" },
    partial: { label: "Partial", bg: "rgba(245,158,11,0.12)", color: "#F59E0B" },
    failed: { label: "Failed", bg: "rgba(239,68,68,0.12)", color: "#EF4444" },
    pending: { label: "Pending", bg: "rgba(59,130,246,0.12)", color: "#60A5FA" },
  };
  const s = cfg[(status ?? "").toLowerCase()] ?? cfg["pending"]!;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "2px 8px", borderRadius: "100px", fontSize: "10px", fontWeight: 600, background: s!.bg, color: s!.color }}>
      <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: s!.color }} />
      {s!.label}
    </span>
  );
}


function CurrencyBadge({ currency }: { currency: string }) {
  const isKES = currency === "KES";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", padding: "1px 6px", borderRadius: "4px",
      fontSize: "9px", fontWeight: 700, letterSpacing: "0.06em",
      fontFamily: "var(--font-mono)",
      background: isKES ? "var(--color-kes-bg, rgba(245,158,11,0.12))" : "var(--color-usd-bg, rgba(59,130,246,0.12))",
      color: isKES ? "var(--color-kes, #F59E0B)" : "var(--color-usd, #60A5FA)",
      border: isKES ? "1px solid var(--color-kes-border, rgba(245,158,11,0.25))" : "1px solid var(--color-usd-border, rgba(59,130,246,0.25))",
    }}>
      {currency}
    </span>
  );
}

function Spinner({ size = 20 }: { size?: number }) {
  return (
    <div style={{
      width: size, height: size,
      border: `2px solid rgba(255,255,255,0.07)`,
      borderTopColor: "#3B82F6",
      borderRadius: "50%",
      animation: "spin 0.8s linear infinite",
    }} />
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function ReportListPage() {
  const navigate = useNavigate();
  const {
    eligibleInvestors,
    loadingEligibleInvestors,
    fetchEligibleInvestors,
    reportRuns,
    loadingReportRuns,
    fetchReportRuns,
  } = useReport();

  // Filter state
  const [period, setPeriod] = useState(getDefaultPeriod());
  const [fundId, setFundId] = useState<string>("all");
  const [shareClassId, setShareClassId] = useState<string>("all");

  // UI state
  const [showInvestors, setShowInvestors] = useState(false);

  // Fund options from /funds/summary
  const [funds, setFunds] = useState<FundSummaryItem[]>([]);

  // NAV runs fallback (shown in "Recent Report Runs" when reportRuns is empty)
  const [navRuns, setNavRuns] = useState<NavValuationRunItem[]>([]);
  const [loadingNavRuns, setLoadingNavRuns] = useState(false);

  // ── Load fund summary on mount ──────────────────────────────────────────────
  useEffect(() => {
    fundService.getSummary()
      .then(s => {
        if (s) setFunds(s.funds);
      })
      .catch(() => {});
  }, []);

  // ── Load recent report runs on mount ───────────────────────────────────────
  useEffect(() => {
    fetchReportRuns();
  }, [fetchReportRuns]);

  // ── Load NAV runs as fallback for "Recent Report Runs" ─────────────────────
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        setLoadingNavRuns(true);
        const runs = await valuationService.listNavRuns(50);
        if (!alive) return;
        setNavRuns(runs);
      } catch {
        if (!alive) return;
        setNavRuns([]);
      } finally {
        if (alive) setLoadingNavRuns(false);
      }
    })();
    return () => { alive = false; };
  }, []);

  // ── Available classes based on fund selection ──────────────────────────────
  const availableClasses = useMemo(() => {
    if (fundId === "all") return funds.flatMap(f => f.classes ?? []);
    const found = funds.find(f => String(f.id) === fundId);
    return found ? (found.classes ?? []) : [];
  }, [funds, fundId]);

  // ── Load investors ──────────────────────────────────────────────────────────
  const handleLoadInvestors = useCallback(async () => {
    setShowInvestors(false);
    try {
      const params: { period: string; fund_id?: number; share_class_id?: number } = { period };
      if (fundId !== "all") params.fund_id = Number(fundId);
      if (shareClassId !== "all") params.share_class_id = Number(shareClassId);
      await fetchEligibleInvestors(params);
      setShowInvestors(true);
    } catch {
      toast.error("Failed to load eligible investors");
    }
  }, [period, fundId, shareClassId, fetchEligibleInvestors]);

  // ── Summary counts ─────────────────────────────────────────────────────────
  const readyCount = eligibleInvestors.filter(i => i.email_status === "ready").length;
  const noEmailCount = eligibleInvestors.filter(i => i.email_status === "no_email").length;
  const alreadySentCount = eligibleInvestors.filter(i => i.email_status === "already_sent").length;

  // ── Individual PDF download ────────────────────────────────────────────────
  const handleDownloadPdf = useCallback(async (clientCode: string) => {
    try {
      const asOf = periodEndDate(period);
      await reportService.downloadInvestorStatementByClientCode(clientCode, asOf, { periodOnly: true });
      toast.success("Statement download started.");
    } catch {
      toast.error("Failed to download investor statement PDF.");
    }
  }, [period]);

  // ── Download all as ZIP ────────────────────────────────────────────────────
  const handleDownloadZip = useCallback(async () => {
    if (eligibleInvestors.length === 0) return;
    try {
      toast.info("Preparing ZIP — this may take a moment…");
      const JSZip = (await import("jszip")).default;
      const zip = new JSZip();
      const asOf = periodEndDate(period);

      await Promise.allSettled(
        eligibleInvestors.map(async (inv) => {
          try {
            const api = (await import("@/services/api")).default;
            const { API } = await import("@/lib/constants");
            const query = new URLSearchParams({ as_of: asOf, period_only: "1" });
            const res = await api.get(
              `${API.INVESTOR_STATEMENT_PDF_CLIENT(inv.internal_client_code)}?${query}`,
              { responseType: "blob" }
            );
            zip.file(`statement-${inv.internal_client_code}-${asOf}.pdf`, res.data);
          } catch (e) {
            console.warn(`Skipped ${inv.internal_client_code}:`, e);
          }
        })
      );

      const blob = await zip.generateAsync({ type: "blob" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `statements-${period}.zip`;
      document.body.appendChild(a);
      a.click();
      a.parentNode?.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("ZIP downloaded.");
    } catch {
      toast.error("Failed to generate ZIP.");
    }
  }, [eligibleInvestors, period]);

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ position: "relative", zIndex: 1, padding: "24px 32px 48px", maxWidth: "1200px", margin: "0 auto", fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)", color: "#FFFFFF", display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Page header */}
      <div>
        <h1 style={{ fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>Reports</h1>
        <p style={{ fontSize: "12px", color: "#94A3B8", marginTop: "4px" }}>Generate and send monthly statements to investors.</p>
      </div>

      {/* ── Generate & Preview Panel ─────────────────────────────────────────── */}
      <div style={{ ...glass, padding: "20px 24px", display: "flex", flexDirection: "column", gap: "18px" }}>
        <div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#FFFFFF", letterSpacing: "-0.01em" }}>Preview &amp; Download Statements</div>
          <p style={{ fontSize: "11px", color: "#64748B", margin: "4px 0 0" }}>
            To email statements to investors, use the <strong style={{ color: "#94A3B8" }}>Send Statements</strong> tab on the Email page.
          </p>
        </div>

        {/* Filters row */}
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "flex-end" }}>
          {/* Period */}
          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            <label style={{ fontSize: "10px", color: "#475569", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Period</label>
            <input
              id="report-period"
              type="month"
              value={period}
              onChange={e => { setPeriod(e.target.value); setShowInvestors(false); }}
              style={{ ...inputBase, fontFamily: "var(--font-mono)", fontSize: "12px", minWidth: "140px" }}
            />
          </div>

          {/* Fund */}
          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            <label style={{ fontSize: "10px", color: "#475569", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Fund</label>
            <select
              id="report-fund"
              value={fundId}
              onChange={e => { setFundId(e.target.value); setShareClassId("all"); setShowInvestors(false); }}
              style={{ ...selectStyle, minWidth: "140px" }}
            >
              <option value="all">All funds</option>
              {funds.map(f => (
                <option key={f.id} value={String(f.id)}>{f.fund_name}</option>
              ))}
            </select>
          </div>

          {/* Share class */}
          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            <label style={{ fontSize: "10px", color: "#475569", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em" }}>Share Class</label>
            <select
              id="report-class"
              value={shareClassId}
              onChange={e => { setShareClassId(e.target.value); setShowInvestors(false); }}
              style={{ ...selectStyle, minWidth: "140px" }}
            >
              <option value="all">All classes</option>
              {availableClasses.map(c => (
                <option key={c.id} value={String(c.id)}>{c.class_code}</option>
              ))}
            </select>
          </div>

          {/* Load investors button */}
          <button
            id="report-load-investors"
            onClick={handleLoadInvestors}
            disabled={loadingEligibleInvestors}
            style={{
              display: "inline-flex", alignItems: "center", gap: "6px", padding: "9px 16px",
              borderRadius: "8px", background: loadingEligibleInvestors ? "rgba(26,69,255,0.5)" : "#1A45FF",
              color: "#fff", border: "none", fontFamily: "var(--font-sans)", fontSize: "12px",
              fontWeight: 500, cursor: loadingEligibleInvestors ? "not-allowed" : "pointer",
              boxShadow: "0 0 16px rgba(26,69,255,0.3)", transition: "all 0.15s", alignSelf: "flex-end",
            }}
          >
            {loadingEligibleInvestors ? (
              <><Spinner size={12} /> Loading…</>
            ) : (
              <>
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                  <path d="M1 6a5 5 0 1 0 10 0A5 5 0 0 0 1 6z" stroke="currentColor" strokeWidth="1.3"/>
                  <path d="M6 3v3l2 1" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
                Load investors
              </>
            )}
          </button>
        </div>

        {/* Investor table section */}
        {showInvestors && (
          <>
            {/* Summary counters */}
            <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
              {[
                { label: "Ready", count: readyCount, color: "#10B981" },
                { label: "Missing email", count: noEmailCount, color: "#F59E0B" },
                { label: "Already sent", count: alreadySentCount, color: "#60A5FA" },
              ].map(({ label, count, color }) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "5px 10px", borderRadius: "8px", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", fontSize: "11px", color: "#94A3B8" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color, fontSize: "12px" }}>{count}</span>
                  {label}
                </div>
              ))}
            </div>

            {/* Investor table */}
            {eligibleInvestors.length === 0 ? (
              <div style={{ textAlign: "center", padding: "28px", fontSize: "13px", color: "#475569" }}>
                No investors found for this period / filter combination.
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", overflow: "hidden", border: "1px solid rgba(255,255,255,0.07)" }}>
                  <thead style={{ background: "rgba(255,255,255,0.03)" }}>
                    <tr>
                      {["Investor", "Client Code", "Fund / Class", "Currency", "Last Statement", "Email", "Status", "PDF"].map((h, n) => (
                        <th key={h} style={{ textAlign: n >= 3 ? "right" : "left", padding: "9px 12px", fontSize: "9px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#475569", borderBottom: "1px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {eligibleInvestors.map(inv => {
                      return (
                        <tr
                          key={inv.id}
                          style={{ borderBottom: "1px solid rgba(255,255,255,0.03)", transition: "background 0.12s" }}
                          onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = "rgba(255,255,255,0.02)"; }}
                          onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = "transparent"; }}
                        >
                          <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "9px" }}>
                              <div style={{ width: "28px", height: "28px", borderRadius: "50%", background: "rgba(59,130,246,0.18)", border: "1px solid rgba(59,130,246,0.3)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "9px", fontWeight: 700, color: "#60A5FA", flexShrink: 0, fontFamily: "var(--font-mono)" }}>
                                {initials(inv.investor_name)}
                              </div>
                              <span style={{ fontWeight: 500, color: "#FFFFFF", fontSize: "12px" }}>{inv.investor_name}</span>
                            </div>
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "#3B82F6", letterSpacing: "0.03em" }}>{inv.internal_client_code}</span>
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                            <span style={{ fontSize: "11px", color: "#94A3B8" }}>{inv.fund_name}</span>
                            <span style={{ margin: "0 4px", color: "#475569" }}>/</span>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "#FFFFFF" }}>{inv.class_code}</span>
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                            <CurrencyBadge currency={inv.currency} />
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: inv.last_statement_date ? "#94A3B8" : "#475569" }}>
                              {inv.last_statement_date
                                ? new Date(inv.last_statement_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase()
                                : "Never"}
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: inv.investor_email ? "#94A3B8" : "#475569", fontStyle: inv.investor_email ? "normal" : "italic" }}>
                              {inv.investor_email ?? "—"}
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                            <EmailStatusBadge status={inv.email_status} />
                          </td>
                          <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                            <button
                              onClick={e => { e.stopPropagation(); handleDownloadPdf(inv.internal_client_code); }}
                              style={{ padding: "5px 10px", borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#94A3B8", fontSize: "11px", cursor: "pointer" }}
                            >
                              Download PDF
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Bottom action row */}
            <div style={{ display: "flex", gap: "10px", justifyContent: "flex-end", paddingTop: "6px", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
              <button
                onClick={handleDownloadZip}
                disabled={eligibleInvestors.length === 0}
                style={{ padding: "9px 16px", borderRadius: "8px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#94A3B8", fontFamily: "var(--font-sans)", fontSize: "12px", fontWeight: 500, cursor: eligibleInvestors.length === 0 ? "not-allowed" : "pointer", transition: "all 0.15s", opacity: eligibleInvestors.length === 0 ? 0.5 : 1 }}
                onMouseEnter={e => { if (eligibleInvestors.length > 0) { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(59,130,246,0.4)"; (e.currentTarget as HTMLButtonElement).style.color = "#FFFFFF"; } }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.1)"; (e.currentTarget as HTMLButtonElement).style.color = "#94A3B8"; }}
              >
                Download all as ZIP
              </button>
            </div>
          </>
        )}

        {/* Prompt when no investors loaded yet */}
        {!showInvestors && !loadingEligibleInvestors && (
          <div style={{ textAlign: "center", padding: "28px 0", fontSize: "12px", color: "#475569" }}>
            Select a period and click <strong style={{ color: "#94A3B8" }}>Load investors</strong> to see eligible recipients for {periodLabel(period)}.
          </div>
        )}
      </div>

      {/* ── Recent Report Runs Panel ──────────────────────────────────────── */}
      <div style={{ ...glass, padding: "20px 24px", display: "flex", flexDirection: "column", gap: "14px" }}>
        <div style={{ fontSize: "13px", fontWeight: 600, color: "#FFFFFF", letterSpacing: "-0.01em" }}>Recent Report Runs</div>

        {loadingReportRuns ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "28px" }}><Spinner /></div>
        ) : reportRuns.length > 0 ? (
          /* Actual report runs table */
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", overflow: "hidden", border: "1px solid rgba(255,255,255,0.07)" }}>
              <thead style={{ background: "rgba(255,255,255,0.03)" }}>
                <tr>
                  {["Date Sent", "Period", "Fund / Class", "Recipients", "Sent By", "Status", ""].map((h, n) => (
                    <th key={n} style={{ textAlign: (n >= 3 && n <= 4) ? "right" : "left", padding: "9px 12px", fontSize: "9px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#475569", borderBottom: "1px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {reportRuns.map(run => (
                  <tr
                    key={run.id}
                    style={{ borderBottom: "1px solid rgba(255,255,255,0.03)", transition: "background 0.12s" }}
                    onMouseEnter={e => (e.currentTarget as HTMLTableRowElement).style.background = "rgba(255,255,255,0.02)"}
                    onMouseLeave={e => (e.currentTarget as HTMLTableRowElement).style.background = "transparent"}
                  >
                    <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "#94A3B8" }}>{formatDateTime(run.sent_at)}</span>
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "#FFFFFF", fontWeight: 500 }}>{periodLabel(run.period)}</span>
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                      <span style={{ color: "#94A3B8", fontSize: "11px" }}>{run.fund_name ?? "—"}</span>
                      {run.class_code && <><span style={{ margin: "0 4px", color: "#475569" }}>/</span><span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "#FFFFFF" }}>{run.class_code}</span></>}
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "#FFFFFF", fontWeight: 500 }}>{run.recipient_count}</span>
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                      <span style={{ fontSize: "10px", color: "#475569", fontFamily: "var(--font-mono)" }}>{run.sent_by ?? "—"}</span>
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "middle" }}>
                      <RunStatusBadge status={run.status} />
                    </td>
                    <td style={{ padding: "10px 12px", verticalAlign: "middle", textAlign: "right" }}>
                      <button
                        onClick={() => navigate(ROUTES.REPORT_DETAIL(run.id))}
                        style={{ display: "inline-flex", alignItems: "center", gap: "4px", padding: "5px 10px", borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#94A3B8", fontFamily: "var(--font-sans)", fontSize: "11px", fontWeight: 500, cursor: "pointer", transition: "all 0.15s" }}
                        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(59,130,246,0.4)"; (e.currentTarget as HTMLButtonElement).style.color = "#FFFFFF"; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(255,255,255,0.1)"; (e.currentTarget as HTMLButtonElement).style.color = "#94A3B8"; }}
                      >
                        View details
                        <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3 2l4 3-4 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/></svg>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : loadingNavRuns ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "28px" }}><Spinner /></div>
        ) : navRuns.length === 0 ? (
          <div style={{ textAlign: "center", padding: "28px", fontSize: "13px", color: "#475569" }}>No report runs yet.</div>
        ) : (
          /* NAV valuation runs fallback table */
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", overflow: "hidden", border: "1px solid rgba(255,255,255,0.07)" }}>
              <thead style={{ background: "rgba(255,255,255,0.03)" }}>
                <tr>
                  {["Valuation Date", "Fund / Class", "Opening", "Profit", "Closing AUM", "Investors"].map((h, n) => (
                    <th key={h} style={{ textAlign: n >= 2 ? "right" : "left", padding: "9px 12px", fontSize: "9px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#475569", borderBottom: "1px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {navRuns.map(run => (
                  <tr key={`${run.share_class_id}-${run.valuation_date}`} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "#94A3B8" }}>
                        {new Date(run.valuation_date).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}
                      </span>
                    </td>
                    <td style={{ padding: "10px 12px" }}>
                      <span style={{ color: "#94A3B8", fontSize: "11px" }}>{run.fund_name}</span>
                      <span style={{ margin: "0 4px", color: "#475569" }}>/</span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "#FFFFFF" }}>{run.share_class_code}</span>
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: "var(--font-mono)", color: "#94A3B8" }}>
                      {run.opening_aum.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: "var(--font-mono)", color: run.profit >= 0 ? "#34D399" : "#F87171" }}>
                      {run.profit.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: "var(--font-mono)", color: "#FFFFFF", fontWeight: 500 }}>
                      {run.closing_aum.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: "var(--font-mono)", color: "#FFFFFF" }}>
                      {run.investors}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
