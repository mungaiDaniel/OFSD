import { useEffect, useState } from "react";
import { userService } from "@/services/userService";
import { useAuth } from "@/context/AuthContext";
import { formatDate } from "@/lib/utils";
import type { User } from "@/lib/types";
import { toast } from "sonner";
import { CheckCircle2, Ban, KeyRound } from "lucide-react";

export default function UserManagementPage() {
  const { role: myRole } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [resetUser, setResetUser] = useState<User | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [savingReset, setSavingReset] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setUsers(await userService.getAll()); }
    catch { toast.error("Failed to load users"); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const approve = async (userId: number) => {
    if (!confirm(`Approve user #${userId}?`)) return;
    try {
      await userService.approve(userId);
      toast.success("User approved");
      await load();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Approval failed");
    }
  };

  const deactivate = async (userId: number) => {
    if (!confirm(`Deactivate user #${userId}? This will set status back to pending.`)) return;
    try {
      await userService.setStatus(userId, "pending");
      toast.success("User set to pending");
      await load();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Deactivation failed");
    }
  };

  const openResetModal = (user: User) => {
    setResetUser(user);
    setNewPassword("");
    setConfirmPassword("");
  };

  const closeResetModal = () => {
    if (savingReset) return;
    setResetUser(null);
    setNewPassword("");
    setConfirmPassword("");
  };

  const submitResetPassword = async () => {
    if (!resetUser) return;
    if (newPassword.trim().length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }
    try {
      setSavingReset(true);
      await userService.resetPassword(resetUser.id, newPassword.trim());
      toast.success(`Password reset for ${resetUser.email}`);
      closeResetModal();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Password reset failed");
    } finally {
      setSavingReset(false);
    }
  };

  const setRole = async (userId: number, role: "user" | "admin" | "super_admin") => {
    try {
      await userService.setRole(userId, role);
      toast.success(`Role updated to ${role}`);
      await load();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Role update failed");
    }
  };

  const safeUsers = Array.isArray(users) ? users : [];

  return (
    <div className="container-fluid px-0">
      {/* Header */}
      <div className="mb-4">
        <h1 className="fw-bold mb-1" style={{ fontSize: "22px", color: "var(--color-text-primary)" }}>
          Users
        </h1>
        <p className="mb-0" style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
          Manage system users and role assignments
        </p>
      </div>

      {/* Table card */}
      <div className="card shadow">
        {loading ? (
          <div className="d-flex align-items-center justify-content-center py-5">
            <div className="spinner-border spinner-border-sm" style={{ color: "var(--color-brand-400)" }} role="status">
              <span className="visually-hidden">Loading...</span>
            </div>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-dark mb-0" style={{ background: "var(--color-bg-surface)" }}>
              <thead>
                <tr>
                  {["Name", "Email", "Role", "Status", "Created", "Actions"].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {safeUsers.map((u) => (
                  <tr key={u.id}>
                    <td className="fw-bold" style={{ fontSize: "13px" }}>{u.name}</td>
                    <td style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>{u.email}</td>
                    <td>
                      <select
                        className="form-select form-select-sm d-inline-block"
                        value={u.role}
                        disabled={myRole !== "super_admin"}
                        onChange={(e) => setRole(u.id, e.target.value as any)}
                        style={{ width: "150px", fontSize: "12px" }}
                        title={myRole !== "super_admin" ? "Only superadmin can change roles" : undefined}
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                        <option value="super_admin">super_admin</option>
                      </select>
                    </td>
                    <td>
                      <span
                        className="badge rounded-pill"
                        style={{
                          fontSize: "10px",
                          fontWeight: 600,
                          background: u.status === "active" ? "var(--color-success-bg)" : "var(--color-warning-bg)",
                          color: u.status === "active" ? "var(--color-success)" : "var(--color-warning)",
                        }}
                      >
                        {u.status}
                      </span>
                    </td>
                    <td style={{ color: "var(--color-text-tertiary)", fontSize: "12px" }}>{formatDate(u.created)}</td>
                    <td>
                      {myRole === "super_admin" && u.status === "pending" && (
                        <button
                          onClick={() => approve(u.id)}
                          className="btn btn-sm d-inline-flex align-items-center gap-1"
                          style={{
                            fontSize: "11px",
                            background: "var(--color-success-bg)",
                            color: "var(--color-success)",
                            border: "1px solid rgba(61, 187, 120, 0.35)",
                            borderRadius: "6px",
                          }}
                        >
                          <CheckCircle2 size={12} /> Approve
                        </button>
                      )}

                      {myRole === "super_admin" && u.status === "active" && (
                        <button
                          onClick={() => deactivate(u.id)}
                          className="btn btn-sm d-inline-flex align-items-center gap-1 ms-2"
                          style={{
                            fontSize: "11px",
                            background: "rgba(239, 68, 68, 0.10)",
                            color: "var(--color-destructive)",
                            border: "1px solid rgba(239, 68, 68, 0.25)",
                            borderRadius: "6px",
                          }}
                          title="Set status back to pending"
                        >
                          <Ban size={12} /> Deactivate
                        </button>
                      )}

                      {myRole === "super_admin" && (
                        <button
                          onClick={() => openResetModal(u)}
                          className="btn btn-sm d-inline-flex align-items-center gap-1 ms-2"
                          style={{
                            fontSize: "11px",
                            background: "rgba(0, 64, 204, 0.10)",
                            color: "var(--color-brand-300)",
                            border: "1px solid rgba(0, 102, 255, 0.25)",
                            borderRadius: "6px",
                          }}
                          title="Reset password"
                        >
                          <KeyRound size={12} /> Reset
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {safeUsers.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-5" style={{ color: "var(--color-text-tertiary)" }}>
                      No users found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        <div
          className="px-4 py-2"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: "11px", color: "var(--color-text-tertiary)" }}
        >
          {safeUsers.length} user{safeUsers.length !== 1 ? "s" : ""}
        </div>
      </div>

      {resetUser && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(6, 11, 26, 0.72)",
            backdropFilter: "blur(3px)",
            zIndex: 1200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
          }}
          onClick={closeResetModal}
        >
          <div
            className="card shadow-lg w-100"
            style={{ maxWidth: "480px", background: "var(--color-bg-surface)", border: "1px solid var(--color-border-subtle)" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="card-body p-4 p-md-5">
              <h3 className="fw-bold mb-1" style={{ color: "var(--color-text-primary)", fontSize: "18px" }}>
                Reset Password
              </h3>
              <p className="mb-4" style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>
                Set a new password for <span style={{ fontFamily: "var(--font-mono)" }}>{resetUser.email}</span>
              </p>

              <div className="mb-3">
                <label className="form-label" style={{ fontSize: "12px" }}>New Password</label>
                <input
                  type="password"
                  className="form-control"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                />
              </div>
              <div className="mb-4">
                <label className="form-label" style={{ fontSize: "12px" }}>Confirm Password</label>
                <input
                  type="password"
                  className="form-control"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat password"
                />
              </div>

              <div className="d-flex justify-content-end gap-2">
                <button className="btn btn-outline-secondary btn-sm" onClick={closeResetModal} disabled={savingReset}>
                  Cancel
                </button>
                <button className="btn btn-primary btn-sm" onClick={submitResetPassword} disabled={savingReset}>
                  {savingReset ? "Saving..." : "Reset Password"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
