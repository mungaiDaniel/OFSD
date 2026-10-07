import api from "./api";
import { API } from "@/lib/constants";
import type {
  ApiResponse,
  EmailSettingsData,
  EmailSettingsUpdate,
  EmailQueueSettingsData,
} from "@/lib/types";

export const settingsService = {
  async getEmailSettings(): Promise<EmailSettingsData | null> {
    const res = await api.get<ApiResponse<EmailSettingsData>>(API.SETTINGS_EMAIL);
    return res.data.data ?? null;
  },

  async updateEmailSettings(data: EmailSettingsUpdate): Promise<ApiResponse<EmailSettingsData>> {
    const res = await api.patch<ApiResponse<EmailSettingsData>>(API.SETTINGS_EMAIL, data);
    return res.data;
  },

  async sendTestEmail(recipient: string): Promise<ApiResponse<{ suppressed: boolean }>> {
    const res = await api.post<ApiResponse<{ suppressed: boolean }>>(API.SETTINGS_EMAIL_TEST, { recipient });
    return res.data;
  },

  async getEmailQueueSettings(): Promise<EmailQueueSettingsData | null> {
    const res = await api.get<ApiResponse<EmailQueueSettingsData>>(API.SETTINGS_EMAIL_QUEUE);
    return res.data.data ?? null;
  },

  async updateEmailQueueSettings(batchSize: number, intervalMinutes: number): Promise<ApiResponse> {
    const res = await api.patch<ApiResponse>(API.SETTINGS_EMAIL_QUEUE, { batch_size: batchSize, interval_minutes: intervalMinutes });
    return res.data;
  },
};
