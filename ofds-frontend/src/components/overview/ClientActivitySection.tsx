import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Search, CircleUserRound, Download, FileSpreadsheet, X, CalendarDays } from "lucide-react";
import { investmentService } from "@/services/investmentService";
import { reportService } from "@/services/reportService";
import type { ClientActivityData, ClientActivityFilters, ClientActivityEventType, DailyActivitySummary } from "@/lib/types";

// ═══════════════════════════════════════════════════════════════════════════
// CLIENT ACTIVITY — embedded at the bottom of the Overview page.
//   1. Search one investor, filter their deposit/withdrawal/valuation history
//      by independent date ranges, and export the result.
//   2. Daily Activity — every deposit/withdrawal/valuation across ALL
//      investors on one date, downloadable as Excel/PDF.
// ═══════════════════════════════════════════════════════════════════════════

interface InvestorSearchRow {
  investor_name: string | null;
  internal_client_code: string;
  investor_email: string | null;
}

const CARD: React.CSSProperties = {
  background: "rgba(16,24,45,0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "16px",
  boxShadow: "0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
};

const SECTION_LABEL: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--color-text-tertiary)",
  marginBottom: "12px",
};

const dateInputStyle: React.CSSProperties = {
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  color: "var(--color-text-primary)",
  fontSize: "12px",
  padding: "6px 8px",
  outline: "none",
  colorScheme: "dark",
};

const exportBtnStyle = (disabled: boolean): React.CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 14px",
  borderRadius: "8px",
  background: "rgba(255,255,255,0.05)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "var(--color-text-secondary)",
  fontSize: "12px",
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.6 : 1,
});

const EVENT_TYPE_META: Record<ClientActivityEventType, { label: string; bg: string; color: string }> = {
  deposit: { label: "Deposit", bg: "rgba(59,130,246,0.12)", color: "#60A5FA" },
  withdrawal: { label: "Withdrawal", bg: "rgba(245,158,11,0.12)", color: "#F59E0B" },
  valuation: { label: "Valuation", bg: "rgba(245,208,11,0.12)", color: "#FCD34D" },
};

function EventTypeBadge({ type }: { type: ClientActivityEventType }) {
  const cfg = EVENT_TYPE_META[type];
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "10px",
        fontWeight: 600,
        letterSpacing: "0.04em",
        background: cfg.bg,
        color: cfg.color,
      }}
    >
      {cfg.label}
    </span>
  );
}

function fmtMoney(v: number | null | undefined, currency?: string | null): string {
  if (v == null) return "—";
  const prefix = currency === "KES" ? "KES " : currency === "USD" ? "$ " : "";
  return `${prefix}${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ClientActivitySection() {
  // ── Per-client search ──
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<InvestorSearchRow[]>([]);
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);

  const [selected, setSelected] = useState<InvestorSearchRow | null>(null);

  const [depositedFrom, setDepositedFrom] = useState("");
  const [depositedTo, setDepositedTo] = useState("");
  const [withdrawnFrom, setWithdrawnFrom] = useState("");
  const [withdrawnTo, setWithdrawnTo] = useState("");
  const [valuedFrom, setValuedFrom] = useState("");
  const [valuedTo, setValuedTo] = useState("");

  const [activity, setActivity] = useState<ClientActivityData | null>(null);
  const [loadingActivity, setLoadingActivity] = useState(false);
  const [exporting, setExporting] = useState<"excel" | "pdf" | null>(null);

  // ── All-investors activity export (date range) ──
  const [dailyFrom, setDailyFrom] = useState(todayIso());
  const [dailyTo, setDailyTo] = useState(todayIso());
  const [dailySummary, setDailySummary] = useState<DailyActivitySummary | null>(null);
  const [loadingDaily, setLoadingDaily] = useState(false);
  const [dailyExporting, setDailyExporting] = useState<"excel" | "pdf" | null>(null);

  const filters: ClientActivityFilters = useMemo(
    () => ({
      deposited_from: depositedFrom || undefined,
      deposited_to: depositedTo || undefined,
      withdrawn_from: withdrawnFrom || undefined,
      withdrawn_to: withdrawnTo || undefined,
      valued_from: valuedFrom || undefined,
      valued_to: valuedTo || undefined,
    }),
    [depositedFrom, depositedTo, withdrawnFrom, withdrawnTo, valuedFrom, valuedTo]
  );

  // Debounced client search (typeahead) — same pattern as the Investor Directory.
  useEffect(() => {
    const trimmed = search.trim();
    if (!trimmed || selected) {
      setResults([]);
      return;
    }
    let alive = true;
    const t = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await investmentService.getInvestorDirectory({ page: 1, per_page: 8, search: trimmed });
        if (!alive) return;
        setResults((res.data as InvestorSearchRow[]) || []);
        setShowResults(true);
      } catch {
        if (alive) setResults([]);
      } finally {
        if (alive) setSearching(false);
      }
    }, 300);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [search, selected]);

  const pickInvestor = (row: InvestorSearchRow) => {
    setSelected(row);
    setSearch("");
    setResults([]);
    setShowResults(false);
  };

  const clearSelection = () => {
    setSelected(null);
    setActivity(null);
    setDepositedFrom("");
    setDepositedTo("");
    setWithdrawnFrom("");
    setWithdrawnTo("");
    setValuedFrom("");
    setValuedTo("");
  };

  useEffect(() => {
    if (!selected) return;
    let alive = true;
    (async () => {
      setLoadingActivity(true);
      try {
        const data = await reportService.getClientActivity(selected.internal_client_code, filters);
        if (alive) setActivity(data);
      } catch {
        if (alive) toast.error("Failed to load client activity");
      } finally {
        if (alive) setLoadingActivity(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, filters]);

  const handleExport = async (format: "excel" | "pdf") => {
    if (!selected) return;
    setExporting(format);
    try {
      if (format === "excel") await reportService.downloadClientActivityExcel(selected.internal_client_code, filters);
      else await reportService.downloadClientActivityPdf(selected.internal_client_code, filters);
    } catch {
      toast.error(`Failed to export ${format === "excel" ? "Excel" : "PDF"}`);
    } finally {
      setExporting(null);
    }
  };

  // Summary loads whenever the picked date range changes (debounced).
  useEffect(() => {
    if (!dailyFrom || !dailyTo) return;
    let alive = true;
    const t = setTimeout(async () => {
      setLoadingDaily(true);
      try {
        const data = await reportService.getDailyActivitySummary(dailyFrom, dailyTo);
        if (alive) setDailySummary(data);
      } catch {
        if (alive) toast.error("Failed to load activity summary");
      } finally {
        if (alive) setLoadingDaily(false);
      }
    }, 300);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [dailyFrom, dailyTo]);

  const handleDailyExport = async (format: "excel" | "pdf") => {
    if (!dailyFrom || !dailyTo) return;
    setDailyExporting(format);
    try {
      if (format === "excel") await reportService.downloadDailyActivityExcel(dailyFrom, dailyTo);
      else await reportService.downloadDailyActivityPdf(dailyFrom, dailyTo);
    } catch {
      toast.error(`Failed to export ${format === "excel" ? "Excel" : "PDF"}`);
    } finally {
      setDailyExporting(null);
    }
  };

  const dailyTotalEvents = dailySummary
    ? dailySummary.counts.deposits + dailySummary.counts.withdrawals + dailySummary.counts.valuations
    : 0;

  return (
    <div style={{ marginTop: "22px" }}>
      <div style={{ marginBottom: "16px" }}>
        <h2 style={{ fontSize: "16px", fontWeight: 700, color: "var(--color-text-primary)", letterSpacing: "-0.01em", marginBottom: "4px" }}>
          Client Activity
        </h2>
        <p style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
          Search an investor to filter their deposits, withdrawals, and valuations by date — or pull everyone's activity for a date range.
        </p>
      </div>

      {/* ── Daily Activity — all investors, one date ── */}
      <div style={{ ...CARD, padding: "18px 22px", marginBottom: "16px" }}>
        <p style={SECTION_LABEL}>Activity — All Investors</p>
        <div style={{ display: "flex", alignItems: "center", gap: "16px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <CalendarDays size={14} style={{ color: "var(--color-text-tertiary)" }} />
            <input type="date" value={dailyFrom} onChange={(e) => setDailyFrom(e.target.value)} style={dateInputStyle} />
            <span style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>to</span>
            <input type="date" value={dailyTo} onChange={(e) => setDailyTo(e.target.value)} style={dateInputStyle} />
          </div>
          <div style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
            {loadingDaily ? (
              "Loading…"
            ) : dailySummary ? (
              <>
                <strong style={{ color: "var(--color-text-primary)" }}>{dailySummary.counts.deposits}</strong> deposits
                {" ("}{fmtMoney(dailySummary.total_deposit_amount)}{")"} ·{" "}
                <strong style={{ color: "var(--color-text-primary)" }}>{dailySummary.counts.withdrawals}</strong> withdrawals
                {" ("}{fmtMoney(dailySummary.total_withdrawal_amount)}{")"} ·{" "}
                <strong style={{ color: "var(--color-text-primary)" }}>{dailySummary.counts.valuations}</strong> valuations
              </>
            ) : (
              "—"
            )}
          </div>
          <div style={{ display: "flex", gap: "10px", marginLeft: "auto" }}>
            <button
              onClick={() => handleDailyExport("excel")}
              disabled={dailyExporting !== null || loadingDaily || dailyTotalEvents === 0}
              style={exportBtnStyle(dailyExporting !== null || loadingDaily || dailyTotalEvents === 0)}
            >
              <FileSpreadsheet size={14} /> {dailyExporting === "excel" ? "Exporting…" : "Export Excel"}
            </button>
            <button
              onClick={() => handleDailyExport("pdf")}
              disabled={dailyExporting !== null || loadingDaily || dailyTotalEvents === 0}
              style={exportBtnStyle(dailyExporting !== null || loadingDaily || dailyTotalEvents === 0)}
            >
              <Download size={14} /> {dailyExporting === "pdf" ? "Exporting…" : "Export PDF"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Investor search / selection ── */}
      <div style={{ ...CARD, padding: "18px 22px", marginBottom: "16px" }}>
        {!selected ? (
          <div style={{ position: "relative", maxWidth: "420px" }}>
            <Search
              size={14}
              style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-tertiary)", pointerEvents: "none" }}
            />
            <input
              placeholder="Search by client code, email, or phone…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onFocus={() => results.length > 0 && setShowResults(true)}
              style={{
                width: "100%",
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: "8px",
                padding: "9px 12px 9px 34px",
                fontSize: "13px",
                color: "var(--color-text-primary)",
                outline: "none",
              }}
            />
            {showResults && search.trim() && (
              <div
                style={{
                  position: "absolute",
                  top: "calc(100% + 6px)",
                  left: 0,
                  right: 0,
                  ...CARD,
                  padding: "6px",
                  zIndex: 20,
                  maxHeight: "260px",
                  overflowY: "auto",
                }}
              >
                {searching ? (
                  <div style={{ padding: "12px", fontSize: "12px", color: "var(--color-text-tertiary)", textAlign: "center" }}>Searching…</div>
                ) : results.length === 0 ? (
                  <div style={{ padding: "12px", fontSize: "12px", color: "var(--color-text-tertiary)", textAlign: "center" }}>
                    No investors found for "{search.trim()}".
                  </div>
                ) : (
                  results.map((row) => (
                    <div
                      key={row.internal_client_code}
                      onClick={() => pickInvestor(row)}
                      style={{
                        padding: "8px 10px",
                        borderRadius: "8px",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "10px",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(255,255,255,0.04)")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <CircleUserRound size={16} style={{ color: "rgb(96,165,250)", flexShrink: 0 }} />
                      <div>
                        <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-text-primary)" }}>{row.investor_name || "—"}</div>
                        <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                          {row.internal_client_code} · {row.investor_email || "—"}
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <div
                style={{
                  width: "32px", height: "32px", borderRadius: "50%", background: "rgba(59,130,246,0.15)",
                  border: "1px solid rgba(59,130,246,0.3)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
                }}
              >
                <CircleUserRound size={16} style={{ color: "rgb(96,165,250)" }} />
              </div>
              <div>
                <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)" }}>{selected.investor_name || "—"}</div>
                <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                  {selected.internal_client_code} · {selected.investor_email || activity?.investor_email || "—"}
                </div>
              </div>
            </div>
            <button onClick={clearSelection} style={exportBtnStyle(false)}>
              <X size={13} /> Change investor
            </button>
          </div>
        )}
      </div>

      {selected && (
        <>
          {/* ── Date range filters ── */}
          <div className="activity-filters-grid" style={{ ...CARD, padding: "18px 22px", marginBottom: "16px", display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
            <div>
              <p style={SECTION_LABEL}>Deposited between</p>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <input type="date" value={depositedFrom} onChange={(e) => setDepositedFrom(e.target.value)} style={dateInputStyle} />
                <span style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>to</span>
                <input type="date" value={depositedTo} onChange={(e) => setDepositedTo(e.target.value)} style={dateInputStyle} />
              </div>
            </div>
            <div>
              <p style={SECTION_LABEL}>Withdrawn between</p>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <input type="date" value={withdrawnFrom} onChange={(e) => setWithdrawnFrom(e.target.value)} style={dateInputStyle} />
                <span style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>to</span>
                <input type="date" value={withdrawnTo} onChange={(e) => setWithdrawnTo(e.target.value)} style={dateInputStyle} />
              </div>
            </div>
            <div>
              <p style={SECTION_LABEL}>Valued between</p>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <input type="date" value={valuedFrom} onChange={(e) => setValuedFrom(e.target.value)} style={dateInputStyle} />
                <span style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>to</span>
                <input type="date" value={valuedTo} onChange={(e) => setValuedTo(e.target.value)} style={dateInputStyle} />
              </div>
            </div>
          </div>

          {/* ── Export ── */}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginBottom: "16px" }}>
            <button onClick={() => handleExport("excel")} disabled={exporting !== null || loadingActivity} style={exportBtnStyle(exporting !== null || loadingActivity)}>
              <FileSpreadsheet size={14} /> {exporting === "excel" ? "Exporting…" : "Export Excel"}
            </button>
            <button onClick={() => handleExport("pdf")} disabled={exporting !== null || loadingActivity} style={exportBtnStyle(exporting !== null || loadingActivity)}>
              <Download size={14} /> {exporting === "pdf" ? "Exporting…" : "Export PDF"}
            </button>
          </div>

          {/* ── Positions ── */}
          <div style={{ ...CARD, padding: "20px 22px", marginBottom: "16px" }}>
            <p style={SECTION_LABEL}>Current Positions</p>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Fund / Class", "Currency", "Deposited", "Shares", "Market Value", "Perf %"].map((h) => (
                      <th key={h} style={{ fontSize: "9px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-text-tertiary)", padding: "8px 10px", textAlign: h === "Fund / Class" ? "left" : "right" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loadingActivity ? (
                    <tr><td colSpan={6} style={{ padding: "24px", textAlign: "center", color: "var(--color-text-tertiary)", fontSize: "12px" }}>Loading…</td></tr>
                  ) : !activity || activity.positions.length === 0 ? (
                    <tr><td colSpan={6} style={{ padding: "24px", textAlign: "center", color: "var(--color-text-tertiary)", fontSize: "12px" }}>No positions.</td></tr>
                  ) : (
                    activity.positions.map((p, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                        <td style={{ padding: "8px 10px", fontSize: "12px", color: "var(--color-text-primary)" }}>
                          {p.fund_name}{p.class_code ? ` (${p.class_code})` : ""}
                        </td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontSize: "11px", color: "var(--color-text-tertiary)" }}>{p.currency || "—"}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>{fmtMoney(p.deposit_amount)}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>{p.shares != null ? p.shares.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px" }}>{fmtMoney(p.market_value)}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 600, color: (p.performance_pct ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                          {p.performance_pct != null ? `${p.performance_pct >= 0 ? "+" : ""}${p.performance_pct.toFixed(2)}%` : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* ── Activity feed ── */}
          <div style={{ ...CARD, padding: "0", overflow: "hidden" }}>
            <div style={{ padding: "16px 22px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
              <p style={{ ...SECTION_LABEL, marginBottom: 0 }}>Activity</p>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Date", "Type", "Fund / Class", "Currency", "Amount", "Status"].map((h) => (
                      <th key={h} style={{ fontSize: "9px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-text-tertiary)", padding: "10px 16px", textAlign: "left", background: "rgba(255,255,255,0.02)", whiteSpace: "nowrap" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {loadingActivity ? (
                    <tr><td colSpan={6} style={{ padding: "32px", textAlign: "center", color: "var(--color-text-tertiary)", fontSize: "13px" }}>Loading…</td></tr>
                  ) : !activity || activity.events.length === 0 ? (
                    <tr><td colSpan={6} style={{ padding: "32px", textAlign: "center", color: "var(--color-text-tertiary)", fontSize: "13px" }}>No activity in the selected range.</td></tr>
                  ) : (
                    activity.events.map((e, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                        <td style={{ padding: "10px 16px", fontSize: "12px", color: "var(--color-text-secondary)", whiteSpace: "nowrap" }}>{e.date || "—"}</td>
                        <td style={{ padding: "10px 16px" }}><EventTypeBadge type={e.type} /></td>
                        <td style={{ padding: "10px 16px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
                          {e.fund_name}{e.class_code ? ` (${e.class_code})` : ""}
                        </td>
                        <td style={{ padding: "10px 16px", fontSize: "11px", color: "var(--color-text-tertiary)" }}>{e.currency || "—"}</td>
                        <td style={{ padding: "10px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)", whiteSpace: "nowrap" }}>{fmtMoney(e.amount, e.currency)}</td>
                        <td style={{ padding: "10px 16px", fontSize: "11px", color: "var(--color-text-tertiary)" }}>{e.status || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <style>{`
        @media (max-width: 700px) {
          .activity-filters-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}
