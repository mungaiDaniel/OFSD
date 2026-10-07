/**
 * BackupsPage — Super Admin: view backup history, trigger a manual backup,
 * see the daily automatic schedule status.
 *
 * Backend: GET /reports/backups is not a thing — this hits /backups,
 * /backups/status, /backups/run-now (app/Backup/route.py). Automatic daily
 * backups are off (DB_BACKUP_ENABLED=False) until Azure/OneDrive env vars
 * are configured — see config.py.
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { backupService } from "@/services/backupService";
import type { BackupLogEntry, BackupStatus } from "@/lib/types";

const glass: React.CSSProperties = {
  background: "rgba(16,24,45,0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "12px",
};

function Spinner({ size = 20 }: { size?: number }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        border: `2px solid rgba(255,255,255,0.07)`,
        borderTopColor: "#3B82F6",
        borderRadius: "50%",
        animation: "spin 0.8s linear infinite",
      }}
    />
  );
}

function StatusBadge({ status }: { status: BackupLogEntry["status"] }) {
  const cfg = {
    success: { label: "Success", bg: "rgba(16,185,129,0.12)", color: "#10B981" },
    failed: { label: "Failed", bg: "rgba(239,68,68,0.12)", color: "#EF4444" },
    running: { label: "Running", bg: "rgba(59,130,246,0.12)", color: "#60A5FA" },
  }[status];
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "2px 8px",
        borderRadius: "100px",
        fontSize: "10px",
        fontWeight: 600,
        background: cfg.bg,
        color: cfg.color,
      }}
    >
      <span style={{ width: "4px", height: "4px", borderRadius: "50%", background: cfg.color }} />
      {cfg.label}
    </span>
  );
}

function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return (
    d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }) +
    " " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
  );
}

export default function BackupsPage() {
  const [backups, setBackups] = useState<BackupLogEntry[]>([]);
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    try {
      const [list, st] = await Promise.all([backupService.getAll(), backupService.getStatus()]);
      setBackups(list);
      setStatus(st);
    } catch {
      toast.error("Failed to load backups");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRunNow = async () => {
    setRunning(true);
    try {
      await backupService.runNow();
      toast.success("Backup completed and uploaded to OneDrive.");
      await load();
    } catch (err: any) {
      const msg = err?.response?.data?.message || "Backup failed";
      toast.error(msg);
      await load();
    } finally {
      setRunning(false);
    }
  };

  return (
    <div
      style={{
        position: "relative",
        zIndex: 1,
        padding: "24px 32px 48px",
        maxWidth: "1100px",
        margin: "0 auto",
        fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
        color: "#FFFFFF",
        display: "flex",
        flexDirection: "column",
        gap: "24px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <h1 style={{ fontSize: "22px", fontWeight: 700, letterSpacing: "-0.02em", margin: 0 }}>Backups</h1>
          <p style={{ fontSize: "12px", color: "#94A3B8", marginTop: "4px" }}>
            Daily automatic database backup to OneDrive, plus manual on-demand backups.
          </p>
        </div>
        <button
          onClick={handleRunNow}
          disabled={running}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "7px",
            padding: "9px 18px",
            borderRadius: "8px",
            background: running ? "rgba(26,69,255,0.45)" : "#1A45FF",
            color: "#fff",
            border: "none",
            fontFamily: "var(--font-sans)",
            fontSize: "12px",
            fontWeight: 500,
            cursor: running ? "not-allowed" : "pointer",
            boxShadow: "0 0 16px rgba(26,69,255,0.3)",
          }}
        >
          {running ? (
            <>
              <Spinner size={12} /> Running…
            </>
          ) : (
            "Run backup now"
          )}
        </button>
      </div>

      {/* Status panel */}
      <div style={{ ...glass, padding: "18px 24px", display: "flex", flexWrap: "wrap", gap: "28px" }}>
        <div>
          <div style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
            Automatic daily backup
          </div>
          {status?.enabled ? (
            <span style={{ fontSize: "13px", color: "#10B981", fontWeight: 600 }}>Enabled</span>
          ) : (
            <span style={{ fontSize: "13px", color: "#F59E0B", fontWeight: 600 }}>Not configured</span>
          )}
        </div>
        <div>
          <div style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
            Next scheduled run
          </div>
          <span style={{ fontSize: "13px", color: "#FFFFFF", fontFamily: "var(--font-mono)" }}>
            {status?.next_run_at ? formatDateTime(status.next_run_at) : "—"}
          </span>
        </div>
        <div>
          <div style={{ fontSize: "10px", color: "#475569", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "4px" }}>
            Last backup
          </div>
          <span style={{ fontSize: "13px", color: "#FFFFFF", fontFamily: "var(--font-mono)" }}>
            {status?.last_backup ? formatDateTime(status.last_backup.started_at) : "Never"}
          </span>
        </div>
      </div>

      {!status?.enabled && (
        <div
          style={{
            ...glass,
            padding: "14px 20px",
            fontSize: "12px",
            color: "#F59E0B",
            border: "1px solid rgba(245,158,11,0.25)",
            background: "rgba(245,158,11,0.06)",
          }}
        >
          Automatic daily backups are off. Set <code>DB_BACKUP_ENABLED=true</code> plus the Azure AD /
          OneDrive environment variables (<code>AZURE_TENANT_ID</code>, <code>AZURE_CLIENT_ID</code>,{" "}
          <code>AZURE_CLIENT_SECRET</code>, <code>ONEDRIVE_USER_ID</code>) and restart the backend to enable
          the schedule. "Run backup now" above uses the same config and will fail until it's set.
        </div>
      )}

      {/* History table */}
      <div style={{ ...glass, padding: "20px 24px", display: "flex", flexDirection: "column", gap: "14px" }}>
        <div style={{ fontSize: "13px", fontWeight: 600 }}>Backup history</div>

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "28px" }}>
            <Spinner />
          </div>
        ) : backups.length === 0 ? (
          <div style={{ textAlign: "center", padding: "28px", fontSize: "13px", color: "#475569" }}>No backups yet.</div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px", background: "rgba(0,0,0,0.15)", borderRadius: "8px", overflow: "hidden", border: "1px solid rgba(255,255,255,0.07)" }}>
              <thead style={{ background: "rgba(255,255,255,0.03)" }}>
                <tr>
                  {["Started", "Filename", "Trigger", "Size", "Status", ""].map((h, n) => (
                    <th
                      key={h}
                      style={{
                        textAlign: n >= 3 && n <= 4 ? "right" : "left",
                        padding: "9px 12px",
                        fontSize: "9px",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        color: "#475569",
                        borderBottom: "1px solid rgba(255,255,255,0.07)",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {backups.map((b) => (
                  <tr key={b.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "10px", color: "#94A3B8" }}>
                      {formatDateTime(b.started_at)}
                    </td>
                    <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: "11px" }}>{b.filename}</td>
                    <td style={{ padding: "10px 12px", fontSize: "11px", color: "#94A3B8", textTransform: "capitalize" }}>{b.triggered_by}</td>
                    <td style={{ padding: "10px 12px", textAlign: "right", fontFamily: "var(--font-mono)", fontSize: "11px", color: "#94A3B8" }}>
                      {formatSize(b.file_size_bytes)}
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "right" }}>
                      <StatusBadge status={b.status} />
                    </td>
                    <td style={{ padding: "10px 12px", textAlign: "right" }}>
                      {b.onedrive_web_url ? (
                        <a
                          href={b.onedrive_web_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{ fontSize: "11px", color: "#3B82F6", textDecoration: "none" }}
                        >
                          Open in OneDrive
                        </a>
                      ) : b.error_message ? (
                        <span title={b.error_message} style={{ fontSize: "11px", color: "#EF4444", cursor: "help" }}>
                          Error
                        </span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}
