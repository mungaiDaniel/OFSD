import api from "./api";
import { API } from "@/lib/constants";
import type {
  ApiResponse,
  Batch,
  BatchInvestorLight,
  CreateBatchRequest,
  PatchBatchRequest,
  ProductType,
  SharesTransferPreview,
  SharesDeploymentPreview,
} from "@/lib/types";

export const batchService = {
  /** Omit `product` for every batch regardless of product (today's default behaviour). */
  async getAll(params?: { product?: ProductType }): Promise<Batch[]> {
    const res = await api.get<ApiResponse<Batch[]>>(API.BATCHES, { params });
    return res.data.data ?? [];
  },

  /**
   * With no `search`, the `investments` list on the returned Batch comes back
   * empty (batch-wide totals are still accurate) — pass `search` (client code,
   * email, or phone) to fetch matching investor rows, paginated.
   */
  async getById(id: number, params?: { search?: string; page?: number; per_page?: number; show_all?: boolean }): Promise<Batch> {
    const res = await api.get<ApiResponse<Batch>>(API.BATCH_BY_ID(id), { params });
    return res.data.data as Batch;
  },

  /** Full per-investor list (cheap fields only) — for the Transfer/Deploy modals, which need every investor to group by share class. */
  async getInvestmentsLight(id: number): Promise<BatchInvestorLight[]> {
    const res = await api.get<ApiResponse<BatchInvestorLight[]>>(API.BATCH_INVESTMENTS_LIGHT(id));
    return res.data.data ?? [];
  },

  /** Super admin: set individual clients' deployment dates in a deployed batch. */
  async updateInvestorDeploymentDates(id: number, dates: Record<number, string>): Promise<string> {
    const res = await api.put<ApiResponse<unknown>>(API.BATCH_INVESTOR_DEPLOYMENT_DATES(id), { dates });
    return res.data.message ?? "Deployment dates updated";
  },

  /** Server-generated Excel export of every investment in this batch matching the current search filter (not just the visible page). */
  async exportInvestments(id: number, params?: { search?: string }): Promise<void> {
    const res = await api.get(API.BATCH_INVESTMENTS_EXPORT(id), {
      params,
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `batch-${id}-clients-${new Date().toISOString().slice(0, 10)}.xlsx`);
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  async create(data: CreateBatchRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.BATCHES, data);
    return res.data;
  },

  async patch(id: number, data: PatchBatchRequest): Promise<ApiResponse> {
    const res = await api.patch<ApiResponse>(API.BATCH_BY_ID(id), data);
    return res.data;
  },

  async toggleActive(id: number): Promise<ApiResponse> {
    const res = await api.patch<ApiResponse>(API.BATCH_TOGGLE_ACTIVE(id), {});
    return res.data;
  },

  async uploadExcel(id: number, file: File): Promise<ApiResponse> {
    const formData = new FormData();
    formData.append("file", file);
    const res = await api.post<ApiResponse>(API.BATCH_UPLOAD_EXCEL(id), formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  async getSummary(id: number): Promise<ApiResponse> {
    const res = await api.get<ApiResponse>(API.BATCH_SUMMARY(id));
    return res.data;
  },

  async delete(id: number): Promise<ApiResponse> {
    const res = await api.delete<ApiResponse>(API.BATCH_BY_ID(id));
    return res.data;
  },

  async getFunds(id: number): Promise<ApiResponse> {
    const res = await api.get<ApiResponse>(API.BATCH_FUNDS(id));
    return res.data;
  },

  async getEmailLogs(id: number): Promise<ApiResponse> {
    const res = await api.get<ApiResponse>(API.BATCH_EMAIL_LOGS(id));
    return res.data;
  },

  /** Dry-run fee preview for the Transferred step of a SHARES batch — no DB writes. */
  async previewSharesTransfer(id: number, entryFeePercent: number | string, totalTransactionCostUsd: number | string): Promise<SharesTransferPreview> {
    const res = await api.get<ApiResponse<SharesTransferPreview>>(API.SHARES_TRANSFER_PREVIEW(id), {
      params: { entry_fee_percent: entryFeePercent, total_transaction_cost_usd: totalTransactionCostUsd },
    });
    return res.data.data as SharesTransferPreview;
  },

  /** Dry-run allocation preview for the Deployed step of a SHARES batch — no DB writes. */
  async previewSharesDeployment(
    id: number,
    exchangeRate: number | string,
    pricePerShareNgn: number | string,
    sharesAllocated: number | string
  ): Promise<SharesDeploymentPreview> {
    const res = await api.get<ApiResponse<SharesDeploymentPreview>>(API.SHARES_DEPLOYMENT_PREVIEW(id), {
      params: { exchange_rate: exchangeRate, price_per_share_ngn: pricePerShareNgn, shares_allocated: sharesAllocated },
    });
    return res.data.data as SharesDeploymentPreview;
  },

  async getHistory(id: number): Promise<ApiResponse> {
    try {
      console.log(`[batchService] Fetching history for batch ${id}`);
      const res = await api.get<ApiResponse>(`/batches/${id}/history`);
      console.log(`[batchService] History response status:`, res.status);
      console.log(`[batchService] History response data:`, res.data);
      return res.data;
    } catch (error) {
      console.error(`[batchService] Error fetching history for batch ${id}:`, error);
      throw error;
    }
  },
};
