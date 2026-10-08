import { useEffect, useState, useRef } from "react";
import { StatusBadge } from "@/components/data/StatusBadge";
import { ProductBadge } from "@/components/ui/ProductBadge";
import { ProductToggle, OVERVIEW_PRODUCT_OPTIONS, type ProductFilterValue } from "@/components/ui/ProductToggle";
import { withdrawalService } from "@/services/withdrawalService";
import { fundService } from "@/services/fundService";
import { formatCurrency, formatDate } from "@/lib/utils";
import type { Withdrawal, WithdrawalSource, CoreFund, ProductType } from "@/lib/types";
import { toast } from "sonner";
import { Upload, Check, X, Download } from "lucide-react";

const FILTERS = ["", "Pending", "Approved", "Rejected"] as const;
const FILTER_LABELS: Record<string, string> = { "": "All", Pending: "Pending", Approved: "Approved", Rejected: "Rejected" };

const SOURCE_FILTERS = ["", "investor_request", "oversubscription_refund"] as const;
const SOURCE_FILTER_LABELS: Record<string, string> = {
  "": "All types",
  investor_request: "Investor Requests",
  oversubscription_refund: "Oversubscription Refunds",
};

export default function WithdrawalListPage() {
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("");
  const [sourceFilter, setSourceFilter] = useState<string>("");
  // Task 11: Product filter (All | Funds | Shares) — refunds only ever occur
  // under Shares (DPRP), but this also scopes normal investor-request rows.
  const [productFilter, setProductFilter] = useState<ProductFilterValue>("ALL");
  const [uploading, setUploading] = useState(false);
  const [processing, setProcessing] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [funds, setFunds] = useState<CoreFund[]>([]);
  const [fundFilter, setFundFilter] = useState<string>("");
  const [exporting, setExporting] = useState<"excel" | "pdf" | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState<{ total: number; total_pages: number }>({ total: 0, total_pages: 1 });
  const PER_PAGE = 200;
  const effectiveSource = sourceFilter;
  const effectiveProduct = productFilter === "ALL" ? undefined : (productFilter as ProductType);

  const load = async () => {
    setLoading(true);
    try {
      const { data, pagination: p } = await withdrawalService.getAll({
        status: filter || undefined,
        source: (effectiveSource || undefined) as WithdrawalSource | undefined,
        product: effectiveProduct,
        fundId: fundFilter ? Number(fundFilter) : undefined,
        search: search.trim() || undefined,
        page,
        perPage: PER_PAGE,
      });
      setWithdrawals(data);
      setPagination({ total: p.total, total_pages: p.total_pages ?? 1 });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter, effectiveSource, effectiveProduct, fundFilter, search, page]);
  useEffect(() => { setPage(1); }, [filter, effectiveSource, effectiveProduct, fundFilter, search]);
  useEffect(() => { fundService.getAll().then(setFunds).catch(() => {}); }, []);

  // Pending count for the "Approve All"/"Reject All" preview — deliberately
  // independent of the status pill (`filter`) above: the bulk action always
  // targets Pending rows server-side regardless of which tab is showing, so
  // viewing the "Approved" tab shouldn't make these buttons look inert. Uses
  // count_only so a fund/source scope with thousands of pending withdrawals
  // doesn't fetch every row just to show a number.
  const [pendingCount, setPendingCount] = useState(0);
  const refreshPendingCount = async () => {
    try {
      const count = await withdrawalService.getCount({
        status: "Pending",
        source: (effectiveSource || undefined) as WithdrawalSource | undefined,
        product: effectiveProduct,
        fundId: fundFilter ? Number(fundFilter) : undefined,
      });
      setPendingCount(count);
    } catch {
      setPendingCount(0);
    }
  };
  useEffect(() => { refreshPendingCount(); }, [effectiveSource, effectiveProduct, fundFilter]);

  const onExport = async (format: "excel" | "pdf") => {
    setExporting(format);
    try {
      await withdrawalService.downloadExport(format, {
        fundId: fundFilter ? Number(fundFilter) : undefined,
        status: filter || undefined,
        source: (effectiveSource || undefined) as WithdrawalSource | undefined,
        product: effectiveProduct,
      });
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Export failed");
    } finally {
      setExporting(null);
    }
  };

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await withdrawalService.uploadExcel(file);
      toast.success("Withdrawals uploaded");
      await load();
      await refreshPendingCount();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onApprove = async (withdrawalId: number, clientId: string) => {
    setProcessing(withdrawalId);
    try {
      await withdrawalService.approve(withdrawalId);
      toast.success(`✅ Withdrawal approved for ${clientId}`);
      await load(); // Reload list
      await refreshPendingCount();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Failed to approve");
    } finally {
      setProcessing(null);
    }
  };

  const onReject = async (withdrawalId: number, clientId: string) => {
    setProcessing(withdrawalId);
    try {
      await withdrawalService.reject(withdrawalId);
      toast.success(`❌ Withdrawal rejected for ${clientId}`);
      await load(); // Reload list
      await refreshPendingCount();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Failed to reject");
    } finally {
      setProcessing(null);
    }
  };

  // Bulk approve/reject scoped to the active source/fund filters. Always
  // restricted server-side to Pending rows regardless of the status pill
  // selected here — see pendingCount above.
  const [bulkRunning, setBulkRunning] = useState<"approve" | "reject" | null>(null);

  const onBulkAction = async (action: "approve" | "reject") => {
    if (pendingCount === 0) return;
    const scopeLabel = [
      effectiveSource ? SOURCE_FILTER_LABELS[effectiveSource] : null,
      effectiveProduct ? (effectiveProduct === "SHARES" ? "Shares" : "Funds") : null,
      fundFilter ? funds.find((f) => String(f.id) === fundFilter)?.fund_name : null,
    ].filter(Boolean).join(" · ") || "all funds/types";
    const confirmed = window.confirm(
      `${action === "approve" ? "Approve" : "Reject"} ALL ${pendingCount} pending withdrawal(s) matching "${scopeLabel}"?\n\nThis cannot be undone in bulk — you'd have to fix each one individually.`
    );
    if (!confirmed) return;

    setBulkRunning(action);
    try {
      const res = await withdrawalService.bulkAction(action, {
        source: (effectiveSource || undefined) as WithdrawalSource | undefined,
        product: effectiveProduct,
        fundId: fundFilter ? Number(fundFilter) : undefined,
      });
      const { processed } = res.data || { processed: 0 };
      toast.success(`${action === "approve" ? "✅ Approved" : "❌ Rejected"} ${processed} withdrawal(s)`);
      await load();
      await refreshPendingCount();
    } catch (err: any) {
      toast.error(err.response?.data?.message || `Failed to bulk ${action}`);
    } finally {
      setBulkRunning(null);
    }
  };

  const pillStyle = (active: boolean) => ({
    fontSize: "11px",
    fontWeight: 600 as const,
    padding: "4px 14px",
    borderRadius: "20px",
    border: active ? "1px solid var(--color-brand-400)" : "1px solid rgba(255,255,255,0.1)",
    background: active ? "var(--color-brand-50)" : "transparent",
    color: active ? "var(--color-brand-300)" : "var(--color-text-secondary)",
    cursor: "pointer" as const,
    transition: "all 0.15s",
  });

  const totalAmount = withdrawals.reduce((s, w) => s + w.amount, 0);

  return (
    <div className="container-fluid px-0">
      {/* Header */}
      <div className="page-header-row mb-4">
        <div>
          <h1 className="fw-bold mb-1" style={{ fontSize: "22px", color: "var(--color-text-primary)" }}>
            Withdrawals
          </h1>
          <p className="mb-0" style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
            Track and manage investor withdrawal requests and oversubscription refunds
          </p>
        </div>
        <div className="d-flex align-items-end gap-3">
          <ProductToggle value={productFilter} onChange={setProductFilter} options={OVERVIEW_PRODUCT_OPTIONS} label="Product" />
          <div className="d-flex align-items-center gap-2">
          <button
            onClick={() => onExport("excel")}
            disabled={exporting !== null}
            className="btn btn-sm d-flex align-items-center gap-2 fw-bold"
            style={{
              padding: "8px 18px",
              borderRadius: "20px",
              border: "1px solid rgba(255,255,255,0.15)",
              background: "transparent",
              color: "var(--color-text-secondary)",
            }}
          >
            <Download size={14} /> {exporting === "excel" ? "Exporting..." : "Export Excel"}
          </button>
          <button
            onClick={() => onExport("pdf")}
            disabled={exporting !== null}
            className="btn btn-sm d-flex align-items-center gap-2 fw-bold"
            style={{
              padding: "8px 18px",
              borderRadius: "20px",
              border: "1px solid rgba(255,255,255,0.15)",
              background: "transparent",
              color: "var(--color-text-secondary)",
            }}
          >
            <Download size={14} /> {exporting === "pdf" ? "Exporting..." : "Export PDF"}
          </button>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="d-none" onChange={onUpload} />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploading}
            className="btn btn-sm d-flex align-items-center gap-2 fw-bold"
            style={{
              padding: "8px 18px",
              borderRadius: "20px",
              border: "1px solid rgba(255,255,255,0.15)",
              background: "transparent",
              color: "var(--color-text-secondary)",
            }}
          >
            <Upload size={14} /> {uploading ? "Uploading..." : "Upload Excel"}
          </button>
          </div>
        </div>
      </div>

      {/* Table card */}
      <div className="card shadow">
        {/* Filter bar */}
        <div
          className="d-flex align-items-center gap-2 px-4 py-3 flex-wrap"
          style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}
        >
          {FILTERS.map((f) => (
            <button key={f || "all"} onClick={() => setFilter(f)} style={pillStyle(filter === f)}>
              {FILTER_LABELS[f]}
            </button>
          ))}
          <span style={{ width: "1px", height: "18px", background: "rgba(255,255,255,0.1)", margin: "0 4px" }} />
          {SOURCE_FILTERS.map((s) => (
            <button key={s || "all-types"} onClick={() => setSourceFilter(s)} style={pillStyle(sourceFilter === s)}>
              {SOURCE_FILTER_LABELS[s]}
            </button>
          ))}
          <span style={{ width: "1px", height: "18px", background: "rgba(255,255,255,0.1)", margin: "0 4px" }} />
          <select
            value={fundFilter}
            onChange={(e) => setFundFilter(e.target.value)}
            title="Filters the table and scopes the Export/Approve All/Reject All actions"
            style={{
              fontSize: "11px",
              fontWeight: 600,
              padding: "5px 10px",
              borderRadius: "8px",
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(0,0,0,0.25)",
              color: "var(--color-text-secondary)",
            }}
          >
            <option value="">All Funds</option>
            {funds.map((f) => (
              <option key={f.id} value={f.id}>{f.fund_name}</option>
            ))}
          </select>
          <span style={{ width: "1px", height: "18px", background: "rgba(255,255,255,0.1)", margin: "0 4px" }} />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by client code…"
            style={{
              fontSize: "11px",
              padding: "5px 10px",
              borderRadius: "8px",
              border: "1px solid rgba(255,255,255,0.1)",
              background: "rgba(0,0,0,0.25)",
              color: "var(--color-text-primary)",
              width: "160px",
              outline: "none",
            }}
          />
          <span style={{ width: "1px", height: "18px", background: "rgba(255,255,255,0.1)", margin: "0 4px" }} />
          <button
            onClick={() => onBulkAction("approve")}
            disabled={bulkRunning !== null || pendingCount === 0}
            className="btn btn-sm d-flex align-items-center gap-1 fw-bold"
            title={pendingCount === 0 ? "No pending withdrawals in this scope" : `Approve all ${pendingCount} pending withdrawal(s) matching the current filters`}
            style={{
              padding: "5px 12px",
              fontSize: "11px",
              borderRadius: "12px",
              border: "none",
              background: "#00005b",
              color: "#ffffff",
              cursor: bulkRunning !== null || pendingCount === 0 ? "not-allowed" : "pointer",
              opacity: bulkRunning !== null || pendingCount === 0 ? 0.5 : 1,
            }}
          >
            <Check size={12} /> {bulkRunning === "approve" ? "Approving..." : `Approve All${pendingCount ? ` (${pendingCount})` : ""}`}
          </button>
          <button
            onClick={() => onBulkAction("reject")}
            disabled={bulkRunning !== null || pendingCount === 0}
            className="btn btn-sm d-flex align-items-center gap-1 fw-bold"
            title={pendingCount === 0 ? "No pending withdrawals in this scope" : `Reject all ${pendingCount} pending withdrawal(s) matching the current filters`}
            style={{
              padding: "5px 12px",
              fontSize: "11px",
              borderRadius: "12px",
              border: "none",
              background: "rgba(239, 68, 68, 0.15)",
              color: "#ef4444",
              cursor: bulkRunning !== null || pendingCount === 0 ? "not-allowed" : "pointer",
              opacity: bulkRunning !== null || pendingCount === 0 ? 0.5 : 1,
            }}
          >
            <X size={12} /> {bulkRunning === "reject" ? "Rejecting..." : `Reject All${pendingCount ? ` (${pendingCount})` : ""}`}
          </button>
        </div>

        {/* Table */}
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
                  {[
                    { label: "Investor",    align: "left"  },
                    { label: "Fund",        align: "left"  },
                    { label: "Product",     align: "left"  },
                    { label: "Type",        align: "left"  },
                    { label: "Batch",       align: "left"  },
                    { label: "Amount (USD)", align: "right" },
                    { label: "Rate Used",   align: "right" },
                    { label: "Status",      align: "left"  },
                    { label: "Date",        align: "left"  },
                    { label: "Approved",    align: "left"  },
                    { label: "Actions",     align: "center" },
                  ].map((h) => (
                    <th key={h.label} style={{ textAlign: h.align as "left" | "right" | "center" }}>{h.label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {withdrawals.map((w) => (
                  <tr key={w.id}>
                    <td>
                      <div style={{ fontSize: "12px", fontWeight: 600, color: "var(--color-text-primary)" }}>
                        {w.investor_name || w.client_id}
                      </div>
                      {w.investor_name && (
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: "10px", color: "var(--color-text-tertiary)" }}>
                          {w.client_id}
                        </div>
                      )}
                    </td>
                    <td className="fw-bold" style={{ fontSize: "13px" }}>{w.fund_name}</td>
                    <td><ProductBadge product={w.product_type ?? "FUNDS"} /></td>
                    <td style={{ fontSize: "11px" }}>
                      {w.source === "oversubscription_refund" ? (
                        <div className="d-flex align-items-center gap-1 flex-wrap">
                          <span
                            style={{
                              display: "inline-flex", alignItems: "center", padding: "3px 8px", borderRadius: "999px",
                              background: "rgba(212, 148, 11, 0.12)", border: "1px solid rgba(212, 148, 11, 0.3)",
                              color: "#D4940B", fontWeight: 600, fontSize: "10px", whiteSpace: "nowrap",
                            }}
                          >
                            Oversubscription Refund
                          </span>
                          <span
                            title={
                              w.oversubscription_notice_sent
                                ? "The one-time Oversubscription/Refund Notice has been sent for this refund"
                                : "The one-time Oversubscription/Refund Notice is queued in Pending Emails, awaiting approval"
                            }
                            style={{
                              display: "inline-flex", alignItems: "center", padding: "3px 8px", borderRadius: "999px",
                              background: w.oversubscription_notice_sent ? "rgba(34,197,94,0.1)" : "rgba(255,255,255,0.06)",
                              border: w.oversubscription_notice_sent ? "1px solid rgba(34,197,94,0.3)" : "1px solid rgba(255,255,255,0.12)",
                              color: w.oversubscription_notice_sent ? "#4ade80" : "var(--color-text-tertiary)",
                              fontWeight: 600, fontSize: "10px", whiteSpace: "nowrap",
                            }}
                          >
                            {w.oversubscription_notice_sent ? "Notice sent" : "Notice pending"}
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: "var(--color-text-tertiary)" }}>Investor Request</span>
                      )}
                    </td>
                    <td style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>{w.batch_name || "—"}</td>
                    <td className="text-end" style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-destructive)" }}>
                      {formatCurrency(w.amount)}
                    </td>
                    <td className="text-end" style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-secondary)" }}>
                      {w.rate_used != null ? `₦${w.rate_used.toLocaleString("en-US", { maximumFractionDigits: 4 })}` : "—"}
                    </td>
                    <td><StatusBadge status={w.status} /></td>
                    <td style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>{formatDate(w.date_withdrawn)}</td>
                    <td style={{ color: "var(--color-text-tertiary)", fontSize: "12px" }}>{formatDate(w.approved_at)}</td>
                    <td style={{ textAlign: "center" }}>
                      {w.status === "Pending" ? (
                        <div className="d-flex gap-2 justify-content-center">
                          <button
                            onClick={() => onApprove(w.id, w.client_id)}
                            disabled={processing === w.id}
                            className="btn btn-sm d-flex align-items-center gap-1"
                            style={{
                              padding: "4px 10px",
                              fontSize: "11px",
                              borderRadius: "12px",
                              border: "none",
                              background: "#00005b",
                              color: "#ffffff",
                              cursor: processing === w.id ? "not-allowed" : "pointer",
                              opacity: processing === w.id ? 0.7 : 1,
                            }}
                            title="Approve this withdrawal"
                          >
                            <Check size={12} /> Approve
                          </button>
                          <button
                            onClick={() => onReject(w.id, w.client_id)}
                            disabled={processing === w.id}
                            className="btn btn-sm d-flex align-items-center gap-1"
                            style={{
                              padding: "4px 10px",
                              fontSize: "11px",
                              borderRadius: "12px",
                              border: "none",
                              background: "rgba(239, 68, 68, 0.15)",
                              color: "#ef4444",
                              cursor: processing === w.id ? "not-allowed" : "pointer",
                              opacity: processing === w.id ? 0.7 : 1,
                            }}
                            title="Reject this withdrawal"
                          >
                            <X size={12} /> Reject
                          </button>
                        </div>
                      ) : (
                        <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>—</span>
                      )}
                    </td>
                  </tr>
                ))}
                {withdrawals.length === 0 && (
                  <tr>
                    <td colSpan={11} className="text-center py-5" style={{ color: "var(--color-text-tertiary)" }}>
                      No withdrawals found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Footer */}
        <div
          className="d-flex align-items-center justify-content-between px-4 py-2 flex-wrap gap-2"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: "11px", color: "var(--color-text-tertiary)" }}
        >
          <span>
            Showing {withdrawals.length} of {pagination.total} withdrawal{pagination.total !== 1 ? "s" : ""}
            {pagination.total_pages > 1 ? ` · page ${page} of ${pagination.total_pages}` : ""}
          </span>
          <div className="d-flex align-items-center gap-3">
            <span>Page total: {formatCurrency(totalAmount)}</span>
            {pagination.total_pages > 1 && (
              <div className="d-flex align-items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="btn btn-sm"
                  style={{ padding: "2px 10px", fontSize: "11px", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.1)", background: "transparent", color: "var(--color-text-secondary)", opacity: page <= 1 ? 0.5 : 1 }}
                >
                  Prev
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(pagination.total_pages, p + 1))}
                  disabled={page >= pagination.total_pages}
                  className="btn btn-sm"
                  style={{ padding: "2px 10px", fontSize: "11px", borderRadius: "8px", border: "1px solid rgba(255,255,255,0.1)", background: "transparent", color: "var(--color-text-secondary)", opacity: page >= pagination.total_pages ? 0.5 : 1 }}
                >
                  Next
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
