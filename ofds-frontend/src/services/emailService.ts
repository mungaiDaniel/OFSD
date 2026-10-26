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
  async getInbox(params?: { search?: string; page?: number; per_page?: number }): Promise<ApiResponse<PendingEmail[]>> {
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
   * Confirm (queue) EVERY resendable email in the inbox — Pending_Confirmation
   * / Suppressed / Failed — optionally scoped to the same search filter the
   * inbox list uses. This is the "Confirm All" for the whole inbox (which can
   * be tens of thousands of rows after a large bulk upload); confirmBatch
   * above is for a small, already-known id list instead.
   */
  async confirmAll(search?: string): Promise<ApiResponse<{ queued: number }>> {
    const res = await api.post<ApiResponse<{ queued: number }>>(API.EMAIL_CONFIRM_ALL, search ? { search } : {});
    return res.data;
  },

  /**
   * Suppress (without sending) EVERY still-actionable email in the inbox —
   * Pending_Confirmation / Queued — optionally scoped to the same search
   * filter. Mirrors confirmAll above; cancelBatch is for a small, already-
   * known id list instead.
   */
  async suppressAll(search?: string): Promise<ApiResponse<{ suppressed: number }>> {
    const res = await api.post<ApiResponse<{ suppressed: number }>>(API.EMAIL_SUPPRESS_ALL, search ? { search } : {});
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
  ): Promise<ApiResponse<{ queued: string[]; skipped: { client_code: string; reason: string }[]; not_found: string[] }>> {
    const res = await api.post<ApiResponse<{ queued: string[]; skipped: { client_code: string; reason: string }[]; not_found: string[] }>>(
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
    const start = await api.post<ApiResponse<{ job_id: string; total: number }>>(
      API.EMAIL_STATEMENTS_DOWNLOAD_BATCH,
      fundIds && fundIds.length ? { client_codes: clientCodes, fund_ids: fundIds } : { client_codes: clientCodes }
    );
    const { job_id, total } = start.data.data as { job_id: string; total: number };
    onProgress?.(0, total);

    for (;;) {
      await new Promise((r) => setTimeout(r, 1500));
      const res = await api.get<ApiResponse<{ state: string; total: number; done: number; failed: { client_code: string; reason: string }[]; error?: string }>>(
        `${API.EMAIL_STATEMENTS_DOWNLOAD_BATCH}/${job_id}`
      );
      const st = res.data.data as { state: string; total: number; done: number; failed: { client_code: string; reason: string }[]; error?: string };
      onProgress?.(st.done, st.total);
      if (st.state === "failed") throw new Error(st.error || "Building the statements failed");
      if (st.state === "completed") {
        const file = await api.get(`${API.EMAIL_STATEMENTS_DOWNLOAD_BATCH}/${job_id}/file`, { responseType: "blob" });
        const url = window.URL.createObjectURL(new Blob([file.data], { type: "application/zip" }));
        const link = document.createElement("a");
        link.href = url;
        link.setAttribute("download", filenameFromDisposition(file.headers?.["content-disposition"], "Statements.zip"));
        document.body.appendChild(link);
        link.click();
        link.parentNode?.removeChild(link);
        window.URL.revokeObjectURL(url);
        return { total: st.total, failed: st.failed ?? [] };
      }
    }
  },
};
