import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, CreatePerformanceRequest, BatchDistributionRow } from "@/lib/types";

export const performanceService = {
  async getByBatch(batchId: number, fundName?: string): Promise<ApiResponse> {
    const url = fundName
      ? `${API.BATCH_PERFORMANCE(batchId)}?fund_name=${fundName}`
      : API.BATCH_PERFORMANCE(batchId);
    const res = await api.get<ApiResponse>(url);
    return res.data;
  },

  async create(batchId: number, data: CreatePerformanceRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.BATCH_PERFORMANCE(batchId), data);
    return res.data;
  },

  async calculateProRata(batchId: number, fundName: string): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(
      `${API.BATCH_PRO_RATA(batchId)}?fund_name=${fundName}`
    );
    return res.data;
  },

  async uploadExcel(file: File): Promise<ApiResponse> {
    const formData = new FormData();
    formData.append("file", file);
    const res = await api.post<ApiResponse>(API.PERFORMANCE_UPLOAD_EXCEL, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  /**
   * Already-computed pro-rata distributions for a batch — read-only, runs no
   * calculation. The API groups rows by fund name instead of repeating it
   * per row; flattened here with fund_name attached to each row. A batch
   * that's never had pro-rata run returns 404 ("run it first") — that's a
   * normal empty state here, not an error, so it resolves to [].
   */
  async getDistributions(batchId: number): Promise<BatchDistributionRow[]> {
    try {
      const res = await api.get<{ funds?: Record<string, Omit<BatchDistributionRow, "fund_name">[]> }>(
        API.BATCH_DISTRIBUTIONS(batchId)
      );
      const funds = res.data.funds || {};
      return Object.entries(funds).flatMap(([fundName, rows]) =>
        rows.map((row) => ({ ...row, fund_name: fundName }))
      );
    } catch (err: any) {
      if (err?.response?.status === 404) return [];
      throw err;
    }
  },
};
