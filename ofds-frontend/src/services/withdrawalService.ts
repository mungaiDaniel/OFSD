import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, Withdrawal, CreateWithdrawalRequest, WithdrawalSource } from "@/lib/types";

type WithdrawalListParams = {
  status?: string;
  source?: WithdrawalSource;
  fundId?: number;
  search?: string;
  page?: number;
  perPage?: number;
};

type WithdrawalPagination = { page?: number; per_page?: number; total: number; total_pages?: number };

export const withdrawalService = {
  /** Paginated (default 200/page, capped 500) — pass `page`/`perPage` for the table, or use `getPendingCount` for a cheap count-only check. */
  async getAll(params?: WithdrawalListParams): Promise<{ data: Withdrawal[]; pagination: WithdrawalPagination }> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.source) query.set("source", params.source);
    if (params?.fundId) query.set("fund_id", String(params.fundId));
    if (params?.search) query.set("search", params.search);
    if (params?.page) query.set("page", String(params.page));
    if (params?.perPage) query.set("per_page", String(params.perPage));
    const qs = query.toString();
    const res = await api.get<ApiResponse<Withdrawal[]> & { pagination: WithdrawalPagination }>(
      qs ? `${API.WITHDRAWALS}?${qs}` : API.WITHDRAWALS
    );
    return { data: res.data.data ?? [], pagination: res.data.pagination ?? { total: (res.data.data ?? []).length } };
  },

  /** Cheap count-only lookup (no rows fetched) — for "Approve All"/"Reject All" previews at scale. */
  async getCount(params?: Omit<WithdrawalListParams, "page" | "perPage">): Promise<number> {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.source) query.set("source", params.source);
    if (params?.fundId) query.set("fund_id", String(params.fundId));
    if (params?.search) query.set("search", params.search);
    query.set("count_only", "true");
    const res = await api.get<ApiResponse<Withdrawal[]> & { pagination: WithdrawalPagination }>(
      `${API.WITHDRAWALS}?${query.toString()}`
    );
    return res.data.pagination?.total ?? 0;
  },

  async create(data: CreateWithdrawalRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.WITHDRAWALS, data);
    return res.data;
  },

  async uploadExcel(file: File): Promise<ApiResponse> {
    const formData = new FormData();
    formData.append("file", file);
    const res = await api.post<ApiResponse>(API.WITHDRAWALS_UPLOAD, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return res.data;
  },

  async approve(withdrawalId: number): Promise<ApiResponse> {
    const res = await api.patch<ApiResponse>(`${API.WITHDRAWALS}/${withdrawalId}`, { status: "Approved" });
    return res.data;
  },

  async reject(withdrawalId: number, note?: string): Promise<ApiResponse> {
    const res = await api.patch<ApiResponse>(`${API.WITHDRAWALS}/${withdrawalId}`, { status: "Rejected", note });
    return res.data;
  },

  // ── Bulk approve/reject — "Approve All" / "Reject All" for the current filter scope ──

  async bulkAction(
    action: "approve" | "reject",
    scope?: { source?: WithdrawalSource; fundId?: number },
    note?: string
  ): Promise<ApiResponse<{ processed: number; approved: number; rejected: number; affected_batch_ids: number[] }>> {
    const body: Record<string, unknown> = { action, note };
    if (scope?.source || scope?.fundId) {
      body.scope = {
        ...(scope.source ? { source: scope.source } : {}),
        ...(scope.fundId ? { fund_id: scope.fundId } : {}),
      };
    }
    const res = await api.post<ApiResponse<{ processed: number; approved: number; rejected: number; affected_batch_ids: number[] }>>(
      `${API.WITHDRAWALS}/bulk-action`,
      body
    );
    return res.data;
  },

  // ── Withdrawals / refunds export (e.g. DPRP oversubscription refunds) ──

  async downloadExport(
    format: "excel" | "pdf",
    filters?: { fundId?: number; status?: string; source?: WithdrawalSource; dateFrom?: string; dateTo?: string }
  ): Promise<void> {
    const query = new URLSearchParams();
    if (filters?.fundId) query.set("fund_id", String(filters.fundId));
    if (filters?.status) query.set("status", filters.status);
    if (filters?.source) query.set("source", filters.source);
    if (filters?.dateFrom) query.set("date_from", filters.dateFrom);
    if (filters?.dateTo) query.set("date_to", filters.dateTo);
    const qs = query.toString();
    const url = format === "excel" ? API.WITHDRAWALS_EXPORT_EXCEL : API.WITHDRAWALS_EXPORT_PDF;
    const res = await api.get(qs ? `${url}?${qs}` : url, { responseType: "blob" });

    const disposition = (res.headers?.["content-disposition"] as string) || "";
    const match = disposition.match(/filename="?([^";]+)"?/);
    const filename = match?.[1] || `Withdrawals.${format === "excel" ? "xlsx" : "pdf"}`;

    const blobUrl = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement("a");
    link.href = blobUrl;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
    window.URL.revokeObjectURL(blobUrl);
  },
};
