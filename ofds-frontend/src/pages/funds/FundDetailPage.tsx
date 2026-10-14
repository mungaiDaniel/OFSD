import React, { useEffect, useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { reportService } from "@/services/reportService";
import { ROUTES } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import { FLOW_COLORS } from "@/lib/chartConfig";
import {
  getBatchDepositBaseTotal,
  getEntryFeePercent,
  getInvestorPrincipalAfterTransfer,
} from "@/lib/transferDeductions";
import { ChartCard } from "@/components/charts/ChartCard";
import { DepositsWithdrawalsBarChart } from "@/components/charts/DepositsWithdrawalsBarChart";
import { NAVLineChart } from "@/components/charts/NAVLineChart";
import type {
  CoreFund,
  FundEditContext,
  FundUpdatePayload,
  ShareClassEditInfo,
  ShareClassUpdatePayload,
  FundShareClass,
  FundsSummaryResponse,
  ReportSummary,
  Batch,
  BatchInvestor,
  ProductType,
} from "@/lib/types";
import { toast } from "sonner";
import { ArrowLeft, Landmark, Coins, Layers, ChevronDown, ChevronUp, Users, Pencil, RefreshCw } from "lucide-react";
import { getUserRole } from "@/lib/auth";
import { FundForm, type FundFormValues } from "@/components/funds/FundForm";
import { ShareClassForm, type ShareClassFormValues } from "@/components/funds/ShareClassForm";
import { CurrencyOverrideDialog } from "@/components/funds/CurrencyOverrideDialog";
import { parseApiError, type ApiFormError } from "@/components/funds/formStyles";
import { useNgnUsdView, NgnUsdViewControl } from "@/components/shares/NgnUsdView";

// Currencies the AUM cards / NAV charts are grouped by. Funds: KES/USD;
// Shares (DPRP) are valued in NGN after deployment, whatever the deposit
// currency (see FundClassSummary.valuation_currency).
const VALUATION_CURRENCIES_BY_PRODUCT: Record<ProductType, string[]> = {
  FUNDS: ["KES", "USD"],
  SHARES: ["NGN"],
};
// Share class (deposit) currencies offered by the Edit Share Class form until
// the server's edit-context allow-list loads. Mirrors FundListPage's copy.
const CLASS_CURRENCIES_BY_PRODUCT: Record<ProductType, string[]> = {
  FUNDS: ["KES", "USD"],
  SHARES: ["USD", "NGN", "KES"],
};
const valuationCurrencyOf = (c: { currency?: string; valuation_currency?: string }) =>
  c.valuation_currency ?? c.currency;

const CURRENCY_COLOR_VAR: Record<string, string> = {
  KES: "--color-kes",
  USD: "--color-usd",
  NGN: "--color-ngn",
};
function currencyColor(currency: string | undefined) {
  return `var(${(currency && CURRENCY_COLOR_VAR[currency]) ?? "--color-usd"})`;
}

function formatNumber(val: number | null | undefined, digits = 4) {
  if (val == null) return "—";
  return val.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function formatPercent(val: number | null | undefined) {
  if (val == null) return null;
  return (val >= 0 ? "+" : "") + val.toFixed(2) + "%";
}

function getTimeRemaining(autoCloseAt: string) {
  const diff = new Date(autoCloseAt).getTime() - Date.now();
  if (diff <= 0) return { days: 0, hours: 0 };
  const hours = Math.floor(diff / (1000 * 60 * 60));
  return { days: Math.floor(hours / 24), hours: hours % 24 };
}

const glassCardStyle: React.CSSProperties = {
  background: "rgba(16,24,45,0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "16px",
  boxShadow: "0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
};

const sectionSubheaderStyle: React.CSSProperties = {
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.1em",
  textTransform: "uppercase",
  color: "var(--color-text-tertiary)",
  marginBottom: "12px",
};

function CurrencyBadge({ currency }: { currency: string }) {
  const varName = CURRENCY_COLOR_VAR[currency] ?? "--color-usd";
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
        background: `var(${varName}-bg)`,
        color: `var(${varName})`,
        border: `1px solid var(${varName}-border)`,
      }}
    >
      {currency}
    </span>
  );
}

function AutoCloseCountdown({ closeAt }: { closeAt: string }) {
  const { days, hours } = getTimeRemaining(closeAt);
  if (days <= 0 && hours <= 0) {
    return <span style={{ fontSize: "10px", color: "#475569" }}>Closed</span>;
  }
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

interface FundDetailPageProps {
  /** Scopes this page to one product — same component, layout, and forms,
   * different data/wording/currency (Task 9). Defaults to FUNDS (unchanged
   * behavior for the existing /funds/:id page). */
  product?: ProductType;
}

export default function FundDetailPage({ product = "FUNDS" }: FundDetailPageProps) {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const fundId = Number(id);
  const isShares = product === "SHARES";
  const noun = isShares ? "share" : "fund";
  const listPath = isShares ? ROUTES.SHARES : ROUTES.FUNDS;
  const currencies = VALUATION_CURRENCIES_BY_PRODUCT[product];
  const ngnView = useNgnUsdView();

  const [fund, setFund] = useState<CoreFund | null>(null);
  const [fundClasses, setFundClasses] = useState<FundShareClass[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [summary, setSummary] = useState<FundsSummaryResponse | null>(null);
  const [allBatches, setAllBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);

  const [expandedBatchId, setExpandedBatchId] = useState<number | null>(null);
  const [batchInvestors, setBatchInvestors] = useState<BatchInvestor[]>([]);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchInvestorSearch, setBatchInvestorSearch] = useState("");

  // Task 12: Edit fund/share + Edit share class (same forms as creation).
  // Editing is limited to the role that can create funds (super_admin); the
  // server enforces this on every edit endpoint regardless of the UI.
  const canEdit = getUserRole() === "super_admin";
  const [editContext, setEditContext] = useState<FundEditContext | null>(null);
  const [editContextLoading, setEditContextLoading] = useState(false);

  const [showEditFund, setShowEditFund] = useState(false);
  const [fundSaving, setFundSaving] = useState(false);
  const [fundErrors, setFundErrors] = useState<Record<string, string>>({});
  const [fundConflict, setFundConflict] = useState<ApiFormError | null>(null);

  const [editingClassId, setEditingClassId] = useState<number | null>(null);
  const [classSaving, setClassSaving] = useState(false);
  const [classErrors, setClassErrors] = useState<Record<string, string>>({});
  const [classConflict, setClassConflict] = useState<ApiFormError | null>(null);
  const [overrideOpen, setOverrideOpen] = useState(false);
  const [overrideConfirmed, setOverrideConfirmed] = useState(false);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const res = await Promise.allSettled([
          fundService.getById(fundId, product),
          fundService.getClasses(fundId, product),
          fundService.getSummary(product),
          batchService.getAll(),
          reportService.getAll(fundId),
        ]);
        if (res[0].status === "fulfilled") setFund(res[0].value);
        if (res[1].status === "fulfilled") setFundClasses(res[1].value);
        if (res[2].status === "fulfilled") setSummary(res[2].value);
        if (res[3].status === "fulfilled") setAllBatches(res[3].value ?? []);
        if (res[4].status === "fulfilled") setReports(res[4].value);
      } finally {
        setLoading(false);
      }
    }
    if (fundId && !Number.isNaN(fundId)) {
      loadData();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fundId, product]);

  const reloadClassesAndFund = async () => {
    const res = await Promise.allSettled([
      fundService.getById(fundId, product),
      fundService.getClasses(fundId, product),
      fundService.getSummary(product),
      batchService.getAll(),
    ]);
    if (res[0].status === "fulfilled") setFund(res[0].value);
    if (res[1].status === "fulfilled") setFundClasses(res[1].value);
    if (res[2].status === "fulfilled") setSummary(res[2].value);
    if (res[3].status === "fulfilled") setAllBatches(res[3].value ?? []);
  };

  const fundSummary = useMemo(
    () => summary?.funds?.find((f) => f.id === fundId) ?? null,
    [summary, fundId]
  );

  // Task 9: one AUM card per currency actually in use by this product — Funds
  // always shows KES + USD (same as before), Shares shows NGN only. Falls
  // back to the product's full currency list so the card still renders
  // (showing "—") before any class/summary data has loaded.
  const currenciesInUse = useMemo(() => {
    const present = new Set((fundSummary?.classes ?? []).map(valuationCurrencyOf));
    return currencies.filter((c) => present.size === 0 || present.has(c));
  }, [fundSummary, currencies]);

  const classesWithNavByCurrency = (currency: string) =>
    (fundSummary?.classes ?? []).filter((c) => valuationCurrencyOf(c) === currency && c.current_nav != null);

  const totalByCurrency = (currency: string) => fundSummary?.totals_by_currency?.[currency] ?? 0;
  const investedByCurrency = (currency: string) => fundSummary?.invested_by_currency?.[currency] ?? 0;
  const gainByCurrency = (currency: string) => fundSummary?.gain_by_currency?.[currency] ?? 0;
  const currencyPrefix = (currency: string | undefined) => (currency === "USD" ? "$ " : currency === "NGN" ? "₦ " : `${currency ?? ""} `);
  // NGN (Shares) figures follow the "View in NGN / USD" control; others pass through.
  const shownCurrency = (currency: string | undefined) => (currency === "NGN" ? ngnView.displayCurrency : currency);
  const shownAmount = (currency: string | undefined, amount: number) => (currency === "NGN" ? ngnView.convert(amount) : amount);

  const linkedBatches = useMemo(() => {
    if (!fund) return [];
    const batchIdSet = new Set((fund.batches ?? []).map((b) => b.batch_id));
    if (batchIdSet.size > 0) {
      return allBatches.filter((b) => batchIdSet.has(b.id)).sort((a, b) => b.id - a.id);
    }
    return allBatches
      .filter((b) => b.funds?.some((f) => f.fund_name === fund.fund_name))
      .sort((a, b) => b.id - a.id);
  }, [allBatches, fund]);

  const openBatches = useMemo(() => linkedBatches.filter((b) => b.is_open), [linkedBatches]);

  const displayClasses = useMemo(
    () =>
      fundSummary && fundSummary.classes && fundSummary.classes.length > 0
        ? fundSummary.classes
        : fundClasses,
    [fundSummary, fundClasses]
  );

  const toggleBatchInvestors = (batchId: number) => {
    if (expandedBatchId === batchId) {
      setExpandedBatchId(null);
      setBatchInvestors([]);
      setBatchInvestorSearch("");
      return;
    }
    setBatchInvestors([]);
    setBatchInvestorSearch("");
    setExpandedBatchId(batchId);
  };

  // Investor rows for an expanded batch are only ever fetched for a non-empty
  // search term — with a batch potentially holding thousands of investors,
  // loading the whole roster just to expand a row would reintroduce the same
  // freeze the Investors list already fixed. Debounced so each keystroke
  // doesn't fire its own request.
  useEffect(() => {
    if (expandedBatchId == null || !fund) return;
    const term = batchInvestorSearch.trim();
    if (!term) {
      setBatchInvestors([]);
      return;
    }
    let cancelled = false;
    setBatchLoading(true);
    const t = setTimeout(async () => {
      try {
        const batch = await batchService.getById(expandedBatchId, { search: term });
        if (cancelled) return;
        const fundName = fund.fund_name;
        const investors = batch?.grouped_by_fund?.[fundName]?.investors ?? [];
        const batchBaseTotal = getBatchDepositBaseTotal(batch?.investments ?? []);
        const entryFeePercent = getEntryFeePercent(batch);
        const transferTransactionCost = Number(batch?.transfer_transaction_cost ?? 0);
        const normalized = investors.map((inv: any) => ({
          ...inv,
          main_balance: getInvestorPrincipalAfterTransfer(inv, {
            stage: batch?.stage,
            batchTotalDepositBase: batchBaseTotal,
            transferTransactionCost,
            entryFeePercent,
          }),
        }));
        setBatchInvestors(normalized);
      } catch {
        if (!cancelled) toast.error("Could not load batch investors");
      } finally {
        if (!cancelled) setBatchLoading(false);
      }
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [expandedBatchId, batchInvestorSearch, fund]);

  const sortedReports = useMemo(
    () =>
      [...reports].sort(
        (a, b) => new Date(a.epoch_end).getTime() - new Date(b.epoch_end).getTime()
      ),
    [reports]
  );

  const reportDates = useMemo(
    () =>
      sortedReports.map((r) =>
        new Date(r.epoch_end).toLocaleDateString("en-GB", {
          month: "short",
          day: "2-digit",
        })
      ),
    [sortedReports]
  );

  // ── Task 12: edit fund / share and share classes ──

  const loadEditContext = async (): Promise<FundEditContext | null> => {
    setEditContextLoading(true);
    try {
      const ctx = await fundService.getEditContext(fundId, product);
      setEditContext(ctx);
      return ctx;
    } catch (err: unknown) {
      toast.error(parseApiError(err, "Could not load the latest values").message);
      return null;
    } finally {
      setEditContextLoading(false);
    }
  };

  // Load once for super admins so inactive share classes can be shown/re-activated.
  useEffect(() => {
    if (canEdit && fundId && !Number.isNaN(fundId)) loadEditContext();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fundId, product, canEdit]);

  const refreshAfterEdit = async () => {
    await Promise.all([reloadClassesAndFund(), loadEditContext()]);
  };

  const openEditFund = async () => {
    setEditingClassId(null);
    setFundErrors({});
    setFundConflict(null);
    // Always fetch fresh values + version when the form opens.
    const ctx = await loadEditContext();
    if (ctx) setShowEditFund(true);
  };

  const closeEditFund = () => {
    setShowEditFund(false);
    setFundErrors({});
    setFundConflict(null);
  };

  const handleSaveFund = async (values: FundFormValues) => {
    if (!editContext) return;
    const current = editContext.fund;
    const payload: FundUpdatePayload = { version: current.version };
    if (values.fund_name !== current.fund_name) payload.fund_name = values.fund_name;
    if (values.fund_code !== (current.fund_code ?? "")) payload.fund_code = values.fund_code;
    if ((values.description || null) !== (current.description || null)) payload.description = values.description || null;
    if (values.is_active !== current.is_active) payload.is_active = values.is_active;
    if (Object.keys(payload).length === 1) {
      toast.info?.("No changes to save");
      closeEditFund();
      return;
    }
    setFundSaving(true);
    setFundErrors({});
    setFundConflict(null);
    try {
      await fundService.updateFund(fundId, payload, product);
      toast.success(`${isShares ? "Share" : "Fund"} updated`);
      closeEditFund();
      await refreshAfterEdit();
    } catch (err: unknown) {
      const e = parseApiError(err, `Failed to update ${noun}`);
      if (e.code === "VERSION_CONFLICT") setFundConflict(e);
      setFundErrors(e.errors);
      toast.error(e.message);
    } finally {
      setFundSaving(false);
    }
  };

  const editingClass: ShareClassEditInfo | null =
    editContext?.share_classes.find((c) => c.id === editingClassId) ?? null;

  const openEditClass = async (classId: number) => {
    setShowEditFund(false);
    setClassErrors({});
    setClassConflict(null);
    setOverrideConfirmed(false);
    const ctx = await loadEditContext();
    if (ctx?.share_classes.some((c) => c.id === classId)) setEditingClassId(classId);
    else if (ctx) toast.error("Share class not found — it may have been removed.");
  };

  const closeEditClass = () => {
    setEditingClassId(null);
    setClassErrors({});
    setClassConflict(null);
    setOverrideConfirmed(false);
  };

  const handleSaveClass = async (values: ShareClassFormValues) => {
    if (!editingClass) return;
    const payload: ShareClassUpdatePayload = { version: editingClass.version };
    if (values.class_name !== editingClass.class_name) payload.class_name = values.class_name;
    if (values.class_code !== editingClass.class_code) payload.class_code = values.class_code;
    if (values.currency !== editingClass.currency) {
      payload.currency = values.currency;
      if (editingClass.currency_locked && overrideConfirmed) payload.confirm_currency_override = true;
    }
    if (values.is_active !== editingClass.is_active) payload.is_active = values.is_active;
    if (Object.keys(payload).length === 1) {
      toast.info?.("No changes to save");
      closeEditClass();
      return;
    }
    setClassSaving(true);
    setClassErrors({});
    setClassConflict(null);
    try {
      await fundService.updateClass(fundId, editingClass.id, payload, product);
      toast.success("Share class updated");
      closeEditClass();
      await refreshAfterEdit();
    } catch (err: unknown) {
      const e = parseApiError(err, "Failed to update share class");
      if (e.code === "VERSION_CONFLICT") setClassConflict(e);
      if (e.code === "CURRENCY_LOCKED") {
        // The class picked up deposits/valuations after the form was opened.
        await loadEditContext();
        if (e.canOverride) setOverrideOpen(true);
      }
      setClassErrors(e.errors);
      toast.error(e.message);
    } finally {
      setClassSaving(false);
    }
  };

  const conflictBanner = (conflict: ApiFormError | null, onReload: () => void) =>
    conflict ? (
      <div
        role="alert"
        style={{
          marginTop: "8px",
          padding: "10px 14px",
          borderRadius: "10px",
          background: "rgba(245,158,11,0.08)",
          border: "1px solid rgba(245,158,11,0.3)",
          color: "#fcd34d",
          fontSize: "12px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "12px",
        }}
      >
        <span>{conflict.message}</span>
        <button
          type="button"
          onClick={onReload}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "6px 10px",
            borderRadius: "8px",
            border: "1px solid rgba(245,158,11,0.45)",
            background: "transparent",
            color: "#fbbf24",
            fontSize: "11px",
            fontWeight: 600,
            cursor: "pointer",
            whiteSpace: "nowrap",
          }}
        >
          <RefreshCw size={12} /> Reload latest
        </button>
      </div>
    ) : null;

  const inactiveClasses = (editContext?.share_classes ?? []).filter((c) => !c.is_active);
  const classCurrencies = Array.from(
    new Set((editContext?.share_classes ?? []).filter((c) => c.is_active).map((c) => c.currency))
  );

  const handleDeleteFund = async () => {
    if (!fundId || !fund) return;
    if (confirm(`Delete this ${noun}? This cannot be undone.`)) {
      try {
        await fundService.delete(fundId, product);
        toast.success("Deleted");
        navigate(listPath);
      } catch (err: any) {
        toast.error(err.response?.data?.message || "Failed");
      }
    }
  };

  const getBatchStatusText = (b: any) => {
    if (b.status) return b.status;
    if (b.is_open) return "Open";
    if (b.stage >= 4) return "Active";
    if (b.stage >= 3) return "Deployed";
    if (b.stage >= 2) return "Transferred";
    return "Deposited";
  };

  const weightedPerf = fundSummary?.weighted_performance_pct;

  if (!fundId || Number.isNaN(fundId)) {
    return (
      <div style={{ padding: "24px", color: "var(--color-text-secondary)" }}>Invalid fund id.</div>
    );
  }

  if (loading) {
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
      </div>
    );
  }

  return (
    <div style={{ maxWidth: "1400px" }}>
      {/* Back button */}
      <button
        type="button"
        onClick={() => navigate(listPath)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          marginBottom: "16px",
          padding: 0,
          border: "none",
          background: "none",
          cursor: "pointer",
          fontSize: "12px",
          color: "var(--color-text-tertiary)",
        }}
      >
        <ArrowLeft size={14} /> {isShares ? "Shares" : "Funds"}
      </button>

      {/* Header Row */}
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
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <div
            style={{
              width: "44px",
              height: "44px",
              borderRadius: "12px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "var(--color-brand-50)",
            }}
          >
            {isShares ? (
              <Coins size={20} style={{ color: "var(--color-brand-400)" }} />
            ) : (
              <Landmark size={20} style={{ color: "var(--color-brand-400)" }} />
            )}
          </div>
          <div>
            <h1
              style={{
                fontSize: "22px",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                letterSpacing: "-0.02em",
                margin: "0 0 6px 0",
              }}
            >
              {fund?.fund_name || "Fund"}
            </h1>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  padding: "3px 10px",
                  borderRadius: "999px",
                  background: fund?.is_active
                    ? "var(--color-success-bg)"
                    : "var(--color-destructive-bg)",
                  color: fund?.is_active ? "var(--color-success)" : "var(--color-destructive)",
                }}
              >
                {fund?.is_active ? "Active" : "Inactive"}
              </span>
              {fund?.fund_code && (
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "11px",
                    color: "var(--color-text-tertiary)",
                  }}
                >
                  {fund.fund_code}
                </span>
              )}
            </div>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {canEdit && (
            <button
              type="button"
              onClick={openEditFund}
              disabled={editContextLoading}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                fontSize: "12px",
                fontWeight: 600,
                borderRadius: "10px",
                cursor: editContextLoading ? "wait" : "pointer",
                border: "1px solid rgba(59,130,246,0.35)",
                background: "rgba(59,130,246,0.14)",
                color: "#60A5FA",
              }}
            >
              <Pencil size={13} /> {isShares ? "Edit share" : "Edit fund"}
            </button>
          )}
          <button
            type="button"
            onClick={handleDeleteFund}
            style={{
              padding: "8px 14px",
              fontSize: "12px",
              fontWeight: 600,
              borderRadius: "10px",
              cursor: "pointer",
              border: "1px solid rgba(239,68,68,0.45)",
              background: "rgba(239,68,68,0.08)",
              color: "#f87171",
            }}
          >
            Delete
          </button>
        </div>
      </div>

      {fund?.description && !showEditFund && (
        <p
          style={{
            fontSize: "13px",
            color: "var(--color-text-secondary)",
            marginTop: "-12px",
            marginBottom: "18px",
            maxWidth: "820px",
            whiteSpace: "pre-wrap",
          }}
        >
          {fund.description}
        </p>
      )}

      {showEditFund && editContext && (
        <FundForm
          mode="edit"
          product={product}
          initial={{
            fund_name: editContext.fund.fund_name,
            fund_code: editContext.fund.fund_code ?? "",
            description: editContext.fund.description ?? "",
            is_active: editContext.fund.is_active,
          }}
          submitting={fundSaving}
          errors={fundErrors}
          banner={conflictBanner(fundConflict, async () => {
            setFundConflict(null);
            setFundErrors({});
            await loadEditContext();
          })}
          onSubmit={handleSaveFund}
          onCancel={closeEditFund}
          classCurrencies={classCurrencies}
          renameLocked={editContext.rename_locked}
          openBatches={editContext.open_batches}
        />
      )}

      {/* Subtitle / Source info */}
      <p
        style={{
          fontSize: "13px",
          color: "var(--color-text-secondary)",
          marginTop: "-12px",
          marginBottom: "22px",
        }}
      >
        {summary?.as_of_date
          ? `NAV as of ${formatDate(summary.as_of_date)} · same source as portfolio overview`
          : fundSummary
          ? "Fund metrics from latest summary"
          : "Summary unavailable — some metrics may be incomplete"}
      </p>

      {isShares && (
        <div style={{ marginBottom: "12px" }}>
          <NgnUsdViewControl view={ngnView} />
        </div>
      )}

      {/* KPI Grid — one AUM card per currency in use, plus Performance + Investors/Batches */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${currenciesInUse.length + 2}, minmax(0, 1fr))`,
          gap: "14px",
          marginBottom: "22px",
        }}
        className="fund-detail-kpi-grid"
      >
        {/* AUM card(s) — one per currency in use */}
        {currenciesInUse.map((currency) => {
          const total = shownAmount(currency, totalByCurrency(currency));
          const invested = shownAmount(currency, investedByCurrency(currency));
          const gain = shownAmount(currency, gainByCurrency(currency));
          const classesWithNav = classesWithNavByCurrency(currency);
          const color = currencyColor(currency);
          const shown = shownCurrency(currency);
          return (
            <div key={currency} style={{ ...glassCardStyle, padding: "18px 22px" }}>
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
                Total <span style={{ color, marginLeft: "4px" }}>{shown}</span>
                {shown !== currency && <span style={{ marginLeft: "4px", textTransform: "none" }}>(from {currency})</span>}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "20px",
                  fontWeight: 700,
                  color,
                  letterSpacing: "-0.02em",
                }}
              >
                {total > 0
                  ? `${currencyPrefix(shown)}${total.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}`
                  : "—"}
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  gap: "10px",
                  marginTop: "6px",
                  fontSize: "11px",
                  color: "var(--color-text-tertiary)",
                }}
              >
                <span>
                  {classesWithNav.length} class{classesWithNav.length !== 1 ? "es" : ""} w/ NAV
                </span>
                <span style={{ fontFamily: "var(--font-mono)" }}>
                  Invested:{" "}
                  {invested > 0
                    ? `${currencyPrefix(shown)}${invested.toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                    : "—"}
                </span>
              </div>
              <div
                style={{
                  marginTop: "4px",
                  fontSize: "11px",
                  color: gain >= 0 ? "#22c55e" : "#ef4444",
                  fontFamily: "var(--font-mono)",
                }}
              >
                Gain/Loss:{" "}
                {total > 0 || invested > 0
                  ? (gain >= 0 ? "+" : "") +
                    `${currencyPrefix(shown)}${Math.abs(gain).toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                  : "—"}
              </div>
            </div>
          );
        })}

        {/* KPI: Weighted Performance */}
        <div style={{ ...glassCardStyle, padding: "18px 22px" }}>
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
            Weighted performance
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "20px",
              fontWeight: 700,
              color:
                weightedPerf == null
                  ? "var(--color-text-primary)"
                  : weightedPerf >= 0
                  ? "#22c55e"
                  : "#ef4444",
              letterSpacing: "-0.02em",
            }}
          >
            {weightedPerf != null ? formatPercent(weightedPerf) : "—"}
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--color-text-tertiary)",
              marginTop: "6px",
            }}
          >
            Across share classes (NAV-based)
          </div>
        </div>

        {/* KPI 4: Investors & Batches */}
        <div style={{ ...glassCardStyle, padding: "18px 22px" }}>
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
            Investors & batches
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
            {fund?.investor_count != null && fund.investor_count > 0 ? fund.investor_count : "—"}
          </div>
          <div
            style={{
              fontSize: "11px",
              color: "var(--color-text-tertiary)",
              marginTop: "6px",
            }}
          >
            {linkedBatches.length} batch{linkedBatches.length !== 1 ? "es" : ""} linked ·{" "}
            {openBatches.length} open
          </div>
        </div>
      </div>

      {/* Main 2-column Grid: Charts on Left, Tables on Right */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 360px",
          gap: "16px",
          marginBottom: "22px",
          alignItems: "start",
        }}
        className="fund-detail-main-grid"
      >
        {/* Left Column: NAV Line Charts */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: currenciesInUse.length > 1 ? "1fr 1fr" : "1fr",
            gap: "14px",
          }}
          className="fund-detail-nav-charts"
        >
          {currenciesInUse.map((currency) => (
            <div key={currency} style={{ ...glassCardStyle, padding: "20px 24px" }}>
              <NAVLineChart
                classes={fundSummary?.classes?.filter((c) => valuationCurrencyOf(c) === currency) ?? []}
                currency={currency}
                title={`${currency} classes — NAV / share`}
                asOfDate={summary?.as_of_date}
              />
            </div>
          ))}
        </div>

        {/* Right Column: Latest Valuation & Batch Status */}
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          {/* Card 1: Latest Valuation */}
          <div style={{ ...glassCardStyle, padding: "20px 22px" }}>
            <p style={sectionSubheaderStyle}>Latest valuation</p>
            {summary?.as_of_date && (
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--color-text-tertiary)",
                  marginBottom: "12px",
                  fontFamily: "var(--font-mono)",
                }}
              >
                as of {formatDate(summary.as_of_date)}
              </div>
            )}
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Class", "NAV / share", "Total NAV", "Perf"].map((col) => (
                      <th
                        key={col}
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
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(fundSummary?.classes ?? [])
                    .filter((c) => c.current_nav != null)
                    .map((c) => {
                      const perfStr = formatPercent(c.performance_pct);
                      const isPositive = (c.performance_pct ?? 0) >= 0;
                      return (
                        <tr
                          key={c.id ?? c.class_code}
                          style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}
                        >
                          <td style={{ padding: "7px 6px" }}>
                            <span
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: "10px",
                                fontWeight: 700,
                                color: currencyColor(valuationCurrencyOf(c)),
                              }}
                            >
                              {c.class_code}
                            </span>
                          </td>
                          <td
                            style={{
                              padding: "7px 6px",
                              fontFamily: "var(--font-mono)",
                              fontSize: "11px",
                              color: "var(--color-text-primary)",
                            }}
                          >
                            {c.current_nav != null
                              ? formatNumber(shownAmount(valuationCurrencyOf(c), c.current_nav))
                              : "—"}
                          </td>
                          <td
                            style={{
                              padding: "7px 6px",
                              fontFamily: "var(--font-mono)",
                              fontSize: "10px",
                              color: "var(--color-text-secondary)",
                            }}
                          >
                            {c.total_nav != null
                              ? currencyPrefix(shownCurrency(valuationCurrencyOf(c))) +
                                shownAmount(valuationCurrencyOf(c), c.total_nav).toLocaleString("en-US", { maximumFractionDigits: 0 })
                              : "—"}
                          </td>
                          <td
                            style={{
                              padding: "7px 6px",
                              fontFamily: "var(--font-mono)",
                              fontSize: "11px",
                              fontWeight: 600,
                              color: isPositive ? "#22c55e" : "#EF4444",
                            }}
                          >
                            {perfStr ?? "—"}
                          </td>
                        </tr>
                      );
                    })}
                  {(fundSummary?.classes ?? []).filter((c) => c.current_nav != null).length ===
                    0 && (
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
                        No valuation data yet
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Card 2: Batch Status */}
          <div style={{ ...glassCardStyle, padding: "20px 22px" }}>
            <p style={sectionSubheaderStyle}>Batch status</p>
            {linkedBatches.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "20px 0",
                  color: "var(--color-text-tertiary)",
                  fontSize: "12px",
                }}
              >
                No batches linked to this fund
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {linkedBatches.map((b) => {
                  const status = getBatchStatusText(b);
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
                            {status}
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
                          style={{
                            fontSize: "11px",
                            color: "var(--color-text-tertiary)",
                          }}
                        >
                          {b.investors_count} investor{b.investors_count !== 1 ? "s" : ""} ·{" "}
                          {b.total_capital != null
                            ? b.total_capital.toLocaleString("en-US", { maximumFractionDigits: 0 })
                            : "—"}
                        </span>
                        {isOpen && b.auto_close_at ? (
                          <AutoCloseCountdown closeAt={b.auto_close_at} />
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Share Classes Section */}
      <div style={{ marginBottom: "22px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "14px",
          }}
        >
          <Layers size={18} style={{ color: "var(--color-brand-400)" }} />
          <h2
            style={{
              fontSize: "16px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              margin: 0,
            }}
          >
            Share classes
          </h2>
          <span
            style={{
              fontSize: "11px",
              padding: "2px 10px",
              borderRadius: "999px",
              background: "rgba(255,255,255,0.07)",
              color: "var(--color-text-tertiary)",
            }}
          >
            {displayClasses.length}
          </span>
        </div>

        {editingClass && (
          <ShareClassForm
            mode="edit"
            product={product}
            currencies={editContext?.allowed_currencies ?? CLASS_CURRENCIES_BY_PRODUCT[product]}
            initial={{
              class_name: editingClass.class_name,
              class_code: editingClass.class_code,
              currency: editingClass.currency,
              is_active: editingClass.is_active,
            }}
            submitting={classSaving}
            errors={classErrors}
            banner={conflictBanner(classConflict, async () => {
              setClassConflict(null);
              setClassErrors({});
              setOverrideConfirmed(false);
              await loadEditContext();
            })}
            onSubmit={handleSaveClass}
            onCancel={closeEditClass}
            currencyLocked={editingClass.currency_locked}
            currencyLockReasons={editingClass.currency_lock_reasons}
            canOverrideCurrency={!!editContext?.can_override_currency}
            onRequestCurrencyOverride={() => setOverrideOpen(true)}
            currencyOverrideConfirmed={overrideConfirmed}
            openBatches={editingClass.open_batches}
          />
        )}

        {displayClasses.length === 0 ? (
          <div
            style={{
              ...glassCardStyle,
              padding: "40px",
              textAlign: "center",
              color: "var(--color-text-tertiary)",
              fontSize: "13px",
            }}
          >
            No share classes yet
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
              gap: "14px",
            }}
          >
            {displayClasses.map((cls: any) => (
              <div
                key={cls.id ?? cls.class_code}
                style={{ ...glassCardStyle, padding: "20px 22px" }}
              >
                <>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        gap: "10px",
                      }}
                    >
                      <h3
                        style={{
                          fontSize: "14px",
                          fontWeight: 700,
                          color: "var(--color-text-primary)",
                          margin: "0 0 8px 0",
                        }}
                      >
                        {cls.class_name}
                      </h3>
                      {canEdit && cls.id != null && (
                      <button
                        type="button"
                        onClick={() => openEditClass(cls.id)}
                        style={{
                          padding: "4px 8px",
                          borderRadius: "8px",
                          border: "1px solid rgba(255,255,255,0.16)",
                          background: "rgba(255,255,255,0.04)",
                          color: "var(--color-text-secondary)",
                          fontSize: "10px",
                          cursor: "pointer",
                        }}
                      >
                        Edit
                      </button>
                      )}
                    </div>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        flexWrap: "wrap",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "10px",
                          padding: "3px 10px",
                          borderRadius: "999px",
                          background: "rgba(255,255,255,0.08)",
                          color: "var(--color-text-secondary)",
                        }}
                      >
                        {cls.class_code}
                      </span>
                      {cls.currency && <CurrencyBadge currency={cls.currency} />}
                    </div>
                    {"current_nav" in cls && cls.current_nav != null && (
                      <div
                        style={{
                          marginTop: "12px",
                          fontSize: "11px",
                          color: "var(--color-text-tertiary)",
                        }}
                      >
                        NAV / share{" "}
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            color: "var(--color-text-primary)",
                          }}
                        >
                          {formatNumber(cls.current_nav)}
                        </span>
                      </div>
                    )}
                </>
              </div>
            ))}
          </div>
        )}

        {canEdit && inactiveClasses.length > 0 && (
          <div style={{ marginTop: "14px" }}>
            <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "8px" }}>
              Inactive share classes
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
              {inactiveClasses.map((c) => (
                <div
                  key={c.id}
                  style={{
                    ...glassCardStyle,
                    padding: "10px 14px",
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    opacity: 0.75,
                  }}
                >
                  <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
                    {c.class_name} · {c.class_code} · {c.currency}
                  </span>
                  <button
                    type="button"
                    onClick={() => openEditClass(c.id)}
                    style={{
                      padding: "4px 8px",
                      borderRadius: "8px",
                      border: "1px solid rgba(255,255,255,0.16)",
                      background: "rgba(255,255,255,0.04)",
                      color: "var(--color-text-secondary)",
                      fontSize: "10px",
                      cursor: "pointer",
                    }}
                  >
                    Edit
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <CurrencyOverrideDialog
        open={overrideOpen && !!editingClass}
        className={editingClass ? `${editingClass.class_name} (${editingClass.class_code})` : ""}
        reasons={editingClass?.currency_lock_reasons ?? []}
        onClose={() => setOverrideOpen(false)}
        onConfirm={() => {
          setOverrideOpen(false);
          setOverrideConfirmed(true);
          setClassErrors((prev) => {
            const next = { ...prev };
            delete next.currency;
            return next;
          });
        }}
      />

      {/* Deposits vs Withdrawals Bar Chart (if epoch reports exist) */}
      {sortedReports.length > 0 && (
        <div
          style={{
            ...glassCardStyle,
            padding: 0,
            marginBottom: "22px",
            overflow: "hidden",
          }}
        >
          <ChartCard
            title="Deposits vs withdrawals"
            subtitle="Per epoch (fund-scoped reports)"
            legend={[
              { label: "Deposits", color: FLOW_COLORS.deposit },
              { label: "Withdrawals", color: FLOW_COLORS.withdrawal },
            ]}
          >
            <DepositsWithdrawalsBarChart
              data={{
                labels: reportDates,
                deposits: sortedReports.map((r) => r.summary?.total_deposits ?? 0),
                withdrawals: sortedReports.map((r) => r.summary?.total_withdrawals ?? 0),
              }}
            />
          </ChartCard>
        </div>
      )}

      {/* Batches & Investors Table Section */}
      <div style={{ marginBottom: "32px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            marginBottom: "14px",
          }}
        >
          <Layers size={18} style={{ color: "var(--color-brand-400)" }} />
          <h2
            style={{
              fontSize: "16px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              margin: 0,
            }}
          >
            Batches & investors
          </h2>
          {fund?.batches && (
            <span
              style={{
                fontSize: "11px",
                padding: "2px 10px",
                borderRadius: "999px",
                background: "rgba(255,255,255,0.07)",
                color: "var(--color-text-tertiary)",
              }}
            >
              {fund.batches.length}
            </span>
          )}
        </div>

        <div style={{ ...glassCardStyle, padding: 0, overflow: "hidden" }}>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                  <th style={{ width: "40px" }}></th>
                  {["Batch", "Total (batch)", "Investors", "Deployed", "Status"].map((col) => (
                    <th
                      key={col}
                      style={{
                        fontSize: "9px",
                        fontWeight: 600,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        color: "var(--color-text-tertiary)",
                        padding: "12px 16px",
                        textAlign: "left",
                      }}
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fund?.batches && fund.batches.length > 0 ? (
                  fund.batches.map((b) => {
                    const isExpanded = expandedBatchId === b.batch_id;
                    return (
                      <React.Fragment key={b.batch_id}>
                        <tr
                          style={{
                            borderBottom: isExpanded ? "none" : "1px solid rgba(255,255,255,0.04)",
                            cursor: "pointer",
                            background: isExpanded ? "rgba(255,255,255,0.03)" : "transparent",
                          }}
                          onClick={() => toggleBatchInvestors(b.batch_id)}
                        >
                          <td style={{ padding: "12px 16px" }}>
                            {batchLoading && isExpanded ? (
                              <div
                                style={{
                                  width: 14,
                                  height: 14,
                                  border: "2px solid var(--color-border-subtle)",
                                  borderTopColor: "var(--color-brand-400)",
                                  borderRadius: "50%",
                                  animation: "spin 0.8s linear infinite",
                                }}
                              />
                            ) : isExpanded ? (
                              <ChevronUp size={14} style={{ color: "var(--color-brand-400)" }} />
                            ) : (
                              <ChevronDown
                                size={14}
                                style={{ color: "var(--color-text-tertiary)" }}
                              />
                            )}
                          </td>
                          <td style={{ padding: "12px 16px" }}>
                            <span
                              style={{
                                fontWeight: 600,
                                color: "var(--color-text-primary)",
                              }}
                            >
                              {b.batch_name}
                            </span>
                          </td>
                          <td
                            style={{
                              padding: "12px 16px",
                              fontFamily: "var(--font-mono)",
                              fontSize: "12px",
                              color: "var(--color-text-secondary)",
                            }}
                          >
                            {b.total_aum != null
                              ? b.total_aum.toLocaleString("en-US", { maximumFractionDigits: 0 })
                              : "—"}
                          </td>
                          <td style={{ padding: "12px 16px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <Users size={12} style={{ color: "var(--color-text-tertiary)" }} />
                              <span
                                style={{
                                  fontSize: "12px",
                                  color: "var(--color-text-secondary)",
                                }}
                              >
                                {b.investor_count}
                              </span>
                            </div>
                          </td>
                          <td
                            style={{
                              padding: "12px 16px",
                              fontSize: "12px",
                              color: "var(--color-text-tertiary)",
                            }}
                          >
                            {formatDate(b.date_deployed)}
                          </td>
                          <td style={{ padding: "12px 16px" }}>
                            <span
                              style={{
                                fontSize: "10px",
                                fontWeight: 600,
                                padding: "4px 10px",
                                borderRadius: "999px",
                                background: b.is_active
                                  ? "var(--color-success-bg)"
                                  : "rgba(255,255,255,0.06)",
                                color: b.is_active
                                  ? "var(--color-success)"
                                  : "var(--color-text-tertiary)",
                              }}
                            >
                              {b.is_active ? "Active" : "Pending"}
                            </span>
                          </td>
                        </tr>

                        {isExpanded && (
                          <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                            <td colSpan={6} style={{ padding: 0, verticalAlign: "top" }}>
                              <div
                                style={{
                                  background: "rgba(255,255,255,0.025)",
                                  borderTop: "1px solid rgba(255,255,255,0.05)",
                                }}
                              >
                                <div style={{ padding: "12px 16px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
                                  <input
                                    type="text"
                                    value={batchInvestorSearch}
                                    onClick={(e) => e.stopPropagation()}
                                    onChange={(e) => setBatchInvestorSearch(e.target.value)}
                                    placeholder="Search this batch by client code, name, email, or phone…"
                                    style={{
                                      width: "100%",
                                      maxWidth: "420px",
                                      padding: "7px 12px",
                                      fontSize: "12px",
                                      borderRadius: "8px",
                                      border: "1px solid rgba(255,255,255,0.1)",
                                      background: "rgba(0,0,0,0.2)",
                                      color: "var(--color-text-primary)",
                                      outline: "none",
                                    }}
                                  />
                                </div>
                                {batchLoading ? (
                                  <div
                                    style={{
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      gap: "8px",
                                      padding: "20px",
                                      color: "var(--color-text-tertiary)",
                                      fontSize: "13px",
                                    }}
                                  >
                                    Loading…
                                  </div>
                                ) : !batchInvestorSearch.trim() ? (
                                  <div
                                    style={{
                                      padding: "20px 16px",
                                      color: "var(--color-text-tertiary)",
                                      fontSize: "13px",
                                    }}
                                  >
                                    Search above to find an investor in this batch ({b.investor_count} on file).
                                  </div>
                                ) : batchInvestors.length === 0 ? (
                                  <div
                                    style={{
                                      padding: "20px 16px",
                                      color: "var(--color-text-tertiary)",
                                      fontSize: "13px",
                                    }}
                                  >
                                    No matches for "{batchInvestorSearch.trim()}"
                                  </div>
                                ) : (
                                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                    <tbody>
                                      {batchInvestors.map((inv: any) => (
                                        <tr
                                          key={inv.id ?? inv.internal_client_code}
                                          style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
                                        >
                                          <td
                                            style={{
                                              padding: "10px 16px",
                                              fontSize: "12px",
                                              color: "var(--color-text-primary)",
                                            }}
                                          >
                                            {inv.investor_name}
                                          </td>
                                          <td style={{ padding: "10px 16px" }}>
                                            <span
                                              style={{
                                                fontSize: "10px",
                                                padding: "2px 8px",
                                                borderRadius: "999px",
                                                background: "rgba(255,255,255,0.06)",
                                                color: "var(--color-text-secondary)",
                                              }}
                                            >
                                              {inv.internal_client_code}
                                            </span>
                                          </td>
                                          <td
                                            style={{
                                              padding: "10px 16px",
                                              fontSize: "12px",
                                              fontFamily: "var(--font-mono)",
                                              color: "var(--color-text-secondary)",
                                            }}
                                          >
                                            {typeof inv.main_balance === "number"
                                              ? inv.main_balance.toLocaleString("en-US", {
                                                  maximumFractionDigits: 2,
                                                })
                                              : inv.main_balance ?? inv.amount_deposited}
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })
                ) : (
                  <tr>
                    <td
                      colSpan={6}
                      style={{
                        padding: "28px",
                        textAlign: "center",
                        color: "var(--color-text-tertiary)",
                        fontSize: "13px",
                      }}
                    >
                      No batches on record
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <style>
        {`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        @media (max-width: 1100px) {
          .fund-detail-main-grid {
            grid-template-columns: 1fr !important;
          }
          .fund-detail-nav-charts {
            grid-template-columns: 1fr !important;
          }
        }
        @media (max-width: 900px) {
          .fund-detail-kpi-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          }
        }
        @media (max-width: 520px) {
          .fund-detail-kpi-grid {
            grid-template-columns: 1fr !important;
          }
        }
      `}
      </style>
    </div>
  );
}
