import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, CoreFund, FundsSummaryResponse, FundShareClass, ProductType } from "@/lib/types";

/** Task 9: /api/v1/funds and /api/v1/shares are the same endpoints, scoped by
 * product (see Task 8) — every fundService method takes an optional
 * `product`, defaulting to FUNDS so every pre-Task-9 call site keeps working
 * unchanged. */
function basePath(product: ProductType = "FUNDS") {
  return product === "SHARES" ? API.SHARES : API.FUNDS;
}
function summaryPath(product: ProductType = "FUNDS") {
  return product === "SHARES" ? API.SHARES_SUMMARY : API.FUNDS_SUMMARY;
}
function classesPath(fundId: number | string, product: ProductType = "FUNDS") {
  return product === "SHARES" ? API.SHARE_CLASSES(fundId) : API.FUND_CLASSES(fundId);
}

export const fundService = {
  async getAll(product: ProductType = "FUNDS"): Promise<CoreFund[]> {
    const res = await api.get<ApiResponse<CoreFund[]>>(basePath(product));
    return res.data.data ?? [];
  },

  async getById(id: number, product: ProductType = "FUNDS"): Promise<CoreFund | null> {
    const res = await api.get<ApiResponse<CoreFund>>(`${basePath(product)}/${id}`);
    return res.data.data ?? null;
  },

  async getSummary(product: ProductType = "FUNDS"): Promise<FundsSummaryResponse | null> {
    try {
      const res = await api.get<ApiResponse<FundsSummaryResponse> | FundsSummaryResponse>(
        summaryPath(product)
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

  async create(fundName: string, product: ProductType = "FUNDS"): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(basePath(product), { fund_name: fundName });
    return res.data;
  },

  async createFund(fundName: string, fundCode: string, product: ProductType = "FUNDS"): Promise<CoreFund> {
    const res = await api.post<ApiResponse<CoreFund>>(basePath(product), {
      fund_name: fundName,
      fund_code: fundCode.toUpperCase(),
    });
    return (res.data as any).data ?? res.data;
  },

  async getClasses(fundId: number, product: ProductType = "FUNDS"): Promise<FundShareClass[]> {
    const res = await api.get<ApiResponse<FundShareClass[]>>(classesPath(fundId, product));
    return res.data.data ?? [];
  },

  async createClass(
    fundId: number | string,
    data: { class_name: string; class_code: string; currency: string },
    product: ProductType = "FUNDS"
  ): Promise<FundShareClass> {
    const res = await api.post<ApiResponse<FundShareClass>>(classesPath(fundId, product), {
      class_name: data.class_name,
      class_code: data.class_code.toUpperCase(),
      currency: data.currency,
    });
    return (res.data as any).data ?? res.data;
  },

  async updateClass(
    fundId: number | string,
    classId: number | string,
    data: Partial<{ class_name: string; class_code: string; currency: string }>,
    product: ProductType = "FUNDS"
  ): Promise<FundShareClass> {
    const payload = {
      ...data,
      class_code: data.class_code ? data.class_code.toUpperCase() : undefined,
    };
    const res = await api.patch<ApiResponse<FundShareClass>>(
      `${classesPath(fundId, product)}/${classId}`,
      payload
    );
    return (res.data as any).data ?? res.data;
  },

  async delete(id: number, product: ProductType = "FUNDS"): Promise<ApiResponse> {
    const res = await api.delete<ApiResponse>(`${basePath(product)}/${id}`);
    return res.data;
  },
};
