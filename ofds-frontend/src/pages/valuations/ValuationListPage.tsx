import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { valuationService } from "@/services/valuationService";
import { formatDate, formatCurrency, formatPercent } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import type { NavValuationRunItem, ProductType } from "@/lib/types";
import { Plus, Download, ChevronRight, Pencil } from "lucide-react";
import { getUserRole } from "@/lib/auth";
import { toast } from "sonner";

interface ValuationListPageProps {
  product?: ProductType;
}

/** Task 9: same screen for Funds and Shares, scoped by `product` so the two
 * valuation histories never mix (see app/Valuation/route.py's product filter). */
export default function ValuationListPage({ product = "FUNDS" }: ValuationListPageProps) {
  const navigate = useNavigate();
  const isShares = product === "SHARES";
  const createPath = isShares ? ROUTES.SHARES_VALUATION_CREATE : ROUTES.FUNDS_VALUATION_CREATE;
  const [runs, setRuns] = useState<NavValuationRunItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [editing, setEditing] = useState<NavValuationRunItem | null>(null);
  const [newDate, setNewDate] = useState("");
  const [saving, setSaving] = useState(false);
  const canEditDate = getUserRole() === "super_admin";

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setErrorMessage(null);
        const data = await valuationService.listNavRuns(100, product);
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
  }, [product, reloadKey]);

  const openEditDate = (run: NavValuationRunItem) => {
    setEditing(run);
    setNewDate(run.valuation_date.slice(0, 10));
  };

  const saveDate = async () => {
    if (!editing) return;
    try {
      setSaving(true);
      const msg = await valuationService.updateRunDate(
        editing.share_class_id,
        editing.valuation_date.slice(0, 10),
        newDate
      );
      toast.success(msg);
      setEditing(null);
      setReloadKey((k) => k + 1);
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to change valuation date");
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadClick = async () => {
    try {
      await valuationService.listNavRuns(1, product);
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
          <h1 className="ofds-page-title">{isShares ? "Shares" : "Funds"} Valuation Statements</h1>
          <p className="ofds-page-subtitle">Committed valuation reports by period</p>
        </div>
        <button
          onClick={() => navigate(createPath)}
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
                    { label: isShares ? "Share" : "Fund", align: "left" },
                    { label: "Valuation Date", align: "left" },
                    { label: "NAV", align: "right" },
                    { label: "Opening", align: "right" },
                    { label: "Closing Total", align: "right" },
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
                      {Number(r.nav_per_share || 0).toFixed(2)}
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
                      {canEditDate && (
                        <Pencil
                          size={16}
                          aria-label="Edit valuation date"
                          style={{ color: "#00005b", cursor: "pointer", marginRight: "12px" }}
                          onClick={(e) => {
                            e.stopPropagation();
                            openEditDate(r);
                          }}
                        />
                      )}
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

      {editing && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
            display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1050,
          }}
          onClick={() => !saving && setEditing(null)}
        >
          <div
            style={{ background: "var(--color-surface, #fff)", borderRadius: "8px", padding: "24px", width: "380px", maxWidth: "92vw" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ fontSize: "16px", marginBottom: "6px" }}>Edit valuation date</h3>
            <p style={{ fontSize: "12px", color: "var(--color-text-secondary)", marginBottom: "16px" }}>
              {editing.fund_name} · {editing.share_class_code} — currently {formatDate(editing.valuation_date)}.
              All statements will show the new date. NAV and values do not change.
            </p>
            <input
              type="date"
              className="form-control"
              value={newDate}
              max={new Date().toISOString().slice(0, 10)}
              onChange={(e) => setNewDate(e.target.value)}
            />
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px", marginTop: "20px" }}>
              <button className="btn btn-sm btn-outline-secondary" disabled={saving} onClick={() => setEditing(null)}>
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary"
                disabled={saving || !newDate || newDate === editing.valuation_date.slice(0, 10)}
                onClick={saveDate}
              >
                {saving ? "Saving..." : "Save date"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
