import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { valuationService } from "@/services/valuationService";
import { formatDate, formatCurrency, formatPercent } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import type { NavValuationRunItem } from "@/lib/types";
import { Plus, Download, ChevronRight } from "lucide-react";
import { toast } from "sonner";

export default function ValuationListPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<NavValuationRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setErrorMessage(null);
        const data = await valuationService.listNavRuns(100);
        setRuns(data);
      } catch (err: any) {
        const message =
          err?.response?.data?.message || "Failed to load valuation reports";
        setErrorMessage(message);
        setRuns([]);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleDownloadClick = async () => {
    try {
      await valuationService.listNavRuns(1);
      toast.success("Valuation run loaded");
    } catch {
      toast.error("Failed to load valuation run");
    }
  };

  return (
    <div>
      {/* Header */}
      <div className="page-header-row" style={{ marginBottom: "24px" }}>
        <div>
          <h1 className="ofds-page-title">Valuation Statements</h1>
          <p className="ofds-page-subtitle">Committed valuation reports by period</p>
        </div>
        <button
          onClick={() => navigate(ROUTES.VALUATION_CREATE)}
          className="btn btn-primary btn-sm rounded-pill d-flex align-items-center gap-2 fw-bold"
          style={{ padding: "8px 18px" }}
        >
          <Plus size={14} /> New valuation
        </button>
      </div>

      {/* Table Card */}
      <div className="ofds-glass" style={{ overflow: "hidden" }}>
        {loading ? (
          <div className="d-flex align-items-center justify-content-center py-5">
            <div
              className="spinner-border spinner-border-sm"
              style={{ color: "var(--color-brand-400)" }}
              role="status"
            >
              <span className="visually-hidden">Loading...</span>
            </div>
          </div>
        ) : errorMessage ? (
          <div className="py-5 text-center" style={{ color: "var(--color-text-secondary)" }}>
            <p className="fs-5 fw-bold mb-2">Unable to load valuation reports</p>
            <p className="mb-0">{errorMessage}</p>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="table table-dark mb-0" style={{ background: "transparent" }}>
              <thead>
                <tr>
                  {[
                    { label: "Fund", align: "left" },
                    { label: "Valuation Date", align: "left" },
                    { label: "NAV", align: "right" },
                    { label: "Opening", align: "right" },
                    { label: "Closing AUM", align: "right" },
                    { label: "Profit", align: "right" },
                    { label: "Investors", align: "right" },
                    { label: "Perf %", align: "right" },
                    { label: "Actions", align: "center" },
                    { label: "", align: "left" },
                  ].map((col) => (
                    <th
                      key={col.label}
                      style={{ textAlign: col.align as "left" | "right" | "center" }}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr
                    key={`${r.share_class_id}-${r.valuation_date}`}
                    style={{ cursor: "default" }}
                  >
                    <td className="fw-bold" style={{ fontSize: "13px" }}>
                      {r.fund_name}
                    </td>
                    <td style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>
                      {formatDate(r.valuation_date)}
                    </td>
                    <td
                      className="text-end"
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "12px",
                        color: "var(--color-text-secondary)",
                      }}
                    >
                      {Number(r.nav_per_share || 0).toFixed(4)}
                    </td>
                    <td
                      className="text-end"
                      style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
                    >
                      {formatCurrency(r.opening_aum)}
                    </td>
                    <td
                      className="text-end fw-bold"
                      style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
                    >
                      {formatCurrency(r.closing_aum)}
                    </td>
                    <td
                      className="text-end"
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "12px",
                        color:
                          r.profit >= 0
                            ? "var(--color-success)"
                            : "var(--color-destructive)",
                      }}
                    >
                      {formatCurrency(r.profit)}
                    </td>
                    <td
                      className="text-end"
                      style={{ fontFamily: "var(--font-mono)", fontSize: "12px" }}
                    >
                      {r.investors}
                    </td>
                    <td
                      className="text-end"
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "12px",
                        color:
                          r.performance_pct >= 0
                            ? "var(--color-success)"
                            : "var(--color-destructive)",
                      }}
                    >
                      {formatPercent(r.performance_pct)}
                    </td>
                    <td className="text-center">
                      <Download
                        size={16}
                        style={{ color: "#00005b", cursor: "pointer" }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDownloadClick();
                        }}
                      />
                    </td>
                    <td>
                      <ChevronRight
                        size={14}
                        style={{ color: "var(--color-text-tertiary)" }}
                      />
                    </td>
                  </tr>
                ))}
                {runs.length === 0 && (
                  <tr>
                    <td
                      colSpan={10}
                      className="text-center py-5"
                      style={{ color: "var(--color-text-tertiary)" }}
                    >
                      No valuation reports available. Commit a valuation to generate reports.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
