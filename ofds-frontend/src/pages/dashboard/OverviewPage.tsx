import { useEffect, useState, useMemo, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NAVLineChart } from "@/components/charts/NAVLineChart";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { dashboardService, type OverviewStats } from "@/services/dashboardService";
import ClientActivitySection from "@/components/overview/ClientActivitySection";
import { ROUTES } from "@/lib/constants";
import type { FundClassSummary, FundsSummaryResponse, Batch } from "@/lib/types";

// ═══════════════════════════════════════════════════════════════════════════════
// OVERVIEW PAGE — Production-matching layout
// ═══════════════════════════════════════════════════════════════════════════════
// Matches: https://osfmr.aib-axysafrica.com/overview
//
// Layout:
//   1. Header: "Portfolio Overview" + NAV as-of date
//   2. KPI row (4 cards): AUM KES, AUM USD, Investors, Batches
//   3. Two-column grid:
//      Left (2x2): KES NAV chart  |  USD NAV chart
//      Right: Latest Valuation table + Batch Status list
//
// Each section loads independently (its own loading flag) rather than blocking
// the whole page behind the slowest of several requests. The old "Recent
// Transactions" table was removed — a client-level activity search/report is
// being built separately to replace it.
// ═══════════════════════════════════════════════════════════════════════════════

// ── Shared glassmorphism card style ──────────────────────────────────────────
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

// ── Currency badge ────────────────────────────────────────────────────────────
function CurrencyBadge({ currency }: { currency: string }) {
  const isKES = currency === "KES";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "1px 6px",
        borderRadius: "4px",
        fontSize: "9px",
        fontWeight: 700,
        letterSpacing: "0.06em",
        fontFamily: "var(--font-mono)",
        background: isKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
        color: isKES ? "var(--color-kes)" : "var(--color-usd)",
        border: isKES ? "1px solid var(--color-kes-border)" : "1px solid var(--color-usd-border)",
      }}
    >
      {currency}
    </span>
  );
}

// ── Batch open countdown ──────────────────────────────────────────────────────
function BatchCloseCountdown({ closeAt }: { closeAt: string }) {
  const diff = new Date(closeAt).getTime() - Date.now();
  if (diff <= 0) {
    return <span style={{ fontSize: "10px", color: "#475569" }}>Closed</span>;
  }
  const totalHours = Math.floor(diff / 3_600_000);
  const days = Math.floor(totalHours / 24);
  const hours = totalHours % 24;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 7px",
        borderRadius: "100px",
        background: "rgba(245,158,11,0.1)",
        border: "1px solid rgba(245,158,11,0.25)",
        fontSize: "10px",
        fontWeight: 600,
        color: "#F59E0B",
      }}
    >
      {days > 0 ? `${days}d ${hours}h` : `${hours}h`}
    </span>
  );
}

// ── Format friendly date ──────────────────────────────────────────────────────
function fmtDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "—";
  try {
    return new Date(dateStr).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

// ── Batch status label ────────────────────────────────────────────────────────
function getBatchStatus(b: Batch): string {
  if (b.status) return b.status;
  if (b.is_open) return "Open";
  if (b.stage >= 4) return "Active";
  if (b.stage >= 3) return "Deployed";
  if (b.stage >= 2) return "Transferred";
  return "Deposited";
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Page Component
// ═══════════════════════════════════════════════════════════════════════════════
export default function OverviewPage() {
  const navigate = useNavigate();

  const [fundSummary, setFundSummary] = useState<FundsSummaryResponse | null>(null);
  const [loadingFundSummary, setLoadingFundSummary] = useState(true);

  const [batches, setBatches] = useState<Batch[]>([]);
  const [loadingBatches, setLoadingBatches] = useState(true);

  const [overviewStats, setOverviewStats] = useState<OverviewStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);

  // Fund filter — persisted in the URL (?fund=<id>) so a refresh doesn't
  // silently reset to "All Funds". "all" (the default/no-param state) means
  // every card below shows portfolio-wide totals, exactly as before this
  // feature existed.
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedFundId = searchParams.get("fund") ?? "all";
  const isFundScoped = selectedFundId !== "all";
  const setSelectedFundId = useCallback(
    (value: string) => {
      const next = new URLSearchParams(searchParams);
      if (value === "all") next.delete("fund");
      else next.set("fund", value);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const fetchFundSummary = useCallback(async () => {
    setLoadingFundSummary(true);
    try {
      const data = await fundService.getSummary();
      setFundSummary(data);
    } catch {
      setFundSummary(null);
    } finally {
      setLoadingFundSummary(false);
    }
  }, []);

  // Each section fires its own request and tracks its own loading flag — the
  // page no longer waits for the slowest of several calls before rendering
  // anything (Batch Status, in particular, can render once its own data is in,
  // independent of the KPI cards / charts above it).
  useEffect(() => {
    fetchFundSummary();

    setLoadingBatches(true);
    batchService.getAll().then((b) => {
      setBatches(b ?? []);
      setLoadingBatches(false);
    }).catch(() => {
      setBatches([]);
      setLoadingBatches(false);
    });

    setLoadingStats(true);
    dashboardService.getOverviewStats()
      .then((s) => setOverviewStats(s))
      .catch(() => setOverviewStats(null))
      .finally(() => setLoadingStats(false));
  }, [fetchFundSummary]);

  // ── Derived data ────────────────────────────────────────────────────────────

  // All active funds, for the selector dropdown — sorted alphabetically.
  const allFunds = useMemo(
    () => [...(fundSummary?.funds ?? [])].sort((a, b) => a.fund_name.localeCompare(b.fund_name)),
    [fundSummary]
  );

  // "All Funds" (default) → every fund; otherwise just the one selected.
  // Every card below is derived from this one array, so selecting a fund
  // filters ALL of them together rather than each card having its own
  // separate filter logic.
  const filteredFunds = useMemo(() => {
    if (!fundSummary) return [];
    if (!isFundScoped) return fundSummary.funds;
    return fundSummary.funds.filter((f) => String(f.id) === selectedFundId);
  }, [fundSummary, isFundScoped, selectedFundId]);

  const selectedFund = isFundScoped ? filteredFunds[0] : undefined;

  // Share classes within the current fund filter
  const allClasses = useMemo<FundClassSummary[]>(
    () => filteredFunds.flatMap((f) => f.classes ?? []),
    [filteredFunds]
  );

  const kesClasses = useMemo(
    () => allClasses.filter((c) => c.currency === "KES" && c.current_nav != null),
    [allClasses]
  );
  const usdClasses = useMemo(
    () => allClasses.filter((c) => c.currency === "USD" && c.current_nav != null),
    [allClasses]
  );
  // Whether this fund has ANY share class in a currency at all (regardless of
  // valuation state) — drives "No <currency> exposure for this fund" vs. a
  // blank dash. Only meaningful once a specific fund is selected; "All Funds"
  // keeps today's behavior (a dash when there's genuinely nothing yet).
  const fundHasKES = useMemo(() => allClasses.some((c) => c.currency === "KES"), [allClasses]);
  const fundHasUSD = useMemo(() => allClasses.some((c) => c.currency === "USD"), [allClasses]);

  const sumByCurrency = (field: "totals_by_currency" | "gain_by_currency" | "gross_deposited_by_currency" | "net_principal_after_refund_by_currency" | "withdrawals_by_currency" | "refunds_by_currency" | "net_holdings_by_currency", currency: "KES" | "USD") =>
    filteredFunds.reduce((s, f) => s + ((f[field]?.[currency]) ?? 0), 0);

  // AUM KES/USD: prefer the global stats endpoint when showing everything
  // (it's the authoritative portfolio-wide figure); once a fund is selected,
  // that endpoint can't scope to it, so sum straight from the fund summary.
  const aumKES = useMemo(
    () => (isFundScoped ? sumByCurrency("totals_by_currency", "KES") : overviewStats?.total_aum_kes ?? sumByCurrency("totals_by_currency", "KES")),
    [filteredFunds, isFundScoped, overviewStats]
  );
  const aumUSD = useMemo(
    () => (isFundScoped ? sumByCurrency("totals_by_currency", "USD") : overviewStats?.total_aum_usd ?? sumByCurrency("totals_by_currency", "USD")),
    [filteredFunds, isFundScoped, overviewStats]
  );

  // GROSS INVESTED — total ever deposited, unadjusted. Distinct from the old
  // "Invested" figure (which was cost-basis/deployment-NAV based) — this is
  // the raw deposit total the Gross/Net split calls for.
  const grossKES = useMemo(() => sumByCurrency("gross_deposited_by_currency", "KES"), [filteredFunds]);
  const grossUSD = useMemo(() => sumByCurrency("gross_deposited_by_currency", "USD"), [filteredFunds]);

  // Withdrawn — shown as its own line so the Gross → Net gap is visible.
  const withdrawnKES = useMemo(() => sumByCurrency("withdrawals_by_currency", "KES"), [filteredFunds]);
  const withdrawnUSD = useMemo(() => sumByCurrency("withdrawals_by_currency", "USD"), [filteredFunds]);

  // Pending/processed oversubscription refunds — real money that's neither
  // "invested" nor "lost"; shown as its own line so it never silently
  // disappears from the totals without being labeled.
  const refundsKES = useMemo(() => sumByCurrency("refunds_by_currency", "KES"), [filteredFunds]);
  const refundsUSD = useMemo(() => sumByCurrency("refunds_by_currency", "USD"), [filteredFunds]);

  // NET HOLDINGS — net principal (gross deposited minus transfer cost, entry
  // fee, and any oversubscription refund) minus withdrawals — computed
  // server-side in compute_funds_summary_data. Deliberately NOT the same
  // number as aumKES/aumUSD above (current market value) — this is "what's
  // still actually committed", the AUM card is "what it's worth today".
  const netHoldingsKES = useMemo(() => sumByCurrency("net_holdings_by_currency", "KES"), [filteredFunds]);
  const netHoldingsUSD = useMemo(() => sumByCurrency("net_holdings_by_currency", "USD"), [filteredFunds]);

  // Gain/Loss — current value vs. Net Holdings (computed server-side in
  // compute_funds_summary_data using net_holdings_by_currency, not the older
  // cost-basis formula still used elsewhere in the app for per-class figures).
  const gainKES = useMemo(
    () => (isFundScoped ? sumByCurrency("gain_by_currency", "KES") : overviewStats?.gain_kes ?? sumByCurrency("gain_by_currency", "KES")),
    [filteredFunds, isFundScoped, overviewStats]
  );
  const gainUSD = useMemo(
    () => (isFundScoped ? sumByCurrency("gain_by_currency", "USD") : overviewStats?.gain_usd ?? sumByCurrency("gain_by_currency", "USD")),
    [filteredFunds, isFundScoped, overviewStats]
  );

  // Total investors — "All Funds" uses the same authoritative count used by
  // the Investor Directory page; a selected fund uses that fund's own
  // distinct-investor count from the fund summary instead.
  const totalInvestors = isFundScoped ? (selectedFund?.investors_count ?? 0) : (overviewStats?.total_investors ?? 0);

  // Batches — scoped to the selected fund's share classes when one is
  // selected; batchService.getAll() already excludes empty batches
  // server-side, so "All Funds" still matches the Batches page directly.
  const fundShareClassIds = useMemo(
    () => new Set((selectedFund?.classes ?? []).map((c) => c.id)),
    [selectedFund]
  );
  const filteredBatches = useMemo(
    () => (isFundScoped ? batches.filter((b) => b.share_class_id != null && fundShareClassIds.has(b.share_class_id)) : batches),
    [batches, isFundScoped, fundShareClassIds]
  );
  const totalBatches = filteredBatches.length;

  // Recent 6 batches (sorted by id desc)
  const recentBatches = useMemo(
    () => [...filteredBatches].sort((a, b) => b.id - a.id).slice(0, 6),
    [filteredBatches]
  );

  // All classes with current_nav (for Latest Valuation table)
  const valuedClasses = useMemo(
    () => allClasses.filter((c) => c.current_nav != null),
    [allClasses]
  );

  // ── Loading spinner ─────────────────────────────────────────────────────────
  // Batch Status (right column) renders its own inline loading state instead of
  // gating the whole page — see loadingBatches usage below.
  if (loadingFundSummary || loadingStats) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "60vh",
        }}
      >
        <div
          style={{
            width: "24px",
            height: "24px",
            border: "2px solid rgba(255,255,255,0.08)",
            borderTopColor: "var(--color-brand-400)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div style={{ maxWidth: "1400px" }}>
      {/* ── Header ── */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "16px",
          marginBottom: "24px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "22px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              letterSpacing: "-0.02em",
              marginBottom: "4px",
            }}
          >
            Portfolio Overview
          </h1>
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
            {fundSummary?.as_of_date
              ? `NAV as of ${fmtDate(fundSummary.as_of_date)}`
              : "Live fund data"}
          </p>
        </div>

        {/* Fund filter — scopes every card on this page, persisted in the URL */}
        <div>
          <label
            style={{
              display: "block",
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--color-text-tertiary)",
              marginBottom: "6px",
            }}
          >
            Fund
          </label>
          <select
            value={selectedFundId}
            onChange={(e) => setSelectedFundId(e.target.value)}
            style={{
              minWidth: "220px",
              padding: "9px 12px",
              borderRadius: "10px",
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(0,0,0,0.25)",
              color: "var(--color-text-primary)",
              fontSize: "13px",
              fontWeight: 600,
            }}
          >
            <option value="all">All Funds</option>
            {allFunds.map((f) => (
              <option key={f.id} value={String(f.id)}>
                {f.fund_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── KPI Row (4 cards) ── */}
      <div
        className="overview-kpi-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "14px",
          marginBottom: "22px",
        }}
      >
        {/* AUM KES */}
        <div style={{ ...CARD, padding: "18px 22px" }}>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--color-text-tertiary)",
              marginBottom: "8px",
            }}
          >
            Total AUM{" "}
            <span style={{ color: "var(--color-kes)", marginLeft: "4px" }}>KES</span>
          </div>
          {isFundScoped && !fundHasKES ? (
            <div style={{ fontSize: "13px", color: "var(--color-text-tertiary)", padding: "6px 0" }}>
              No KES exposure for this fund
            </div>
          ) : (
            <>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "20px",
                  fontWeight: 700,
                  color: "var(--color-kes)",
                  letterSpacing: "-0.02em",
                }}
              >
                {aumKES > 0
                  ? aumKES.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })
                  : "—"}
              </div>
              <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "6px" }}>
                {kesClasses.length} active class{kesClasses.length !== 1 ? "es" : ""}
              </div>
              <div
                style={{
                  marginTop: "8px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "13px",
                  fontWeight: 700,
                  color: "var(--color-text-primary)",
                }}
              >
                Net Holdings:{" "}
                {netHoldingsKES !== 0
                  ? netHoldingsKES.toLocaleString("en-US", { maximumFractionDigits: 2 })
                  : "—"}
              </div>
              <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                Gross Invested:{" "}
                {grossKES > 0 ? grossKES.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}
              </div>
              {withdrawnKES > 0 && (
                <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                  Withdrawn: -{withdrawnKES.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </div>
              )}
              {refundsKES > 0 && (
                <div style={{ fontSize: "11px", color: "#F59E0B", fontFamily: "var(--font-mono)" }}>
                  Pending Refunds: {refundsKES.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </div>
              )}
              <div
                style={{
                  marginTop: "6px",
                  fontSize: "11px",
                  color: aumKES > 0 ? (gainKES >= 0 ? "#22c55e" : "#ef4444") : "#22c55e",
                  fontFamily: "var(--font-mono)",
                }}
              >
                Gain/Loss:{" "}
                {/* Gated on aumKES (actual deployed current value), not just a
                    NAV price existing — a deposit can have a NAV/share known
                    (current_nav set) while still sitting undeployed with zero
                    shares, so total value (aumKES) is genuinely 0. That's not
                    a loss, it's cash awaiting deployment, so it's never shown
                    in red: no realized position yet means nothing to lose. */}
                {aumKES > 0
                  ? (gainKES >= 0 ? "+" : "") +
                    gainKES.toLocaleString("en-US", { maximumFractionDigits: 2 })
                  : "Not deployed yet"}
              </div>
            </>
          )}
        </div>

        {/* AUM USD */}
        <div style={{ ...CARD, padding: "18px 22px" }}>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--color-text-tertiary)",
              marginBottom: "8px",
            }}
          >
            Total AUM{" "}
            <span style={{ color: "var(--color-usd)", marginLeft: "4px" }}>USD</span>
          </div>
          {isFundScoped && !fundHasUSD ? (
            <div style={{ fontSize: "13px", color: "var(--color-text-tertiary)", padding: "6px 0" }}>
              No USD exposure for this fund
            </div>
          ) : (
            <>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "20px",
                  fontWeight: 700,
                  color: "var(--color-usd)",
                  letterSpacing: "-0.02em",
                }}
              >
                {aumUSD > 0
                  ? `$ ${aumUSD.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}`
                  : "—"}
              </div>
              <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "6px" }}>
                {usdClasses.length} active class{usdClasses.length !== 1 ? "es" : ""}
              </div>
              <div
                style={{
                  marginTop: "8px",
                  fontFamily: "var(--font-mono)",
                  fontSize: "13px",
                  fontWeight: 700,
                  color: "var(--color-text-primary)",
                }}
              >
                Net Holdings:{" "}
                {netHoldingsUSD !== 0
                  ? `$ ${netHoldingsUSD.toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                  : "—"}
              </div>
              <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                Gross Invested:{" "}
                {grossUSD > 0 ? `$ ${grossUSD.toLocaleString("en-US", { maximumFractionDigits: 2 })}` : "—"}
              </div>
              {withdrawnUSD > 0 && (
                <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                  Withdrawn: -${withdrawnUSD.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </div>
              )}
              {refundsUSD > 0 && (
                <div style={{ fontSize: "11px", color: "#F59E0B", fontFamily: "var(--font-mono)" }}>
                  Pending Refunds: ${refundsUSD.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                </div>
              )}
              <div
                style={{
                  marginTop: "6px",
                  fontSize: "11px",
                  color: aumUSD > 0 ? (gainUSD >= 0 ? "#22c55e" : "#ef4444") : "#22c55e",
                  fontFamily: "var(--font-mono)",
                }}
              >
                Gain/Loss:{" "}
                {/* See the KES card's comment — gated on aumUSD (actual deployed
                    value), not just a NAV price existing. */}
                {aumUSD > 0
                  ? (gainUSD >= 0 ? "+" : "-") +
                    `$ ${Math.abs(gainUSD).toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                  : "Not deployed yet"}
              </div>
            </>
          )}
        </div>

        {/* Investors */}
        <div style={{ ...CARD, padding: "18px 22px" }}>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--color-text-tertiary)",
              marginBottom: "8px",
            }}
          >
            Investors
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              letterSpacing: "-0.02em",
            }}
          >
            {totalInvestors > 0 ? totalInvestors.toLocaleString("en-US") : "—"}
          </div>
          <div
            style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "4px" }}
          >
            {isFundScoped ? `In ${selectedFund?.fund_name ?? "this fund"}` : "Across all funds"}
          </div>
        </div>

        {/* Batches */}
        <div style={{ ...CARD, padding: "18px 22px" }}>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: "var(--color-text-tertiary)",
              marginBottom: "8px",
            }}
          >
            Batches
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
            }}
          >
            {loadingBatches ? "—" : totalBatches}
          </div>
          <div
            style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "4px" }}
          >
            {isFundScoped ? `In ${selectedFund?.fund_name ?? "this fund"}` : "Total batches"}
          </div>
        </div>
      </div>

      {/* ── Main 2-column grid ── */}
      <div
        className="overview-main-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 360px",
          gap: "16px",
          marginBottom: "22px",
          alignItems: "start",
        }}
      >
        {/* Left: 2x2 NAV charts */}
        <div className="overview-nav-charts" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
          {/* KES chart */}
          <div style={{ ...CARD, padding: "20px 24px" }}>
            <NAVLineChart
              classes={kesClasses}
              currency="KES"
              title="KES Classes — NAV / Share"
              asOfDate={fundSummary?.as_of_date}
            />
          </div>

          {/* USD chart */}
          <div style={{ ...CARD, padding: "20px 24px" }}>
            <NAVLineChart
              classes={usdClasses}
              currency="USD"
              title="USD Classes — NAV / Share"
              asOfDate={fundSummary?.as_of_date}
            />
          </div>
        </div>

        {/* Right: Latest Valuation + Batch Status */}
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {/* Latest Valuation */}
          <div style={{ ...CARD, padding: "20px 22px" }}>
            <p style={SECTION_LABEL}>Latest Valuation</p>
            {fundSummary?.as_of_date && (
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--color-text-tertiary)",
                  marginBottom: "12px",
                  fontFamily: "var(--font-mono)",
                }}
              >
                as of {fmtDate(fundSummary.as_of_date)}
              </div>
            )}
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Class", "NAV / Share", "Total NAV", "Perf"].map((h) => (
                      <th
                        key={h}
                        style={{
                          fontSize: "9px",
                          fontWeight: 600,
                          letterSpacing: "0.08em",
                          textTransform: "uppercase",
                          color: "var(--color-text-tertiary)",
                          padding: "4px 6px",
                          textAlign: "left",
                          borderBottom: "1px solid rgba(255,255,255,0.06)",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {valuedClasses.map((cls) => {
                    const isKES = cls.currency === "KES";
                    const perf = cls.performance_pct;
                    const perfStr =
                      perf != null
                        ? (perf >= 0 ? "+" : "") + perf.toFixed(2) + "%"
                        : "—";
                    const positive = (perf ?? 0) >= 0;
                    const navDisplay =
                      cls.current_nav != null
                        ? cls.current_nav.toLocaleString("en-US", {
                            minimumFractionDigits: 4,
                            maximumFractionDigits: 4,
                          })
                        : "—";
                    return (
                      <tr
                        key={cls.id ?? cls.class_code ?? cls.class_name}
                        style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}
                      >
                        <td style={{ padding: "7px 6px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                            <span
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: "10px",
                                fontWeight: 700,
                                color: isKES ? "var(--color-kes)" : "var(--color-usd)",
                              }}
                            >
                              {cls.class_code ?? cls.class_name}
                            </span>
                          </div>
                        </td>
                        <td
                          style={{
                            padding: "7px 6px",
                            fontFamily: "var(--font-mono)",
                            fontSize: "11px",
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {navDisplay}
                        </td>
                        <td
                          style={{
                            padding: "7px 6px",
                            fontFamily: "var(--font-mono)",
                            fontSize: "10px",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          {cls.total_nav != null
                            ? (isKES ? "KES " : "$ ") +
                              cls.total_nav.toLocaleString("en-US", { maximumFractionDigits: 0 })
                            : "—"}
                        </td>
                        <td
                          style={{
                            padding: "7px 6px",
                            fontFamily: "var(--font-mono)",
                            fontSize: "11px",
                            fontWeight: 600,
                            color: positive ? "#22c55e" : "#EF4444",
                          }}
                        >
                          {perfStr}
                        </td>
                      </tr>
                    );
                  })}
                  {valuedClasses.length === 0 && (
                    <tr>
                      <td
                        colSpan={4}
                        style={{
                          padding: "20px",
                          textAlign: "center",
                          color: "var(--color-text-tertiary)",
                          fontSize: "12px",
                        }}
                      >
                        {isFundScoped ? "No valuation data yet for this fund" : "No valuation data yet"}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Batch Status — loads independently of the KPI cards / charts above */}
          <div style={{ ...CARD, padding: "20px 22px" }}>
            <p style={SECTION_LABEL}>Batch Status</p>
            {loadingBatches ? (
              <div style={{ textAlign: "center", padding: "20px 0", color: "var(--color-text-tertiary)", fontSize: "12px" }}>
                Loading…
              </div>
            ) : recentBatches.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "20px 0",
                  color: "var(--color-text-tertiary)",
                  fontSize: "12px",
                }}
              >
                {isFundScoped ? "No batches for this fund" : "No batches available"}
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {recentBatches.map((b) => {
                  const statusLabel = getBatchStatus(b);
                  const isOpen = b.is_open;
                  return (
                    <div
                      key={b.id}
                      onClick={() => navigate(ROUTES.BATCH_DETAIL(b.id))}
                      style={{
                        padding: "10px 12px",
                        borderRadius: "10px",
                        background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.06)",
                        cursor: "pointer",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          marginBottom: "4px",
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "11px",
                            fontWeight: 600,
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {b.batch_name}
                        </span>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          {b.class_currency && <CurrencyBadge currency={b.class_currency} />}
                          <span
                            style={{
                              fontSize: "10px",
                              padding: "2px 7px",
                              borderRadius: "999px",
                              fontWeight: 600,
                              background: isOpen
                                ? "rgba(16,185,129,0.12)"
                                : "rgba(148,163,184,0.12)",
                              color: isOpen ? "#10B981" : "#94A3B8",
                              border: isOpen
                                ? "1px solid rgba(16,185,129,0.25)"
                                : "1px solid rgba(148,163,184,0.22)",
                            }}
                          >
                            {statusLabel}
                          </span>
                        </div>
                      </div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                        }}
                      >
                        <span
                          style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}
                        >
                          {b.investors_count} investor{b.investors_count !== 1 ? "s" : ""} ·{" "}
                          {b.total_capital != null
                            ? b.total_capital.toLocaleString("en-US", { maximumFractionDigits: 0 })
                            : "—"}
                        </span>
                        {isOpen && b.auto_close_at && (
                          <BatchCloseCountdown closeAt={b.auto_close_at} />
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Client Activity (search one investor, or pull everyone's activity for a day) ── */}
      <ClientActivitySection />

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @media (max-width: 1100px) {
          .overview-main-grid { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 900px) {
          .overview-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)) !important; }
          .overview-nav-charts { grid-template-columns: 1fr !important; }
        }
        @media (max-width: 520px) {
          .overview-kpi-grid { grid-template-columns: 1fr !important; }
        }
      `}</style>
    </div>
  );
}
