import api from "./api";
import { API } from "@/lib/constants";
import type { ApiResponse, BackupLogEntry, BackupStatus } from "@/lib/types";

export const backupService = {
  async getAll(limit = 50): Promise<BackupLogEntry[]> {
    const res = await api.get<ApiResponse<BackupLogEntry[]>>(`${API.BACKUPS}?limit=${limit}`);
    return res.data.data ?? [];
  },

  async getStatus(): Promise<BackupStatus | null> {
    const res = await api.get<ApiResponse<BackupStatus>>(API.BACKUPS_STATUS);
    return res.data.data ?? null;
  },

  /** Triggers pg_dump + OneDrive upload synchronously; can take a while for a large DB. */
  async runNow(): Promise<BackupLogEntry> {
    const res = await api.post<ApiResponse<BackupLogEntry>>(API.BACKUPS_RUN_NOW, undefined, {
      timeout: 5 * 60 * 1000,
    });
    return res.data.data as BackupLogEntry;
  },
};
