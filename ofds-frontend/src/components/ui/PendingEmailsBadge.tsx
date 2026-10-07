import { useState, useEffect, useCallback, useRef } from "react";
import { Mail } from "lucide-react";
import { emailService } from "@/services/emailService";
import { EmailConfirmationModal } from "./EmailConfirmationModal";
import { useAuth } from "@/context/AuthContext";

// Intentionally not polling on an interval.
// We fetch once on mount (for admins) and again on window focus / after modal closes.
const FOCUS_THROTTLE_MS = 15_000;

/**
 * PendingEmailsBadge
 *
 * Fixed bottom-right corner badge that polls /emails/pending every 30s.
 * Shows a pulsing red dot + count when there are pending emails.
 * Clicking opens the EmailConfirmationModal globally.
 *
 * Mount once in App.tsx — it persists across all routes.
 */
export function PendingEmailsBadge() {
  const { isAuthenticated, role } = useAuth();
  const [count, setCount] = useState(0);
  const [modalOpen, setModalOpen] = useState(false);
  const inFlightRef = useRef(false);
  const lastFetchAtRef = useRef(0);

  const poll = useCallback(async (reason?: string) => {
    if (!isAuthenticated) return;
    if (inFlightRef.current) return;
    const now = Date.now();
    if (reason === "focus" && now - lastFetchAtRef.current < FOCUS_THROTTLE_MS) return;

    inFlightRef.current = true;
    try {
      const res = await emailService.getPending();
      setCount(res.data?.count ?? 0);
    } catch {
      // Silently ignore on poll failures — don't interrupt the admin
    } finally {
      inFlightRef.current = false;
      lastFetchAtRef.current = Date.now();
    }
  }, [isAuthenticated]);

  useEffect(() => {
    // Only show/poll inside the authenticated app, and only for admins.
    const pathname = typeof window !== "undefined" ? window.location.pathname : "";
    const isAuthRoute = pathname === "/login" || pathname === "/register";
    const canSee = role === "admin" || role === "super_admin";

    if (!isAuthenticated || isAuthRoute || !canSee) {
      setCount(0);
      return;
    }

    poll();

    const onFocus = () => poll("focus");
    window.addEventListener("focus", onFocus);
    return () => {
      window.removeEventListener("focus", onFocus);
    };
  }, [poll, isAuthenticated, role]);

  // After modal closes, refresh the count immediately
  const handleModalClose = useCallback(() => {
    setModalOpen(false);
    if (isAuthenticated) poll();
  }, [poll, isAuthenticated]);


  // Don't render anything if no pending emails and modal not open
  if (count === 0 && !modalOpen) return null;

  return (
    <>
      {/* ─── Floating trigger button ─────────────────────────────────── */}
      <button
        id="pending-emails-badge"
        onClick={() => setModalOpen(true)}
        aria-label={`${count} pending email${count !== 1 ? "s" : ""} awaiting confirmation`}
        style={{
          position: "fixed",
          bottom: "28px",
          right: "28px",
          zIndex: 9997,
          display: "flex",
          alignItems: "center",
          gap: "9px",
          padding: "10px 16px",
          borderRadius: "999px",
          background: "linear-gradient(135deg, #0B1228, #131E3D)",
          border: "1px solid rgba(59,111,212,0.4)",
          color: "#FFFFFF",
          fontSize: "13px",
          fontWeight: 700,
          cursor: "pointer",
          boxShadow: "0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(59,111,212,0.2)",
          fontFamily: "var(--font-body)",
          transition: "box-shadow 0.2s ease, transform 0.15s ease",
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLButtonElement).style.boxShadow =
            "0 12px 40px rgba(0,0,0,0.6), 0 0 0 1px rgba(59,111,212,0.5)";
          (e.currentTarget as HTMLButtonElement).style.transform = "translateY(-2px)";
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLButtonElement).style.boxShadow =
            "0 8px 32px rgba(0,0,0,0.5), 0 0 0 1px rgba(59,111,212,0.2)";
          (e.currentTarget as HTMLButtonElement).style.transform = "translateY(0)";
        }}
      >
        {/* Mail icon */}
        <Mail size={15} color="#3B6FD4" />

        {/* Label */}
        <span style={{ color: "#94A3B8", fontWeight: 500, fontSize: "12px" }}>
          Pending emails
        </span>

        {/* Count pill with pulse */}
        <span
          style={{
            position: "relative",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minWidth: "20px",
            height: "20px",
            padding: "0 6px",
            borderRadius: "999px",
            background: "#D44B4B",
            color: "#FFFFFF",
            fontSize: "11px",
            fontWeight: 700,
            lineHeight: 1,
          }}
        >
          {count}
          {/* Pulsing ring */}
          <span
            style={{
              position: "absolute",
              inset: "-3px",
              borderRadius: "999px",
              border: "2px solid #D44B4B",
              animation: "badge-pulse 2s ease-in-out infinite",
              opacity: 0.6,
            }}
          />
        </span>
      </button>

      {/* ─── Keyframe for pulse ring ──────────────────────────────────── */}
      <style>{`
        @keyframes badge-pulse {
          0%   { transform: scale(1);   opacity: 0.6; }
          50%  { transform: scale(1.5); opacity: 0; }
          100% { transform: scale(1);   opacity: 0.6; }
        }
      `}</style>

      {/* ─── Modal ───────────────────────────────────────────────────── */}
      <EmailConfirmationModal
        open={modalOpen}
        onClose={handleModalClose}
      />
    </>
  );
}
