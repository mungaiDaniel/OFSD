import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "@/lib/constants";
import { LogOut, User, Shield, Info } from "lucide-react";
import EmailSettingsSection from "@/components/settings/EmailSettingsSection";

const CARD: React.CSSProperties = {
  background: "rgba(16, 24, 45, 0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255, 255, 255, 0.07)",
  borderRadius: "16px",
  boxShadow: "rgba(0, 0, 0, 0.25) 0px 4px 24px",
  padding: "20px 24px",
};

const ROW: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "10px 0px",
  borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
};

export default function SettingsPage() {
  const { role, userName, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate(ROUTES.LOGIN);
  };

  const permissions = [
    { perm: "View dashboard, batches, funds, valuations, reports", has: true },
    { perm: "Create and manage batches and investments", has: true },
    { perm: "Commit valuations and trigger pro-rata allocation", has: true },
    { perm: "Manage user roles", has: role === "admin" || role === "super_admin" },
    { perm: "Access audit logs", has: role === "super_admin" },
  ];

  return (
    <div className="ofds-page">
      <div>
        <h1 style={{ fontSize: "22px", fontWeight: 700, color: "var(--color-text-primary)", letterSpacing: "-0.02em", marginBottom: "4px" }}>
          Settings
        </h1>
        <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "24px" }}>
          Account settings and system info
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: "14px", maxWidth: "540px" }}>
          {/* Account */}
          <div style={CARD}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
              <User size={16} style={{ color: "rgb(96, 165, 250)" }} />
              <h3 style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>Account</h3>
            </div>
            {userName && (
              <div style={ROW}>
                <span style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>Name</span>
                <span style={{ fontSize: "13px", color: "var(--color-text-primary)" }}>{userName}</span>
              </div>
            )}
            <div style={ROW}>
              <span style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>Role</span>
              <span
                style={{
                  fontSize: "10px", fontWeight: 600, padding: "2px 8px", borderRadius: "100px",
                  background: "rgba(168, 85, 247, 0.12)", color: "rgb(192, 132, 252)",
                }}
              >
                {role}
              </span>
            </div>
            <div style={ROW}>
              <span style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>API endpoint</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                {import.meta.env.VITE_API_URL}
              </span>
            </div>
          </div>

          {/* Email settings — super_admin only */}
          {role === "super_admin" && <EmailSettingsSection />}

          {/* Permissions */}
          <div style={CARD}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "16px" }}>
              <Shield size={16} style={{ color: "rgb(96, 165, 250)" }} />
              <h3 style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>Permissions</h3>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {permissions.map((p) => (
                <div key={p.perm} style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span
                    style={{
                      width: "6px", height: "6px", borderRadius: "50%", flexShrink: 0,
                      background: p.has ? "rgb(34, 197, 94)" : "var(--color-text-tertiary)",
                    }}
                  />
                  <span style={{ fontSize: "12px", color: p.has ? "var(--color-text-primary)" : "var(--color-text-tertiary)" }}>
                    {p.perm}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* About */}
          <div style={CARD}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
              <Info size={16} style={{ color: "rgb(96, 165, 250)" }} />
              <h3 style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", margin: 0 }}>About</h3>
            </div>
            <p style={{ fontSize: "13px", color: "var(--color-text-secondary)", margin: "0 0 4px" }}>
              OFDS — Operations Fund Distribution System
            </p>
            <p style={{ fontSize: "11px", color: "var(--color-text-tertiary)", margin: 0 }}>AIB AXYS Africa · v2.0.0</p>
          </div>

          {/* Sign out */}
          <button
            onClick={handleLogout}
            style={{
              width: "100%", padding: "12px 16px", borderRadius: "12px",
              background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.25)",
              color: "rgb(248, 113, 113)", fontSize: "13px", fontWeight: 500, cursor: "pointer",
              display: "flex", alignItems: "center", justifyContent: "center", gap: "8px",
            }}
          >
            <LogOut size={15} /> Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
