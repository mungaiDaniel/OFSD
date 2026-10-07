import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { KPICard } from "@/components/data/KPICard";
import { reportService } from "@/services/reportService";
import { investmentService } from "@/services/investmentService";
import { formatCurrency, formatDate, formatPercent } from "@/lib/utils";
import type { ReportDetail } from "@/lib/types";
import { toast } from "sonner";
import { ArrowLeft, FileText, Eye, Download } from "lucide-react";

interface PeriodInvestorMetrics {
  opening: number;
  deposits: number;
  withdrawals: number;
  profit: number;
  closing: number;
}

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const reportId = Number(id);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<{ status: number; message: string } | null>(null);
  const [investorModalOpen, setInvestorModalOpen] = useState(false);
  const [selectedInvestorStatement, setSelectedInvestorStatement] = useState<any>(null);
  const [investorLoading, setInvestorLoading] = useState(false);
  const [statementTitle, setStatementTitle] = useState<string>("");
  const [periodMetricsByClient, setPeriodMetricsByClient] = useState<Record<string, PeriodInvestorMetrics>>({});
  const [periodMetricsLoading, setPeriodMetricsLoading] = useState(false);

  useEffect(() => {
    if (!reportId) return;
    setLoading(true);
    setError(null);
    reportService.getById(reportId)
      .then(setReport)
      .catch((err) => {
        const status = err.response?.status || 500;
        const message = err.response?.data?.message || "Failed to load report";
        setError({ status, message });
        if (status !== 404 && status !== 409) {
          toast.error(message);
        }
      })
      .finally(() => setLoading(false));
  }, [reportId]);

  useEffect(() => {
    const loadPeriodMetrics = async () => {
      if (!report?.investor_breakdown?.length) {
        setPeriodMetricsByClient({});
        return;
      }

      setPeriodMetricsLoading(true);
      try {
        const epochStartTs = new Date(report.epoch_start).getTime();
        const epochEndTs = new Date(report.epoch_end).getTime();
        const records: Record<string, PeriodInvestorMetrics> = {};

        await Promise.all(
          report.investor_breakdown.map(async (inv) => {
            const clientCode = String(inv.internal_client_code || "").trim();
            if (!clientCode) return;

            try {
              const res = await investmentService.getInvestorStatements(clientCode);
              const statements = Array.isArray(res?.data) ? (res.data as any[]) : [];

              const periodRows = statements.filter((row) => {
                const rowTs = new Date(row?.date).getTime();
                return Number.isFinite(rowTs) && rowTs >= epochStartTs && rowTs <= epochEndTs;
              });

              const monthlyRow =
                periodRows.find((row) => row?.type === "MONTHLY_REPORT") ??
                statements.find((row) => {
                  if (row?.type !== "MONTHLY_REPORT") return false;
                  const rowTs = new Date(row?.date).getTime();
                  return Number.isFinite(rowTs) && rowTs >= epochStartTs && rowTs <= epochEndTs;
                });

              const opening = Number(monthlyRow?.opening_balance ?? 0);
              const deposits = periodRows
                .filter((row) => row?.type === "DEPOSIT")
                .reduce((sum, row) => sum + Number(row?.deposits ?? 0), 0);
              const withdrawals = periodRows
                .filter((row) => row?.type === "WITHDRAWAL")
                .reduce((sum, row) => sum + Number(row?.withdrawals ?? 0), 0);
              const profit = Number(monthlyRow?.profit ?? 0);

              let closing = Number(monthlyRow?.end_balance ?? 0);
              if (!closing) {
                const latestInPeriod = [...periodRows].sort(
                  (a, b) => new Date(b?.date).getTime() - new Date(a?.date).getTime()
                )[0];
                closing = Number(latestInPeriod?.end_balance ?? opening + deposits - withdrawals + profit);
              }

              records[clientCode] = { opening, deposits, withdrawals, profit, closing };
            } catch {
              // Fallback to report breakdown row for resiliency on a per-investor failure.
              records[clientCode] = {
                opening: Number(inv.start_balance ?? 0),
                deposits: Number(inv.deposits ?? 0),
                withdrawals: Number(inv.withdrawals ?? 0),
                profit: Number(inv.pro_rata_profit ?? 0),
                closing: Number(inv.end_balance ?? 0),
              };
            }
          })
        );

        setPeriodMetricsByClient(records);
      } finally {
        setPeriodMetricsLoading(false);
      }
    };

    loadPeriodMetrics();
  }, [report]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-96">
        <div className="w-10 h-10 border-4 rounded-full animate-spin mb-4" style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }} />
        <p className="text-sm animate-pulse" style={{ color: "var(--color-text-tertiary)" }}>Fetching committed valuation records...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-96 text-center px-6">
        <div className="w-16 h-16 rounded-full flex items-center justify-center mb-6" style={{ background: error.status === 409 ? "rgba(239, 68, 68, 0.1)" : "var(--color-bg-surface-alt)" }}>
          <FileText size={32} style={{ color: error.status === 409 ? "var(--color-destructive)" : "var(--color-text-tertiary)" }} />
        </div>
        <h2 className="fs-5 fw-bold mb-2" style={{ color: "var(--color-text-primary)" }}>
          {error.status === 409 ? "Security & Reconciliation Alert" : "Report Not Found"}
        </h2>
        <p className="text-sm max-w-md mb-8" style={{ color: "var(--color-text-secondary)" }}>
          {error.status === 404 
            ? "No Committed Data Found for this Epoch. Please ensure the valuation validation has been finalized and committed."
            : error.message}
        </p>
        <button 
          onClick={() => navigate("/reports")}
          className="rounded-md px-4 py-2 text-sm font-medium cursor-pointer"
          style={{ background: "var(--color-brand-500)", color: "white" }}
        >
          Back to Reports
        </button>
      </div>
    );
  }

  if (!report) return null;

  const periodRows = report.investor_breakdown || [];
  const computedPeriodSummary = periodRows.reduce(
    (acc, inv) => {
      const clientCode = String(inv.internal_client_code || "").trim();
      const period = periodMetricsByClient[clientCode];
      const opening = Number(period?.opening ?? inv.start_balance ?? 0);
      const deposits = Number(period?.deposits ?? inv.deposits ?? 0);
      const withdrawals = Number(period?.withdrawals ?? inv.withdrawals ?? 0);
      const profit = Number(period?.profit ?? inv.pro_rata_profit ?? 0);
      const closing = Number(period?.closing ?? inv.end_balance ?? 0);
      acc.total_opening_capital += opening;
      acc.total_deposits += deposits;
      acc.total_withdrawals += withdrawals;
      acc.total_profit_distributed += profit;
      acc.total_closing_aum += closing;
      return acc;
    },
    {
      total_opening_capital: 0,
      total_deposits: 0,
      total_withdrawals: 0,
      total_profit_distributed: 0,
      total_closing_aum: 0,
      investor_count: periodRows.length,
    }
  );

  const s = computedPeriodSummary;
  const reconciliationDiff = report.reconciliation_diff ?? 0;
  const diffPositive = reconciliationDiff >= 0;

  const openInvestorStatement = async (
    investorEmail: string | null | undefined,
    batchId: number | null | undefined
  ) => {
    if (!investorEmail) {
      toast.error("Investor email not available");
      return;
    }
    if (!batchId) {
      toast.error("Batch ID not available");
      return;
    }

    setInvestorLoading(true);
    setInvestorModalOpen(true);
    setStatementTitle(`Individual Statement - ${investorEmail}`);

    try {
      const statement = await reportService.getInvestorStatement(batchId, investorEmail, report?.id);
      setSelectedInvestorStatement(statement);
    } catch (error: any) {
      const errorMsg = error?.response?.data?.message || "Failed to load investor statement";
      toast.error(errorMsg);
      setSelectedInvestorStatement(null);
    } finally {
      setInvestorLoading(false);
    }
  };

  const openBatchStatement = async () => {
    if (!report) return;

    setInvestorLoading(true);
    setInvestorModalOpen(true);
    setStatementTitle(`Batch Statement - ${report.fund_name}`);

    try {
      // Get all investor data from the report and format as batch summary
      const batchSummary = {
        fund_name: report.fund_name,
        batch_id: report.batch_id,
        epoch_start: report.epoch_start,
        epoch_end: report.epoch_end,
        performance_rate_percent: report.performance_rate_percent,
        head_office_total: report.head_office_total,
        summary: report.summary,
        investor_breakdown: report.investor_breakdown,
        reconciliation_diff: report.reconciliation_diff,
      };
      setSelectedInvestorStatement(batchSummary);
    } catch (error) {
      setSelectedInvestorStatement(null);
      toast.error("Failed to load batch statement");
    } finally {
      setInvestorLoading(false);
    }
  };

  const closeInvestorModal = () => {
    setInvestorModalOpen(false);
    setSelectedInvestorStatement(null);
  };

  const downloadInvestorStatement = async (
    investorEmail: string | null | undefined,
    batchId: number | null | undefined,
    internalClientCode?: string | null
  ) => {
    const normalizedClientCode = String(internalClientCode || "").trim();
    if (!normalizedClientCode) {
      if (!investorEmail) {
        toast.error("Investor email is required");
      } else if (!batchId) {
        toast.error("Batch ID is required");
      } else {
        toast.error("Investor client code is required");
      }
      return;
    }

    try {
      // Use unified client statement endpoint with as_of to match this exact report period layout.
      await reportService.downloadInvestorStatementByClientCode(normalizedClientCode, report.epoch_end);
      toast.success("Investor statement PDF downloaded successfully");
    } catch (error) {
      toast.error("Failed to download investor statement. Please try again.");
    }
  };

  return (
    <div>
      <button onClick={() => navigate("/reports")} className="flex items-center gap-1 text-[12px] mb-3 cursor-pointer" style={{ color: "var(--color-text-tertiary)" }}><ArrowLeft size={14} /> Reports</button>

      <div className="d-flex align-items-start justify-content-between mb-3">
        <div>
          <h1 className="fw-bold mb-1" style={{ fontSize: "22px", color: "var(--color-text-primary)" }}>{report.fund_name} — Epoch report</h1>
          <p className="mb-0" style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>{formatDate(report.epoch_start)} → {formatDate(report.epoch_end)} · {formatPercent(report.performance_rate_percent)} rate</p>
        </div>
        <div className="d-flex gap-2">
          <button
            onClick={openBatchStatement}
            className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12px] font-medium cursor-pointer"
            style={{ background: "#00005b", color: "white", border: "none", borderRadius: "12px" }}
            title="View batch statement"
          >
            <Eye size={14} /> View
          </button>
          <button
            onClick={async () => {
              try {
                await reportService.downloadPdf(reportId);
                toast.success("Report PDF downloaded successfully");
              } catch (error) {
                toast.error("Failed to download report PDF");
              }
            }}
            className="flex items-center gap-1.5 rounded-md px-3 py-2 text-[12px] font-medium cursor-pointer"
            style={{ background: "#00005b", color: "white", border: "none", borderRadius: "12px" }}
            title="Download report PDF"
          >
            <FileText size={14} /> Download
          </button>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="row gx-2 gy-2 mb-4">
        <div className="col-12 col-md-6 col-lg-2">
          <KPICard valueSize="1.0 rem" label="Opening capital" value={formatCurrency(s.total_opening_capital)} />
        </div>
        <div className="col-12 col-md-6 col-lg-2">
          <KPICard valueSize="1.0 rem" label="Deposits" value={formatCurrency(s.total_deposits)} />
        </div>
        <div className="col-12 col-md-6 col-lg-2">
          <KPICard valueSize="1.0 rem" label="Withdrawals" value={formatCurrency(s.total_withdrawals)} />
        </div>
        <div className="col-12 col-md-6 col-lg-2">
          <KPICard valueSize="1.0 rem" label="Profit distributed" value={formatCurrency(s.total_profit_distributed)} />
        </div>
        <div className="col-12 col-md-6 col-lg-2">
          <KPICard valueSize="1.0 rem" label="Closing AUM" value={formatCurrency(s.total_closing_aum)} />
        </div>
        <div className="col-12 col-md-6 col-lg-2">
          <KPICard valueSize="1.0 rem" label="Investors" value={String(s.investor_count)} />
        </div>
      </div>
      {periodMetricsLoading && (
        <p className="mb-3" style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>
          Refreshing period totals from historical statements...
        </p>
      )}

      {/* Reconciliation */}
      <div className="rounded-lg p-3 p-md-5 mb-4 d-flex flex-column flex-sm-row align-items-stretch align-items-sm-center justify-content-between gap-3" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
        <div>
          <p className="text-xs font-medium" style={{ color: "var(--color-text-secondary)" }}>Reconciliation difference</p>
          <p className="text-sm mt-0.5" style={{ color: "var(--color-text-tertiary)" }}>Local closing AUM vs head office total ({formatCurrency(report.head_office_total)})</p>
        </div>
        <p className="text-lg fw-bold" style={{ fontFamily: "var(--font-mono)", color: diffPositive ? "var(--color-success)" : "var(--color-destructive)" }}>
          {diffPositive ? "+" : ""}{formatCurrency(reconciliationDiff)}
        </p>
      </div>

      {/* Investor breakdown */}
      <div className="card shadow-sm rounded-4 overflow-hidden border-0" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
        <div className="px-4 py-3 border-bottom" style={{ borderColor: "var(--color-border-subtle)" }}>
          <div className="page-header-row align-items-start">
            <h3 className="fw-bold mb-1" style={{ fontSize: "16px", color: "var(--color-text-primary)" }}>Investor breakdown ({report.investor_breakdown?.length || 0})</h3>
            <span className="badge rounded-pill align-self-start" style={{ background: "rgba(0, 0, 91, 0.08)", color: "#00005b", fontSize: "11px" }} title="Opening balances include compound growth from previous epochs">
              Compound Growth Applied
            </span>
          </div>
          <p className="mb-0" style={{ fontSize: "12px", color: "var(--color-text-secondary)", lineHeight: 1.4 }}>Opening Balance = Previous Epoch Closing + New Deposits; Profit = (Opening + Mid-Period Deposits - Withdrawals) × Rate</p>
        </div>
        <div className="table-responsive">
          <table className="table table-sm table-hover table-dark mb-0" style={{ fontSize: "12px", minWidth: "100%", backgroundColor: "transparent" }}>
            <thead>
              <tr>
                {["Investor", "Client code", "Start balance*", "Deposits", "Withdrawals", "Profit", "End balance", "Actions"].map((h) => (
                  <th key={h} className="text-uppercase" style={{ color: "var(--color-text-secondary)", padding: "0.55rem 0.75rem", textAlign: h === "Actions" || (h !== "Investor" && h !== "Client code") ? "right" : "left" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
            {(report.investor_breakdown || []).map((inv, i) => {
              const clientCode = String(inv.internal_client_code || "").trim();
              const period = periodMetricsByClient[clientCode];
              const opening = Number(period?.opening ?? inv.start_balance ?? 0);
              const deposits = Number(period?.deposits ?? inv.deposits ?? 0);
              const withdrawals = Number(period?.withdrawals ?? inv.withdrawals ?? 0);
              const profit = Number(period?.profit ?? inv.pro_rata_profit ?? 0);
              const closing = Number(period?.closing ?? inv.end_balance ?? 0);
              return (
              <tr key={i} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                <td className="px-4 py-2.5 text-[13px] font-medium">{inv.investor_name}</td>
                <td className="px-4 py-2.5 text-[12px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-secondary)" }}>{inv.internal_client_code}</td>
                <td className="px-4 py-2.5 text-right text-[12px] font-medium" style={{ fontFamily: "var(--font-mono)", background: "rgba(0, 0, 91, 0.03)", color: "#00005b" }}>{formatCurrency(opening)}</td>
                <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-success)" }}>{formatCurrency(deposits)}</td>
                <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-destructive)" }}>{formatCurrency(withdrawals)}</td>
                <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)", color: profit >= 0 ? "var(--color-success)" : "var(--color-destructive)" }}>{formatCurrency(profit)}</td>
                <td className="px-4 py-2.5 text-right text-[12px] font-medium" style={{ fontFamily: "var(--font-mono)", background: "rgba(0, 0, 91, 0.05)" }}>{formatCurrency(closing)}</td>
                <td className="px-4 py-2.5 text-right text-[12px] flex gap-2 justify-end">
                  <button
                    onClick={(e) => { e.stopPropagation(); openInvestorStatement(inv.investor_email, inv.batch_id); }}
                    className="px-2 py-1 rounded text-xs font-medium transition-colors hover:bg-blue-500 hover:text-white"
                    style={{ background: "rgba(0, 0, 91, 0.1)", color: "#00005b" }}
                    title="View investor statement"
                  >
                    <Eye size={14} />
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); downloadInvestorStatement(inv.investor_email, inv.batch_id, inv.internal_client_code); }}
                    className="px-2 py-1 rounded text-xs font-medium transition-colors hover:bg-blue-500 hover:text-white"
                    style={{ background: "rgba(0, 0, 91, 0.1)", color: "#00005b" }}
                    title="Download investor statement"
                  >
                    <Download size={14} />
                  </button>
                </td>
              </tr>
            )})}
            {(!report.investor_breakdown || report.investor_breakdown.length === 0) && <tr><td colSpan={8} className="px-4 py-12 text-center text-sm" style={{ color: "var(--color-text-tertiary)" }}>No investor data for this report.</td></tr>}
          </tbody>
        </table>
        <div className="px-5 py-2.5 border-t text-[11px]" style={{ borderColor: "var(--color-border-subtle)", color: "var(--color-text-tertiary)" }}>
          * Start balance reflects compound growth from previous epochs. End balance becomes next epoch's opening balance.
        </div>
      </div>

      {investorModalOpen && (
        <div className="modal show d-block" style={{ backgroundColor: "rgba(0,0,0,0.5)" }} onClick={closeInvestorModal}>
          <div className="modal-dialog modal-lg" onClick={(e) => e.stopPropagation()}>
            <div className="modal-content" style={{ background: "var(--color-bg-surface)", color: "var(--color-text-primary)" }}>
              <div className="modal-header" style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                <h5 className="modal-title">{statementTitle}</h5>
                <button type="button" className="btn-close" onClick={closeInvestorModal}></button>
              </div>
              <div className="modal-body" style={{ maxHeight: "70vh", overflowY: "auto" }}>
                {investorLoading ? (
                  <div className="d-flex align-items-center justify-content-center py-5">
                    <div className="spinner-border spinner-border-sm" style={{ color: "var(--color-brand-400)" }} role="status">
                      <span className="visually-hidden">Loading...</span>
                    </div>
                  </div>
                ) : selectedInvestorStatement ? (
                  <div>
                    {selectedInvestorStatement.investor_breakdown ? (
                      // Batch Statement View
                      <div>
                        <div className="mb-4 p-3 rounded" style={{ background: "var(--color-bg-surface-alt)" }}>
                          <div className="row">
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Fund Name</p>
                              <p className="font-medium">{selectedInvestorStatement.fund_name}</p>
                            </div>
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Batch ID</p>
                              <p className="font-medium">{selectedInvestorStatement.batch_id || "N/A"}</p>
                            </div>
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Epoch Period</p>
                              <p className="font-medium text-sm">{formatDate(selectedInvestorStatement.epoch_start)} → {formatDate(selectedInvestorStatement.epoch_end)}</p>
                            </div>
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Performance Rate</p>
                              <p className="font-medium">{formatPercent(selectedInvestorStatement.performance_rate_percent)}</p>
                            </div>
                          </div>
                        </div>
                        <div className="table-responsive">
                          <table className="table table-sm" style={{ fontSize: "12px" }}>
                            <thead style={{ background: "var(--color-bg-surface-alt)" }}>
                              <tr>
                                <th style={{ color: "var(--color-text-secondary)" }}>Investor</th>
                                <th style={{ color: "var(--color-text-secondary)" }}>Client Code</th>
                                <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Start</th>
                                <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Deposits</th>
                                <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Withdrawals</th>
                                <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Profit</th>
                                <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>End Balance</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selectedInvestorStatement.investor_breakdown?.map((inv: any, i: number) => (
                                <tr key={i}>
                                  <td>{inv.investor_name}</td>
                                  <td style={{ fontFamily: "monospace", fontSize: "11px" }}>{inv.internal_client_code}</td>
                                  <td className="text-right" style={{ fontFamily: "monospace" }}>{formatCurrency(inv.start_balance)}</td>
                                  <td className="text-right" style={{ fontFamily: "monospace", color: "var(--color-success)" }}>{formatCurrency(inv.deposits)}</td>
                                  <td className="text-right" style={{ fontFamily: "monospace", color: "var(--color-destructive)" }}>{formatCurrency(inv.withdrawals)}</td>
                                  <td className="text-right" style={{ fontFamily: "monospace", color: inv.pro_rata_profit >= 0 ? "var(--color-success)" : "var(--color-destructive)" }}>{formatCurrency(inv.pro_rata_profit)}</td>
                                  <td className="text-right" style={{ fontFamily: "monospace", fontWeight: "bold" }}>{formatCurrency(inv.end_balance)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : (
                      // Individual Investor Statement View
                      <div>
                        <div className="mb-4 p-3 rounded" style={{ background: "var(--color-bg-surface-alt)" }}>
                          <div className="row">
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Investor Email</p>
                              <p className="font-medium text-sm">{selectedInvestorStatement.investor_email}</p>
                            </div>
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Investor Name</p>
                              <p className="font-medium">{selectedInvestorStatement.investor_name || "N/A"}</p>
                            </div>
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Batch Name</p>
                              <p className="font-medium">{selectedInvestorStatement.batch_name || "N/A"}</p>
                            </div>
                            <div className="col-md-6 mb-2">
                              <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Generated</p>
                              <p className="font-medium text-sm">{new Date().toLocaleDateString()}</p>
                            </div>
                          </div>
                        </div>
                        {selectedInvestorStatement.funds && selectedInvestorStatement.funds.length > 0 ? (
                          <div className="table-responsive">
                            <h6 className="mb-3" style={{ color: "var(--color-text-primary)" }}>Fund Holdings</h6>
                            <table className="table table-sm" style={{ fontSize: "12px" }}>
                              <thead style={{ background: "var(--color-bg-surface-alt)" }}>
                                <tr>
                                  <th style={{ color: "var(--color-text-secondary)" }}>Fund</th>
                                  <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Opening Balance</th>
                                  <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Performance Gain</th>
                                  <th className="text-right" style={{ color: "var(--color-text-secondary)" }}>Closing Balance</th>
                                </tr>
                              </thead>
                              <tbody>
                                {selectedInvestorStatement.funds.map((fund: any, i: number) => (
                                  <tr key={i}>
                                    <td>{fund.fund_name}</td>
                                    <td className="text-right" style={{ fontFamily: "monospace" }}>{formatCurrency(fund.opening_balance)}</td>
                                    <td className="text-right" style={{ fontFamily: "monospace", color: fund.performance_gain >= 0 ? "var(--color-success)" : "var(--color-destructive)" }}>{formatCurrency(fund.performance_gain)}</td>
                                    <td className="text-right" style={{ fontFamily: "monospace", fontWeight: "bold" }}>{formatCurrency(fund.closing_balance)}</td>
                                  </tr>
                                ))}
                                {selectedInvestorStatement.summary && (
                                  <tr style={{ background: "var(--color-bg-surface-alt)", fontWeight: "bold" }}>
                                    <td style={{ fontWeight: "bold" }}>TOTAL</td>
                                    <td className="text-right" style={{ fontFamily: "monospace" }}>{formatCurrency(selectedInvestorStatement.summary.total_opening_balance)}</td>
                                    <td className="text-right" style={{ fontFamily: "monospace", color: selectedInvestorStatement.summary.total_performance_gain >= 0 ? "var(--color-success)" : "var(--color-destructive)" }}>{formatCurrency(selectedInvestorStatement.summary.total_performance_gain)}</td>
                                    <td className="text-right" style={{ fontFamily: "monospace", color: "var(--color-brand-500)" }}>{formatCurrency(selectedInvestorStatement.summary.total_closing_balance)}</td>
                                  </tr>
                                )}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <pre style={{ fontSize: "11px", background: "var(--color-bg-input)", padding: "15px", borderRadius: "4px", overflow: "auto" }}>
                            {JSON.stringify(selectedInvestorStatement, null, 2)}
                          </pre>
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  <p style={{ color: "var(--color-text-secondary)" }}>No statement available.</p>
                )}
              </div>
              <div className="modal-footer" style={{ borderTop: "1px solid var(--color-border-subtle)" }}>
                {selectedInvestorStatement && !selectedInvestorStatement.investor_breakdown && statementTitle.includes("Individual") && (
                  <button 
                    type="button" 
                    className="btn btn-primary" 
                    onClick={async () => {
                      const email = selectedInvestorStatement.investor_email;
                      const batchId = selectedInvestorStatement.batch_id;
                      const clientCode = selectedInvestorStatement.internal_client_code;
                      if (batchId) {
                        await downloadInvestorStatement(email, batchId, clientCode);
                      }
                    }}
                    style={{ background: "var(--color-brand-500)" }}
                  >
                    <Download size={14} className="me-1" /> Download PDF
                  </button>
                )}
                <button type="button" className="btn btn-secondary" onClick={closeInvestorModal}>Close</button>
              </div>
            </div>
          </div>
        </div>
      )}

    </div>
    </div>
  );
}
