import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { valuationService, watchValuationJob } from "@/services/valuationService";
import { ROUTES } from "@/lib/constants";
import { formatDate } from "@/lib/utils";
import type {
  NavValuationPreviewResponse,
  NavClassPreview,
  NavValuationCommitResults,
  ValuationJobStatus,
} from "@/lib/types";
import { toast } from "sonner";

function formatNumberDecimals(val: number | null | undefined, digits = 4) {
  if (val == null) return "—";
  return val.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "9px 12px",
  borderRadius: "8px",
  background: "rgba(0, 0, 0, 0.25)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  color: "#FFFFFF",
  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
  fontSize: "13px",
  outline: "none",
  transition: "all 0.15s",
  letterSpacing: "-0.01em",
};

function handleFocus(e: React.FocusEvent<HTMLInputElement>) {
  e.target.style.borderColor = "#3B82F6";
  e.target.style.boxShadow = "0 0 0 3px rgba(59, 130, 246, 0.15)";
  e.target.style.background = "rgba(0, 0, 0, 0.35)";
}

function handleBlur(e: React.FocusEvent<HTMLInputElement>) {
  e.target.style.borderColor = "rgba(255, 255, 255, 0.1)";
  e.target.style.boxShadow = "none";
  e.target.style.background = "rgba(0, 0, 0, 0.25)";
}

function CurrencyBadge({ currency }: { currency: string }) {
  const isKES = currency === "KES";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: "6px",
        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
        fontSize: "10px",
        fontWeight: 600,
        letterSpacing: "0.04em",
        background: isKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
        color: isKES ? "var(--color-kes)" : "var(--color-usd)",
        border: isKES ? "1px solid var(--color-kes-border)" : "1px solid var(--color-usd-border)",
      }}
    >
      {currency}
    </span>
  );
}

function StatusPill({ status, diff }: { status: "PASS" | "FAIL"; diff: number }) {
  const isPass = status === "PASS";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "5px",
        padding: "3px 10px",
        borderRadius: "100px",
        fontSize: "10px",
        fontWeight: 600,
        letterSpacing: "0.02em",
        background: isPass ? "rgba(16,185,129,0.12)" : "rgba(239,68,68,0.12)",
        color: isPass ? "#10B981" : "#EF4444",
        border: isPass ? "1px solid rgba(16,185,129,0.3)" : "1px solid rgba(239,68,68,0.3)",
      }}
    >
      <span
        style={{
          width: "5px",
          height: "5px",
          borderRadius: "50%",
          background: isPass ? "#10B981" : "#EF4444",
        }}
      />
      {isPass ? "PASS" : "FAIL"} {!isPass && `Δ ${diff.toFixed(2)}`}
    </span>
  );
}

interface ClassRowState {
  classId: number;
  classCode: string;
  className: string;
  fundName: string;
  currency: string;
  prevNav: number | null | undefined;
  navPerShare: string;
  totalFundNav: string;
}

function extractClassRows(funds: any[], activeShareClassIds: Set<number>): ClassRowState[] {
  const list: ClassRowState[] = [];
  const filterByBatches = activeShareClassIds.size > 0;
  for (const fund of funds) {
    for (const cls of fund.classes || []) {
      if (cls.is_active !== false && (!filterByBatches || activeShareClassIds.has(cls.id))) {
        list.push({
          classId: cls.id,
          classCode: cls.class_code,
          className: cls.class_name,
          fundName: fund.fund_name,
          currency: cls.currency,
          prevNav: cls.current_nav,
          navPerShare: "",
          totalFundNav: "",
        });
      }
    }
  }
  return list;
}

export default function ValuationCreatePage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [classRows, setClassRows] = useState<ClassRowState[]>([]);
  const [valuationDate, setValuationDate] = useState(new Date().toISOString().slice(0, 10));
  const [step, setStep] = useState<"entry" | "preview" | "committing" | "success">("entry");
  const [previewing, setPreviewing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [previewData, setPreviewData] = useState<NavValuationPreviewResponse | null>(null);
  const [successData, setSuccessData] = useState<NavValuationCommitResults | null>(null);
  const [commitJob, setCommitJob] = useState<ValuationJobStatus | null>(null);
  const watcherCancelRef = React.useRef<(() => void) | null>(null);

  useEffect(() => () => watcherCancelRef.current?.(), []);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [summary, batches] = await Promise.all([
          fundService.getSummary().catch(() => null),
          batchService.getAll().catch(() => []),
        ]);
        const activeBatches = batches.filter((b: any) => b.is_active);
        const activeShareClassIds = new Set(
          activeBatches
            .map((b: any) => b.share_class_id)
            .filter((id: any) => typeof id === "number")
        );

        if (summary?.funds && summary.funds.length > 0) {
          setClassRows(extractClassRows(summary.funds, activeShareClassIds));
        } else {
          const funds = await fundService.getAll();
          const fundsWithClasses = await Promise.all(
            funds.map(async (f: any) => {
              const classes = await fundService.getClasses(f.id).catch(() => []);
              return {
                ...f,
                classes: classes.map((c: any) => ({
                  ...c,
                  is_active: true,
                })),
              };
            })
          );
          setClassRows(extractClassRows(fundsWithClasses, activeShareClassIds));
        }
      } catch {
        toast.error("Failed to load funds");
        setClassRows([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const updateRow = (classId: number, field: "navPerShare" | "totalFundNav", val: string) => {
    setClassRows((rows) =>
      rows.map((r) => (r.classId === classId ? { ...r, [field]: val } : r))
    );
  };

  const clean = (val: string) => val.replace(/[,\s]/g, "").trim();

  const filledRows = classRows.filter((r) => {
    const n = clean(r.navPerShare);
    const o = clean(r.totalFundNav);
    return (
      n !== "" &&
      !Number.isNaN(Number(n)) &&
      Number(n) > 0 &&
      o !== "" &&
      !Number.isNaN(Number(o)) &&
      Number(o) > 0
    );
  });

  const partialMismatch = classRows.some((r) => {
    const n = !!r.navPerShare.trim();
    const o = !!r.totalFundNav.trim();
    return n !== o;
  });

  const canPreview = filledRows.length > 0 && !partialMismatch && !!valuationDate;

  const buildPayload = () => ({
    valuation_date: valuationDate,
    classes: filledRows.map((r) => ({
      share_class_id: r.classId,
      nav_per_share: parseFloat(clean(r.navPerShare)),
      total_fund_nav: parseFloat(clean(r.totalFundNav)),
    })),
  });

  const handlePreview = async () => {
    if (!canPreview) return;
    setPreviewing(true);
    try {
      const res = await valuationService.preview(buildPayload());
      setPreviewData(res);
      setStep("preview");
    } catch (err: any) {
      toast.error(
        err?.response?.data?.message ??
          "Preview failed — check your values and try again."
      );
    } finally {
      setPreviewing(false);
    }
  };

  const handleCommit = async () => {
    if (!previewData) return;
    if (!previewData.classes.every((c) => c.status === "PASS")) {
      toast.error("Cannot commit: one or more classes failed reconciliation.");
      return;
    }
    setCommitting(true);
    try {
      const { job_id } = await valuationService.startCommit(buildPayload());
      setStep("committing");
      watcherCancelRef.current = watchValuationJob(job_id, (status) => {
        setCommitJob(status);
        if (status.status === "completed") {
          setCommitting(false);
          setSuccessData(status.results ?? null);
          setStep("success");
          toast.success(`Valuation committed — ${status.snapshots_created} snapshot(s) saved`);
        } else if (status.status === "failed") {
          setCommitting(false);
          setStep("preview");
          toast.error(status.error_message || "Valuation commit job failed");
        }
      });
    } catch (err: any) {
      toast.error(err?.response?.data?.message ?? "Commit failed. Please try again.");
      setCommitting(false);
    }
  };

  // ── STEP 2.5: COMMITTING (background job progress) ──
  if (step === "committing") {
    const total = commitJob?.total_investors ?? 0;
    const processed = commitJob?.processed_investors ?? 0;
    const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
    return (
      <div
        style={{
          position: "relative",
          zIndex: 1,
          padding: "24px 32px 48px",
          maxWidth: "600px",
          margin: "0 auto",
          fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
          color: "#FFFFFF",
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ textAlign: "center", paddingTop: "60px" }}
        >
          <div
            style={{
              width: "48px",
              height: "48px",
              margin: "0 auto 20px",
              borderRadius: "50%",
              border: "3px solid rgba(255,255,255,0.1)",
              borderTopColor: "var(--color-brand-400, #3B82F6)",
              animation: "spin 0.8s linear infinite",
            }}
          />
          <div style={{ fontSize: "18px", fontWeight: 700, marginBottom: "8px" }}>
            Committing valuation…
          </div>
          <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "24px" }}>
            {total > 0
              ? `${processed.toLocaleString()} of ${total.toLocaleString()} investor(s) processed`
              : "Starting…"}
            {" — safe to leave this page, it keeps running in the background."}
          </div>
          <div
            style={{
              height: "8px",
              borderRadius: "999px",
              background: "rgba(255,255,255,0.08)",
              overflow: "hidden",
              marginBottom: "8px",
            }}
          >
            <div
              style={{
                height: "100%",
                width: `${pct}%`,
                background: "var(--color-brand-400, #3B82F6)",
                borderRadius: "999px",
                transition: "width 0.3s ease",
              }}
            />
          </div>
          <div style={{ fontSize: "12px", color: "#475569" }}>{pct}% complete</div>
        </motion.div>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // ── STEP 3: SUCCESS ──
  if (step === "success" && successData) {
    return (
      <div
        style={{
          position: "relative",
          zIndex: 1,
          padding: "24px 32px 48px",
          maxWidth: "800px",
          margin: "0 auto",
          fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
          color: "#FFFFFF",
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          style={{ textAlign: "center" }}
        >
          <div
            style={{
              width: "64px",
              height: "64px",
              borderRadius: "50%",
              background: "rgba(16,185,129,0.12)",
              border: "1px solid rgba(16,185,129,0.35)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 20px",
              boxShadow: "0 0 30px rgba(16,185,129,0.15)",
            }}
          >
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <path
                d="M9 16l5 5 9-10"
                stroke="#10B981"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div
            style={{
              fontSize: "22px",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              marginBottom: "8px",
            }}
          >
            Valuation committed
          </div>
          <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "8px" }}>
            NAV as of <strong style={{ color: "#FFFFFF" }}>{formatDate(successData.valuation_date)}</strong>
          </div>
          <div style={{ fontSize: "12px", color: "#475569", marginBottom: "28px" }}>
            Snapshots saved for all investors. Monthly statements can now be generated.
          </div>

          <div
            style={{
              background: "rgba(16,24,45,0.72)",
              border: "1px solid rgba(255,255,255,0.07)",
              borderRadius: "12px",
              overflow: "hidden",
              marginBottom: "24px",
              textAlign: "left",
            }}
          >
            {successData.classes.map((cls, idx) => {
              const row = classRows.find((r) => r.classCode === cls.class_code);
              const isKES = row?.currency === "KES";
              return (
                <div
                  key={cls.class_code}
                  style={{
                    padding: "14px 18px",
                    borderBottom:
                      idx < successData.classes.length - 1
                        ? "1px solid rgba(255,255,255,0.07)"
                        : "none",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: "14px",
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        fontSize: "12px",
                        color: isKES ? "var(--color-kes)" : "var(--color-usd)",
                        fontWeight: 600,
                      }}
                    >
                      {cls.class_code}
                    </div>
                    <div style={{ fontSize: "11px", color: "#475569", marginTop: "2px" }}>
                      {cls.investor_count} investor{cls.investor_count !== 1 ? "s" : ""} updated
                      {cls.snapshots_created !== cls.investor_count ? ` (${cls.snapshots_created} new snapshot${cls.snapshots_created !== 1 ? "s" : ""})` : ""}
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div
                      style={{
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        fontSize: "12px",
                        color: "#FFFFFF",
                      }}
                    >
                      NAV {formatNumberDecimals(cls.nav_per_share, 4)}
                    </div>
                    <StatusPill status={cls.status} diff={cls.difference} />
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
            <button
              onClick={() => navigate(ROUTES.REPORTS)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "9px 16px",
                borderRadius: "8px",
                background: "transparent",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "#94A3B8",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              View reports
            </button>
            <button
              onClick={() => {
                setStep("entry");
                setPreviewData(null);
                setSuccessData(null);
              }}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "9px 16px",
                borderRadius: "8px",
                background: "#1A45FF",
                color: "#fff",
                border: "none",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
                boxShadow: "0 0 16px rgba(26,69,255,0.3)",
              }}
            >
              New valuation
            </button>
          </div>
        </motion.div>
      </div>
    );
  }

  // ── STEP 2: PREVIEW ──
  if (step === "preview" && previewData) {
    const allPass = previewData.classes.every((c) => c.status === "PASS");

    return (
      <div
        style={{
          position: "relative",
          zIndex: 1,
          padding: "24px 32px 48px",
          maxWidth: "900px",
          margin: "0 auto",
          fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
          color: "#FFFFFF",
        }}
      >
        <div style={{ marginBottom: "22px" }}>
          <button
            onClick={() => setStep("entry")}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              background: "transparent",
              border: "none",
              color: "#94A3B8",
              fontSize: "11px",
              cursor: "pointer",
              padding: "0 0 12px",
              fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
            }}
          >
            <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
              <path
                d="M11 7H3M6 4L3 7l3 3"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Back to edit
          </button>
          <h1
            style={{
              fontSize: "22px",
              fontWeight: 700,
              color: "#FFFFFF",
              letterSpacing: "-0.02em",
              margin: 0,
              marginBottom: "4px",
            }}
          >
            Valuation Preview
          </h1>
          <div style={{ fontSize: "12px", color: "#94A3B8" }}>
            NAV as of <strong style={{ color: "#FFFFFF" }}>{formatDate(previewData.valuation_date)}</strong> ·
            Review reconciliation before committing.
          </div>
        </div>

        {!allPass && (
          <div
            style={{
              padding: "12px 16px",
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.3)",
              borderRadius: "10px",
              display: "flex",
              gap: "10px",
              alignItems: "flex-start",
              marginBottom: "18px",
              fontSize: "12px",
              color: "#FCA5A5",
              lineHeight: 1.55,
            }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              style={{ color: "#EF4444", flexShrink: 0, marginTop: "1px" }}
            >
              <path
                d="M7 1L1 12h12L7 1z"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinejoin="round"
              />
              <line
                x1="7"
                y1="5.5"
                x2="7"
                y2="8"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinecap="round"
              />
              <circle cx="7" cy="10" r="0.6" fill="currentColor" />
            </svg>
            <span>
              <strong style={{ color: "#EF4444" }}>Reconciliation failed.</strong> One or more
              classes have a difference greater than 10.00 currency units. Review the values and
              re-enter the correct NAV.
            </span>
          </div>
        )}

        {previewData.classes.map((cls: NavClassPreview, idx: number) => {
          const row = classRows.find((r) => r.classCode === cls.class_code);
          const isKES = row?.currency === "KES";
          const isPass = cls.status === "PASS";

          return (
            <motion.div
              key={cls.class_code}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: idx * 0.1, duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
              style={{
                background: "rgba(16,24,45,0.72)",
                WebkitBackdropFilter: "blur(20px) saturate(150%)",
                backdropFilter: "blur(20px) saturate(150%)",
                border: `1px solid ${isPass ? "rgba(255,255,255,0.07)" : "rgba(239,68,68,0.2)"}`,
                borderRadius: "12px",
                overflow: "hidden",
                marginBottom: "14px",
              }}
            >
              <div
                style={{
                  padding: "14px 18px",
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  gap: "14px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                  <CurrencyBadge currency={row?.currency ?? (isKES ? "KES" : "USD")} />
                  <div>
                    <div
                      style={{
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        fontSize: "13px",
                        fontWeight: 600,
                        color: "#FFFFFF",
                      }}
                    >
                      {cls.class_code}
                    </div>
                    <div style={{ fontSize: "11px", color: "#475569" }}>
                      {row?.className ?? ""}
                    </div>
                  </div>
                </div>
                <StatusPill status={cls.status} diff={cls.difference} />
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, 1fr)",
                  gap: "1px",
                  background: "rgba(255,255,255,0.04)",
                  borderBottom: "1px solid rgba(255,255,255,0.07)",
                }}
              >
                {[
                  {
                    label: "Shares",
                    value: cls.total_shares.toLocaleString("en-US", {
                      minimumFractionDigits: 4,
                      maximumFractionDigits: 4,
                    }),
                  },
                  {
                    label: "NAV / Share",
                    value: formatNumberDecimals(cls.nav_per_share, 4),
                  },
                  {
                    label: "System Total",
                    value: cls.system_total_nav.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    }),
                  },
                  {
                    label: "AXYS Total",
                    value: cls.head_office_nav.toLocaleString("en-US", {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    }),
                  },
                ].map(({ label, value }) => (
                  <div
                    key={label}
                    style={{ padding: "12px 18px", background: "rgba(16,24,45,0.72)" }}
                  >
                    <div
                      style={{
                        fontSize: "9px",
                        fontWeight: 600,
                        color: "#475569",
                        textTransform: "uppercase",
                        letterSpacing: "0.08em",
                        marginBottom: "5px",
                      }}
                    >
                      {label}
                    </div>
                    <div
                      style={{
                        fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                        fontSize: "13px",
                        fontWeight: 600,
                        color: "#FFFFFF",
                        letterSpacing: "-0.01em",
                      }}
                    >
                      {value}
                    </div>
                  </div>
                ))}
              </div>

              <div
                style={{
                  padding: "10px 18px",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span style={{ fontSize: "11px", color: "#475569" }}>Difference</span>
                <span
                  style={{
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: isPass ? "#10B981" : "#EF4444",
                  }}
                >
                  {cls.difference >= 0 ? "+" : ""}
                  {cls.difference.toFixed(4)}{" "}
                  {isPass ? "✓ within tolerance" : "✗ exceeds 10.00"}
                </span>
              </div>

              {cls.investors && cls.investors.length > 0 && (
                <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                    <thead>
                      <tr style={{ background: "rgba(255,255,255,0.02)" }}>
                        {["Client Code", "Shares", "Market Value", "Performance"].map(
                          (header, colIdx) => (
                            <th
                              key={header}
                              style={{
                                padding: "8px 18px",
                                textAlign: colIdx === 0 ? "left" : "right",
                                fontSize: "9px",
                                fontWeight: 600,
                                color: "#475569",
                                textTransform: "uppercase",
                                letterSpacing: "0.06em",
                                borderBottom: "1px solid rgba(255,255,255,0.07)",
                              }}
                            >
                              {header}
                            </th>
                          )
                        )}
                      </tr>
                    </thead>
                    <tbody>
                      {cls.investors.slice(0, 5).map((inv) => (
                        <tr
                          key={inv.client_code}
                          style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}
                        >
                          <td
                            style={{
                              padding: "8px 18px",
                              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                              color: "#94A3B8",
                              fontSize: "11px",
                            }}
                          >
                            {inv.client_code}
                          </td>
                          <td
                            style={{
                              padding: "8px 18px",
                              textAlign: "right",
                              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                              color: "#FFFFFF",
                              fontSize: "11px",
                            }}
                          >
                            {inv.shares.toFixed(4)}
                          </td>
                          <td
                            style={{
                              padding: "8px 18px",
                              textAlign: "right",
                              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                              color: isKES ? "var(--color-kes)" : "var(--color-usd)",
                              fontSize: "11px",
                            }}
                          >
                            {inv.market_value.toLocaleString("en-US", {
                              minimumFractionDigits: 2,
                              maximumFractionDigits: 2,
                            })}
                          </td>
                          <td
                            style={{
                              padding: "8px 18px",
                              textAlign: "right",
                              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                              color: inv.performance_pct >= 0 ? "#10B981" : "#EF4444",
                              fontWeight: 600,
                              fontSize: "11px",
                            }}
                          >
                            {inv.performance_pct >= 0 ? "+" : ""}
                            {inv.performance_pct.toFixed(2)}%
                          </td>
                        </tr>
                      ))}
                      {cls.investors.length > 5 && (
                        <tr>
                          <td
                            colSpan={4}
                            style={{
                              padding: "8px 18px",
                              fontSize: "10px",
                              color: "#475569",
                              textAlign: "center",
                            }}
                          >
                            + {cls.investors.length - 5} more investors
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </motion.div>
          );
        })}

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginTop: "6px",
            padding: "16px 20px",
            background: "rgba(16,24,45,0.72)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: "12px",
            gap: "12px",
          }}
        >
          <div style={{ fontSize: "11px", color: "#475569" }}>
            {allPass
              ? "All classes passed reconciliation. Ready to commit."
              : "Fix the failing classes before committing."}
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={() => setStep("entry")}
              style={{
                background: "transparent",
                border: "none",
                color: "#94A3B8",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
                padding: "9px 16px",
                borderRadius: "8px",
              }}
            >
              Edit values
            </button>
            <button
              onClick={handleCommit}
              disabled={!allPass || committing}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                background: allPass && !committing ? "#1A45FF" : "rgba(255,255,255,0.06)",
                color: allPass && !committing ? "#fff" : "#475569",
                border: "none",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: allPass && !committing ? "pointer" : "not-allowed",
                padding: "9px 16px",
                borderRadius: "8px",
                boxShadow: allPass && !committing ? "0 0 16px rgba(26,69,255,0.3)" : "none",
                transition: "all 0.15s",
              }}
            >
              {committing ? (
                <>
                  <div
                    style={{
                      width: "11px",
                      height: "11px",
                      border: "1.5px solid rgba(255,255,255,0.3)",
                      borderTopColor: "#fff",
                      borderRadius: "50%",
                      animation: "spin 0.8s linear infinite",
                    }}
                  />
                  Committing…
                </>
              ) : (
                <>
                  Commit valuation
                  <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                    <path
                      d="M3 7h8M8 4l3 3-3 3"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── LOADING STATE ──
  if (loading) {
    return (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          height: "260px",
        }}
      >
        <div
          style={{
            width: "24px",
            height: "24px",
            border: "2px solid rgba(255,255,255,0.07)",
            borderTopColor: "#3B82F6",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }}
        />
      </div>
    );
  }

  // ── EMPTY STATE ──
  if (classRows.length === 0) {
    return (
      <div
        style={{
          position: "relative",
          zIndex: 1,
          padding: "24px 32px 48px",
          maxWidth: "800px",
          margin: "0 auto",
          fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
          color: "#FFFFFF",
          textAlign: "center",
        }}
      >
        <div style={{ padding: "64px 24px" }}>
          <div style={{ fontSize: "17px", fontWeight: 600, marginBottom: "8px" }}>
            No active share classes
          </div>
          <div style={{ fontSize: "13px", color: "#94A3B8", marginBottom: "20px" }}>
            Set up at least one fund with an active share class before running a valuation.
          </div>
          <button
            onClick={() => navigate(ROUTES.FUNDS)}
            style={{
              padding: "9px 16px",
              borderRadius: "8px",
              background: "#1A45FF",
              color: "#fff",
              border: "none",
              fontSize: "12px",
              fontWeight: 500,
              cursor: "pointer",
              fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
            }}
          >
            Go to Fund Management
          </button>
        </div>
      </div>
    );
  }

  // ── STEP 1: ENTRY ──
  const kesRows = classRows.filter((r) => r.currency === "KES");
  const usdRows = classRows.filter((r) => r.currency === "USD");

  const renderCurrencyGroup = (rows: ClassRowState[], currency: string) => {
    if (rows.length === 0) return null;
    const currencyColor = currency === "KES" ? "var(--color-kes)" : "var(--color-usd)";

    return (
      <div style={{ marginBottom: "20px" }} key={currency}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            padding: "10px 18px",
            background: "rgba(255,255,255,0.02)",
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: "10px 10px 0 0",
            borderBottom: "none",
          }}
        >
          <CurrencyBadge currency={currency} />
          <span style={{ fontSize: "11px", color: "#94A3B8", fontWeight: 500 }}>
            {currency === "KES" ? "Kenyan Shilling classes" : "US Dollar classes"}
          </span>
          <span
            style={{
              fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
              fontSize: "10px",
              color: "#475569",
              marginLeft: "4px",
            }}
          >
            {rows.length} class{rows.length !== 1 ? "es" : ""}
          </span>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1.5fr 1.5fr",
            gap: "14px",
            padding: "9px 18px",
            background: "rgba(255,255,255,0.02)",
            borderLeft: "1px solid rgba(255,255,255,0.07)",
            borderRight: "1px solid rgba(255,255,255,0.07)",
            borderBottom: "1px solid rgba(255,255,255,0.07)",
            fontSize: "9px",
            fontWeight: 600,
            color: "#475569",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          <div>Class</div>
          <div>
            NAV per Share{" "}
            <span style={{ color: "#475569", textTransform: "none", fontWeight: 400, fontSize: "9px" }}>
              (from AXYS)
            </span>
          </div>
          <div>
            Total Fund NAV{" "}
            <span style={{ color: "#475569", textTransform: "none", fontWeight: 400, fontSize: "9px" }}>
              (AXYS total)
            </span>
          </div>
        </div>

        <div
          style={{
            border: "1px solid rgba(255,255,255,0.07)",
            borderTop: "none",
            borderRadius: "0 0 10px 10px",
            overflow: "hidden",
          }}
        >
          {rows.map((r, idx) => (
            <div
              key={r.classId}
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1.5fr 1.5fr",
                gap: "14px",
                padding: "14px 18px",
                borderBottom:
                  idx < rows.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
                background: "rgba(16,24,45,0.72)",
                alignItems: "start",
              }}
            >
              <div>
                <div
                  style={{
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: currencyColor,
                    marginBottom: "2px",
                  }}
                >
                  {r.classCode}
                </div>
                <div style={{ fontSize: "10px", color: "#475569" }}>
                  {r.fundName} · {r.className}
                </div>
                {r.prevNav != null && (
                  <div
                    style={{
                      fontSize: "9px",
                      color: "#475569",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      marginTop: "3px",
                      letterSpacing: "0.02em",
                    }}
                  >
                    prev {formatNumberDecimals(r.prevNav, 4)}
                  </div>
                )}
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <input
                  value={r.navPerShare}
                  onChange={(e) => updateRow(r.classId, "navPerShare", e.target.value)}
                  placeholder="e.g. 1389.5737"
                  style={inputStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                />
                <div style={{ fontSize: "9px", color: "#475569", letterSpacing: "0.02em" }}>
                  6 decimal places (e.g. 1389.5737)
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                <input
                  value={r.totalFundNav}
                  onChange={(e) => updateRow(r.classId, "totalFundNav", e.target.value)}
                  placeholder="e.g. 1072636.69"
                  style={inputStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                />
                <div style={{ fontSize: "9px", color: "#475569", letterSpacing: "0.02em" }}>
                  From AXYS NAV statement
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div
      style={{
        position: "relative",
        zIndex: 1,
        padding: "24px 32px 48px",
        maxWidth: "900px",
        margin: "0 auto",
        fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
        color: "#FFFFFF",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-end",
          marginBottom: "22px",
          gap: "20px",
          flexWrap: "wrap",
        }}
      >
        <div>
          <h1
            style={{
              fontSize: "22px",
              fontWeight: 700,
              color: "#FFFFFF",
              letterSpacing: "-0.02em",
              margin: 0,
              marginBottom: "4px",
            }}
          >
            Monthly Valuation
          </h1>
          <div style={{ fontSize: "12px", color: "#94A3B8" }}>
            Enter NAV per share and total fund NAV from the AXYS statement. System will reconcile
            and allocate snapshots.
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          <label
            style={{
              fontSize: "10px",
              fontWeight: 600,
              color: "#475569",
              textTransform: "uppercase",
              letterSpacing: "0.08em",
            }}
          >
            Valuation Date
          </label>
          <input
            type="date"
            value={valuationDate}
            onChange={(e) => setValuationDate(e.target.value)}
            style={{
              ...inputStyle,
              padding: "8px 10px",
              colorScheme: "dark",
              fontSize: "12px",
              width: "auto",
            }}
            onFocus={handleFocus}
            onBlur={handleBlur}
          />
        </div>
      </div>

      <div
        style={{
          padding: "12px 16px",
          background: "rgba(245,158,11,0.06)",
          border: "1px solid rgba(245,158,11,0.18)",
          borderRadius: "9px",
          display: "flex",
          gap: "10px",
          alignItems: "flex-start",
          marginBottom: "22px",
          fontSize: "11px",
          color: "rgba(251,191,36,0.9)",
          lineHeight: 1.55,
        }}
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 14 14"
          fill="none"
          style={{ color: "#F59E0B", flexShrink: 0, marginTop: "1px" }}
        >
          <path
            d="M7 1L1 12h12L7 1z"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinejoin="round"
          />
          <line
            x1="7"
            y1="5.5"
            x2="7"
            y2="8"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
          <circle cx="7" cy="10" r="0.6" fill="currentColor" />
        </svg>
        <span>
          Values come directly from the AXYS NAV statement. The system will compute{" "}
          <strong style={{ color: "#FCD34D" }}>
            system total NAV = shares × NAV/share
          </strong>{" "}
          and compare it to your entered AXYS total. Difference must be &lt; 1.00 to pass
          reconciliation. Once committed, these values cannot be changed.
        </span>
      </div>

      {renderCurrencyGroup(kesRows, "KES")}
      {renderCurrencyGroup(usdRows, "USD")}

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "16px 20px",
          background: "rgba(16,24,45,0.72)",
          border: "1px solid rgba(255,255,255,0.07)",
          borderRadius: "12px",
          gap: "12px",
          marginTop: "4px",
        }}
      >
        <div
          style={{
            fontSize: "10px",
            color: "#475569",
            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            letterSpacing: "0.04em",
          }}
        >
          {partialMismatch
            ? "Complete both fields for any row you start"
            : canPreview
            ? `Ready to preview (${filledRows.length} class${filledRows.length !== 1 ? "es" : ""})`
            : "Enter NAV/share and AXYS total for at least one class"}
        </div>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => navigate(ROUTES.VALUATIONS)}
            style={{
              background: "transparent",
              border: "none",
              color: "#94A3B8",
              fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
              fontSize: "12px",
              fontWeight: 500,
              cursor: "pointer",
              padding: "9px 16px",
              borderRadius: "8px",
            }}
          >
            Cancel
          </button>
          <button
            onClick={handlePreview}
            disabled={!canPreview || previewing}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "7px",
              background: canPreview && !previewing ? "#1A45FF" : "rgba(255,255,255,0.06)",
              color: canPreview && !previewing ? "#fff" : "#475569",
              border: "none",
              fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
              fontSize: "12px",
              fontWeight: 500,
              cursor: canPreview && !previewing ? "pointer" : "not-allowed",
              padding: "9px 16px",
              borderRadius: "8px",
              boxShadow: canPreview && !previewing ? "0 0 16px rgba(26,69,255,0.3)" : "none",
              transition: "all 0.15s",
            }}
          >
            {previewing ? (
              <>
                <div
                  style={{
                    width: "11px",
                    height: "11px",
                    border: "1.5px solid rgba(255,255,255,0.3)",
                    borderTopColor: "#fff",
                    borderRadius: "50%",
                    animation: "spin 0.8s linear infinite",
                  }}
                />
                Previewing…
              </>
            ) : (
              <>
                Preview reconciliation
                <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M3 7h8M8 4l3 3-3 3"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
