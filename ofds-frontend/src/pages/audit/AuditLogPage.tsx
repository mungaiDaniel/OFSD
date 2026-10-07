import { useEffect, useState } from "react";
import { auditService } from "@/services/auditService";
import { formatDateTime } from "@/lib/utils";
import {} from "@/lib/utils";
import type { AuditLogEntry } from "@/lib/types";
import { Search, ShieldCheck, AlertTriangle, Download } from "lucide-react";

export default function AuditLogPage() {
  const [logs, setLogs] = useState<AuditLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionFilter, setActionFilter] = useState("");
  const [search, setSearch] = useState("");
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    setLoading(true);
    auditService.getAll({ action: actionFilter || undefined })
      .then((data) => {
        setLogs(data);
        setUnavailable(false);
      })
      .catch(() => setUnavailable(true))
      .finally(() => setLoading(false));
  }, [actionFilter]);

  const filtered = search
    ? logs.filter((l) =>
        (l.action || "").toLowerCase().includes(search.toLowerCase()) ||
        (l.target_name || "").toLowerCase().includes(search.toLowerCase()) ||
        (l.description || "").toLowerCase().includes(search.toLowerCase())
      )
    : logs;

  const uniqueActions = [...new Set(logs.map((l) => l.action))].sort();
  const onDownload = async () => {
    try {
      await auditService.download({ action: actionFilter || undefined });
    } catch {
      setUnavailable(true);
    }
  };

  return (
    <div className="container-fluid px-0">
      <div className="page-header-row mb-4">
        <div className="d-flex align-items-center gap-3">
          <ShieldCheck size={22} style={{ color: "var(--color-brand-400)" }} />
          <div>
            <h1 className="fw-bold mb-1" style={{ fontSize: "22px", color: "var(--color-text-primary)" }}>Audit log</h1>
            <p className="mb-0" style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
              System-wide activity log — super admin access only
            </p>
          </div>
        </div>
        <button
          type="button"
          className="btn btn-sm d-inline-flex align-items-center gap-2"
          onClick={onDownload}
          style={{ background: "var(--color-brand-50)", color: "var(--color-brand-300)", border: "1px solid rgba(59,111,212,0.35)" }}
        >
          <Download size={14} />
          Download CSV
        </button>
      </div>

      {unavailable && (
        <div className="rounded-lg border p-5 mb-4 flex items-center gap-3" style={{ background: "var(--color-warning-bg)", borderColor: "var(--color-warning)" }}>
          <AlertTriangle size={18} style={{ color: "var(--color-warning)" }} />
          <div>
            <p className="text-sm font-medium" style={{ color: "var(--color-warning)" }}>Audit log endpoint not available</p>
            <p className="text-xs mt-0.5" style={{ color: "var(--color-text-secondary)" }}>The backend needs to implement <span style={{ fontFamily: "var(--font-mono)" }}>GET /api/v1/audit-logs</span> with pagination. This UI is ready and will work once the endpoint is deployed.</p>
          </div>
        </div>
      )}

      <div className="card shadow overflow-hidden" style={{ background: "var(--color-bg-surface)", borderColor: "var(--color-border-subtle)" }}>
        <div className="d-flex flex-wrap align-items-center justify-content-between gap-3 px-3 px-md-4 py-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="form-select form-select-sm" style={{ maxWidth: "220px" }}>
            <option value="">All actions</option>
            {uniqueActions.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>

          <div className="position-relative w-100 ms-md-auto" style={{ minWidth: 0, maxWidth: "min(100%, 280px)" }}>
            <Search size={14} style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-tertiary)" }} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search logs..." className="form-control form-control-sm w-100" style={{ paddingLeft: "30px" }} />
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20"><div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }} /></div>
        ) : (
          <div className="table-responsive">
          <table className="table table-dark mb-0" style={{ background: "var(--color-bg-surface)" }}>
            <thead>
              <tr>
                {["Timestamp", "Action", "Target", "User", "Description", "Status", "IP"].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((log) => (
                <tr key={log.id}>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-tertiary)" }}>{formatDateTime(log.timestamp)}</td>
                  <td><span className="badge rounded-pill" style={{ background: "var(--color-brand-50)", color: "var(--color-brand-300)", fontSize: "10px", fontWeight: 700 }}>{log.action}</span></td>
                  <td style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>{log.target_type || "—"}{log.target_name ? ` · ${log.target_name}` : ""}</td>
                  <td style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>
                    {log.user_name || "Unknown user"}
                  </td>
                  <td style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>{log.description || "—"}</td>
                  <td><span className="badge rounded-pill" style={{ background: log.success ? "var(--color-success-bg)" : "var(--color-destructive-bg)", color: log.success ? "var(--color-success)" : "var(--color-destructive)", fontSize: "10px", fontWeight: 700 }}>{log.success ? "OK" : "FAIL"}</span></td>
                  <td style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-tertiary)" }}>{log.ip_address || "—"}</td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan={7} className="px-4 py-12 text-center text-sm" style={{ color: "var(--color-text-tertiary)" }}>{unavailable ? "Waiting for backend endpoint." : "No audit logs found."}</td></tr>}
            </tbody>
          </table>
          </div>
        )}

        <div className="px-3 px-md-4 py-2" style={{ borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
          {filtered.length} entries
        </div>
      </div>
    </div>
  );
}
