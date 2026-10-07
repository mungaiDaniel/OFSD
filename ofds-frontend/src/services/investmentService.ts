import api from "./api";
import { API } from "@/lib/constants";
import type {
  ApiResponse,
  CreateInvestmentRequest,
  CreateNewInvestorRequest,
  AddExistingDepositRequest,
  InvestorOverviewData,
} from "@/lib/types";

export const investmentService = {
  async create(data: CreateInvestmentRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.INVESTMENTS, data);
    return res.data;
  },

  async getInvestorDirectory(params?: { page?: number; per_page?: number; search?: string }): Promise<ApiResponse> {
    const query = new URLSearchParams();
    if (params?.page) query.set("page", String(params.page));
    if (params?.per_page) query.set("per_page", String(params.per_page));
    if (params?.search) query.set("search", params.search);
    const qs = query.toString();
    const res = await api.get<ApiResponse>(qs ? `${API.INVESTOR_DIRECTORY}?${qs}` : API.INVESTOR_DIRECTORY);
    return res.data;
  },

  /** Register a brand-new investor and their first deposit (auto-assigned to a batch). */
  async createNewInvestor(data: CreateNewInvestorRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.INVESTOR_CREATE, data);
    return res.data;
  },

  /** Add a deposit for an investor that already has a client code on file. */
  async addExistingDeposit(data: AddExistingDepositRequest): Promise<ApiResponse> {
    const res = await api.post<ApiResponse>(API.INVESTOR_EXISTING_DEPOSIT, data);
    return res.data;
  },

  async getInvestorPortfolio(clientCode: string): Promise<ApiResponse> {
    const code = encodeURIComponent(clientCode);
    const res = await api.get<ApiResponse>(`/investors/${code}/portfolio`);
    return res.data;
  },

  /** Full position summary (per-currency, per-class) backing the investor overview page. */
  async getInvestorOverview(clientCode: string): Promise<ApiResponse<InvestorOverviewData>> {
    const code = encodeURIComponent(clientCode);
    const res = await api.get<ApiResponse<InvestorOverviewData>>(`/investors/${code}/overview`);
    return res.data;
  },

  /**
   * Update an investor's identity/advisory fields (propagates across all their
   * investment rows), and optionally move their non-deployed holdings to a
   * different share class / batch in the same call. Provide at most one of
   * `batch_id` (move to that existing open batch) or `create_new_batch` (spin
   * up a fresh batch for the resolved share class) — the backend rejects both
   * being set together.
   */
  async updateInvestorProfile(
    clientCode: string,
    data: Partial<{
      investor_name: string;
      investor_email: string;
      investor_phone: string;
      wealth_manager: string;
      IFA: string;
      contract_note: string;
      share_class_id: number;
      batch_id: number;
      create_new_batch: boolean;
    }>
  ): Promise<ApiResponse> {
    const code = encodeURIComponent(clientCode);
    const res = await api.patch<ApiResponse>(`/investors/${code}`, data);
    return res.data;
  },

  /** Queue a statement email for this investor as Pending_Confirmation (sent via the admin email queue). */
  async queueStatementEmail(clientCode: string): Promise<ApiResponse> {
    const code = encodeURIComponent(clientCode);
    const res = await api.post<ApiResponse>(`/investors/${code}/statement-email/preview`);
    return res.data;
  },

  async getInvestorHistory(clientCode: string): Promise<ApiResponse> {
    const code = encodeURIComponent(clientCode);
    const res = await api.get<ApiResponse>(`/investors/${code}/history`);
    return res.data;
  },

  async getInvestorStatements(clientCode: string): Promise<ApiResponse> {
    const code = encodeURIComponent(clientCode);
    // ✅ FIX: Call plural /statements endpoint which includes deposits, monthly reports, and withdrawals
    const res = await api.get<ApiResponse>(`/investors/${code}/statements`);
    return res.data;
  },

  async getInvestorEmailLogs(clientCode: string): Promise<ApiResponse> {
    const res = await api.get<ApiResponse>(API.INVESTOR_EMAIL_LOGS(clientCode));
    return res.data;
  },

  async downloadInvestorStatementPdf(clientCode: string): Promise<void> {
    const normalizedClientCode = decodeURIComponent(clientCode);
    const res = await api.get(`${API.INVESTOR_STATEMENT_PDF_CLIENT(normalizedClientCode)}`, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `investor-statement-${normalizedClientCode}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.parentNode?.removeChild(link);
    window.URL.revokeObjectURL(url);
  },

  async getRecentNotifications(): Promise<ApiResponse> {
    const res = await api.get<ApiResponse>(API.RECENT_NOTIFICATIONS);
    return res.data;
  },

  async getNotificationFailures(notificationId: number): Promise<ApiResponse> {
    const res = await api.get<ApiResponse>(`/batches/notifications/recent/${notificationId}/failures`);
    return res.data;
  },
};
