import { useEffect, useState, useMemo, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NAVLineChart } from "@/components/charts/NAVLineChart";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { dashboardService, type OverviewStats } from "@/services/dashboardService";
import ClientActivitySection from "@/components/overview/ClientActivitySection";
import { ROUTES } from "@/lib/constants";
import type { FundClassSummary, FundSummaryItem, FundsSummaryResponse, Batch, ProductType } from "@/lib/types";
import { ProductToggle, OVERVIEW_PRODUCT_OPTIONS, type ProductFilterValue } from "@/components/ui/ProductToggle";
import { useNgnUsdView, NgnUsdViewControl, type NgnUsdView } from "@/components/shares/NgnUsdView";

// ═══════════════════════════════════════════════════════════════════════════════
// OVERVIEW PAGE — Production-matching layout
// ═══════════════════════════════════════════════════════════════════════════════
// Matches: https://osfmr.aib-axysafrica.com/overview
//
// Layout:
//   1. Header: "Portfolio Overview" + NAV as-of date
//   2. KPI row: Total KES, Total USD, Total NGN, Investors, Batches — the
//      currency cards shown depend on the Product filter (Task 10)
//   3. Two-column grid:
//      Left: one NAV chart per visible currency | Right: Latest Valuation + Batch Status
//
// Each section loads independently (its own loading flag) rather than blocking
// the whole page behind the slowest of several requests. The old "Recent
// Transactions" table was removed — a client-level activity search/report is
// being built separately to replace it.
//
// Task 10: Funds and Shares (NGN) used to be two separate blocks on this page
// (Shares priced per-batch, not NAV-based). Now both are the same NAV-based
// KPI/chart/table shapes, merged into one layout and scoped by the Product
// filter / the Fund-or-Share dropdown — never summed together across
// currencies or products.
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

// Shares (DPRP) classes are valued in NGN whatever their deposit currency.
const valuationCurrencyOf = (c: FundClassSummary) => c.valuation_currency ?? c.currency;

// ── Currency color/prefix lookups (KES/USD/NGN) ──────────────────────────────
const CURRENCY_COLOR_VAR: Record<string, string> = { KES: "--color-kes", USD: "--color-usd", NGN: "--color-ngn" };
function currencyColorVar(currency: string | undefined) {
  return (currency && CURRENCY_COLOR_VAR[currency]) ?? "--color-usd";
}
function currencyPrefix(currency: string | undefined) {
  return currency === "USD" ? "$ " : currency === "NGN" ? "₦ " : "";
}

// ── Currency badge ────────────────────────────────────────────────────────────
function CurrencyBadge({ currency }: { currency: string }) {
  const colorVar = currencyColorVar(currency);
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
        background: `var(${colorVar}-bg)`,
        color: `var(${colorVar})`,
        border: `1px solid var(${colorVar}-border)`,
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

// ── One "Total <currency>" KPI card — shared shape for KES/USD/NGN (Task 10) ──
interface CurrencyKpiCardProps {
  currency: string;
  total: number;
  activeClassesCount: number;
  netHoldings: number;
  gross: number;
  withdrawn: number;
  refunds: number;
  gain: number;
  /** Only meaningful when a single fund/share is selected — "No <currency>
   * exposure for this fund/share" vs. a blank dash for the portfolio-wide view. */
  scopedToThisEntity: boolean;
  hasExposure: boolean;
  entityNoun: "fund" | "share";
  /** When provided, gates the Gain/Loss line with an extra "Not valued yet"
   * state (Task 10, NGN/Shares only — see FundClassSummary.is_valued). */
  anyValued?: boolean;
  /** Currency of the deposit-side lines (Net Holdings, Gross, Withdrawn,
   * Refunds) when it differs from the card's value currency — Shares are
   * valued in NGN but deposited/refunded in USD. Defaults to `currency`. */
  depositCurrency?: string;
  /** Shares only: "View in NGN / USD" for the NGN value lines. */
  ngnView?: NgnUsdView;
}

function CurrencyKpiCard({
  currency,
  total,
  activeClassesCount,
  netHoldings,
  gross,
  withdrawn,
  refunds,
  gain,
  scopedToThisEntity,
  hasExposure,
  entityNoun,
  anyValued,
  depositCurrency,
  ngnView,
}: CurrencyKpiCardProps) {
  const colorVar = currencyColorVar(currency);
  const color = `var(${colorVar})`;
  const deployed = total > 0;
  // Value lines (Total, Gain) may be shown converted; deposit lines never are.
  const shownCurrency = ngnView && currency === "NGN" ? ngnView.displayCurrency : currency;
  if (ngnView && currency === "NGN") {
    total = ngnView.convert(total);
    gain = ngnView.convert(gain);
  }
  const prefix = currencyPrefix(shownCurrency);
  const depositPrefix = currencyPrefix(depositCurrency ?? currency);
  const gainLabel = !deployed
    ? "Not deployed yet"
    : anyValued === false
      ? "Not valued yet"
      : (gain >= 0 ? "+" : "-") + `${prefix}${Math.abs(gain).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  return (
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
        Total <span style={{ color, marginLeft: "4px" }}>{shownCurrency}</span>
        {shownCurrency !== currency && <span style={{ marginLeft: "4px", textTransform: "none" }}>(from {currency})</span>}
      </div>
      {ngnView && currency === "NGN" && (
        <div style={{ marginBottom: "8px" }}>
          <NgnUsdViewControl view={ngnView} compact />
        </div>
      )}
      {scopedToThisEntity && !hasExposure ? (
        <div style={{ fontSize: "13px", color: "var(--color-text-tertiary)", padding: "6px 0" }}>
          No {currency} exposure for this {entityNoun}
        </div>
      ) : (
        <>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "20px",
              fontWeight: 700,
              color,
              letterSpacing: "-0.02em",
            }}
          >
            {total > 0 ? `${prefix}${total.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginTop: "6px" }}>
            {activeClassesCount} active class{activeClassesCount !== 1 ? "es" : ""}
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
            {netHoldings !== 0 ? `${depositPrefix}${netHoldings.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
          </div>
          <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
            Gross Invested:{" "}
            {gross > 0 ? `${depositPrefix}${gross.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "—"}
          </div>
          {withdrawn > 0 && (
            <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
              Withdrawn: -{depositPrefix}{withdrawn.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          )}
          {refunds > 0 && (
            <div style={{ fontSize: "11px", color: "#F59E0B", fontFamily: "var(--font-mono)" }}>
              Pending Refunds: {depositPrefix}{refunds.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          )}
          <div
            style={{
              marginTop: "6px",
              fontSize: "11px",
              // Gated on `deployed` (actual current value existing) AND
              // `anyValued` (a real valuation, not just the deployment-NAV
              // fallback) — neither "not deployed" nor "not valued" is a loss,
              // so both stay green; only a real negative gain shows red.
              color: !deployed || anyValued === false ? "#22c55e" : gain >= 0 ? "#22c55e" : "#ef4444",
              fontFamily: "var(--font-mono)",
            }}
          >
            Gain/Loss: {gainLabel}
          </div>
        </>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Main Page Component
// ═══════════════════════════════════════════════════════════════════════════════
export default function OverviewPage() {
  const navigate = useNavigate();

  const [fundSummary, setFundSummary] = useState<FundsSummaryResponse | null>(null);
  const [loadingFundSummary, setLoadingFundSummary] = useState(true);

  const [sharesSummary, setSharesSummary] = useState<FundsSummaryResponse | null>(null);
  const [loadingSharesSummary, setLoadingSharesSummary] = useState(true);

  const [batches, setBatches] = useState<Batch[]>([]);
  const [loadingBatches, setLoadingBatches] = useState(true);

  const [overviewStats, setOverviewStats] = useState<OverviewStats | null>(null);
  const [loadingStats, setLoadingStats] = useState(true);

  // Fund/Share filter — persisted in the URL (?fund=<id>) so a refresh doesn't
  // silently reset to "All". "all" (the default/no-param state) means every
  // card below shows totals for the current Product filter instead of one
  // specific fund/share.
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

  // Product filter — same URL-persisted pattern as the fund filter above.
  const productFilter = (searchParams.get("product") as ProductFilterValue) ?? "ALL";
  const setProductFilter = useCallback(
    (value: ProductFilterValue) => {
      const next = new URLSearchParams(searchParams);
      if (value === "ALL") next.delete("product");
      else next.set("product", value);
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams]
  );
  // Task 10: KES/USD cards show for Funds or All; NGN shows for Shares or All —
  // never add different currencies together.
  const showFundsGroup = productFilter !== "SHARES";
  const showSharesGroup = productFilter !== "FUNDS";

  const fetchFundSummary = useCallback(async () => {
    setLoadingFundSummary(true);
    try {
      const data = await fundService.getSummary("FUNDS");
      setFundSummary(data);
    } catch {
      setFundSummary(null);
    } finally {
      setLoadingFundSummary(false);
    }
  }, []);

  const fetchSharesSummary = useCallback(async () => {
    setLoadingSharesSummary(true);
    try {
      const data = await fundService.getSummary("SHARES");
      setSharesSummary(data);
    } catch {
      setSharesSummary(null);
    } finally {
      setLoadingSharesSummary(false);
    }
  }, []);

  // Each section fires its own request and tracks its own loading flag — the
  // page no longer waits for the slowest of several calls before rendering
  // anything (Batch Status, in particular, can render once its own data is in,
  // independent of the KPI cards / charts above it).
  useEffect(() => {
    fetchFundSummary();
    fetchSharesSummary();

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
  }, [fetchFundSummary, fetchSharesSummary]);

  // ── Derived data ────────────────────────────────────────────────────────────

  // Dropdown option lists — each summary endpoint is already scoped to one
  // product server-side (Task 8/9), so no extra filtering is needed here.
  const fundsOptions = useMemo(
    () => [...(fundSummary?.funds ?? [])].sort((a, b) => a.fund_name.localeCompare(b.fund_name)),
    [fundSummary]
  );
  const sharesOptions = useMemo(
    () => [...(sharesSummary?.funds ?? [])].sort((a, b) => a.fund_name.localeCompare(b.fund_name)),
    [sharesSummary]
  );

  const selectedFundEntity = useMemo(
    () => fundsOptions.find((f) => String(f.id) === selectedFundId),
    [fundsOptions, selectedFundId]
  );
  const selectedShareEntity = useMemo(
    () => sharesOptions.find((f) => String(f.id) === selectedFundId),
    [sharesOptions, selectedFundId]
  );
  const selectedEntity: FundSummaryItem | undefined = selectedFundEntity ?? selectedShareEntity;
  const scopedProduct: ProductType | undefined = selectedFundEntity ? "FUNDS" : selectedShareEntity ? "SHARES" : undefined;

  // Task 10: the combined Fund/Share dropdown stays in sync with the Product
  // tabs — picking a share switches the tab to Shares; narrowing the tab to
  // one product resets a now-hidden selection back to "all" rather than
  // leaving an invisible option selected.
  const handleEntitySelect = useCallback(
    (value: string) => {
      setSelectedFundId(value);
      if (value !== "all") {
        const isShare = sharesOptions.some((f) => String(f.id) === value);
        if (isShare && productFilter !== "SHARES") setProductFilter("SHARES");
      }
    },
    [setSelectedFundId, sharesOptions, productFilter, setProductFilter]
  );

  useEffect(() => {
    if (selectedFundId === "all" || productFilter === "ALL") return;
    const stillVisible =
      productFilter === "FUNDS"
        ? fundsOptions.some((f) => String(f.id) === selectedFundId)
        : sharesOptions.some((f) => String(f.id) === selectedFundId);
    if (!stillVisible) setSelectedFundId("all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productFilter, fundsOptions, sharesOptions]);

  // "All" (default, per group) → every fund/share in that product; otherwise
  // just the one selected. Every NAV-based card/chart below is derived from
  // these two arrays, so selecting an entity filters ALL of them together.
  const fundsEntities = useMemo(() => {
    if (!showFundsGroup) return [];
    if (scopedProduct === "FUNDS" && selectedEntity) return [selectedEntity];
    if (isFundScoped) return [];
    return fundsOptions;
  }, [showFundsGroup, scopedProduct, selectedEntity, isFundScoped, fundsOptions]);

  const sharesEntities = useMemo(() => {
    if (!showSharesGroup) return [];
    if (scopedProduct === "SHARES" && selectedEntity) return [selectedEntity];
    if (isFundScoped) return [];
    return sharesOptions;
  }, [showSharesGroup, scopedProduct, selectedEntity, isFundScoped, sharesOptions]);

  const fundsClasses = useMemo<FundClassSummary[]>(() => fundsEntities.flatMap((f) => f.classes ?? []), [fundsEntities]);
  const sharesClasses = useMemo<FundClassSummary[]>(() => sharesEntities.flatMap((f) => f.classes ?? []), [sharesEntities]);

  const kesClasses = useMemo(
    () => fundsClasses.filter((c) => c.currency === "KES" && c.current_nav != null),
    [fundsClasses]
  );
  const usdClasses = useMemo(
    () => fundsClasses.filter((c) => c.currency === "USD" && c.current_nav != null),
    [fundsClasses]
  );
  const ngnClasses = useMemo(
    () => sharesClasses.filter((c) => valuationCurrencyOf(c) === "NGN" && c.current_nav != null),
    [sharesClasses]
  );

  // Whether the SPECIFIC selected fund/share has ANY class in that currency at
  // all (regardless of valuation state) — drives "No <currency> exposure for
  // this fund/share" vs. a blank dash. Only meaningful once one entity is
  // selected; "All" keeps the portfolio-wide behavior (a dash when there's
  // genuinely nothing yet).
  const fundHasKES = useMemo(() => fundsClasses.some((c) => c.currency === "KES"), [fundsClasses]);
  const fundHasUSD = useMemo(() => fundsClasses.some((c) => c.currency === "USD"), [fundsClasses]);
  const shareHasNGN = useMemo(() => sharesClasses.some((c) => valuationCurrencyOf(c) === "NGN"), [sharesClasses]);
  // Shares deposits/refunds/withdrawals are in the share classes' deposit
  // currency (USD for DPRP), not the NGN they're valued in after deployment.
  const sharesDepositCurrency = sharesClasses.find((c) => c.currency)?.currency ?? "USD";
  const ngnView = useNgnUsdView();

  // Task 10: "Not valued yet" (deployed with only a deployment-NAV fallback
  // price, see FundClassSummary.is_valued) vs "Not deployed yet" (nothing
  // deployed at all) — only tracked for NGN/Shares today.
  const ngnAnyValued = useMemo(() => ngnClasses.some((c) => c.is_valued), [ngnClasses]);

  const sumByCurrencyFor = (
    entities: FundSummaryItem[],
    field: "totals_by_currency" | "gain_by_currency" | "gross_deposited_by_currency" | "net_principal_after_refund_by_currency" | "withdrawals_by_currency" | "refunds_by_currency" | "net_holdings_by_currency",
    currency: string
  ) => entities.reduce((s, f) => s + ((f[field]?.[currency]) ?? 0), 0);

  // Total KES/USD/NGN: prefer the global stats endpoint for the portfolio-wide
  // figure (authoritative); once a specific fund/share is selected, that
  // endpoint can't scope to it, so sum straight from the relevant summary.
  const totalKES = useMemo(
    () => (scopedProduct === "FUNDS" ? sumByCurrencyFor(fundsEntities, "totals_by_currency", "KES") : overviewStats?.total_aum_kes ?? sumByCurrencyFor(fundsEntities, "totals_by_currency", "KES")),
    [fundsEntities, scopedProduct, overviewStats]
  );
  const totalUSD = useMemo(
    () => (scopedProduct === "FUNDS" ? sumByCurrencyFor(fundsEntities, "totals_by_currency", "USD") : overviewStats?.total_aum_usd ?? sumByCurrencyFor(fundsEntities, "totals_by_currency", "USD")),
    [fundsEntities, scopedProduct, overviewStats]
  );
  const totalNGN = useMemo(
    () => (scopedProduct === "SHARES" ? sumByCurrencyFor(sharesEntities, "totals_by_currency", "NGN") : overviewStats?.total_ngn ?? sumByCurrencyFor(sharesEntities, "totals_by_currency", "NGN")),
    [sharesEntities, scopedProduct, overviewStats]
  );

  // GROSS INVESTED — total ever deposited, unadjusted.
  const grossKES = useMemo(() => sumByCurrencyFor(fundsEntities, "gross_deposited_by_currency", "KES"), [fundsEntities]);
  const grossUSD = useMemo(() => sumByCurrencyFor(fundsEntities, "gross_deposited_by_currency", "USD"), [fundsEntities]);
  const grossShares = useMemo(() => sumByCurrencyFor(sharesEntities, "gross_deposited_by_currency", sharesDepositCurrency), [sharesEntities, sharesDepositCurrency]);

  // Withdrawn — shown as its own line so the Gross → Net gap is visible.
  const withdrawnKES = useMemo(() => sumByCurrencyFor(fundsEntities, "withdrawals_by_currency", "KES"), [fundsEntities]);
  const withdrawnUSD = useMemo(() => sumByCurrencyFor(fundsEntities, "withdrawals_by_currency", "USD"), [fundsEntities]);
  const withdrawnShares = useMemo(() => sumByCurrencyFor(sharesEntities, "withdrawals_by_currency", sharesDepositCurrency), [sharesEntities, sharesDepositCurrency]);

  // Pending/processed oversubscription refunds.
  const refundsKES = useMemo(() => sumByCurrencyFor(fundsEntities, "refunds_by_currency", "KES"), [fundsEntities]);
  const refundsUSD = useMemo(() => sumByCurrencyFor(fundsEntities, "refunds_by_currency", "USD"), [fundsEntities]);
  const refundsShares = useMemo(() => sumByCurrencyFor(sharesEntities, "refunds_by_currency", sharesDepositCurrency), [sharesEntities, sharesDepositCurrency]);

  // NET HOLDINGS — net principal minus withdrawals, computed server-side.
  // Deliberately NOT the same number as totalKES/USD/NGN above (current
  // market value) — this is "what's still actually committed".
  const netHoldingsKES = useMemo(() => sumByCurrencyFor(fundsEntities, "net_holdings_by_currency", "KES"), [fundsEntities]);
  const netHoldingsUSD = useMemo(() => sumByCurrencyFor(fundsEntities, "net_holdings_by_currency", "USD"), [fundsEntities]);
  const netHoldingsShares = useMemo(() => sumByCurrencyFor(sharesEntities, "net_holdings_by_currency", sharesDepositCurrency), [sharesEntities, sharesDepositCurrency]);

  // Gain/Loss — current value vs. Net Holdings, computed server-side.
  const gainKES = useMemo(
    () => (scopedProduct === "FUNDS" ? sumByCurrencyFor(fundsEntities, "gain_by_currency", "KES") : overviewStats?.gain_kes ?? sumByCurrencyFor(fundsEntities, "gain_by_currency", "KES")),
    [fundsEntities, scopedProduct, overviewStats]
  );
  const gainUSD = useMemo(
    () => (scopedProduct === "FUNDS" ? sumByCurrencyFor(fundsEntities, "gain_by_currency", "USD") : overviewStats?.gain_usd ?? sumByCurrencyFor(fundsEntities, "gain_by_currency", "USD")),
    [fundsEntities, scopedProduct, overviewStats]
  );
  const gainNGN = useMemo(
    () => (scopedProduct === "SHARES" ? sumByCurrencyFor(sharesEntities, "gain_by_currency", "NGN") : overviewStats?.gain_ngn ?? sumByCurrencyFor(sharesEntities, "gain_by_currency", "NGN")),
    [sharesEntities, scopedProduct, overviewStats]
  );

  // Total investors — "All" uses the same authoritative, distinct-across-the-
  // portfolio count used by the Investor Directory page (summing per-fund
  // investors_count would double-count investors holding more than one fund);
  // a selected fund/share uses that entity's own distinct-investor count.
  const totalInvestors = isFundScoped ? (selectedEntity?.investors_count ?? 0) : (overviewStats?.total_investors ?? 0);

  // Batches — scoped to the current Product filter, then further narrowed to
  // the selected fund/share's own share classes when one is picked (Task 10:
  // "the Batches and Batch Status cards follow the selected product").
  const productScopedBatches = useMemo(
    () => (productFilter === "ALL" ? batches : batches.filter((b) => b.product_type === productFilter)),
    [batches, productFilter]
  );
  const entityShareClassIds = useMemo(
    () => new Set((selectedEntity?.classes ?? []).map((c) => c.id)),
    [selectedEntity]
  );
  const filteredBatches = useMemo(
    () => (isFundScoped ? productScopedBatches.filter((b) => b.share_class_id != null && entityShareClassIds.has(b.share_class_id)) : productScopedBatches),
    [productScopedBatches, isFundScoped, entityShareClassIds]
  );
  const totalBatches = filteredBatches.length;

  // Recent 6 batches (sorted by id desc)
  const recentBatches = useMemo(
    () => [...filteredBatches].sort((a, b) => b.id - a.id).slice(0, 6),
    [filteredBatches]
  );

  // All classes with current_nav (for Latest Valuation table) — Funds and/or
  // Shares, following the same product visibility as everything else above.
  const valuedClasses = useMemo(
    () => [...(showFundsGroup ? fundsClasses : []), ...(showSharesGroup ? sharesClasses : [])].filter((c) => c.current_nav != null),
    [showFundsGroup, showSharesGroup, fundsClasses, sharesClasses]
  );

  const asOfDate = showFundsGroup ? fundSummary?.as_of_date : sharesSummary?.as_of_date;

  const chartGroups = useMemo(
    () =>
      [
        showFundsGroup && { currency: "KES", classes: kesClasses, asOf: fundSummary?.as_of_date },
        showFundsGroup && { currency: "USD", classes: usdClasses, asOf: fundSummary?.as_of_date },
        showSharesGroup && { currency: "NGN", classes: ngnClasses, asOf: sharesSummary?.as_of_date },
      ].filter((g): g is { currency: string; classes: FundClassSummary[]; asOf: string | undefined } => Boolean(g)),
    [showFundsGroup, showSharesGroup, kesClasses, usdClasses, ngnClasses, fundSummary, sharesSummary]
  );

  const currencyCards = useMemo(
    () =>
      [
        showFundsGroup && {
          currency: "KES",
          total: totalKES,
          activeClassesCount: kesClasses.length,
          netHoldings: netHoldingsKES,
          gross: grossKES,
          withdrawn: withdrawnKES,
          refunds: refundsKES,
          gain: gainKES,
          scopedToThisEntity: scopedProduct === "FUNDS",
          hasExposure: fundHasKES,
        },
        showFundsGroup && {
          currency: "USD",
          total: totalUSD,
          activeClassesCount: usdClasses.length,
          netHoldings: netHoldingsUSD,
          gross: grossUSD,
          withdrawn: withdrawnUSD,
          refunds: refundsUSD,
          gain: gainUSD,
          scopedToThisEntity: scopedProduct === "FUNDS",
          hasExposure: fundHasUSD,
        },
        showSharesGroup && {
          currency: "NGN",
          total: totalNGN,
          activeClassesCount: ngnClasses.length,
          netHoldings: netHoldingsShares,
          gross: grossShares,
          withdrawn: withdrawnShares,
          refunds: refundsShares,
          gain: gainNGN,
          scopedToThisEntity: scopedProduct === "SHARES",
          hasExposure: shareHasNGN,
          anyValued: ngnAnyValued,
          depositCurrency: sharesDepositCurrency,
          ngnView,
        },
      ].filter(Boolean) as (CurrencyKpiCardProps & { currency: string })[],
    [
      showFundsGroup, showSharesGroup, scopedProduct,
      totalKES, kesClasses, netHoldingsKES, grossKES, withdrawnKES, refundsKES, gainKES, fundHasKES,
      totalUSD, usdClasses, netHoldingsUSD, grossUSD, withdrawnUSD, refundsUSD, gainUSD, fundHasUSD,
      totalNGN, ngnClasses, netHoldingsShares, grossShares, withdrawnShares, refundsShares, gainNGN, shareHasNGN, ngnAnyValued,
      sharesDepositCurrency, ngnView,
    ]
  );

  const entityNoun: "fund" | "share" = scopedProduct === "SHARES" ? "share" : "fund";
  const dropdownLabel = productFilter === "FUNDS" ? "Fund" : productFilter === "SHARES" ? "Share" : "Fund / Share";
  const allOptionLabel = productFilter === "FUNDS" ? "All Funds" : productFilter === "SHARES" ? "All Shares" : "All";

  // ── Loading spinner ─────────────────────────────────────────────────────────
  // Batch Status (right column) renders its own inline loading state instead of
  // gating the whole page — see loadingBatches usage below.
  if (loadingFundSummary || loadingSharesSummary || loadingStats) {
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
            {asOfDate ? `NAV as of ${fmtDate(asOfDate)}` : "Live fund data"}
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "flex-end", gap: "16px", flexWrap: "wrap" }}>
          {showSharesGroup && (
            <button
              onClick={() => navigate(ROUTES.SHARES_BATCHES)}
              style={{ fontSize: "11px", fontWeight: 500, color: "var(--color-brand-400)", background: "none", border: "none", cursor: "pointer", padding: "0 0 9px" }}
            >
              View Shares batches →
            </button>
          )}

          {/* Product filter — default All shows every currency; persisted in the URL */}
          <ProductToggle value={productFilter} onChange={setProductFilter} options={OVERVIEW_PRODUCT_OPTIONS} label="Product" />

          {/* Fund/Share filter — Task 10: one combined dropdown, grouped and
              narrowed by the Product filter above */}
          {(showFundsGroup || showSharesGroup) && (
            <div>
              <label
                htmlFor="overview-entity-select"
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
                {dropdownLabel}
              </label>
              <select
                id="overview-entity-select"
                value={selectedFundId}
                onChange={(e) => handleEntitySelect(e.target.value)}
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
                <option value="all">{allOptionLabel}</option>
                {showFundsGroup && fundsOptions.length > 0 && (
                  <optgroup label="Funds">
                    {fundsOptions.map((f) => (
                      <option key={f.id} value={String(f.id)}>
                        {f.fund_name}
                      </option>
                    ))}
                  </optgroup>
                )}
                {showSharesGroup && sharesOptions.length > 0 && (
                  <optgroup label="Shares">
                    {sharesOptions.map((f) => (
                      <option key={f.id} value={String(f.id)}>
                        {f.fund_name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* ── KPI Row ── */}
      <div
        className="overview-kpi-grid"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${currencyCards.length + 2}, 1fr)`,
          gap: "14px",
          marginBottom: "22px",
        }}
      >
        {currencyCards.map((c) => (
          <CurrencyKpiCard key={c.currency} {...c} entityNoun={entityNoun} />
        ))}

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
            {isFundScoped ? `In ${selectedEntity?.fund_name ?? `this ${entityNoun}`}` : "Across all funds"}
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
            {isFundScoped ? `In ${selectedEntity?.fund_name ?? `this ${entityNoun}`}` : "Total batches"}
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
        {/* Left: one NAV chart per visible currency */}
        <div
          className="overview-nav-charts"
          style={{ display: "grid", gridTemplateColumns: chartGroups.length > 1 ? "1fr 1fr" : "1fr", gap: "14px" }}
        >
          {chartGroups.map((g) => (
            <div key={g.currency} style={{ ...CARD, padding: "20px 24px" }}>
              <NAVLineChart
                classes={g.classes}
                currency={g.currency}
                title={`${g.currency} Classes — NAV / Share`}
                asOfDate={g.asOf}
              />
            </div>
          ))}
        </div>

        {/* Right: Latest Valuation + Batch Status */}
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {/* Latest Valuation */}
          <div style={{ ...CARD, padding: "20px 22px" }}>
            <p style={SECTION_LABEL}>Latest Valuation</p>
            {asOfDate && (
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--color-text-tertiary)",
                  marginBottom: "12px",
                  fontFamily: "var(--font-mono)",
                }}
              >
                as of {fmtDate(asOfDate)}
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
                                color: `var(${currencyColorVar(cls.currency)})`,
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
                            ? currencyPrefix(cls.currency) + cls.total_nav.toLocaleString("en-US", { maximumFractionDigits: 0 })
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
                        {isFundScoped ? `No valuation data yet for this ${entityNoun}` : "No valuation data yet"}
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
                {isFundScoped ? `No batches for this ${entityNoun}` : "No batches available"}
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
