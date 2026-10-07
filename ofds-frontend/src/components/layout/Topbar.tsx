import { useAuth } from "@/context/AuthContext";
import { LogOut, Menu } from "lucide-react";
import { useUI } from "@/context/UIContext";
import { useLocation } from "react-router-dom";
import { BulkUploadJobIndicator } from "./BulkUploadJobIndicator";

export function Topbar() {
  const { role, userName, logout } = useAuth();
  const { setSidebarMobileOpen } = useUI();
  const location = useLocation();

  const avatarText = userName ? userName.trim().split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase() : "U";

  const pathSegments = location.pathname
    .split("/")
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1).replace(/-/g, " "));

  return (
    <header
      className="app-topbar"
      style={{
        height: "var(--topbar-height)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "0 0.75rem",
        background: "var(--color-bg-surface)",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        flexShrink: 0,
        zIndex: 1020,
        gap: "0.5rem",
      }}
    >
      {/* Left: menu + breadcrumb */}
      <div className="d-flex align-items-center gap-2 min-w-0 flex-grow-1">
        <button
          type="button"
          className="d-lg-none btn p-2 border-0 rounded-2 flex-shrink-0"
          onClick={() => setSidebarMobileOpen(true)}
          style={{ color: "var(--color-text-secondary)", background: "rgba(255,255,255,0.06)" }}
          aria-label="Open navigation menu"
        >
          <Menu size={20} />
        </button>

        <nav
          className="min-w-0 text-truncate"
          style={{ color: "var(--color-text-tertiary)", fontSize: "12px" }}
        >
          {pathSegments.length === 0 ? (
            <span style={{ color: "var(--color-text-secondary)" }}>Dashboard</span>
          ) : (
            pathSegments.map((segment, i) => (
              <span key={i}>
                {i > 0 && <span className="mx-2" style={{ opacity: 0.4 }}>/</span>}
                <span style={{ color: i === pathSegments.length - 1 ? "var(--color-text-secondary)" : "var(--color-text-tertiary)" }}>
                  {segment}
                </span>
              </span>
            ))
          )}
        </nav>
      </div>

      {/* Right: bulk-upload progress + role + username + avatar + logout */}
      <div className="d-flex align-items-center gap-2 flex-shrink-0">
        <BulkUploadJobIndicator />

        {role && (
          <span
            className="badge rounded-pill"
            style={{ background: "var(--color-brand-50)", color: "var(--color-brand-300)", fontSize: "10px", fontWeight: 600 }}
          >
            {role}
          </span>
        )}

        {userName && (
          <span
            className="d-none d-md-inline fw-semibold"
            style={{ color: "var(--color-text-secondary)", fontSize: "13px" }}
          >
            {userName}
          </span>
        )}

        <div
          className="d-flex align-items-center justify-content-center rounded-circle fw-bold"
          style={{
            width: "30px",
            height: "30px",
            background: "var(--color-brand-50)",
            color: "var(--color-brand-400)",
            fontSize: "12px",
          }}
        >
          {avatarText}
        </div>

        <button
          onClick={() => {
            logout();
            window.location.href = "/login";
          }}
          className="btn p-1 border-0"
          style={{ color: "var(--color-text-tertiary)", background: "none" }}
          title="Logout"
        >
          <LogOut size={16} />
        </button>
      </div>
    </header>
  );
}
