import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { createPerformanceSchema, type CreatePerformanceFormData } from "@/lib/validators/performance.schema";
import { performanceService } from "@/services/performanceService";
import { batchService } from "@/services/batchService";
import { formatCurrency, formatDate } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import type { Batch, Performance } from "@/lib/types";
import { toast } from "sonner";
import { ArrowLeft, Upload, FileSpreadsheet, Play } from "lucide-react";

export default function BatchPerformancePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const batchId = Number(id);
  const [batch, setBatch] = useState<Batch | null>(null);
  const [performances, setPerformances] = useState<Performance[]>([]);
  const [loading, setLoading] = useState(true);
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
        const [b, p] = await Promise.allSettled([
          batchService.getById(batchId),
          performanceService.getByBatch(batchId),
        ]);
        if (b.status === "fulfilled") setBatch(b.value);
        if (p.status === "fulfilled") setPerformances((p.value as any).data || []);
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

  const inputStyle = { background: "var(--color-bg-input)", borderColor: "var(--color-border-default)", color: "var(--color-text-primary)" };

  if (loading) {
    return <div className="flex items-center justify-center h-64"><div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }} /></div>;
  }

  return (
    <div>
      <button onClick={() => navigate(ROUTES.BATCH_DETAIL(batchId))} className="flex items-center gap-1 text-[12px] mb-3 cursor-pointer" style={{ color: "var(--color-text-tertiary)" }}>
        <ArrowLeft size={14} /> {batch?.batch_name || "Batch"}
      </button>

      <h1 className="text-sm fw-bold mb-1" style={{ color: "var(--color-text-primary)" }}>Performance</h1>
      <p className="text-xs mb-4" style={{ color: "var(--color-text-secondary)" }}>Enter performance data and trigger pro-rata calculations</p>

      {/* Existing performance records */}
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

      {/* Entry form */}
      <div className="max-w-xl rounded-lg border" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
        <div className="flex border-b" style={{ borderColor: "var(--color-border-subtle)" }}>
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
      </div>
    </div>
  );
}
