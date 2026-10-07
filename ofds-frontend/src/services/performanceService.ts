import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, CreatePerformanceRequest } from "@/lib/types";

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
};
