import api from "./api";
import { API } from "@/lib/constants";
import type {
  ApiResponse,
  CreateValuationRequest,
  CoreFund,
  NavValuationRequest,
  NavValuationPreviewResponse,
  NavValuationRunItem,
  ValuationJobStatus,
  ProductType,
  BatchValuationHistoryPoint,
} from "@/lib/types";

export const valuationService = {
  async createEpoch(data: CreateValuationRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.VALUATION_EPOCH, data);
    return res.data;
  },

  async dryRun(data: CreateValuationRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.VALUATION_DRY_RUN, data);
    return res.data;
  },

  /** Task 9: product scopes this to FUNDS or SHARES funds — Funds and Shares
   * valuations never mix (see app/Valuation/route.py's product filter). */
  async getActiveFunds(product?: ProductType): Promise<CoreFund[]> {
    const qs = product ? `?product=${product}` : "";
    const res = await api.get<ApiResponse<CoreFund[]>>(`${API.VALUATION_FUNDS}${qs}`);
    return res.data.data ?? [];
  },

  async confirm(data: CreateValuationRequest | any): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.VALUATION_CONFIRM, data);
    return res.data;
  },

  async preview(data: NavValuationRequest): Promise<NavValuationPreviewResponse> {
    const res = await api.post<ApiResponse<NavValuationPreviewResponse>>(
      API.VALUATION_PREVIEW,
      data
    );
    return (res.data as any).data ?? res.data;
  },

  /**
   * Starts the NAV valuation commit as a background job and returns
   * immediately — committing used to write a ValuationSnapshot per investor
   * inline in this request, which is what froze "commit valuation" at scale.
   * See watchValuationJob below for polling it to completion.
   */
  async startCommit(data: NavValuationRequest): Promise<{ job_id: number; total_investors: number; status: string }> {
    const res = await api.post<ApiResponse<{ job_id: number; total_investors: number; status: string }>>(
      API.VALUATION_NAV,
      data
    );
    return res.data.data as { job_id: number; total_investors: number; status: string };
  },

  async getJobStatus(jobId: number): Promise<ValuationJobStatus> {
    const res = await api.get<ApiResponse<ValuationJobStatus>>(`${API.VALUATION_JOBS}/${jobId}`);
    return res.data.data as ValuationJobStatus;
  },

  async listNavRuns(limit = 50, product?: ProductType): Promise<NavValuationRunItem[]> {
    const params = new URLSearchParams();
    params.set("limit", String(limit));
    if (product) params.set("product", product);
    const res = await api.get<ApiResponse<NavValuationRunItem[]>>(
      `${API.VALUATION_NAV_RUNS}?${params.toString()}`
    );
    return res.data.data ?? [];
  },

  /** Super admin: correct the date of a committed valuation run; statements follow automatically. */
  async updateRunDate(shareClassId: number, oldDate: string, newDate: string): Promise<string> {
    const res = await api.put<ApiResponse<unknown>>(API.VALUATION_NAV_RUN_DATE, {
      share_class_id: shareClassId,
      old_date: oldDate,
      new_date: newDate,
    });
    return res.data.message ?? "Valuation date updated";
  },

  /** Already-committed NAV valuation history for one batch — read-only, triggers no calculation. */
  async getBatchValuationHistory(batchId: number): Promise<BatchValuationHistoryPoint[]> {
    const res = await api.get<ApiResponse<BatchValuationHistoryPoint[]>>(API.VALUATION_BATCH_HISTORY(batchId));
    return res.data.data ?? [];
  },
};

/**
 * Polls a valuation commit job until it reaches a terminal state
 * (completed/failed), calling onUpdate after every poll so a progress bar
 * can track processed_investors. Returns a cancel function — call it if the
 * component unmounts mid-poll. Mirrors watchBulkUploadJob in bulkUploadService.ts.
 */
export function watchValuationJob(
  jobId: number,
  onUpdate: (status: ValuationJobStatus) => void,
  { intervalMs = 1500 }: { intervalMs?: number } = {}
): () => void {
  let cancelled = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const poll = async () => {
    if (cancelled) return;
    try {
      const status = await valuationService.getJobStatus(jobId);
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
