import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, Batch, BatchInvestorLight, CreateBatchRequest, PatchBatchRequest } from "@/lib/types";

export const batchService = {
  async getAll(): Promise<Batch[]> {
    const res = await api.get<ApiResponse<Batch[]>>(API.BATCHES);
    return res.data.data ?? [];
  },

  /**
   * With no `search`, the `investments` list on the returned Batch comes back
   * empty (batch-wide totals are still accurate) — pass `search` (client code,
   * email, or phone) to fetch matching investor rows, paginated.
   */
  async getById(id: number, params?: { search?: string; page?: number; per_page?: number }): Promise<Batch> {
    const res = await api.get<ApiResponse<Batch>>(API.BATCH_BY_ID(id), { params });
    return res.data.data as Batch;
  },

  /** Full per-investor list (cheap fields only) — for the Transfer/Deploy modals, which need every investor to group by share class. */
  async getInvestmentsLight(id: number): Promise<BatchInvestorLight[]> {
    const res = await api.get<ApiResponse<BatchInvestorLight[]>>(API.BATCH_INVESTMENTS_LIGHT(id));
    return res.data.data ?? [];
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
