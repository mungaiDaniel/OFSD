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
  FundShareClass,
  FundsSummaryResponse,
  ReportSummary,
  Batch,
  BatchInvestor,
} from "@/lib/types";
import { toast } from "sonner";
import { ArrowLeft, Landmark, Layers, ChevronDown, ChevronUp, Users } from "lucide-react";

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

export default function FundDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const fundId = Number(id);

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

  // Edit Share Class State
  const [editingClassId, setEditingClassId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editCode, setEditCode] = useState("");
  const [editCurrency, setEditCurrency] = useState("KES");
  const [editSaving, setEditSaving] = useState(false);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        const res = await Promise.allSettled([
          fundService.getById(fundId),
          fundService.getClasses(fundId),
          fundService.getSummary(),
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
  }, [fundId]);

  const reloadClassesAndFund = async () => {
    const res = await Promise.allSettled([
      fundService.getById(fundId),
      fundService.getClasses(fundId),
      fundService.getSummary(),
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

  const kesClassesWithNav = useMemo(
    () => (fundSummary?.classes ?? []).filter((c) => c.currency === "KES" && c.current_nav != null),
    [fundSummary]
  );

  const usdClassesWithNav = useMemo(
    () => (fundSummary?.classes ?? []).filter((c) => c.currency === "USD" && c.current_nav != null),
    [fundSummary]
  );

  const totalKES = fundSummary?.totals_by_currency?.KES ?? 0;
  const totalUSD = fundSummary?.totals_by_currency?.USD ?? 0;
  const investedKES = fundSummary?.invested_by_currency?.KES ?? 0;
  const investedUSD = fundSummary?.invested_by_currency?.USD ?? 0;
  const gainKES = fundSummary?.gain_by_currency?.KES ?? 0;
  const gainUSD = fundSummary?.gain_by_currency?.USD ?? 0;

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

  const startEditClass = (cls: any) => {
    setEditingClassId(cls.id);
    setEditName(cls.class_name ?? "");
    setEditCode(cls.class_code ?? "");
    setEditCurrency(cls.currency ?? "KES");
  };

  const handleSaveClass = async (classId: number) => {
    if (!editName.trim()) {
      toast.error("Class name is required");
      return;
    }
    if (!editCode.trim()) {
      toast.error("Class code is required");
      return;
    }
    setEditSaving(true);
    try {
      await fundService.updateClass(fundId, classId, {
        class_name: editName.trim(),
        class_code: editCode.trim().toUpperCase(),
        currency: editCurrency,
      });
      toast.success("Share class updated");
      setEditingClassId(null);
      await reloadClassesAndFund();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Failed to update share class");
    } finally {
      setEditSaving(false);
    }
  };

  const handleDeleteFund = async () => {
    if (!fundId || !fund) return;
    if (confirm("Delete this fund? This cannot be undone.")) {
      try {
        await fundService.delete(fundId);
        toast.success("Deleted");
        navigate(ROUTES.FUNDS);
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
        onClick={() => navigate(ROUTES.FUNDS)}
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
        <ArrowLeft size={14} /> Funds
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
            <Landmark size={20} style={{ color: "var(--color-brand-400)" }} />
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

      {/* 4-Column KPI Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
          gap: "14px",
          marginBottom: "22px",
        }}
        className="fund-detail-kpi-grid"
      >
        {/* KPI 1: KES Total AUM */}
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
            Total AUM{" "}
            <span style={{ color: "var(--color-kes)", marginLeft: "4px" }}>KES</span>
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--color-kes)",
              letterSpacing: "-0.02em",
            }}
          >
            {totalKES > 0
              ? totalKES.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })
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
              {kesClassesWithNav.length} class{kesClassesWithNav.length !== 1 ? "es" : ""} w/ NAV
            </span>
            <span style={{ fontFamily: "var(--font-mono)" }}>
              Invested:{" "}
              {investedKES > 0
                ? investedKES.toLocaleString("en-US", { maximumFractionDigits: 2 })
                : "—"}
            </span>
          </div>
          <div
            style={{
              marginTop: "4px",
              fontSize: "11px",
              color: gainKES >= 0 ? "#22c55e" : "#ef4444",
              fontFamily: "var(--font-mono)",
            }}
          >
            Gain/Loss:{" "}
            {totalKES > 0 || investedKES > 0
              ? (gainKES >= 0 ? "+" : "") +
                gainKES.toLocaleString("en-US", { maximumFractionDigits: 2 })
              : "—"}
          </div>
        </div>

        {/* KPI 2: USD Total AUM */}
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
            Total AUM{" "}
            <span style={{ color: "var(--color-usd)", marginLeft: "4px" }}>USD</span>
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "20px",
              fontWeight: 700,
              color: "var(--color-usd)",
              letterSpacing: "-0.02em",
            }}
          >
            {totalUSD > 0
              ? `$ ${totalUSD.toLocaleString("en-US", {
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
              {usdClassesWithNav.length} class{usdClassesWithNav.length !== 1 ? "es" : ""} w/ NAV
            </span>
            <span style={{ fontFamily: "var(--font-mono)" }}>
              Invested:{" "}
              {investedUSD > 0
                ? `$ ${investedUSD.toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                : "—"}
            </span>
          </div>
          <div
            style={{
              marginTop: "4px",
              fontSize: "11px",
              color: gainUSD >= 0 ? "#22c55e" : "#ef4444",
              fontFamily: "var(--font-mono)",
            }}
          >
            Gain/Loss:{" "}
            {totalUSD > 0 || investedUSD > 0
              ? (gainUSD >= 0 ? "+" : "") +
                `$ ${Math.abs(gainUSD).toLocaleString("en-US", { maximumFractionDigits: 2 })}`
              : "—"}
          </div>
        </div>

        {/* KPI 3: Weighted Performance */}
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
            gridTemplateColumns: "1fr 1fr",
            gap: "14px",
          }}
          className="fund-detail-nav-charts"
        >
          <div style={{ ...glassCardStyle, padding: "20px 24px" }}>
            <NAVLineChart
              classes={fundSummary?.classes?.filter((c) => c.currency === "KES") ?? []}
              currency="KES"
              title="KES classes — NAV / share"
              asOfDate={summary?.as_of_date}
            />
          </div>
          <div style={{ ...glassCardStyle, padding: "20px 24px" }}>
            <NAVLineChart
              classes={fundSummary?.classes?.filter((c) => c.currency === "USD") ?? []}
              currency="USD"
              title="USD classes — NAV / share"
              asOfDate={summary?.as_of_date}
            />
          </div>
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
                      const isKES = c.currency === "KES";
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
                                color: isKES ? "var(--color-kes)" : "var(--color-usd)",
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
                            {formatNumber(c.current_nav)}
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
                              ? (isKES ? "KES " : "$ ") +
                                c.total_nav.toLocaleString("en-US", { maximumFractionDigits: 0 })
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
                {editingClassId === cls.id ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    <input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      placeholder="Class name"
                      style={{
                        width: "100%",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: "8px",
                        padding: "8px 10px",
                        color: "var(--color-text-primary)",
                        fontSize: "12px",
                      }}
                    />
                    <input
                      value={editCode}
                      onChange={(e) => setEditCode(e.target.value.toUpperCase())}
                      placeholder="Class code"
                      style={{
                        width: "100%",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: "8px",
                        padding: "8px 10px",
                        color: "var(--color-text-primary)",
                        fontSize: "12px",
                        fontFamily: "var(--font-mono)",
                        textTransform: "uppercase",
                      }}
                    />
                    <select
                      value={editCurrency}
                      onChange={(e) => setEditCurrency(e.target.value)}
                      style={{
                        width: "100%",
                        background: "rgba(255,255,255,0.05)",
                        border: "1px solid rgba(255,255,255,0.12)",
                        borderRadius: "8px",
                        padding: "8px 10px",
                        color: "var(--color-text-primary)",
                        fontSize: "12px",
                      }}
                    >
                      <option value="KES">KES</option>
                      <option value="USD">USD</option>
                    </select>
                    <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                      <button
                        type="button"
                        onClick={() => setEditingClassId(null)}
                        disabled={editSaving}
                        style={{
                          padding: "6px 10px",
                          borderRadius: "8px",
                          border: "1px solid rgba(255,255,255,0.18)",
                          background: "transparent",
                          color: "var(--color-text-secondary)",
                          fontSize: "11px",
                          cursor: editSaving ? "not-allowed" : "pointer",
                        }}
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSaveClass(cls.id)}
                        disabled={editSaving}
                        style={{
                          padding: "6px 10px",
                          borderRadius: "8px",
                          border: "1px solid rgba(59,130,246,0.35)",
                          background: "rgba(59,130,246,0.14)",
                          color: "#60A5FA",
                          fontSize: "11px",
                          fontWeight: 600,
                          cursor: editSaving ? "not-allowed" : "pointer",
                        }}
                      >
                        Save
                      </button>
                    </div>
                  </div>
                ) : (
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
                      <button
                        type="button"
                        onClick={() => startEditClass(cls)}
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
                )}
              </div>
            ))}
          </div>
        )}
      </div>

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
                  {["Batch", "AUM (batch)", "Investors", "Deployed", "Status"].map((col) => (
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
