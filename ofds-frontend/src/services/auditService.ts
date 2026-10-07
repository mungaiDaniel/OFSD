import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, AuditLogEntry } from "@/lib/types";

/**
 * Audit log service — requires GET /api/v1/audit-logs endpoint
 * (backend dependency, may not exist yet)
 */
export const auditService = {
  async getAll(params?: {
    action?: string;
    target_type?: string;
    page?: number;
    per_page?: number;
  }): Promise<AuditLogEntry[]> {
    try {
      const res = await api.get<ApiResponse<AuditLogEntry[]>>(API.AUDIT_LOGS, { params });
      return res.data.data ?? [];
    } catch {
      // Backend endpoint may not exist yet — return empty array
      console.warn("Audit log endpoint not available yet");
      return [];
    }
  },

  async download(params?: {
    action?: string;
    target_type?: string;
  }): Promise<void> {
    const res = await api.get(API.AUDIT_LOGS_EXPORT, {
      params,
      responseType: "blob",
    });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "audit_logs.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  },
};
