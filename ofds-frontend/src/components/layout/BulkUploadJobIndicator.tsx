import { useNavigate } from "react-router-dom";
import { X } from "lucide-react";
import { useBulkUploadJob } from "@/context/BulkUploadJobContext";
import { ROUTES } from "@/lib/constants";

/**
 * Small progress chip in the Topbar (visible on every page) for the active
 * bulk-upload commit job — so a 100k-row commit stays trackable even after
 * navigating away from the Bulk Upload page. Clicking it jumps back there.
 */
export function BulkUploadJobIndicator() {
  const { activeJob, dismiss } = useBulkUploadJob();
  const navigate = useNavigate();

  if (!activeJob) return null;

  const isRunning = activeJob.status === "queued" || activeJob.status === "running";
  const pct = activeJob.total_rows > 0 ? Math.min(100, Math.round((activeJob.processed_rows / activeJob.total_rows) * 100)) : 0;

  const label = isRunning
    ? `Uploading investors ${activeJob.processed_rows.toLocaleString()}/${activeJob.total_rows.toLocaleString()} (${pct}%)`
    : activeJob.status === "completed"
      ? `Upload complete — ${activeJob.succeeded_count.toLocaleString()} added`
      : `Upload failed`;

  return (
    <button
      type="button"
      onClick={() => navigate(ROUTES.INVESTOR_BULK_UPLOAD)}
      title="Go to bulk upload progress"
      className="d-none d-md-flex align-items-center"
      style={{
        gap: "8px",
        padding: "4px 10px 4px 4px",
        borderRadius: "999px",
        border: "1px solid rgba(255,255,255,0.1)",
        background: "rgba(255,255,255,0.05)",
        cursor: "pointer",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          position: "relative",
          width: "22px",
          height: "22px",
          borderRadius: "50%",
          flexShrink: 0,
          background: isRunning
            ? `conic-gradient(var(--color-brand-400) ${pct * 3.6}deg, rgba(255,255,255,0.1) 0deg)`
            : activeJob.status === "completed"
              ? "var(--color-success)"
              : "var(--color-destructive)",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: "3px",
            borderRadius: "50%",
            background: "var(--color-bg-surface)",
          }}
        />
      </div>
      <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--color-text-secondary)", whiteSpace: "nowrap" }}>
        {label}
      </span>
      {!isRunning && (
        <span
          role="button"
          onClick={(e) => {
            e.stopPropagation();
            dismiss();
          }}
          title="Dismiss"
          style={{ color: "var(--color-text-tertiary)", display: "flex", padding: "2px" }}
        >
          <X size={12} />
        </span>
      )}
    </button>
  );
}
