/**
 * BulkUploadPage — "Bulk Upload Clients"
 *
 * Upload (.csv/.xlsx) -> map spreadsheet columns to system fields (remembered
 * per user via bulkUploadService.getMapping/saveMapping) -> preview + server-side
 * validation (no writes) -> commit only the rows the user selects.
 *
 * Commit reuses the exact same creation path as manual "Add Investor"
 * (InvestmentController.create_new_investor / add_existing_investor_deposit on
 * the backend), so batch auto-assignment and the Stage-1 deposit email behave
 * identically to entering these rows one at a time.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import * as XLSX from "xlsx";
import { ROUTES } from "@/lib/constants";
import { useBulkUploadJob } from "@/context/BulkUploadJobContext";
import { fundService } from "@/services/fundService";
import type { CoreFund, ProductType } from "@/lib/types";
import { ProductToggle } from "@/components/ui/ProductToggle";
import {
  bulkUploadService,
  BULK_UPLOAD_SYSTEM_FIELDS,
  type BulkUploadSystemField,
  type ColumnMapping,
  type ValidatedRow,
  type ValidateSummary,
  type SameFundDecision,
} from "@/services/bulkUploadService";

type Step = "upload" | "map" | "preview" | "committing" | "done";

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

const btnPrimary: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "7px",
  padding: "9px 18px",
  borderRadius: "8px",
  background: "#1A45FF",
  color: "#fff",
  border: "none",
  fontFamily: "var(--font-sans)",
  fontSize: "12px",
  fontWeight: 500,
  cursor: "pointer",
  boxShadow: "0 0 16px rgba(26,69,255,0.3)",
};

const btnSecondary: React.CSSProperties = {
  padding: "9px 16px",
  borderRadius: "8px",
  background: "transparent",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#94A3B8",
  fontFamily: "var(--font-sans)",
  fontSize: "12px",
  fontWeight: 500,
  cursor: "pointer",
};

function Spinner({ size = 14 }: { size?: number }) {
  return (
    <div
      style={{
        width: size, height: size,
        border: "2px solid rgba(255,255,255,0.07)",
        borderTopColor: "#3B82F6",
        borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
      }}
    />
  );
}

function StatusBadge({ status }: { status: ValidatedRow["status"] }) {
  const cfg = {
    valid: { label: "New", bg: "rgba(16,185,129,0.12)", color: "#10B981" },
    existing_new_fund: { label: "Existing — new fund", bg: "rgba(96,165,250,0.12)", color: "#60A5FA" },
    existing_same_fund: { label: "Existing — same fund", bg: "rgba(245,158,11,0.14)", color: "#F59E0B" },
    error: { label: "Error", bg: "rgba(239,68,68,0.12)", color: "#EF4444" },
  }[status];
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "5px", padding: "2px 8px", borderRadius: "100px", fontSize: "10px", fontWeight: 600, background: cfg.bg, color: cfg.color }}>
      <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: cfg.color }} />
      {cfg.label}
    </span>
  );
}

function guessHeaderForField(field: BulkUploadSystemField, headers: string[]): string | undefined {
  const patterns: Record<BulkUploadSystemField, RegExp> = {
    client_code: /client\s*code|investor\s*id|code/i,
    investor_name: /client\s*name|investor\s*name|^name$/i,
    investor_email: /email/i,
    investor_phone: /phone|mobile|tel/i,
    fund_name: /fund/i,
    share_class_code: /share\s*class|class\s*code|class/i,
    deposit_amount: /amount\s*deposit|deposit\s*amount|^amount$/i,
    deposit_date: /date\s*deposit|deposit\s*date|^date$/i,
  };
  const re = patterns[field];
  return headers.find((h) => re.test(h.trim()));
}

function toCsvBlob(headers: string[], rows: (string | number | null)[][]): Blob {
  const esc = (v: string | number | null) => {
    const s = v == null ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))];
  return new Blob([lines.join("\n")], { type: "text/csv" });
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export default function BulkUploadPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [product, setProduct] = useState<ProductType>(searchParams.get("product") === "SHARES" ? "SHARES" : "FUNDS");
  const [fundsById, setFundsById] = useState<Map<number, CoreFund>>(new Map());
  useEffect(() => {
    fundService.getAll().then((funds) => setFundsById(new Map(funds.map((f) => [f.id, f])))).catch(() => {});
  }, []);
  /** The product this row's resolved fund actually belongs to, if known. */
  const rowProduct = useCallback(
    (row: ValidatedRow): ProductType | null => {
      const fundId = row.resolved.fund_id;
      if (fundId == null) return null;
      return fundsById.get(fundId)?.product_type ?? null;
    },
    [fundsById]
  );
  const [step, setStep] = useState<Step>("upload");
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState<string>("");
  const [sourceHeaders, setSourceHeaders] = useState<string[]>([]);
  const [sourceRows, setSourceRows] = useState<Record<string, string>[]>([]);
  const [mapping, setMapping] = useState<ColumnMapping>({});
  const [loadingMapping, setLoadingMapping] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validatedRows, setValidatedRows] = useState<ValidatedRow[]>([]);
  const [summary, setSummary] = useState<ValidateSummary | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [committing, setCommitting] = useState(false);

  // The active job (and its polling) lives in BulkUploadJobContext, mounted
  // at the app root — so it keeps running, and stays visible as a Topbar
  // chip, even if the admin navigates away from this page mid-commit. This
  // page just reads the shared status instead of owning its own poller.
  const { activeJob: jobStatus, startWatching, dismiss: dismissJob } = useBulkUploadJob();
  const notifiedJobIdRef = useRef<number | null>(null);

  // Resume the "committing" view if we land/return on this page while a job
  // started earlier is still running (e.g. navigated away and back).
  useEffect(() => {
    if (jobStatus && (jobStatus.status === "queued" || jobStatus.status === "running") && step === "upload") {
      setCommitting(true);
      setStep("committing");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobStatus]);

  // Fire the completion toast exactly once per job, whichever page happens
  // to be mounted when it finishes.
  useEffect(() => {
    if (!jobStatus) return;
    if (jobStatus.status !== "completed" && jobStatus.status !== "failed") return;
    if (notifiedJobIdRef.current === jobStatus.id) return;
    notifiedJobIdRef.current = jobStatus.id;

    setStep("done");
    setCommitting(false);
    if (jobStatus.status === "failed" && !jobStatus.results) {
      toast.error(jobStatus.error_message || "Bulk upload job failed");
    } else {
      const skippedNote = jobStatus.skipped_count > 0 ? `, ${jobStatus.skipped_count} skipped` : "";
      if (jobStatus.failed_count === 0) {
        toast.success(`${jobStatus.succeeded_count} investor(s) created${skippedNote}`);
      } else {
        toast.warning(`${jobStatus.succeeded_count} created, ${jobStatus.failed_count} failed${skippedNote}`);
      }
    }
  }, [jobStatus]);

  // Per-row decision for "existing_same_fund" rows only — unset behaves like
  // "skip" on the backend, so an admin who never touches a row can't
  // accidentally add a duplicate deposit by just clicking Commit.
  const [decisions, setDecisions] = useState<Record<number, SameFundDecision>>({});

  // The preview table used to render every validated row at once — fine for
  // a few hundred rows, but 100,000 <tr> elements in one go is what actually
  // froze the browser tab on a big file (the backend validate call itself
  // finishes in seconds; nothing server-side was hanging). By default this
  // now shows a small slice, with a search box to jump straight to a
  // specific client instead of paging through thousands of screens —
  // matching the same "don't render everything, let them search" pattern
  // already used on the Investor Directory and Pending Emails pages.
  // Nothing about this touches validatedRows/selected/decisions — every row
  // is still selected for commit by default regardless of what's on screen
  // or what the search box currently matches; the filter is purely a
  // reviewing aid, not a selection scope.
  const PREVIEW_PAGE_SIZE = 50;
  const [previewPage, setPreviewPage] = useState(1);
  const [previewSearch, setPreviewSearch] = useState("");

  const filteredRows = useMemo(() => {
    const q = previewSearch.trim().toLowerCase();
    if (!q) return validatedRows;
    return validatedRows.filter((r) => {
      const { client_code, investor_name, investor_email } = r.resolved;
      return (
        (client_code || "").toLowerCase().includes(q) ||
        (investor_name || "").toLowerCase().includes(q) ||
        (investor_email || "").toLowerCase().includes(q)
      );
    });
  }, [validatedRows, previewSearch]);

  useEffect(() => { setPreviewPage(1); }, [previewSearch]);

  const totalPreviewPages = Math.max(1, Math.ceil(filteredRows.length / PREVIEW_PAGE_SIZE));
  const visibleRows = useMemo(
    () => filteredRows.slice((previewPage - 1) * PREVIEW_PAGE_SIZE, previewPage * PREVIEW_PAGE_SIZE),
    [filteredRows, previewPage]
  );

  const sameFundRows = useMemo(() => validatedRows.filter((r) => r.status === "existing_same_fund"), [validatedRows]);
  const sameFundUndecidedSelected = useMemo(
    () => sameFundRows.some((r) => selected.has(r.row_index) && !decisions[r.row_index]),
    [sameFundRows, selected, decisions]
  );
  const setAllSameFundDecisions = (decision: SameFundDecision) => {
    setDecisions((prev) => {
      const next = { ...prev };
      for (const r of sameFundRows) next[r.row_index] = decision;
      return next;
    });
  };

  const parseFile = useCallback(async (file: File) => {
    try {
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: "array" });
      const firstSheetName = wb.SheetNames[0];
      if (!firstSheetName) {
        toast.error("The file appears to be empty");
        return;
      }
      const sheet = wb.Sheets[firstSheetName];
      if (!sheet) {
        toast.error("The file appears to be empty");
        return;
      }
      const asRows: string[][] = XLSX.utils.sheet_to_json(sheet, { header: 1, raw: false, defval: "" });
      const headerRow = asRows[0];
      if (!asRows.length || !headerRow) {
        toast.error("The file appears to be empty");
        return;
      }
      const headers = headerRow.map((h) => String(h ?? "").trim()).filter(Boolean);
      const dataRows = asRows.slice(1)
        .filter((r) => r.some((cell) => String(cell ?? "").trim() !== ""))
        .map((r) => {
          const obj: Record<string, string> = {};
          headers.forEach((h, idx) => { obj[h] = String(r[idx] ?? "").trim(); });
          return obj;
        });

      setFileName(file.name);
      setSourceHeaders(headers);
      setSourceRows(dataRows);

      // Auto-guess mapping, then overlay any saved mapping for this exact header set.
      const guessed: ColumnMapping = {};
      for (const f of BULK_UPLOAD_SYSTEM_FIELDS) {
        const h = guessHeaderForField(f.key, headers);
        if (h) guessed[f.key] = h;
      }
      setMapping(guessed);

      setLoadingMapping(true);
      try {
        const saved = await bulkUploadService.getMapping(headers);
        if (saved) {
          setMapping(saved.mapping);
          toast.info("Loaded your saved column mapping for this file layout");
        }
      } catch {
        // No saved mapping yet — guessed mapping stands.
      } finally {
        setLoadingMapping(false);
      }

      setStep("map");
    } catch (err) {
      console.error(err);
      toast.error("Could not read that file — make sure it's a valid .csv or .xlsx");
    }
  }, []);

  const onFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) parseFile(file);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) parseFile(file);
  };

  const requiredFieldsMapped = BULK_UPLOAD_SYSTEM_FIELDS
    .filter((f) => f.required)
    .every((f) => !!mapping[f.key]);

  const handleContinueToPreview = async () => {
    if (!requiredFieldsMapped) return;
    setValidating(true);
    try {
      await bulkUploadService.saveMapping(sourceHeaders, mapping).catch(() => {});
      const mappedRows = sourceRows.map((row) => {
        const obj: Record<string, string> = {};
        for (const f of BULK_UPLOAD_SYSTEM_FIELDS) {
          const header = mapping[f.key];
          if (header) obj[f.key] = row[header] ?? "";
        }
        return obj;
      });
      const result = await bulkUploadService.validate(mappedRows);
      setValidatedRows(result.rows);
      setSummary(result.summary);
      // Rows resolving to a fund from the OTHER product are excluded by default
      // (not an error — the mixing is already impossible server-side, see
      // Task 1 — just a likely sign this row belongs in the other upload).
      setSelected(
        new Set(
          result.rows
            .filter((r) => r.status !== "error")
            .filter((r) => {
              const p = rowProduct(r);
              return p == null || p === product;
            })
            .map((r) => r.row_index)
        )
      );
      setDecisions({});
      setPreviewPage(1);
      setStep("preview");
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Validation failed");
    } finally {
      setValidating(false);
    }
  };

  const toggleRow = (idx: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  };

  const downloadErrorsCsv = () => {
    const errorRows = validatedRows.filter((r) => r.status === "error");
    const headers = ["Row", "Client Code", "Client Name", "Email", "Share Class", "Amount", "Date", "Errors"];
    const rows = errorRows.map((r) => [
      r.row_index + 2, // +1 header row, +1 for 1-indexing
      r.resolved.client_code, r.resolved.investor_name, r.resolved.investor_email,
      r.resolved.class_code, r.resolved.deposit_amount, r.resolved.deposit_date,
      r.errors.map((e) => `${e.field}: ${e.message}`).join("; "),
    ]);
    downloadBlob(toCsvBlob(headers, rows), `bulk-upload-errors-${fileName || "file"}.csv`);
  };

  const handleCommit = async () => {
    const rowsToCommit = validatedRows.filter((r) => selected.has(r.row_index));
    if (rowsToCommit.length === 0) {
      toast.error("Select at least one row to commit");
      return;
    }
    if (sameFundUndecidedSelected) {
      toast.error('Resolve every "Existing — same fund" row (Additional deposit or Skip) before committing');
      return;
    }
    const rowsWithDecisions = rowsToCommit.map((r) => ({ ...r, decision: decisions[r.row_index] }));
    setCommitting(true);
    try {
      const { job_id } = await bulkUploadService.startCommit(rowsWithDecisions, fileName);
      setStep("committing");
      startWatching(job_id);
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Could not start the bulk upload job");
      setCommitting(false);
    }
  };

  const resetAll = () => {
    setStep("upload");
    setFileName("");
    setSourceHeaders([]);
    setSourceRows([]);
    setMapping({});
    setValidatedRows([]);
    setSummary(null);
    setSelected(new Set());
    dismissJob();
    setDecisions({});
  };

  const previewRows = useMemo(() => sourceRows.slice(0, 10), [sourceRows]);

  return (
    <div style={{ position: "relative", zIndex: 1, padding: "24px 32px 48px", maxWidth: "1100px", margin: "0 auto", fontFamily: "var(--font-sans)", color: "#FFFFFF", display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: "7px", fontSize: "11px", color: "rgb(71,85,105)" }}>
        <a href={ROUTES.INVESTORS} onClick={(e) => { e.preventDefault(); navigate(ROUTES.INVESTORS); }} style={{ color: "rgb(148,163,184)", textDecoration: "none" }}>
          Investors
        </a>
        <span style={{ opacity: 0.5 }}>/</span>
        <span>Bulk upload</span>
      </div>

      <div>
        <h1 style={{ fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>Bulk Upload Clients</h1>
        <p style={{ fontSize: "12px", color: "#94A3B8", marginTop: "4px" }}>
          Import many investors from a spreadsheet — validated before anything is written, using the same creation path as adding one investor at a time.
        </p>
      </div>

      {/* Product — first control; rows resolving to the other product's funds
          are flagged in the preview and unselected by default. */}
      <ProductToggle value={product} onChange={(v) => setProduct(v as ProductType)} label="Product" />

      {/* Step indicator */}
      <div style={{ display: "flex", gap: "6px", fontSize: "11px", color: "#475569" }}>
        {(["upload", "map", "preview", "done"] as Step[]).map((s, i) => (
          <div key={s} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ color: step === s ? "#60A5FA" : (["upload","map","preview","done"].indexOf(step) > i ? "#10B981" : "#475569"), fontWeight: step === s ? 700 : 500, textTransform: "capitalize" }}>
              {i + 1}. {s}
            </span>
            {i < 3 && <span style={{ opacity: 0.4 }}>→</span>}
          </div>
        ))}
      </div>

      {/* Step: Upload */}
      {step === "upload" && (
        <div style={{ ...glass, padding: "20px 24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <button onClick={() => bulkUploadService.downloadTemplate()} style={btnSecondary}>
              Download template (.csv)
            </button>
          </div>
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            style={{
              border: `1px dashed ${dragOver ? "#3B82F6" : "rgba(255,255,255,0.15)"}`,
              borderRadius: "12px",
              padding: "48px 24px",
              textAlign: "center",
              background: dragOver ? "rgba(59,130,246,0.06)" : "transparent",
              transition: "all 0.15s",
            }}
          >
            <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "12px" }}>
              Drag & drop a .csv or .xlsx file here, or
            </div>
            <label style={{ ...btnPrimary, display: "inline-flex", cursor: "pointer" }}>
              Choose file
              <input type="file" accept=".csv,.xlsx,.xls" onChange={onFileInput} style={{ display: "none" }} />
            </label>
          </div>
        </div>
      )}

      {/* Step: Map */}
      {step === "map" && (
        <div style={{ ...glass, padding: "20px 24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ fontSize: "13px", fontWeight: 600 }}>
            Map columns — {fileName} ({sourceRows.length} row{sourceRows.length !== 1 ? "s" : ""})
            {loadingMapping && <span style={{ marginLeft: "8px", color: "#94A3B8", fontWeight: 400 }}>checking for a saved mapping…</span>}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            {BULK_UPLOAD_SYSTEM_FIELDS.map((f) => (
              <div key={f.key} style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
                <label style={{ fontSize: "11px", color: "#94A3B8" }}>
                  {f.label} {f.required && <span style={{ color: "#EF4444" }}>*</span>}
                </label>
                <select
                  value={mapping[f.key] ?? ""}
                  onChange={(e) => setMapping((prev) => ({ ...prev, [f.key]: e.target.value || undefined }))}
                  style={{ ...inputBase, cursor: "pointer" }}
                >
                  <option value="">— not mapped —</option>
                  {sourceHeaders.map((h) => (
                    <option key={h} value={h}>{h}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          {previewRows.length > 0 && (
            <div>
              <div style={{ fontSize: "11px", color: "#475569", marginBottom: "6px" }}>Preview (first {previewRows.length} rows)</div>
              <div style={{ overflowX: "auto", border: "1px solid rgba(255,255,255,0.07)", borderRadius: "8px" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                  <thead>
                    <tr style={{ background: "rgba(255,255,255,0.03)" }}>
                      {sourceHeaders.map((h) => (
                        <th key={h} style={{ padding: "6px 10px", textAlign: "left", color: "#475569", whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {previewRows.map((row, i) => (
                      <tr key={i} style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                        {sourceHeaders.map((h) => (
                          <td key={h} style={{ padding: "6px 10px", color: "#94A3B8", whiteSpace: "nowrap" }}>{row[h]}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
            <button onClick={resetAll} style={btnSecondary}>Start over</button>
            <button
              onClick={handleContinueToPreview}
              disabled={!requiredFieldsMapped || validating}
              style={{ ...btnPrimary, opacity: (!requiredFieldsMapped || validating) ? 0.5 : 1, cursor: (!requiredFieldsMapped || validating) ? "not-allowed" : "pointer" }}
            >
              {validating ? <><Spinner /> Validating…</> : "Continue to preview"}
            </button>
          </div>
        </div>
      )}

      {/* Step: Preview / validate */}
      {step === "preview" && summary && (
        <>
          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            {[
              { label: "Total", count: summary.total, color: "#94A3B8" },
              { label: "New", count: summary.valid, color: "#10B981" },
              { label: "Existing — new fund", count: summary.existing_new_fund, color: "#60A5FA" },
              { label: "Existing — same fund", count: summary.existing_same_fund, color: "#F59E0B" },
              { label: "Errors", count: summary.error, color: "#EF4444" },
              { label: "Warnings", count: summary.warnings, color: "#F59E0B" },
            ].map(({ label, count, color }) => (
              <div key={label} style={{ display: "flex", alignItems: "center", gap: "6px", padding: "5px 10px", borderRadius: "8px", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.07)", fontSize: "11px", color: "#94A3B8" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color, fontSize: "12px" }}>{count}</span>
                {label}
              </div>
            ))}
          </div>

          {sameFundRows.length > 0 && (
            <div style={{ ...glass, padding: "14px 18px", border: "1px solid rgba(245,158,11,0.3)", background: "rgba(245,158,11,0.06)", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
              <div style={{ fontSize: "12px", color: "#F59E0B" }}>
                {sameFundRows.length} row{sameFundRows.length !== 1 ? "s" : ""} match a client who already holds this exact fund — each needs a decision before it can be committed.
              </div>
              <div style={{ display: "flex", gap: "8px" }}>
                <button onClick={() => setAllSameFundDecisions("additional_deposit")} style={{ ...btnSecondary, borderColor: "rgba(16,185,129,0.4)", color: "#10B981" }}>
                  Treat all as additional deposits
                </button>
                <button onClick={() => setAllSameFundDecisions("skip")} style={{ ...btnSecondary, borderColor: "rgba(239,68,68,0.4)", color: "#EF4444" }}>
                  Skip all
                </button>
              </div>
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder={`Search ${validatedRows.length.toLocaleString()} rows by client code, name, or email…`}
              value={previewSearch}
              onChange={(e) => setPreviewSearch(e.target.value)}
              style={{ ...inputBase, maxWidth: "420px", flex: "1 1 320px" }}
            />
            {previewSearch.trim() !== "" && (
              <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                {filteredRows.length.toLocaleString()} match{filteredRows.length !== 1 ? "es" : ""}
                {" "}
                <button
                  onClick={() => setPreviewSearch("")}
                  style={{ background: "none", border: "none", color: "var(--color-brand-400, #4f8cff)", cursor: "pointer", fontSize: "11px", padding: 0 }}
                >
                  clear
                </button>
              </span>
            )}
          </div>

          <div style={{ ...glass, overflow: "hidden" }}>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ background: "rgba(255,255,255,0.03)" }}>
                    {["", "Status", "Client Code", "Name", "Email", "Class", "Amount", "Date", "Issues", "Decision"].map((h) => (
                      <th key={h} style={{ padding: "9px 12px", fontSize: "9px", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", color: "#475569", textAlign: "left", borderBottom: "1px solid rgba(255,255,255,0.07)", whiteSpace: "nowrap" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((r) => {
                    const needsDecision = r.status === "existing_same_fund";
                    const decided = decisions[r.row_index];
                    return (
                      <tr
                        key={r.row_index}
                        style={{
                          borderBottom: "1px solid rgba(255,255,255,0.03)",
                          opacity: r.status === "error" ? 0.6 : 1,
                          background: needsDecision && !decided ? "rgba(245,158,11,0.06)" : undefined,
                        }}
                      >
                        <td style={{ padding: "8px 12px" }}>
                          <input
                            type="checkbox"
                            checked={selected.has(r.row_index)}
                            disabled={r.status === "error"}
                            onChange={() => toggleRow(r.row_index)}
                            style={{ cursor: r.status === "error" ? "not-allowed" : "pointer" }}
                          />
                        </td>
                        <td style={{ padding: "8px 12px" }}><StatusBadge status={r.status} /></td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: "11px" }}>{r.resolved.client_code || "—"}</td>
                        <td style={{ padding: "8px 12px" }}>{r.resolved.investor_name || "—"}</td>
                        <td style={{ padding: "8px 12px", fontSize: "11px", color: "#94A3B8" }}>{r.resolved.investor_email || "—"}</td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: "11px" }}>{r.resolved.class_code || "—"}</td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: "11px" }}>
                          {r.resolved.deposit_amount != null ? `${r.resolved.currency ?? ""} ${r.resolved.deposit_amount.toLocaleString()}` : "—"}
                        </td>
                        <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: "11px" }}>{r.resolved.deposit_date || "—"}</td>
                        <td style={{ padding: "8px 12px", fontSize: "11px", maxWidth: "260px" }}>
                          {r.errors.map((e, i) => <div key={i} style={{ color: "#EF4444" }}>{e.message}</div>)}
                          {r.warnings.map((w, i) => <div key={i} style={{ color: "#F59E0B" }}>{w.message}</div>)}
                          {r.status !== "valid" && r.resolved.existing_fund_names.length > 0 && (
                            <div style={{ color: "#64748B" }}>Already holds: {r.resolved.existing_fund_names.join(", ")}</div>
                          )}
                          {(() => {
                            const p = rowProduct(r);
                            return p && p !== product ? (
                              <div style={{ color: "#F59E0B" }}>
                                Resolves to a {p === "SHARES" ? "Shares" : "Funds"} fund — unselected by default
                              </div>
                            ) : null;
                          })()}
                        </td>
                        <td style={{ padding: "8px 12px" }}>
                          {needsDecision ? (
                            <select
                              value={decided ?? ""}
                              onChange={(e) => setDecisions((prev) => ({ ...prev, [r.row_index]: (e.target.value || undefined) as SameFundDecision }))}
                              style={{
                                ...inputBase,
                                cursor: "pointer",
                                borderColor: decided ? "rgba(255,255,255,0.1)" : "rgba(245,158,11,0.5)",
                              }}
                            >
                              <option value="">— choose —</option>
                              <option value="additional_deposit">Additional deposit</option>
                              <option value="skip">Skip (possible duplicate)</option>
                            </select>
                          ) : (
                            <span style={{ color: "#475569", fontSize: "11px" }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {filteredRows.length === 0 && (
                    <tr>
                      <td colSpan={10} style={{ padding: "24px 12px", textAlign: "center", fontSize: "12px", color: "var(--color-text-tertiary)" }}>
                        No rows match "{previewSearch}"
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {filteredRows.length > 0 && (
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 16px", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                  Showing {(previewPage - 1) * PREVIEW_PAGE_SIZE + 1}–{Math.min(previewPage * PREVIEW_PAGE_SIZE, filteredRows.length)} of{" "}
                  {previewSearch.trim() ? `${filteredRows.length.toLocaleString()} matching (${validatedRows.length.toLocaleString()} total)` : `${validatedRows.length.toLocaleString()} rows`}
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <button
                    onClick={() => setPreviewPage((p) => Math.max(1, p - 1))}
                    disabled={previewPage <= 1}
                    style={{ ...btnSecondary, padding: "5px 12px", fontSize: "11px", opacity: previewPage <= 1 ? 0.5 : 1, cursor: previewPage <= 1 ? "not-allowed" : "pointer" }}
                  >
                    Previous
                  </button>
                  <span style={{ fontSize: "11px", color: "var(--color-text-secondary)" }}>
                    Page {previewPage} of {totalPreviewPages}
                  </span>
                  <button
                    onClick={() => setPreviewPage((p) => Math.min(totalPreviewPages, p + 1))}
                    disabled={previewPage >= totalPreviewPages}
                    style={{ ...btnSecondary, padding: "5px 12px", fontSize: "11px", opacity: previewPage >= totalPreviewPages ? 0.5 : 1, cursor: previewPage >= totalPreviewPages ? "not-allowed" : "pointer" }}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>

          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", gap: "10px" }}>
              <button onClick={() => setStep("map")} style={btnSecondary}>Back to mapping</button>
              {summary.error > 0 && (
                <button onClick={downloadErrorsCsv} style={btnSecondary}>Download errors CSV ({summary.error})</button>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "6px" }}>
              {sameFundUndecidedSelected && (
                <div style={{ fontSize: "11px", color: "#F59E0B" }}>
                  Resolve every "Existing — same fund" row above before committing
                </div>
              )}
              <button
                onClick={handleCommit}
                disabled={committing || selected.size === 0 || sameFundUndecidedSelected}
                style={{
                  ...btnPrimary,
                  opacity: (committing || selected.size === 0 || sameFundUndecidedSelected) ? 0.5 : 1,
                  cursor: (committing || selected.size === 0 || sameFundUndecidedSelected) ? "not-allowed" : "pointer",
                }}
              >
                {committing ? <><Spinner /> Creating…</> : `Commit ${selected.size} selected row${selected.size !== 1 ? "s" : ""}`}
              </button>
            </div>
          </div>
        </>
      )}

      {/* Step: Committing — background job progress bar */}
      {step === "committing" && jobStatus && (
        <div style={{ ...glass, padding: "32px 24px", textAlign: "center", display: "flex", flexDirection: "column", gap: "18px", alignItems: "center" }}>
          <div style={{ fontSize: "18px", fontWeight: 700 }}>
            Creating investors… {jobStatus.processed_rows.toLocaleString()} of {jobStatus.total_rows.toLocaleString()}
          </div>
          <div style={{ width: "100%", maxWidth: "560px" }}>
            <div style={{ height: "10px", borderRadius: "999px", background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  width: `${jobStatus.total_rows > 0 ? Math.min(100, (jobStatus.processed_rows / jobStatus.total_rows) * 100) : 0}%`,
                  background: "var(--color-brand-400, #4f8cff)",
                  transition: "width 0.3s ease",
                }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--color-text-secondary)", marginTop: "8px" }}>
              <span>{jobStatus.total_rows > 0 ? Math.round((jobStatus.processed_rows / jobStatus.total_rows) * 100) : 0}% complete</span>
              <span>
                {jobStatus.succeeded_count.toLocaleString()} created
                {jobStatus.failed_count > 0 && ` · ${jobStatus.failed_count.toLocaleString()} failed`}
                {jobStatus.skipped_count > 0 && ` · ${jobStatus.skipped_count.toLocaleString()} skipped`}
              </span>
            </div>
          </div>
          <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>
            This runs in the background — safe to leave this page; the upload will keep going.
          </div>
        </div>
      )}

      {/* Step: Done */}
      {step === "done" && jobStatus && (
        <div style={{ ...glass, padding: "32px 24px", textAlign: "center", display: "flex", flexDirection: "column", gap: "16px", alignItems: "center" }}>
          {jobStatus.status === "failed" && !jobStatus.results ? (
            <>
              <div style={{ fontSize: "18px", fontWeight: 700, color: "#EF4444" }}>Bulk upload job failed</div>
              <div style={{ fontSize: "13px", color: "var(--color-text-secondary)", maxWidth: "560px" }}>
                {jobStatus.error_message || "Unknown error"}
                {jobStatus.processed_rows > 0 && ` — ${jobStatus.processed_rows.toLocaleString()} row(s) had already been processed before it failed.`}
              </div>
            </>
          ) : (
            <div style={{ fontSize: "18px", fontWeight: 700 }}>
              {jobStatus.succeeded_count} investor{jobStatus.succeeded_count !== 1 ? "s" : ""} created
              {jobStatus.failed_count > 0 && `, ${jobStatus.failed_count} failed`}
              {jobStatus.skipped_count > 0 && `, ${jobStatus.skipped_count} skipped`}
            </div>
          )}
          {jobStatus.results && jobStatus.results.failed.length > 0 && (
            <div style={{ ...glass, padding: "14px 18px", textAlign: "left", maxWidth: "560px", width: "100%", maxHeight: "260px", overflowY: "auto" }}>
              {jobStatus.results.failed_count > jobStatus.results.failed.length && (
                <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
                  Showing {jobStatus.results.failed.length} of {jobStatus.results.failed_count} failed rows
                </div>
              )}
              {jobStatus.results.failed.map((f, i) => (
                <div key={i} style={{ fontSize: "12px", color: "#EF4444", marginBottom: "4px" }}>
                  {f.client_code || "—"}: {f.message}
                </div>
              ))}
            </div>
          )}
          {jobStatus.results && jobStatus.results.skipped.length > 0 && (
            <div style={{ ...glass, padding: "14px 18px", textAlign: "left", maxWidth: "560px", width: "100%", maxHeight: "260px", overflowY: "auto" }}>
              {jobStatus.results.skipped_count > jobStatus.results.skipped.length && (
                <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
                  Showing {jobStatus.results.skipped.length} of {jobStatus.results.skipped_count} skipped rows
                </div>
              )}
              {jobStatus.results.skipped.map((s, i) => (
                <div key={i} style={{ fontSize: "12px", color: "#F59E0B", marginBottom: "4px" }}>
                  {s.client_code || "—"}: {s.reason}
                </div>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: "10px" }}>
            <button onClick={resetAll} style={btnSecondary}>Upload another file</button>
            <button onClick={() => navigate(ROUTES.INVESTORS)} style={btnPrimary}>Back to Investors</button>
          </div>
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
