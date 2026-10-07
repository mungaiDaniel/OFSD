import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, CoreFund, FundsSummaryResponse, FundShareClass } from "@/lib/types";

export const fundService = {
  async getAll(): Promise<CoreFund[]> {
    const res = await api.get<ApiResponse<CoreFund[]>>(API.FUNDS);
    return res.data.data ?? [];
  },

  async getById(id: number): Promise<CoreFund | null> {
    const res = await api.get<ApiResponse<CoreFund>>(`${API.FUNDS}/${id}`);
    return res.data.data ?? null;
  },

  async getSummary(): Promise<FundsSummaryResponse | null> {
    try {
      const res = await api.get<ApiResponse<FundsSummaryResponse> | FundsSummaryResponse>(
        API.FUNDS_SUMMARY
      );
      const data = (res.data as any)?.data ?? res.data;
      if (!data || !Array.isArray(data.funds)) return null;
      return {
        as_of_date: data.as_of_date ?? new Date().toISOString().slice(0, 10),
        funds: data.funds,
      };
    } catch (err) {
      console.warn("Fund summary unavailable", err);
      return null;
    }
  },

  async create(fundName: string): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.FUNDS, { fund_name: fundName });
    return res.data;
  },

  async createFund(fundName: string, fundCode: string): Promise<CoreFund> {
    const res = await api.post<ApiResponse<CoreFund>>(API.FUNDS, {
      fund_name: fundName,
      fund_code: fundCode.toUpperCase(),
    });
    return (res.data as any).data ?? res.data;
  },

  async getClasses(fundId: number): Promise<FundShareClass[]> {
    const res = await api.get<ApiResponse<FundShareClass[]>>(API.FUND_CLASSES(fundId));
    return res.data.data ?? [];
  },

  async createClass(
    fundId: number | string,
    data: { class_name: string; class_code: string; currency: string }
  ): Promise<FundShareClass> {
    const res = await api.post<ApiResponse<FundShareClass>>(API.FUND_CLASSES(fundId), {
      class_name: data.class_name,
      class_code: data.class_code.toUpperCase(),
      currency: data.currency,
    });
    return (res.data as any).data ?? res.data;
  },

  async updateClass(
    fundId: number | string,
    classId: number | string,
    data: Partial<{ class_name: string; class_code: string; currency: string }>
  ): Promise<FundShareClass> {
    const payload = {
      ...data,
      class_code: data.class_code ? data.class_code.toUpperCase() : undefined,
    };
    const res = await api.patch<ApiResponse<FundShareClass>>(
      `${API.FUND_CLASSES(fundId)}/${classId}`,
      payload
    );
    return (res.data as any).data ?? res.data;
  },

  async delete(id: number): Promise<ApiResponse> {
    const res = await api.delete<ApiResponse>(`${API.FUNDS}/${id}`);
    return res.data;
  },
};
