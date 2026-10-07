/**
 * ReportContext — provides the ReportProvider and useReport hook.
 *
 *   - fetchEligibleInvestors(params) → loads eligible investors list
 *   - fetchReportRuns() → loads recent report runs list
 *   - fetchReportRunDetail(id) → loads a single run's details
 *
 * Actually emailing statements to investors lives on the Email page's "Send
 * Statements" tab (emailService.queueStatementsBatch) — this context's old
 * generateReports(..., send_email: true) never sent anything (the backend
 * endpoint only ever wrote "pending" ReportRecipient rows), so it's been
 * removed rather than left as a dead, misleading action.
 */

import React, { createContext, useCallback, useContext, useState } from "react";
import { reportService } from "@/services/reportService";
import type {
  EligibleInvestor,
  ReportRunItem,
} from "@/lib/types";

// ── Context Shape ─────────────────────────────────────────────────────────────

interface ReportContextValue {
  // Eligible investors
  eligibleInvestors: EligibleInvestor[];
  loadingEligibleInvestors: boolean;
  errorEligibleInvestors: string | null;
  fetchEligibleInvestors: (params: {
    period: string;
    fund_id?: number;
    share_class_id?: number;
  }) => Promise<void>;

  // Report runs list
  reportRuns: ReportRunItem[];
  loadingReportRuns: boolean;
  errorReportRuns: string | null;
  fetchReportRuns: () => Promise<void>;

  // Single run detail
  selectedRun: ReportRunItem | null;
  loadingRunDetail: boolean;
  errorRunDetail: string | null;
  fetchReportRunDetail: (id: number | string) => Promise<void>;
}

// ── Context ───────────────────────────────────────────────────────────────────

const ReportContext = createContext<ReportContextValue | undefined>(undefined);

// ── Provider ──────────────────────────────────────────────────────────────────

export function ReportProvider({ children }: { children: React.ReactNode }) {
  // Eligible investors
  const [eligibleInvestors, setEligibleInvestors] = useState<EligibleInvestor[]>([]);
  const [loadingEligibleInvestors, setLoadingEligibleInvestors] = useState(false);
  const [errorEligibleInvestors, setErrorEligibleInvestors] = useState<string | null>(null);

  // Report runs list
  const [reportRuns, setReportRuns] = useState<ReportRunItem[]>([]);
  const [loadingReportRuns, setLoadingReportRuns] = useState(false);
  const [errorReportRuns, setErrorReportRuns] = useState<string | null>(null);

  // Single run detail
  const [selectedRun, setSelectedRun] = useState<ReportRunItem | null>(null);
  const [loadingRunDetail, setLoadingRunDetail] = useState(false);
  const [errorRunDetail, setErrorRunDetail] = useState<string | null>(null);

  // ── Actions ────────────────────────────────────────────────────────────────

  const fetchEligibleInvestors = useCallback(
    async (params: { period: string; fund_id?: number; share_class_id?: number }) => {
      setLoadingEligibleInvestors(true);
      setErrorEligibleInvestors(null);
      try {
        const data = await reportService.getEligibleInvestors(params);
        setEligibleInvestors(data);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to load eligible investors";
        setErrorEligibleInvestors(msg);
        console.error("Error fetching eligible investors:", err);
      } finally {
        setLoadingEligibleInvestors(false);
      }
    },
    []
  );

  const fetchReportRuns = useCallback(async () => {
    setLoadingReportRuns(true);
    setErrorReportRuns(null);
    try {
      const data = await reportService.getReportRuns();
      setReportRuns(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load report runs";
      setErrorReportRuns(msg);
      console.error("Error fetching report runs:", err);
    } finally {
      setLoadingReportRuns(false);
    }
  }, []);

  const fetchReportRunDetail = useCallback(async (id: number | string) => {
    setLoadingRunDetail(true);
    setErrorRunDetail(null);
    try {
      const data = await reportService.getReportRunById(id);
      setSelectedRun(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to load report run details";
      setErrorRunDetail(msg);
      console.error("Error fetching report run detail:", err);
    } finally {
      setLoadingRunDetail(false);
    }
  }, []);

  return (
    <ReportContext.Provider
      value={{
        eligibleInvestors,
        loadingEligibleInvestors,
        errorEligibleInvestors,
        fetchEligibleInvestors,
        reportRuns,
        loadingReportRuns,
        errorReportRuns,
        fetchReportRuns,
        selectedRun,
        loadingRunDetail,
        errorRunDetail,
        fetchReportRunDetail,
      }}
    >
      {children}
    </ReportContext.Provider>
  );
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useReport(): ReportContextValue {
  const ctx = useContext(ReportContext);
  if (!ctx) throw new Error("useReport must be used within ReportProvider");
  return ctx;
}
