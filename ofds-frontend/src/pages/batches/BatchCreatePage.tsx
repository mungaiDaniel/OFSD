import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { createBatchSchema, type CreateBatchFormData } from "@/lib/validators/batch.schema";
import { batchService } from "@/services/batchService";
import { ROUTES } from "@/lib/constants";
import { toast } from "sonner";
import { Upload, FileSpreadsheet, ArrowLeft } from "lucide-react";
import { EmailConfirmationModal } from "@/components/ui/EmailConfirmationModal";

export default function BatchCreatePage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<"manual" | "excel">("manual");
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [excelBatchName, setExcelBatchName] = useState("");
  const [createdBatch, setCreatedBatch] = useState<{ id: number; name: string } | null>(null);
  const [emailConfirmModalOpen, setEmailConfirmModalOpen] = useState(false);

  // Manual form
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<CreateBatchFormData>({
    resolver: zodResolver(createBatchSchema),
  });

  const onManualSubmit = async (data: CreateBatchFormData) => {
    try {
      const res = await batchService.create(data);
      const batchId = (res.data as any)?.id;
      
      toast.success("Batch created successfully. Please upload investor file.");
      
      if (batchId) {
        setCreatedBatch({ id: batchId, name: data.batch_name });
        setTab("excel");
      } else {
        navigate(ROUTES.BATCHES);
      }
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to create batch";
      toast.error(msg);
    }
  };

  const onExcelUpload = async () => {
    if (!selectedFile) return;
    
    // If a batch is NOT already created, require a name
    if (!createdBatch && !excelBatchName.trim()) {
      toast.error("Please enter a batch name first");
      return;
    }

    setUploading(true);
    setUploadProgress(0);

    // Simulate progress (real Axios progress would use onUploadProgress)
    const interval = setInterval(() => setUploadProgress((p) => Math.min(p + 15, 90)), 200);

    try {
      let batchId = createdBatch?.id;

      if (!batchId) {
        // 1. Create batch
        const createRes = await batchService.create({ batch_name: excelBatchName.trim() });
        batchId = (createRes.data as { id?: number })?.id;

        if (!batchId) {
          throw new Error("Failed to receive batch ID from creation");
        }
        setCreatedBatch({ id: batchId, name: excelBatchName.trim() });
      }

      // 2. Upload excel
      await batchService.uploadExcel(batchId, selectedFile);

      setUploadProgress(100);
      toast.success("Excel batch uploaded successfully");
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || (err as Error).message || "Upload failed";
      toast.error(msg);
    } finally {
      clearInterval(interval);
      setUploading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const validTypes = [
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
    ];
    if (!validTypes.includes(file.type) && !file.name.match(/\.xlsx?$/i)) {
      toast.error("Please select an .xlsx or .xls file");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("File must be under 10MB");
      return;
    }
    setSelectedFile(file);
  };

  const inputStyle = {
    background: "var(--color-bg-input)",
    borderColor: "var(--color-border-default)",
    color: "var(--color-text-primary)",
  };

  return (
    <div className="container-fluid px-0" style={{ paddingTop: '1.5rem', paddingBottom: '1.5rem', minHeight: '100vh' }}>
      {/* Header */}
      <div className="mb-4 px-3" style={{ maxWidth: '960px', margin: '0 auto' }}>
        <button
          onClick={() => navigate(ROUTES.BATCHES)}
          className="d-flex align-items-center gap-1 mb-3 btn btn-link p-0 text-decoration-none"
          style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}
        >
          <ArrowLeft size={14} /> Back to batches
        </button>
        <h1 className="fw-bold mb-1" style={{ fontSize: "22px", color: "var(--color-text-primary)" }}>New batch</h1>
        <p className="mb-0" style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>Create a new investment batch manually or import from Excel</p>
      </div>

      {/* Form card */}
      <div className="d-flex justify-content-center">
        <div className="card shadow mb-4" style={{ maxWidth: "680px", width: "100%", margin: "0 auto", border: "none", padding: "0.25rem" }}>
          {/* Tabs */}
          <div className="d-flex border-bottom" style={{ borderColor: "rgba(255,255,255,0.06)" }}>
          {(["manual", "excel"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className="flex-grow-1 py-3 transition-colors text-center"
              style={{
                fontSize: "13px",
                fontWeight: 500,
                background: "transparent",
                border: "none",
                borderBottom: tab === t ? "2px solid var(--color-brand-400)" : "2px solid transparent",
                color: tab === t ? "var(--color-text-primary)" : "var(--color-text-tertiary)",
              }}
            >
              {t === "manual" ? "Manual entry" : "Excel upload"}
            </button>
          ))}
        </div>

        <div className="card-body p-4 p-md-5">
          {tab === "manual" ? (
            <form onSubmit={handleSubmit(onManualSubmit)} className="d-flex flex-column gap-4">
              <div>
                <label className="form-label small fw-bold mb-2 tracking-wide" style={{ color: "var(--color-text-primary)" }}>Batch name *</label>
                <input {...register("batch_name")} className="form-control py-3 border-secondary" style={{...inputStyle, borderColor: errors.batch_name ? "var(--color-destructive)" : inputStyle.borderColor }} placeholder="Q2-2026 Portfolio" />
                {errors.batch_name && <p className="text-xs mt-1" style={{ color: "var(--color-destructive)" }}>{errors.batch_name.message}</p>}
              </div>
              <div>
                <label className="form-label small fw-bold mb-2 tracking-wide" style={{ color: "var(--color-text-primary)" }}>Certificate number</label>
                <input {...register("certificate_number")} className="form-control py-3 border-secondary" style={inputStyle} placeholder="CERT-Q2-001 (optional)" />
              </div>
              <div>
                <label className="form-label text-muted small fw-bold mb-2 tracking-wide">Date deployed</label>
                <input type="date" {...register("date_deployed")} className="form-control py-3 border-secondary" style={inputStyle} />
              </div>
              <div className="d-flex gap-3 pt-3">
                <button type="button" onClick={() => navigate(ROUTES.BATCHES)} className="btn btn-outline-secondary w-50 fw-bold py-3 rounded-pill" style={{ fontSize: "14px" }}>Cancel</button>
                <button type="submit" disabled={isSubmitting} className="btn btn-primary w-50 fw-bold py-3 rounded-pill" style={{ fontSize: "14px" }}>{isSubmitting ? "Creating..." : "Create batch"}</button>
              </div>
            </form>
          ) : (
            <div className="d-flex flex-column gap-4">
              {!createdBatch ? (
                <div>
                  <label className="form-label small fw-bold mb-2 tracking-wide" style={{ color: "var(--color-text-primary)" }}>Batch name *</label>
                  <input 
                    value={excelBatchName}
                    onChange={(e) => setExcelBatchName(e.target.value)}
                    className="form-control py-3 border-secondary" 
                    style={inputStyle} 
                    placeholder="Q2-2026 Direct Upload" 
                  />
                </div>
              ) : (
                <div className="p-3 rounded-4 border-0 d-flex align-items-center justify-content-between" style={{ background: "var(--color-bg-surface-alt)", border: "1px solid var(--color-border-default)" }}>
                  <div>
                    <span className="text-xs block mb-1" style={{ color: "var(--color-text-secondary)" }}>Uploading investors for batch</span>
                    <span className="text-sm fw-bold" style={{ color: "var(--color-text-primary)" }}>{createdBatch.name}</span>
                  </div>
                </div>
              )}

              {/* Drop zone */}
              <div
                className="rounded-4 p-5 text-center cursor-pointer transition-all hover-op-80"
                style={{ 
                  border: `2px dashed ${selectedFile ? "var(--color-success)" : "var(--color-border-default)"}`, 
                  background: "rgba(255,255,255,0.015)",
                  minHeight: "180px",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center"
                }}
                onClick={() => fileRef.current?.click()}
              >
                <input ref={fileRef} type="file" accept=".xlsx,.xls" className="hidden" onChange={handleFileSelect} />
                {selectedFile ? (
                  <div className="d-flex flex-column align-items-center gap-2">
                    <FileSpreadsheet size={40} style={{ color: "var(--color-success)" }} />
                    <p className="text-sm font-bold mb-0" style={{ color: "var(--color-text-primary)" }}>{selectedFile.name}</p>
                    <p className="small" style={{ color: "var(--color-text-secondary)" }}>{(selectedFile.size / 1024).toFixed(0)} KB</p>
                  </div>
                ) : (
                  <div className="d-flex flex-column align-items-center gap-2">
                    <Upload size={40} style={{ color: "var(--color-brand-300)" }} />
                    <p className="text-sm font-medium mb-0" style={{ color: "var(--color-text-primary)" }}>Click to select or drag an Excel file</p>
                    <p className="extra-small" style={{ color: "var(--color-text-secondary)" }}>.xlsx or .xls, max 10MB</p>
                  </div>
                )}
              </div>

              {/* Progress bar */}
              {uploading && (
                <div className="h-1.5 w-100 rounded-pill overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
                  <div className="h-full rounded-pill transition-all duration-300" style={{ width: `${uploadProgress}%`, background: "var(--color-brand-400)" }} />
                </div>
              )}

              <div className="d-flex gap-3 pt-3">
                <button onClick={() => navigate(ROUTES.BATCHES)} className="btn btn-outline-secondary w-50 fw-bold py-3 rounded-pill" style={{ fontSize: "14px" }}>Cancel</button>
                <button onClick={onExcelUpload} disabled={!selectedFile || uploading} className="btn btn-primary w-50 fw-bold py-3 rounded-pill" style={{ fontSize: "14px" }}>{uploading ? "Uploading..." : "Upload"}</button>
              </div>
            </div>
          )}
        </div>
      </div>

      <EmailConfirmationModal
        open={emailConfirmModalOpen}
        onClose={() => {
          setEmailConfirmModalOpen(false);
          // Navigate to batches once user has confirmed/cancelled emails out of the prompt
          navigate(ROUTES.BATCHES);
        }}
        batchId={createdBatch?.id}
      />
    </div>
  </div>
);
}
