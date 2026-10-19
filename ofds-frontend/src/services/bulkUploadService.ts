import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse } from "@/lib/types";

export const BULK_UPLOAD_SYSTEM_FIELDS = [
  { key: "client_code", label: "Client Code", required: true },
  { key: "investor_name", label: "Client Name", required: true },
  { key: "investor_email", label: "Email", required: true },
  { key: "investor_phone", label: "Phone", required: false },
  { key: "fund_name", label: "Fund Invested In", required: false },
  { key: "share_class_code", label: "Share Class", required: true },
  { key: "deposit_amount", label: "Amount Deposited", required: true },
  { key: "deposit_date", label: "Date Deposited", required: true },
] as const;

export type BulkUploadSystemField = (typeof BULK_UPLOAD_SYSTEM_FIELDS)[number]["key"];

export type ColumnMapping = Partial<Record<BulkUploadSystemField, string>>;

export interface SavedMapping {
  id: number;
  template_key: string;
  source_headers: string[];
  mapping: ColumnMapping;
  updated_at: string;
}

export interface ResolvedRow {
  client_code: string | null;
  investor_name: string | null;
  investor_email: string | null;
  investor_phone: string | null;
  fund_id: number | null;
  fund_name: string | null;
  share_class_id: number | null;
  class_code: string | null;
  currency: string | null;
  deposit_amount: number | null;
  deposit_date: string | null;
  /** SHARES row under the minimum deposit — needs an approved exception (with a reason) to commit. */
  below_minimum?: boolean;
  min_deposit_usd?: number | null;
  // Funds this client_code already holds a position in — populated whenever
  // status is existing_new_fund/existing_same_fund, empty for a brand-new client.
  existing_fund_names: string[];
}

export interface RowIssue {
  field: string;
  message: string;
}

// "existing_investor" was split into two so the preview can tell "they hold a
// DIFFERENT fund" apart from "they already hold THIS exact fund" (the one
// case that needs an explicit admin decision before it can commit).
export type RowStatus = "valid" | "existing_new_fund" | "existing_same_fund" | "error";

// Only meaningful on an existing_same_fund row. Unset/undefined behaves like
// "skip" — the backend never commits a same-fund match without this being
// explicitly set to "additional_deposit".
export type SameFundDecision = "additional_deposit" | "skip";

export interface ValidatedRow {
  row_index: number;
  status: RowStatus;
  errors: RowIssue[];
  warnings: RowIssue[];
  resolved: ResolvedRow;
  decision?: SameFundDecision;
  /** Set on commit for a below-minimum row an admin approved as an exception. */
  min_deposit_exception?: boolean;
  min_deposit_exception_reason?: string;
}

export interface ValidateSummary {
  total: number;
  valid: number;
  existing_new_fund: number;
  existing_same_fund: number;
  error: number;
  warnings: number;
}

export interface CommitResult {
  succeeded: { client_code: string; investment_id: number | null }[];
  failed: { client_code: string | null; message: string }[];
  skipped: { client_code: string | null; reason: string }[];
}

export type BulkUploadJobState = "queued" | "running" | "completed" | "failed";

// succeeded_sample is capped (currently 200) server-side so a 100k-row job's
// results don't serialize a multi-megabyte JSON blob — succeeded_count above
// it is always exact. failed/skipped are capped much higher (5,000) since
// those are what an admin actually needs to see in full to fix something.
export interface BulkUploadJobResults {
  succeeded_count: number;
  failed_count: number;
  skipped_count: number;
  succeeded_sample: { client_code: string; investment_id: number | null }[];
  failed: { client_code: string | null; message: string }[];
  skipped: { client_code: string | null; reason: string }[];
}

export interface BulkUploadJobStatus {
  id: number;
  filename: string | null;
  status: BulkUploadJobState;
  total_rows: number;
  processed_rows: number;
  succeeded_count: number;
  failed_count: number;
  skipped_count: number;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  results?: BulkUploadJobResults;
}

export const bulkUploadService = {
  async downloadTemplate(): Promise<void> {
    const res = await api.get(API.BULK_UPLOAD_TEMPLATE, { responseType: "blob" });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "bulk_upload_template.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },

  async getMapping(headers: string[]): Promise<SavedMapping | null> {
    const res = await api.get<ApiResponse<SavedMapping | null>>(
      `${API.BULK_UPLOAD_MAPPING}?headers=${encodeURIComponent(headers.join("||"))}`
    );
    return res.data.data ?? null;
  },

  async saveMapping(sourceHeaders: string[], mapping: ColumnMapping): Promise<SavedMapping> {
    const res = await api.post<ApiResponse<SavedMapping>>(API.BULK_UPLOAD_MAPPING, {
      source_headers: sourceHeaders,
      mapping,
    });
    return res.data.data as SavedMapping;
  },

  async validate(rows: Record<string, unknown>[]): Promise<{ rows: ValidatedRow[]; summary: ValidateSummary }> {
    const res = await api.post<ApiResponse<{ rows: ValidatedRow[]; summary: ValidateSummary }>>(
      API.BULK_UPLOAD_VALIDATE,
      { rows }
    );
    return res.data.data as { rows: ValidatedRow[]; summary: ValidateSummary };
  },

  // Starts the commit as a background job and returns immediately — the
  // actual writes happen off-request (see startBulkUploadJobPolling below
  // for watching it to completion). Previously this awaited the full commit
  // inline, which for a large file held the request open long enough to
  // freeze the app; see app/BulkUpload/route.py's commit_rows() docstring.
  async startCommit(rows: ValidatedRow[], filename: string): Promise<{ job_id: number; total_rows: number; status: BulkUploadJobState }> {
    const res = await api.post<ApiResponse<{ job_id: number; total_rows: number; status: BulkUploadJobState }>>(
      API.BULK_UPLOAD_COMMIT,
      { rows, filename }
    );
    return res.data.data as { job_id: number; total_rows: number; status: BulkUploadJobState };
  },

  async getJobStatus(jobId: number): Promise<BulkUploadJobStatus> {
    const res = await api.get<ApiResponse<BulkUploadJobStatus>>(`${API.BULK_UPLOAD_JOBS}/${jobId}`);
    return res.data.data as BulkUploadJobStatus;
  },
};

/**
 * Polls a bulk-upload job until it reaches a terminal state (completed/failed),
 * calling onUpdate after every poll so a progress bar can track processed_rows.
 * Returns a cancel function — call it if the component unmounts mid-poll.
 */
export function watchBulkUploadJob(
  jobId: number,
  onUpdate: (status: BulkUploadJobStatus) => void,
  { intervalMs = 1500 }: { intervalMs?: number } = {}
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const poll = async () => {
    if (cancelled) return;
    try {
      const status = await bulkUploadService.getJobStatus(jobId);
      if (cancelled) return;
      onUpdate(status);
      if (status.status === "completed" || status.status === "failed") return;
    } catch {
      // A transient network hiccup shouldn't stop polling — just try again next tick.
    }
    if (!cancelled) timer = setTimeout(poll, intervalMs);
  };

  poll();

  return () => {
    cancelled = true;
    if (timer) clearTimeout(timer);
  };
}
