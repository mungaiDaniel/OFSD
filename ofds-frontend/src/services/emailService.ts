import type { AxiosResponse } from "axios";
import api from "./api";
import { API } from "@/lib/constants";
import { filenameFromDisposition } from "@/lib/utils";
import type { ApiResponse, PendingEmail } from "@/lib/types";

// Re-exported so existing consumers (EmailConfirmationModal, PendingEmailsBadge)
// can keep importing the type from this module.
export type { PendingEmail };

export const emailService = {
  /**
   * Strictly-pending emails (excludes Suppressed). Returns the raw axios
   * response — NOT unwrapped — because EmailConfirmationModal / PendingEmailsBadge
   * read `res.data.data` and `res.data.count` off it.
   */
  async getPending(): Promise<AxiosResponse<ApiResponse<PendingEmail[]> & { count?: number }>> {
    return api.get<ApiResponse<PendingEmail[]> & { count?: number }>(API.EMAILS_PENDING);
  },

  /**
   * Emails still needing human attention: Pending_Confirmation + Suppressed + Queued.
   * With no `search`, `data` comes back empty — only counts. Pass `search`
   * (client code, email, or phone) to fetch matching rows.
   */
  async getInbox(params?: { search?: string; page?: number; per_page?: number; email_type?: string; batch_id?: number }): Promise<ApiResponse<PendingEmail[]>> {
    const res = await api.get<ApiResponse<PendingEmail[]>>(API.EMAILS_INBOX, { params });
    return res.data;
  },

  /** Emails already actioned: Confirmed (sent) + Failed. Same search-only-loads-rows pattern. */
  async getProcessed(params?: { search?: string; page?: number; per_page?: number }): Promise<ApiResponse<PendingEmail[]>> {
    const res = await api.get<ApiResponse<PendingEmail[]>>(API.EMAILS_PROCESSED, { params });
    return res.data;
  },

  /** Approve a pending/suppressed/failed email — queues it; the send-queue scheduler sends it within a few minutes. */
  async confirm(id: number): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.EMAIL_CONFIRM(id));
    return res.data;
  },

  /** Suppress a pending (or already-queued) email without sending it. */
  async cancel(id: number): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.EMAIL_CANCEL(id));
    return res.data;
  },

  /** Approve many emails in one request instead of one call per email. */
  async confirmBatch(ids: number[]): Promise<ApiResponse<{ queued: number[]; skipped: { id: number; reason: string }[]; not_found: number[] }>> {
    const res = await api.post<ApiResponse<{ queued: number[]; skipped: { id: number; reason: string }[]; not_found: number[] }>>(
      API.EMAIL_CONFIRM_BATCH,
      { ids }
    );
    return res.data;
  },

  /** Suppress many emails in one request instead of one call per email. */
  async cancelBatch(ids: number[]): Promise<ApiResponse<{ suppressed: number[]; skipped: { id: number; reason: string }[]; not_found: number[] }>> {
    const res = await api.post<ApiResponse<{ suppressed: number[]; skipped: { id: number; reason: string }[]; not_found: number[] }>>(
      API.EMAIL_CANCEL_BATCH,
      { ids }
    );
    return res.data;
  },

  /**
   * How many emails are queued, when the send-queue scheduler next runs, and
   * the active drain rate (batch_size/interval_minutes) — used to estimate
   * how long a bulk confirm will actually take to finish SENDING, not just
   * queuing (queuing is instant; sending is throttled on purpose).
   */
  async getQueueStatus(): Promise<ApiResponse<{ next_run_at: string | null; queued_count: number; batch_size: number; interval_minutes: number }>> {
    const res = await api.get<ApiResponse<{ next_run_at: string | null; queued_count: number; batch_size: number; interval_minutes: number }>>(API.EMAIL_QUEUE_STATUS);
    return res.data;
  },

  /**
   * Confirm (queue) every PENDING email matching the filters (type / batch / search).
   * expectedCount is the number the admin saw and typed; the server refuses (409)
   * if it now counts something different, so a stale screen can never approve more
   * than was shown.
   */
  async confirmAll(
    expectedCount: number,
    filters?: { search?: string; emailType?: string; batchId?: number }
  ): Promise<ApiResponse<{ queued: number }>> {
    const body: Record<string, unknown> = { expected_count: expectedCount };
    if (filters?.search) body.search = filters.search;
    if (filters?.emailType) body.email_type = filters.emailType;
    if (filters?.batchId != null) body.batch_id = filters.batchId;
    const res = await api.post<ApiResponse<{ queued: number }>>(API.EMAIL_CONFIRM_ALL, body);
    return res.data;
  },

  /** What a bulk send of one statement type would do for a fund/batch. Sends nothing. */
  async bulkSendPreview(sel: BulkSelection): Promise<BulkPreview> {
    const res = await api.get<ApiResponse<BulkPreview>>(API.EMAIL_BULK_SEND_PREVIEW, {
      params: { kind: sel.kind, fund_id: sel.fundId, batch_id: sel.batchId, include_sent: sel.includeSent ? 1 : undefined, client_code: sel.clientCode },
    });
    return res.data.data as BulkPreview;
  },

  /** The exact email one investor in the selection would get. Sends nothing. */
  async bulkSample(sel: BulkSelection, clientCode: string): Promise<BulkSample> {
    const res = await api.get<ApiResponse<BulkSample>>(API.EMAIL_BULK_SEND_SAMPLE, {
      params: { kind: sel.kind, fund_id: sel.fundId, batch_id: sel.batchId, client_code: clientCode },
    });
    return res.data.data as BulkSample;
  },

  /** The attached statement PDF for one investor, as a Blob (for an inline viewer). */
  async bulkSamplePdf(sel: BulkSelection, clientCode: string): Promise<Blob> {
    const res = await api.get(API.EMAIL_BULK_SEND_SAMPLE_PDF, {
      params: { kind: sel.kind, fund_id: sel.fundId, batch_id: sel.batchId, client_code: clientCode },
      responseType: "blob",
    });
    return res.data as Blob;
  },

  /** Queue exactly the previewed emails (expectedCount must equal the preview's will_send). */
  async bulkSend(sel: BulkSelection, expectedCount: number): Promise<{ email_ids: number[]; created: number; requeued: number }> {
    const res = await api.post<ApiResponse<{ email_ids: number[]; created: number; requeued: number }>>(API.EMAIL_BULK_SEND, {
      kind: sel.kind,
      fund_id: sel.fundId,
      batch_id: sel.batchId,
      include_sent: !!sel.includeSent,
      client_code: sel.clientCode,
      expected_count: expectedCount,
    });
    return res.data.data as { email_ids: number[]; created: number; requeued: number };
  },

  /** Status breakdown of just these emails (progress of one send). */
  async statusCounts(ids: number[]): Promise<{ total: number; counts: Record<string, number> }> {
    const res = await api.post<ApiResponse<{ total: number; counts: Record<string, number> }>>(API.EMAIL_STATUS_COUNTS, { ids });
    return res.data.data as { total: number; counts: Record<string, number> };
  },

  /**
   * Suppress (without sending) EVERY still-actionable email in the inbox —
   * Pending_Confirmation / Queued — optionally scoped to the same search
   * filter. Mirrors confirmAll above; cancelBatch is for a small, already-
   * known id list instead.
   */
  async suppressAll(search?: string, emailType?: string): Promise<ApiResponse<{ suppressed: number }>> {
    const body: Record<string, string> = {};
    if (search) body.search = search;
    if (emailType) body.email_type = emailType;
    const res = await api.post<ApiResponse<{ suppressed: number }>>(API.EMAIL_SUPPRESS_ALL, body);
    return res.data;
  },

  /**
   * Queues one "overall statement" email per client code (reusing the same
   * logic as the single-investor statement-email preview) — used by the
   * Email page's "Send Statements" tab after filtering eligible investors by
   * period/fund/share-class. Dedupes client codes and skips anyone who
   * already has a pending/queued statement email.
   *
   * fundIds: when the admin filtered this send to specific fund(s) (e.g.
   * "Fund = DPRP"), every matched recipient gets THAT fund's fund-scoped
   * statement in this send, not their full portfolio, even if they also
   * hold other funds. Omitted (the "All funds" filter) means every
   * recipient gets their full consolidated statement instead.
   */
  async queueStatementsBatch(
    clientCodes: string[],
    fundIds?: number[]
  ): Promise<ApiResponse<QueueBatchResult>> {
    const res = await api.post<ApiResponse<QueueBatchResult>>(
      API.EMAIL_STATEMENTS_QUEUE_BATCH,
      fundIds && fundIds.length ? { client_codes: clientCodes, fund_ids: fundIds } : { client_codes: clientCodes }
    );
    return res.data;
  },

  /**
   * Build every given client's statement PDF in the background and download ONE zip.
   * Same fund_ids rule as queueStatementsBatch (one fund -> that fund's statement;
   * omitted -> full consolidated statement). No email address is needed.
   * onProgress(done, total) is called while the server builds the PDFs.
   */
  async downloadStatementsZip(
    clientCodes: string[],
    fundIds: number[] | undefined,
    onProgress?: (done: number, total: number) => void
  ): Promise<{ total: number; failed: { client_code: string; reason: string }[] }> {
    return pollAndDownloadZip(
      API.EMAIL_STATEMENTS_DOWNLOAD_BATCH,
      fundIds && fundIds.length ? { client_codes: clientCodes, fund_ids: fundIds } : { client_codes: clientCodes },
      "Statements.zip",
      onProgress
    );
  },

  /** Recent zip jobs (kept 24h on the server), newest first. */
  async listStatementDownloads(): Promise<StatementDownloadJob[]> {
    const res = await api.get<ApiResponse<StatementDownloadJob[]>>(API.EMAIL_STATEMENT_DOWNLOADS);
    return (res.data.data as StatementDownloadJob[]) ?? [];
  },

  /** Save the zip of a finished job again (e.g. after closing the page before it was saved). */
  async saveFinishedDownload(jobId: string, fallbackName = "Statements.zip"): Promise<void> {
    await saveJobZip(jobId, fallbackName);
  },

  /**
   * Download the Transfer Statement & Confirmation PDFs of every investor in the chosen
   * batches/funds as ONE zip (folder per batch + summary.csv). Works before deployment.
   * stage "undeployed" = transferred but not yet deployed; "all" = any transferred batch.
   */
  async downloadTransferStatementsZip(
    selection: { batchIds?: number[]; fundIds?: number[]; stage?: "undeployed" | "all" },
    onProgress?: (done: number, total: number) => void
  ): Promise<{ total: number; failed: { client_code: string; reason: string }[] }> {
    return pollAndDownloadZip(
      API.EMAIL_TRANSFER_STATEMENTS_DOWNLOAD,
      { batch_ids: selection.batchIds, fund_ids: selection.fundIds, stage: selection.stage ?? "undeployed" },
      "Transfer Statements.zip",
      onProgress
    );
  },
};

/** Rows created by one queueStatementsBatch call - the ONLY emails that call may send. */
export interface QueuedStatementEmail {
  id: number;
  client_code: string;
  recipient_name: string | null;
  recipient_email: string | null;
  fund_name: string | null;
}

export interface QueueBatchResult {
  queued: string[];
  skipped: { client_code: string; reason: string }[];
  not_found: string[];
  emails: QueuedStatementEmail[];
}

export type BulkKind = "deposit" | "transfer" | "deployment" | "withdrawal" | "oversubscription";

export interface BulkSelection {
  kind: BulkKind;
  fundId?: number;
  batchId?: number;
  includeSent?: boolean;
  /** Narrow the selection to ONE investor (per-row "send again"). */
  clientCode?: string;
}

export interface BulkSample {
  to: string;
  name: string;
  subject: string;
  body: string;
  html: string;
  attachment_name: string | null;
}

export interface BulkPreviewRow {
  client_code: string;
  name: string;
  email: string;
  fund_name: string | null;
  batch_name: string | null;
  amount: number | null;
  currency: string;
  email_type: string;
  state: "none" | "pending" | "suppressed" | "failed" | "queued" | "sending" | "sent" | "no_email";
}

export interface BulkPreview {
  kind: BulkKind;
  label: string;
  counts: { total: number; no_email: number; ready: number; in_progress: number; already_sent: number; will_send: number };
  rows: BulkPreviewRow[];
}

export interface StatementDownloadJob {
  job_id: string;
  label: string;
  state: "running" | "completed" | "failed" | "interrupted" | string;
  total: number;
  done: number;
  failed_count: number;
  created_at: number | null;
  ready: boolean;
}

async function saveJobZip(jobId: string, fallbackName: string): Promise<void> {
  const file = await api.get(`${API.EMAIL_STATEMENTS_DOWNLOAD_BATCH}/${jobId}/file`, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([file.data], { type: "application/zip" }));
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", filenameFromDisposition(file.headers?.["content-disposition"], fallbackName));
  document.body.appendChild(link);
  link.click();
  link.parentNode?.removeChild(link);
  window.URL.revokeObjectURL(url);
}

type ZipJobResult = { total: number; failed: { client_code: string; reason: string }[] };

/** Start a background zip job, poll it (status/file routes are shared), save the zip. */
async function pollAndDownloadZip(
  startUrl: string,
  body: Record<string, unknown>,
  fallbackName: string,
  onProgress?: (done: number, total: number) => void
): Promise<ZipJobResult> {
  type Status = { state: string; total: number; done: number; failed: { client_code: string; reason: string }[]; error?: string };
  const start = await api.post<ApiResponse<{ job_id: string; total: number }>>(startUrl, body);
  const { job_id, total } = start.data.data as { job_id: string; total: number };
  onProgress?.(0, total);

  for (;;) {
    await new Promise((r) => setTimeout(r, 1500));
    const res = await api.get<ApiResponse<Status>>(`${API.EMAIL_STATEMENTS_DOWNLOAD_BATCH}/${job_id}`);
    const st = res.data.data as Status;
    onProgress?.(st.done, st.total);
    if (st.state === "interrupted") throw new Error("The server restarted while building the statements. Please start the download again.");
    if (st.state === "failed") throw new Error(st.error || "Building the statements failed");
    if (st.state === "completed") {
      await saveJobZip(job_id, fallbackName);
      return { total: st.total, failed: st.failed ?? [] };
    }
  }
}
