/**
 * BulkUploadJobContext — tracks the active bulk-upload commit job at the app
 * root (mounted above the router, alongside AuthProvider/UIProvider), not
 * inside BulkUploadPage. A commit on 100k rows can take several minutes;
 * without this, navigating away from the Bulk Upload page would unmount its
 * poller and the progress bar would simply disappear. Lifting it here means
 * the job keeps polling — and a small progress chip stays visible in the
 * Topbar (see BulkUploadJobIndicator) — no matter which page you're on.
 *
 * The active job id is also persisted to localStorage so a hard page reload
 * (not just SPA navigation) still finds and resumes watching an in-flight job.
 */
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { bulkUploadService, watchBulkUploadJob, type BulkUploadJobStatus } from "@/services/bulkUploadService";

const STORAGE_KEY = "ofsd_active_bulk_upload_job_id";

interface BulkUploadJobContextValue {
  activeJob: BulkUploadJobStatus | null;
  startWatching: (jobId: number) => void;
  dismiss: () => void;
}

const BulkUploadJobContext = createContext<BulkUploadJobContextValue | undefined>(undefined);

export function BulkUploadJobProvider({ children }: { children: React.ReactNode }) {
  const [activeJob, setActiveJob] = useState<BulkUploadJobStatus | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  const stopWatching = useCallback(() => {
    cancelRef.current?.();
    cancelRef.current = null;
  }, []);

  const startWatching = useCallback(
    (jobId: number) => {
      stopWatching();
      try {
        localStorage.setItem(STORAGE_KEY, String(jobId));
      } catch {
        // localStorage unavailable (private mode, blocked) — job still
        // tracked for the rest of this tab session, just won't survive reload.
      }
      cancelRef.current = watchBulkUploadJob(jobId, (status) => {
        setActiveJob(status);
        if (status.status === "completed" || status.status === "failed") {
          cancelRef.current = null;
          try {
            localStorage.removeItem(STORAGE_KEY);
          } catch {
            // ignore
          }
        }
      });
    },
    [stopWatching]
  );

  const dismiss = useCallback(() => {
    stopWatching();
    setActiveJob(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
  }, [stopWatching]);

  // On first mount (including after a hard reload), resume watching whatever
  // job id was left in localStorage — but only if it isn't already terminal,
  // so a completed/failed job from a previous session doesn't reappear.
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(STORAGE_KEY);
    } catch {
      saved = null;
    }
    const jobId = saved ? Number(saved) : NaN;
    if (!Number.isFinite(jobId)) return;

    let cancelled = false;
    bulkUploadService
      .getJobStatus(jobId)
      .then((status) => {
        if (cancelled) return;
        if (status.status === "completed" || status.status === "failed") {
          setActiveJob(status);
          try {
            localStorage.removeItem(STORAGE_KEY);
          } catch {
            // ignore
          }
          return;
        }
        startWatching(jobId);
      })
      .catch(() => {
        try {
          localStorage.removeItem(STORAGE_KEY);
        } catch {
          // ignore
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => stopWatching(), [stopWatching]);

  return (
    <BulkUploadJobContext.Provider value={{ activeJob, startWatching, dismiss }}>
      {children}
    </BulkUploadJobContext.Provider>
  );
}

export function useBulkUploadJob(): BulkUploadJobContextValue {
  const ctx = useContext(BulkUploadJobContext);
  if (!ctx) throw new Error("useBulkUploadJob must be used within BulkUploadJobProvider");
  return ctx;
}
