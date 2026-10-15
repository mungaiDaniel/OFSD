import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { createPerformanceSchema, type CreatePerformanceFormData } from "@/lib/validators/performance.schema";
import { performanceService } from "@/services/performanceService";
import { batchService } from "@/services/batchService";
import { valuationService } from "@/services/valuationService";
import { formatCurrency, formatDate } from "@/lib/utils";
import { ROUTES, STAGE_LABELS } from "@/lib/constants";
import type { Batch, Performance, BatchValuationHistoryPoint, BatchDistributionRow } from "@/lib/types";
import { toast } from "sonner";
import { PortfolioAUMChart } from "@/components/charts/PortfolioAUMChart";
import { DepositsWithdrawalsBarChart } from "@/components/charts/DepositsWithdrawalsBarChart";
import * as XLSX from "xlsx";
import { ArrowLeft, Upload, FileSpreadsheet, Play, Download, ChevronDown, ChevronUp, TrendingUp } from "lucide-react";

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border p-3" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
      <div className="text-[9px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--color-text-tertiary)" }}>{label}</div>
      <div className="text-sm font-bold" style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}>{value}</div>
      {sub && <div className="text-[10px] mt-0.5" style={{ color: "var(--color-text-tertiary)" }}>{sub}</div>}
    </div>
  );
}

export default function BatchPerformancePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const batchId = Number(id);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [performances, setPerformances] = useState<Performance[]>([]);
  const [valuationHistory, setValuationHistory] = useState<BatchValuationHistoryPoint[]>([]);
  const [distributions, setDistributions] = useState<BatchDistributionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [entrySectionOpen, setEntrySectionOpen] = useState(false);
  const [tab, setTab] = useState<"manual" | "upload">("manual");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<CreatePerformanceFormData>({
    resolver: zodResolver(createPerformanceSchema),
  });

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [b, p, vh, d] = await Promise.allSettled([
          batchService.getById(batchId),
          performanceService.getByBatch(batchId),
          valuationService.getBatchValuationHistory(batchId),
          performanceService.getDistributions(batchId),
        ]);
        if (b.status === "fulfilled") setBatch(b.value);
        if (p.status === "fulfilled") setPerformances((p.value as any).data || []);
        if (vh.status === "fulfilled") setValuationHistory(vh.value);
        if (d.status === "fulfilled") setDistributions(d.value);
      } finally {
        setLoading(false);
      }
    }
    if (batchId) load();
  }, [batchId]);

  const onManualSubmit = async (data: CreatePerformanceFormData) => {
    try {
      await performanceService.create(batchId, data);
      toast.success("Performance data recorded");
      const res = await performanceService.getByBatch(batchId);
      setPerformances((res as any).data || []);
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Failed to save performance");
    }
  };

  const onProRata = async (fundName: string) => {
    try {
      await performanceService.calculateProRata(batchId, fundName);
      toast.success(`Pro-rata calculated for ${fundName}`);
      const rows = await performanceService.getDistributions(batchId);
      setDistributions(rows);
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Pro-rata calculation failed");
    }
  };

  const onExcelUpload = async () => {
    if (!selectedFile) return;
    setUploading(true);
    try {
      await performanceService.uploadExcel(selectedFile);
      toast.success("Performance Excel uploaded");
      setSelectedFile(null);
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onExportDistributions = () => {
    const rows = distributions.map((d) => ({
      Fund: d.fund_name,
      Investor: d.investor_name,
      "Client Code": d.internal_client_code,
      Email: d.investor_email,
      "Amount Deposited": d.amount_deposited,
      "Days Active": d.days_active,
      "Weighted Capital": d.weighted_capital,
      "Profit Share %": d.profit_share_percentage,
      "Profit Allocated": d.profit_allocated,
    }));
    const sheet = XLSX.utils.json_to_sheet(rows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, sheet, "Distributions");
    XLSX.writeFile(workbook, `batch-${batchId}-distributions.xlsx`);
  };

  const inputStyle = { background: "var(--color-bg-input)", borderColor: "var(--color-border-default)", color: "var(--color-text-primary)" };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }} /></div>;
  }

  // Real, already-committed NAV valuation history — never a new calculation
  // triggered by viewing this page. Feeds the two trend charts below.
  const aumChartData = {
    labels: valuationHistory.map((v) => formatDate(v.period_end_date)),
    funds: [{
      name: batch?.batch_name || "Batch",
      data: valuationHistory.map((v) => v.balance_at_end_of_period),
      growth: valuationHistory.map((v) => v.performance_rate * 100),
    }],
  };
  const principalProfitData = {
    labels: valuationHistory.map((v) => formatDate(v.period_end_date)),
    deposits: [],
    withdrawals: [],
  };
  const principalProfitDatasets = [
    { label: "Total Principal", data: valuationHistory.map((v) => v.total_principal), backgroundColor: "#0066ff" },
    { label: "Total Profit", data: valuationHistory.map((v) => v.total_profit), backgroundColor: "#22c55e" },
  ];

  return (
    <div>
      <button onClick={() => navigate(ROUTES.BATCH_DETAIL(batchId))} className="flex items-center gap-1 text-[12px] mb-3 cursor-pointer" style={{ color: "var(--color-text-tertiary)" }}>
        <ArrowLeft size={14} /> {batch?.batch_name || "Batch"}
      </button>

      <h1 className="text-sm fw-bold mb-1" style={{ color: "var(--color-text-primary)" }}>Performance</h1>
      <p className="text-xs mb-4" style={{ color: "var(--color-text-secondary)" }}>Overall performance and recorded data for this batch</p>

      {/* Summary cards */}
      {batch && (
        <div className="grid gap-3 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))" }}>
          <SummaryCard label="Current Capital" value={formatCurrency(batch.total_capital)} sub="Live standing" />
          <SummaryCard label="Total Deposited" value={formatCurrency(batch.total_principal)} sub="Raw gross deposits" />
          <SummaryCard label="Investors" value={String(batch.investors_count)} />
          <SummaryCard label="Stage" value={STAGE_LABELS[batch.stage]} />
          <SummaryCard label="Product" value={batch.product_type || "—"} />
          <SummaryCard label="Deployed" value={batch.date_deployed ? formatDate(batch.date_deployed) : "—"} />
        </div>
      )}

      {/* Trend charts — real NAV valuation history, read-only */}
      {valuationHistory.length > 0 ? (
        <div className="grid gap-4 mb-4" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))" }}>
          <div className="rounded-lg border p-4" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
            <h3 className="text-xs font-bold mb-3 flex items-center gap-1.5" style={{ color: "var(--color-text-primary)" }}>
              <TrendingUp size={14} /> Capital &amp; Growth
            </h3>
            <PortfolioAUMChart data={aumChartData} height={240} />
          </div>
          <div className="rounded-lg border p-4" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
            <h3 className="text-xs font-bold mb-3" style={{ color: "var(--color-text-primary)" }}>Principal vs Profit per period</h3>
            <DepositsWithdrawalsBarChart data={principalProfitData} datasets={principalProfitDatasets} height={240} />
          </div>
        </div>
      ) : (
        <div className="rounded-lg border p-4 mb-4 text-xs" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)", color: "var(--color-text-tertiary)" }}>
          No NAV valuation history yet for this batch — trend charts will appear here once a valuation has been committed.
        </div>
      )}

      {/* Per-investor distributions — already-computed, display + download only */}
      {distributions.length > 0 && (
        <div className="rounded-lg border overflow-hidden mb-4" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
          <div className="px-3 px-md-5 py-3 border-b flex items-center justify-between" style={{ borderColor: "var(--color-border-subtle)" }}>
            <h3 className="text-sm fw-bold" style={{ color: "var(--color-text-primary)" }}>Investor distributions ({distributions.length})</h3>
            <button onClick={onExportDistributions} className="flex items-center gap-1.5 text-[11px] font-medium cursor-pointer px-2.5 py-1.5 rounded" style={{ background: "var(--color-brand-50)", color: "var(--color-brand-300)" }}>
              <Download size={12} /> Export to Excel
            </button>
          </div>
          <div className="app-table-scroll">
            <table className="w-full" style={{ minWidth: "720px" }}>
              <thead>
                <tr style={{ background: "var(--color-bg-surface-alt)" }}>
                  {["Fund", "Investor", "Client Code", "Deposited", "Days Active", "Profit Share %", "Profit Allocated"].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-[11px] fw-bold uppercase tracking-wider border-b" style={{ color: "var(--color-text-secondary)", borderColor: "var(--color-border-subtle)", textAlign: ["Deposited", "Days Active", "Profit Share %", "Profit Allocated"].includes(h) ? "right" : "left" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {distributions.map((d) => (
                  <tr key={d.distribution_id} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                    <td className="px-4 py-2.5 text-[12px]">{d.fund_name}</td>
                    <td className="px-4 py-2.5 text-[13px] font-medium">{d.investor_name}</td>
                    <td className="px-4 py-2.5 text-[12px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-secondary)" }}>{d.internal_client_code}</td>
                    <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)" }}>{formatCurrency(d.amount_deposited)}</td>
                    <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)" }}>{d.days_active}</td>
                    <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)" }}>{d.profit_share_percentage.toFixed(2)}%</td>
                    <td className="px-4 py-2.5 text-right text-[12px] font-medium" style={{ fontFamily: "var(--font-mono)", color: "var(--color-success)" }}>{formatCurrency(d.profit_allocated)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Recorded performance entries */}
      {performances.length > 0 && (
        <div className="rounded-lg border overflow-hidden mb-4" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
          <div className="px-3 px-md-5 py-3 border-b" style={{ borderColor: "var(--color-border-subtle)" }}>
            <h3 className="text-sm fw-bold" style={{ color: "var(--color-text-primary)" }}>Recorded performance ({performances.length})</h3>
          </div>
          <div className="app-table-scroll">
          <table className="w-full" style={{ minWidth: "520px" }}>
            <thead>
              <tr style={{ background: "var(--color-bg-surface-alt)" }}>
                {["Fund", "Gross profit", "Costs", "Net profit", "Date", ""].map((h) => (
                  <th key={h} className="text-left px-4 py-2.5 text-[11px] fw-bold uppercase tracking-wider border-b" style={{ color: "var(--color-text-secondary)", borderColor: "var(--color-border-subtle)", textAlign: ["Gross profit", "Costs", "Net profit"].includes(h) ? "right" : "left" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {performances.map((p) => (
                <tr key={p.performance_id} style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
                  <td className="px-4 py-2.5 text-[13px] font-medium">{p.fund_name || "—"}</td>
                  <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-success)" }}>{formatCurrency(p.gross_profit)}</td>
                  <td className="px-4 py-2.5 text-right text-[12px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-destructive)" }}>{formatCurrency(p.transaction_costs)}</td>
                  <td className="px-4 py-2.5 text-right text-[12px] font-medium" style={{ fontFamily: "var(--font-mono)" }}>{formatCurrency(p.net_profit)}</td>
                  <td className="px-4 py-2.5 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>{formatDate(p.date_created)}</td>
                  <td className="px-4 py-2.5">
                    {p.fund_name && (
                      <button onClick={() => onProRata(p.fund_name)} className="flex items-center gap-1 text-[11px] font-medium cursor-pointer px-2.5 py-1 rounded" style={{ background: "var(--color-brand-50)", color: "var(--color-brand-300)" }}>
                        <Play size={10} /> Pro-rata
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Entry form — collapsed by default; this page opens display-first */}
      <div className="max-w-xl rounded-lg border" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
        <button
          onClick={() => setEntrySectionOpen((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 cursor-pointer"
          style={{ background: "transparent", border: "none" }}
        >
          <span className="text-xs font-bold" style={{ color: "var(--color-text-primary)" }}>Record new performance data</span>
          {entrySectionOpen ? <ChevronUp size={14} style={{ color: "var(--color-text-tertiary)" }} /> : <ChevronDown size={14} style={{ color: "var(--color-text-tertiary)" }} />}
        </button>

        {entrySectionOpen && (
          <>
            <div className="flex border-t border-b" style={{ borderColor: "var(--color-border-subtle)" }}>
              {(["manual", "upload"] as const).map((t) => (
                <button key={t} onClick={() => setTab(t)} className="flex-1 py-3 text-[13px] font-medium cursor-pointer border-b-2 transition-colors" style={{ borderColor: tab === t ? "var(--color-brand-400)" : "transparent", color: tab === t ? "var(--color-text-primary)" : "var(--color-text-tertiary)" }}>
                  {t === "manual" ? "Manual entry" : "Excel upload"}
                </button>
              ))}
            </div>

            <div className="p-3 md:p-6">
              {tab === "manual" ? (
                <form onSubmit={handleSubmit(onManualSubmit)} className="space-y-5">
                  <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-secondary)" }}>Fund name</label>
                    <input {...register("fund_name")} className="form-control py-3 border-secondary" style={inputStyle} placeholder="e.g. axiom" />
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-secondary)" }}>Gross profit *</label>
                      <input type="number" step="0.01" {...register("gross_profit", { valueAsNumber: true })} className="form-control py-3 border-secondary" style={{ ...inputStyle, borderColor: errors.gross_profit ? "var(--color-destructive)" : inputStyle.borderColor }} placeholder="150000.00" />
                      {errors.gross_profit && <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.gross_profit.message}</p>}
                    </div>
                    <div>
                      <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-secondary)" }}>Transaction costs *</label>
                      <input type="number" step="0.01" {...register("transaction_costs", { valueAsNumber: true })} className="form-control py-3 border-secondary" style={{ ...inputStyle, borderColor: errors.transaction_costs ? "var(--color-destructive)" : inputStyle.borderColor }} placeholder="5000.00" />
                      {errors.transaction_costs && <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.transaction_costs.message}</p>}
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs font-medium mb-1.5" style={{ color: "var(--color-text-secondary)" }}>Date closed</label>
                    <input type="datetime-local" {...register("date_closed")} className="form-control py-3 border-secondary" style={inputStyle} />
                  </div>
                  <button type="submit" disabled={isSubmitting} className="w-full rounded-md py-2.5 text-sm fw-bold cursor-pointer disabled:opacity-50" style={{ background: "var(--color-brand-400)", color: "#FFF" }}>{isSubmitting ? "Saving..." : "Record performance"}</button>
                </form>
              ) : (
                <div className="space-y-5">
                  <p className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Upload an Excel file with columns: <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}>date, fund_name, duration, performance_percentage</span></p>
                  <div className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer" style={{ borderColor: selectedFile ? "var(--color-success)" : "var(--color-border-default)" }} onClick={() => fileRef.current?.click()}>
                    <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) setSelectedFile(f); }} />
                    {selectedFile ? (
                      <div className="flex flex-col items-center gap-2">
                        <FileSpreadsheet size={32} style={{ color: "var(--color-success)" }} />
                        <p className="text-sm font-medium">{selectedFile.name}</p>
                      </div>
                    ) : (
                      <div className="flex flex-col items-center gap-2">
                        <Upload size={32} style={{ color: "var(--color-text-tertiary)" }} />
                        <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Select performance Excel file</p>
                      </div>
                    )}
                  </div>
                  <button onClick={onExcelUpload} disabled={!selectedFile || uploading} className="w-full rounded-md py-2.5 text-sm fw-bold cursor-pointer disabled:opacity-50" style={{ background: "var(--color-brand-400)", color: "#FFF" }}>{uploading ? "Uploading..." : "Upload performance data"}</button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
