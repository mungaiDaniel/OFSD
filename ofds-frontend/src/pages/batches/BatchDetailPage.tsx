import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { batchService } from "@/services/batchService";
import { reportService } from "@/services/reportService";
import { investmentService } from "@/services/investmentService";
import { ROUTES, STAGE_LABELS } from "@/lib/constants";
import type { Batch, BatchStage } from "@/lib/types";
import { toast } from "sonner";
import { useBatchReconciliation } from "@/hooks/useBatchReconciliation";
import { getUserRole } from "@/lib/auth";
import { ArrowLeft, Pencil, Upload, Download, Trash2, Search, ChevronLeft, ChevronRight, Users2, Rows3 } from "lucide-react";
import type { BatchInvestorLight } from "@/lib/types";
import { EmailConfirmationModal } from "@/components/ui/EmailConfirmationModal";
import { DeploymentDateModal, type DeploymentConfirmPayload } from "@/components/ui/DeploymentDateModal";
import { TransferCostModal } from "@/components/ui/TransferCostModal";
import { SharesTransferModal } from "@/components/ui/SharesTransferModal";
import { SharesDeploymentPanel, type SharesDeploymentConfirmPayload } from "@/components/ui/SharesDeploymentPanel";
import { ProductBadge } from "@/components/ui/ProductBadge";
import { VirtualizedList } from "@/components/ui/VirtualizedList";

// Task 6: product-relevant columns for the batch client list/export — SHARES
// is priced per-share and tracks net USD/NGN + oversubscription refund;
// FUNDS is NAV-based and tracks shares/NAV/market value. Shared by the
// default table, the "Show all" virtualized view, and the column widths
// used to line both up.
function getInvestorColumns(isShares: boolean) {
  const base = [
    {
      key: "investor", label: "Investor", align: "left" as const, grid: "2fr",
      render: (inv: any) => (
        <div>
          <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--color-brand-400)" }}>{inv.investor_name}</div>
          <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>{inv.investor_email || ""}</div>
        </div>
      ),
    },
    {
      key: "code", label: "Client Code", align: "left" as const, grid: "1.1fr",
      render: (inv: any) => <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-secondary)" }}>{inv.internal_client_code || "—"}</span>,
    },
    { key: "deposit", label: "Deposit", align: "right" as const, grid: "1fr", render: (inv: any) => fmtMoney(inv.amount_deposited) },
  ];
  const sharesCols = [
    { key: "net_usd", label: "Net (USD)", align: "right" as const, grid: "1fr", render: (inv: any) => fmtMoney(inv.net_usd) },
    { key: "net_ngn", label: "Net (NGN)", align: "right" as const, grid: "1.1fr", render: (inv: any) => (inv.net_ngn != null ? `₦${Number(inv.net_ngn).toLocaleString("en-US", { maximumFractionDigits: 2 })}` : "—") },
    { key: "shares_allocated", label: "Shares Allocated", align: "right" as const, grid: "1fr", render: (inv: any) => (inv.shares_owned != null ? Number(inv.shares_owned).toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—") },
    { key: "refund_usd", label: "Refund (USD)", align: "right" as const, grid: "1fr", render: (inv: any) => (inv.refund_usd != null ? fmtMoney(inv.refund_usd) : "—") },
  ];
  const fundsCols = [
    { key: "net_amount", label: "Net Amount", align: "right" as const, grid: "1fr", render: (inv: any) => fmtMoney(inv.main_balance) },
    { key: "shares", label: "Shares", align: "right" as const, grid: "0.9fr", render: (inv: any) => (inv.shares_owned != null ? Number(inv.shares_owned).toLocaleString("en-US", { maximumFractionDigits: 4 }) : "—") },
    { key: "market_value", label: "Market Value", align: "right" as const, grid: "1.1fr", render: (inv: any) => fmtMoney(inv.market_value ?? inv.current_balance) },
    { key: "perf", label: "Perf %", align: "right" as const, grid: "0.8fr", render: (inv: any) => (inv.performance_pct != null ? `${inv.performance_pct >= 0 ? "+" : ""}${Number(inv.performance_pct).toFixed(2)}%` : "—") },
  ];
  return [...base, ...(isShares ? sharesCols : fundsCols)];
}

const glassCard: React.CSSProperties = {
  background: "rgba(16, 24, 45, 0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255, 255, 255, 0.07)",
  borderRadius: "16px",
  boxShadow: "rgba(0, 0, 0, 0.3) 0px 8px 32px",
};

const iconBtn: React.CSSProperties = {
  padding: "7px 10px",
  borderRadius: "8px",
  background: "rgba(255, 255, 255, 0.05)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  color: "var(--color-text-secondary)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
};

const dangerIconBtn: React.CSSProperties = {
  padding: "7px 10px",
  borderRadius: "8px",
  background: "rgba(239, 68, 68, 0.06)",
  border: "1px solid rgba(239, 68, 68, 0.15)",
  color: "rgb(239, 68, 68)",
  cursor: "pointer",
  display: "inline-flex",
  alignItems: "center",
};

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$ ${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function fmtDate(d: string | null | undefined): string {
  if (!d) return "—";
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ ...glassCard, padding: "14px 16px" }}>
      <div style={{ fontSize: "9px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--color-text-tertiary)", marginBottom: "6px" }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "14px", fontWeight: 700, color: "var(--color-text-primary)" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", marginTop: "2px" }}>{sub}</div>}
    </div>
  );
}

const STAGE_KEYS: BatchStage[] = [1, 2, 3, 4];

function DeploymentStepper({ stage }: { stage: BatchStage }) {
  return (
    <div className="flex items-center w-full">
      {STAGE_KEYS.map((s) => {
        const isDone = s < stage;
        const isCurrent = s === stage;
        const isLast = s === STAGE_KEYS[STAGE_KEYS.length - 1];
        const filled = isDone || isCurrent;
        return (
          <div className="flex items-center flex-1 last:flex-none" key={s}>
            <div className="flex flex-col items-center">
              <div
                className="w-8 h-8 rounded-full flex items-center justify-center text-xs fw-bold border-2 transition-colors"
                style={{
                  background: filled ? "var(--color-brand-400)" : "transparent",
                  borderColor: filled ? "var(--color-brand-400)" : "rgba(255,255,255,0.15)",
                  color: filled ? "rgb(255, 255, 255)" : "var(--color-text-tertiary)",
                  boxShadow: isCurrent ? "rgba(59, 111, 212, 0.2) 0px 0px 0px 4px" : "none",
                }}
              >
                {isDone ? "✓" : s}
              </div>
              <span
                className="text-[11px] font-medium mt-2 whitespace-nowrap"
                style={{ color: isCurrent ? "var(--color-text-primary)" : "var(--color-text-secondary)" }}
              >
                {STAGE_LABELS[s]}
              </span>
            </div>
            {!isLast && (
              <div
                className="flex-1 h-0.5 mx-3 mt-[-20px]"
                style={{ background: isDone ? "var(--color-brand-400)" : "rgba(255,255,255,0.1)" }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function BatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [batch, setBatch] = useState<Batch | null>(null);
  // Investor rows shown in the table below — only populated once the admin
  // searches by client code / email / phone (see investorSearch). The batch
  // itself never loads its full investor list just to render the page.
  const [investments, setInvestments] = useState<any[]>([]);
  const [investorSearch, setInvestorSearch] = useState("");
  const [investorPage, setInvestorPage] = useState(1);
  const [investorTotalPages, setInvestorTotalPages] = useState(1);
  const [investorSearchLoading, setInvestorSearchLoading] = useState(false);
  // "Show all" — chunk-loaded + virtualized, bypassing the search-first gate
  // above (never fetches the whole batch in one request; see SHOW_ALL_CHUNK).
  const [showAllInvestors, setShowAllInvestors] = useState(false);
  const [allBatchRows, setAllBatchRows] = useState<any[]>([]);
  const [allBatchRowsLoading, setAllBatchRowsLoading] = useState(false);
  const [allBatchRowsLoadingMore, setAllBatchRowsLoadingMore] = useState(false);
  const [allBatchRowsHasMore, setAllBatchRowsHasMore] = useState(true);
  const allBatchRowsPageRef = useRef(1);
  const allBatchRowsFetchingRef = useRef(false);
  const [exportingBatch, setExportingBatch] = useState(false);
  // Delete-investor (Show all view only, super_admin only — see isSuperAdmin below).
  const [deletingInvestmentId, setDeletingInvestmentId] = useState<number | null>(null);
  // Full per-investor list (cheap fields only) fetched on-demand right before
  // the Transfer/Deploy modals open — those need every investor in the batch
  // to group by share class, but that only happens once per stage change.
  const [fullInvestments, setFullInvestments] = useState<BatchInvestorLight[]>([]);
  const [loadingFullInvestments, setLoadingFullInvestments] = useState(false);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [emailConfirmModalOpen, setEmailConfirmModalOpen] = useState(false);
  const [deployModalOpen, setDeployModalOpen] = useState(false);
  const [transferModalOpen, setTransferModalOpen] = useState(false);
  const [sharesTransferModalOpen, setSharesTransferModalOpen] = useState(false);
  const [isDeploying, setIsDeploying] = useState(false);
  const [isTransferring, setIsTransferring] = useState(false);
  const [isSharesTransferring, setIsSharesTransferring] = useState(false);
  const [isSharesDeploying, setIsSharesDeploying] = useState(false);
  const [editBatchName, setEditBatchName] = useState("");
  const [editCertificateNumber, setEditCertificateNumber] = useState("");
  const [editDurationDays, setEditDurationDays] = useState<number>(30);
  const [uploadingFile, setUploadingFile] = useState(false);
  const [selectedBatchFile, setSelectedBatchFile] = useState<File | null>(null);
  const [fileUploadProgress, setFileUploadProgress] = useState(0);

  const batchId = Number(id);
  const { reconciliation } = useBatchReconciliation(batchId);
  const trimmedInvestorSearch = investorSearch.trim();

  // Debounce investor search so we're not hitting the server on every keystroke.
  useEffect(() => {
    const t = setTimeout(() => setInvestorPage(1), 300);
    return () => clearTimeout(t);
  }, [investorSearch]);

  useEffect(() => {
    if (!batchId || isNaN(batchId) || !trimmedInvestorSearch) {
      setInvestments([]);
      setInvestorTotalPages(1);
      return;
    }
    let alive = true;
    (async () => {
      setInvestorSearchLoading(true);
      try {
        const data = await batchService.getById(batchId, { search: trimmedInvestorSearch, page: investorPage, per_page: 50 });
        if (!alive) return;
        setInvestments((data as any).investments || []);
        setInvestorTotalPages(data.investments_pagination?.total_pages ?? 1);
      } catch {
        if (alive) toast.error("Failed to search investors");
      } finally {
        if (alive) setInvestorSearchLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [batchId, trimmedInvestorSearch, investorPage]);

  const SHOW_ALL_CHUNK = 200;

  // Reset and reload the first chunk whenever "Show all" turns on, or the
  // search filter changes while it's already on.
  useEffect(() => {
    if (!showAllInvestors || !batchId || isNaN(batchId)) return;
    let alive = true;
    allBatchRowsPageRef.current = 1;
    allBatchRowsFetchingRef.current = true;
    setAllBatchRows([]);
    setAllBatchRowsHasMore(true);
    setAllBatchRowsLoading(true);
    (async () => {
      try {
        const data = await batchService.getById(batchId, {
          show_all: true, page: 1, per_page: SHOW_ALL_CHUNK, search: trimmedInvestorSearch || undefined,
        });
        if (!alive) return;
        const rows = (data as any).investments || [];
        setAllBatchRows(rows);
        setAllBatchRowsHasMore((data.investments_pagination?.total_pages ?? 1) > 1);
      } catch {
        if (alive) toast.error("Failed to load investors");
      } finally {
        if (alive) {
          setAllBatchRowsLoading(false);
          allBatchRowsFetchingRef.current = false;
        }
      }
    })();
    return () => { alive = false; };
  }, [showAllInvestors, batchId, trimmedInvestorSearch]);

  const loadMoreBatchRows = () => {
    if (!showAllInvestors || !allBatchRowsHasMore || allBatchRowsFetchingRef.current) return;
    allBatchRowsFetchingRef.current = true;
    const nextPage = allBatchRowsPageRef.current + 1;
    setAllBatchRowsLoadingMore(true);
    batchService
      .getById(batchId, { show_all: true, page: nextPage, per_page: SHOW_ALL_CHUNK, search: trimmedInvestorSearch || undefined })
      .then((data) => {
        const rows = (data as any).investments || [];
        allBatchRowsPageRef.current = nextPage;
        setAllBatchRows((prev) => [...prev, ...rows]);
        setAllBatchRowsHasMore(nextPage < (data.investments_pagination?.total_pages ?? 1));
      })
      .catch(() => toast.error("Failed to load more investors"))
      .finally(() => {
        setAllBatchRowsLoadingMore(false);
        allBatchRowsFetchingRef.current = false;
      });
  };

  async function handleExportBatchInvestments() {
    setExportingBatch(true);
    try {
      await batchService.exportInvestments(batchId, { search: trimmedInvestorSearch || undefined });
    } catch {
      toast.error("Failed to export clients to Excel");
    } finally {
      setExportingBatch(false);
    }
  }

  useEffect(() => {
    async function load() {
      if (!batchId || isNaN(batchId)) return;
      setLoading(true);
      try {
        const data = await batchService.getById(batchId);
        setBatch(data);
        setEditBatchName(data.batch_name);
        setEditCertificateNumber(data.certificate_number || "");
        setEditDurationDays(data.duration_days || 30);
        setInvestments((data as any).investments || []);
      } catch {
        toast.error("Failed to load batch");
        navigate(ROUTES.BATCHES);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [batchId, navigate]);

  const isShares = batch?.product_type === "SHARES";
  const investorColumns = getInvestorColumns(isShares);
  const isSuperAdmin = getUserRole() === "super_admin";

  // "Show all" view only — delete an investor's deposit row from this batch
  // completely (super_admin only, server-enforced too). Not offered from the
  // search-first table to keep that path simple; super admins doing cleanup
  // use "Show all" anyway.
  const handleDeleteInvestor = async (inv: BatchInvestorLight & { investor_name?: string }) => {
    if (!window.confirm(`Permanently delete ${inv.investor_name || "this investor"}'s deposit from this batch? This cannot be undone.`)) {
      return;
    }
    setDeletingInvestmentId(inv.id);
    try {
      await investmentService.deleteInvestment(inv.id);
      setAllBatchRows((prev) => prev.filter((row) => row.id !== inv.id));
      setBatch((prev) => (prev ? { ...prev, investors_count: Math.max(0, (prev.investors_count ?? 1) - 1) } : prev));
      toast.success("Investor deleted");
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || "Failed to delete investor";
      toast.error(msg);
    } finally {
      setDeletingInvestmentId(null);
    }
  };

  const showAllColumns = isSuperAdmin
    ? [
        ...investorColumns,
        {
          key: "actions",
          label: "",
          align: "right" as const,
          grid: "44px",
          render: (inv: any) => (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDeleteInvestor(inv);
              }}
              disabled={deletingInvestmentId === inv.id}
              title="Delete this investor's deposit from the batch (super admin only)"
              style={{
                background: "transparent", border: "none", color: "#F87171", padding: "4px", borderRadius: "4px",
                cursor: deletingInvestmentId === inv.id ? "not-allowed" : "pointer",
                opacity: deletingInvestmentId === inv.id ? 0.5 : 1, display: "inline-flex",
              }}
            >
              <Trash2 size={14} />
            </button>
          ),
        },
      ]
    : investorColumns;

  const advanceStage = async () => {
    if (!batch) return;
    const nextStage = (batch.stage + 1) as BatchStage;
    if (nextStage > 4) return;

    if (nextStage === 3 || nextStage === 2) {
      // SHARES batches use their own modals/panels, which fetch a live
      // preview straight from the backend (Tasks 2/3) — no need to preload
      // the cheap-fields investor list the FUNDS modals use for client-side
      // math. Deploying (nextStage === 3) is Task 9's inline panel below,
      // shown once the batch is Transferred — not a click-to-open modal.
      if (isShares) {
        if (nextStage === 3) return;
        setSharesTransferModalOpen(true);
        return;
      }

      setLoadingFullInvestments(true);
      try {
        const full = await batchService.getInvestmentsLight(batchId);
        setFullInvestments(full);
      } catch {
        toast.error("Failed to load investors for this batch");
        setLoadingFullInvestments(false);
        return;
      }
      setLoadingFullInvestments(false);
      if (nextStage === 3) setDeployModalOpen(true);
      else setTransferModalOpen(true);
      return;
    }

    const patchData: Record<string, unknown> = { stage: nextStage };
    if (nextStage === 4) patchData.is_active = true;

    try {
      await batchService.patch(batchId, patchData);
      toast.success(`Batch advanced to ${STAGE_LABELS[nextStage]}`);
      const data = await batchService.getById(batchId);
      setBatch(data);
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to update";
      toast.error(msg);
    }
  };

  const handleDeployDateConfirm = async ({ dateString, classes, oversubscription }: DeploymentConfirmPayload) => {
    setIsDeploying(true);
    const totalShares = classes.reduce((sum, c) => sum + c.totalShares, 0);
    const totalNav = classes.reduce((sum, c) => sum + c.totalNav, 0);
    const patchData: Record<string, unknown> = {
      stage: 3,
      deployment_confirmed: true,
      date_deployed: dateString,
      deployment_nav: classes[0]?.navPerShare ?? null,
      total_shares: totalShares,
      total_nav: totalNav,
      deployment_breakdown: classes,
    };
    if (oversubscription?.isOversubscribed) {
      patchData.is_oversubscribed = true;
      patchData.allocation_rate = oversubscription.allocationRate;
    }
    try {
      await batchService.patch(batchId, patchData);
      toast.success(
        oversubscription?.isOversubscribed
          ? `Batch deployed with ${oversubscription.allocationRate.toFixed(2)}% pro-rata allocation`
          : "Batch advanced to Deployed"
      );
      const data = await batchService.getById(batchId);
      setBatch(data);
      setDeployModalOpen(false);
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || "Failed to advance stage";
      toast.error(msg);
    } finally {
      setIsDeploying(false);
    }
  };

  const handleTransferCostConfirm = async (
    mode: "manual" | "aggregate",
    amountsReceived: Record<number, number> | null,
    transactionCostUsd: number | null,
    entryFeePercent: number
  ) => {
    setIsTransferring(true);
    const patchData: Record<string, unknown> = {
      stage: 2,
      is_transferred: true,
      entry_fee_percentage: entryFeePercent,
      ...(mode === "manual"
        ? { transfer_amounts_received: amountsReceived }
        : { transfer_transaction_cost: transactionCostUsd }),
    };
    try {
      await batchService.patch(batchId, patchData);
      toast.success("Batch advanced to Transferred");
      const data = await batchService.getById(batchId);
      setBatch(data);
      setTransferModalOpen(false);
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || "Failed to advance stage";
      toast.error(msg);
    } finally {
      setIsTransferring(false);
    }
  };

  const handleSharesTransferConfirm = async (entryFeePercent: number, totalTransactionCostUsd: number) => {
    setIsSharesTransferring(true);
    try {
      await batchService.patch(batchId, {
        is_transferred: true,
        entry_fee_percentage: entryFeePercent,
        transfer_transaction_cost: totalTransactionCostUsd,
      });
      toast.success("Batch advanced to Transferred");
      const data = await batchService.getById(batchId);
      setBatch(data);
      setSharesTransferModalOpen(false);
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || "Failed to advance stage";
      toast.error(msg);
    } finally {
      setIsSharesTransferring(false);
    }
  };

  const handleSharesDeployConfirm = async ({ dateString, exchangeRate, pricePerShareNgn, sharesAllocated }: SharesDeploymentConfirmPayload) => {
    setIsSharesDeploying(true);
    try {
      await batchService.patch(batchId, {
        deployment_confirmed: true,
        date_deployed: dateString,
        exchange_rate: exchangeRate,
        price_per_share_ngn: pricePerShareNgn,
        shares_allocated: sharesAllocated,
      });
      toast.success("Batch deployed");
      const data = await batchService.getById(batchId);
      setBatch(data);
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as any)?.response?.data?.message || "Failed to advance stage";
      toast.error(msg);
    } finally {
      setIsSharesDeploying(false);
    }
  };

  const handleEditToggle = () => {
    setIsEditing((current) => !current);
    if (batch) {
      setEditBatchName(batch.batch_name);
      setEditCertificateNumber(batch.certificate_number || "");
      setEditDurationDays(batch.duration_days || 30);
    }
  };

  const handleSaveEdit = async () => {
    if (!batch) return;
    if (!editBatchName.trim()) {
      toast.error("Batch name is required");
      return;
    }
    try {
      const payload: Record<string, unknown> = {
        batch_name: editBatchName.trim(),
        duration_days: editDurationDays,
      };
      payload.certificate_number = editCertificateNumber.trim() || null;

      await batchService.patch(batchId, payload);
      toast.success("Batch updated");
      setIsEditing(false);
      const updated = await batchService.getById(batchId);
      setBatch(updated);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to update batch";
      toast.error(msg);
    }
  };

  const batchFileInputRef = useRef<HTMLInputElement>(null);

  const handleBatchFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const validTypes = [
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-excel",
    ];
    if (!validTypes.includes(file.type) && !file.name.match(/\.xlsx?$/i)) {
      toast.error("Please select an .xlsx or .xls file");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("File must be under 10MB");
      return;
    }

    setSelectedBatchFile(file);
    setUploadingFile(true);
    setFileUploadProgress(0);
    const interval = setInterval(() => setFileUploadProgress((p) => Math.min(p + 20, 90)), 250);

    try {
      await batchService.uploadExcel(batchId, file);
      setFileUploadProgress(100);
      toast.success("File uploaded to existing batch");
      const updated = await batchService.getById(batchId);
      setBatch(updated);
      setInvestments((updated as any).investments || []);
      setEmailConfirmModalOpen(true);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "File upload failed";
      toast.error(msg);
    } finally {
      clearInterval(interval);
      setUploadingFile(false);
    }
  };

  const openBatchFileSelector = () => batchFileInputRef.current?.click();

  const handleDelete = async () => {
    if (!confirm("Are you sure you want to delete this batch? This cannot be undone.")) return;
    try {
      await batchService.delete(batchId);
      toast.success("Batch deleted");
      navigate(ROUTES.BATCHES);
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to delete batch";
      toast.error(msg);
    }
  };

  const handleToggleBatchActive = async () => {
    if (!batch) return;
    const actionLabel = batch.is_active ? "close" : "open";
    if (!confirm(`Are you sure you want to ${actionLabel} this batch?`)) return;
    try {
      await batchService.toggleActive(batchId);
      const refreshed = await batchService.getById(batchId);
      setBatch(refreshed);
      toast.success(batch.is_active ? "Batch closed" : "Batch opened");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Failed to update batch status";
      toast.error(msg);
    }
  };


  if (loading || !batch) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }} />
      </div>
    );
  }

  // ── Stage date grid: only date_deployed is persisted at batch level, so
  // Transferred/Deployed/Active all reflect it — Deposited uses the latest
  // investment's date_deposited (handles batches topped up after deployment).
  // Computed server-side as a cheap SQL MAX() so we never need to load every
  // investment client-side just to find this. ──
  const depositedDate = batch.latest_deposit_date ?? null;

  return (
    <div style={{ maxWidth: "1200px" }}>
      {/* Back button */}
      <button
        onClick={() => navigate(ROUTES.BATCHES)}
        style={{ display: "flex", alignItems: "center", gap: "5px", background: "none", border: "none", color: "var(--color-text-tertiary)", fontSize: "12px", cursor: "pointer", marginBottom: "16px", padding: 0 }}
      >
        <ArrowLeft size={13} /> Back to batches
      </button>

      {/* Header card */}
      <div style={{ ...glassCard, padding: "22px 24px", marginBottom: "16px" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "16px", flexWrap: "wrap" }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}>
              <h1 style={{ fontFamily: "var(--font-mono)", fontSize: "18px", fontWeight: 700, color: "var(--color-text-primary)", margin: 0 }}>
                {batch.batch_name}
              </h1>
              {batch.product_type && <ProductBadge product={batch.product_type} />}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              {reconciliation && (
                <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                  Recon Total:{" "}
                  <span style={{ color: reconciliation.reconciled === false ? "rgb(239, 68, 68)" : "rgb(34, 197, 94)", fontFamily: "var(--font-mono)" }}>
                    {fmtMoney(reconciliation.total_closing_aum)}
                  </span>
                  {reconciliation.source === "share_based_recompute" && (
                    <span style={{ marginLeft: "5px", opacity: 0.7 }}>(share-based)</span>
                  )}
                  {reconciliation.reconciled === false && (
                    <span style={{ marginLeft: "5px", color: "rgb(239, 68, 68)" }}>— mismatch vs. cache</span>
                  )}
                </span>
              )}
            </div>
            {isEditing && (
              <div className="mt-2 p-3" style={{ background: "rgba(0, 0, 0, 0.25)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "10px", maxWidth: "360px" }}>
                <div className="mb-2">
                  <label className="text-xs fw-semibold" style={{ color: "var(--color-text-secondary)" }}>Batch name</label>
                  <input value={editBatchName} onChange={(e) => setEditBatchName(e.target.value)} className="form-control" style={{ background: "var(--color-bg-input)", borderColor: "var(--color-border-default)", color: "var(--color-text-primary)" }} />
                </div>
                <div className="mb-2">
                  <label className="text-xs fw-semibold" style={{ color: "var(--color-text-secondary)" }}>Certificate number</label>
                  <input value={editCertificateNumber} onChange={(e) => setEditCertificateNumber(e.target.value)} className="form-control" style={{ background: "var(--color-bg-input)", borderColor: "var(--color-border-default)", color: "var(--color-text-primary)" }} />
                </div>
                <div className="mb-2">
                  <label className="text-xs fw-semibold" style={{ color: "var(--color-text-secondary)" }}>Duration (days)</label>
                  <input type="number" value={editDurationDays} onChange={(e) => setEditDurationDays(Number(e.target.value))} className="form-control" style={{ background: "var(--color-bg-input)", borderColor: "var(--color-border-default)", color: "var(--color-text-primary)" }} min={1} />
                </div>
                <div className="d-flex gap-2 mt-2">
                  <button onClick={handleSaveEdit} className="btn btn-primary btn-sm" style={{ fontSize: "12px" }}>Save</button>
                  <button onClick={handleEditToggle} className="btn btn-outline-secondary btn-sm" style={{ fontSize: "12px" }}>Cancel</button>
                </div>
              </div>
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexShrink: 0, flexWrap: "wrap" }}>
            <button title="Edit" onClick={handleEditToggle} style={iconBtn}>
              <Pencil size={13} />
            </button>
            <button title="Upload investors" onClick={openBatchFileSelector} style={iconBtn}>
              <Upload size={13} />
            </button>
            <button title="Export" onClick={() => reportService.downloadBatchSummary(batchId)} style={iconBtn}>
              <Download size={13} />
            </button>
            <button
              onClick={handleToggleBatchActive}
              style={{ padding: "7px 12px", borderRadius: "8px", background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.2)", color: "rgb(239, 68, 68)", fontSize: "11px", fontWeight: 500, cursor: "pointer" }}
            >
              {batch.is_active ? "Close" : "Open"}
            </button>
            <button title="Delete batch" onClick={handleDelete} style={dangerIconBtn}>
              <Trash2 size={13} />
            </button>
          </div>
        </div>
        <input ref={batchFileInputRef} type="file" accept=".xlsx,.xls" style={{ display: "none" }} onChange={handleBatchFileChange} />
      </div>

      {/* Deployment progress */}
      <div style={{ ...glassCard, padding: "18px 22px", marginBottom: "16px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px" }}>
          <p style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-text-tertiary)", margin: 0 }}>
            Deployment Progress
          </p>
          {batch.stage < 4 && !(isShares && batch.stage === 2) && (
            <button
              onClick={advanceStage}
              disabled={loadingFullInvestments}
              style={{
                background: "linear-gradient(135deg, var(--color-brand-500), var(--color-brand-400))",
                color: "#FFFFFF",
                borderRadius: "8px",
                border: "none",
                boxShadow: "0 4px 12px rgba(0, 102, 255, 0.2)",
                padding: "7px 14px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: loadingFullInvestments ? "not-allowed" : "pointer",
                opacity: loadingFullInvestments ? 0.6 : 1,
              }}
            >
              {loadingFullInvestments ? "Loading…" : `Advance to ${STAGE_LABELS[(batch.stage + 1) as BatchStage]}`}
            </button>
          )}
        </div>

        <DeploymentStepper stage={batch.stage} />

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px", marginTop: "12px" }}>
          <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", textAlign: "center" }}>
            <div style={{ fontWeight: 600, marginBottom: "2px", color: "var(--color-text-secondary)" }}>Deposited</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px" }}>{fmtDate(depositedDate)}</div>
          </div>
          <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", textAlign: "center" }}>
            <div style={{ fontWeight: 600, marginBottom: "2px", color: "var(--color-text-secondary)" }}>Transferred</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px" }}>{batch.is_transferred ? fmtDate(batch.date_deployed) : "—"}</div>
          </div>
          <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", textAlign: "center" }}>
            <div style={{ fontWeight: 600, marginBottom: "2px", color: "var(--color-text-secondary)" }}>Deployed</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px" }}>{fmtDate(batch.date_deployed)}</div>
          </div>
          <div style={{ fontSize: "10px", color: "var(--color-text-tertiary)", textAlign: "center" }}>
            <div style={{ fontWeight: 600, marginBottom: "2px", color: "var(--color-text-secondary)" }}>Active</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: "9px" }}>{batch.is_active ? fmtDate(batch.date_deployed) : "—"}</div>
          </div>
        </div>

        {uploadingFile && (
          <div className="mt-2" style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>
            Uploading file... {fileUploadProgress}%
            <div className="h-2 mt-1 rounded-full" style={{ background: "rgba(255,255,255,0.08)" }}>
              <div className="h-full rounded-full" style={{ width: `${fileUploadProgress}%`, background: "var(--color-brand-400)" }} />
            </div>
          </div>
        )}
        {!uploadingFile && selectedBatchFile && (
          <p className="mt-2 mb-0" style={{ color: "var(--color-text-secondary)", fontSize: "12px" }}>
            Selected file: {selectedBatchFile.name}
          </p>
        )}
      </div>

      {/* Task 9: Shares deployment form + allocation preview/confirm, shown
          inline once the batch is Transferred and awaiting deployment —
          replaces the old SharesDeploymentModal dialog. */}
      {isShares && batch.stage === 2 && (
        <div style={{ marginBottom: "16px" }}>
          <SharesDeploymentPanel batchId={batchId} onConfirm={handleSharesDeployConfirm} isLoading={isSharesDeploying} />
        </div>
      )}

      {/* Stat grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: "12px", marginBottom: "16px" }}>
        {/* Raw gross deposit sum at the Deposited stage — a live SUM() query
            (see fresh_total_principal in get_batch_by_id), never a re-derivation
            from shares/NAV, so it can't drift when fees/oversubscription/re-
            valuation happen later. Was previously wired to batch.total_capital
            (current live standing, i.e. shares × current price) by mistake —
            that's a different, intentionally-changing number, not this one. */}
        <StatCard label="Total Deposited" value={fmtMoney(batch.total_principal)} sub="Raw gross deposits" />
        <StatCard label="Net Principal" value={fmtMoney(batch.total_net_principal)} sub="After transfer cost + entry fee" />
        <StatCard label="Investors" value={String(batch.investors_count)} />
        <StatCard label="Deployment Date" value={fmtDate(batch.date_deployed)} />
        <StatCard label="NAV at Deployment" value={batch.deployment_nav != null ? batch.deployment_nav.toFixed(4) : "—"} sub="/ share" />
        <StatCard label="Total NAV" value={fmtMoney(batch.deployment_total_nav)} sub="Computed at deployment" />
        <StatCard label="Total Shares" value={batch.total_shares != null ? batch.total_shares.toLocaleString("en-US", { maximumFractionDigits: 4 }) : "—"} />
      </div>

      {/* SHARES-only allocation stats (Task 3) — kept in their own row, never
          blended into the NAV-labeled cards above, since the two products are
          valued completely differently (price per share vs. NAV). */}
      {isShares && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "12px", marginBottom: "16px" }}>
          <StatCard label="Exchange Rate" value={batch.shares_exchange_rate_ngn != null ? batch.shares_exchange_rate_ngn.toLocaleString("en-US", { maximumFractionDigits: 6 }) : "—"} sub="NGN / USD" />
          <StatCard label="Price Per Share" value={batch.shares_price_per_share_ngn != null ? batch.shares_price_per_share_ngn.toLocaleString("en-US", { maximumFractionDigits: 4 }) : "—"} sub="NGN" />
          <StatCard label="Shares Allocated" value={batch.shares_allocated_total != null ? batch.shares_allocated_total.toLocaleString() : "—"} />
          <StatCard label="Shares Demand" value={batch.shares_demand_total != null ? batch.shares_demand_total.toLocaleString() : "—"} />
          <StatCard
            label="Unallocated"
            value={batch.shares_unallocated_total != null ? batch.shares_unallocated_total.toLocaleString() : "—"}
            sub={batch.is_oversubscribed ? "Oversubscribed" : (batch.shares_allocated_total != null ? "Fully subscribed" : undefined)}
          />
        </div>
      )}

      {/* Investors table */}
      <div style={{ ...glassCard, overflow: "hidden" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid rgba(255, 255, 255, 0.06)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap" }}>
          <p style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-text-tertiary)", margin: 0 }}>
            Investors ({batch.investors_count})
          </p>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div style={{ position: "relative" }}>
              <Search
                size={12}
                style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--color-text-tertiary)", pointerEvents: "none" }}
              />
              <input
                placeholder="Search by client code, email, or phone…"
                value={investorSearch}
                onChange={(e) => setInvestorSearch(e.target.value)}
                style={{
                  background: "rgba(255, 255, 255, 0.04)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "8px",
                  padding: "6px 12px 6px 28px",
                  fontSize: "12px",
                  color: "var(--color-text-primary)",
                  width: "230px",
                  outline: "none",
                }}
              />
            </div>
            <button
              onClick={() => setShowAllInvestors((v) => !v)}
              title={showAllInvestors ? "Back to search mode" : "Show every client in this batch (virtualized list)"}
              style={{
                display: "flex", alignItems: "center", gap: "6px", padding: "6px 12px", borderRadius: "8px",
                background: showAllInvestors ? "rgba(26, 69, 255, 0.15)" : "transparent",
                border: `1px solid ${showAllInvestors ? "rgba(26, 69, 255, 0.4)" : "rgba(255, 255, 255, 0.1)"}`,
                color: showAllInvestors ? "rgb(96, 148, 255)" : "var(--color-text-secondary)",
                fontSize: "12px", fontWeight: 500, cursor: "pointer", whiteSpace: "nowrap",
              }}
            >
              <Rows3 size={13} /> {showAllInvestors ? "Showing all" : "Show all"}
            </button>
            <button
              onClick={handleExportBatchInvestments}
              disabled={exportingBatch}
              title="Export every matching client to Excel"
              style={{
                display: "flex", alignItems: "center", gap: "6px", padding: "6px 12px", borderRadius: "8px",
                background: "transparent", border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "var(--color-text-secondary)", fontSize: "12px", fontWeight: 500,
                cursor: exportingBatch ? "not-allowed" : "pointer", opacity: exportingBatch ? 0.6 : 1, whiteSpace: "nowrap",
              }}
            >
              <Download size={13} /> {exportingBatch ? "Exporting…" : "Export to Excel"}
            </button>
            <button
              onClick={() => navigate(ROUTES.BATCH_PERFORMANCE(batchId))}
              style={{ fontSize: "11px", fontWeight: 500, color: "var(--color-brand-400)", background: "none", border: "none", cursor: "pointer", padding: 0, whiteSpace: "nowrap" }}
            >
              View performance →
            </button>
          </div>
        </div>
        {showAllInvestors ? (
          <div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: showAllColumns.map((c) => c.grid).join(" "),
                gap: "12px",
                borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                padding: "10px 16px",
                background: "rgba(255, 255, 255, 0.02)",
              }}
            >
              {showAllColumns.map((c) => (
                <span
                  key={c.key}
                  style={{
                    fontSize: "9px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase",
                    color: "var(--color-text-tertiary)", textAlign: c.align, whiteSpace: "nowrap",
                  }}
                >
                  {c.label}
                </span>
              ))}
            </div>
            {allBatchRowsLoading ? (
              <div style={{ padding: "32px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                Loading…
              </div>
            ) : (
              <VirtualizedList
                items={allBatchRows}
                rowHeight={52}
                height={520}
                onEndReached={loadMoreBatchRows}
                loadingMore={allBatchRowsLoadingMore}
                emptyState={
                  <div style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                    No investments in this batch yet.
                  </div>
                }
                renderRow={(inv: any) => (
                  <div
                    onClick={() => inv.internal_client_code && navigate(ROUTES.INVESTOR_OVERVIEW(inv.internal_client_code))}
                    style={{
                      display: "grid",
                      gridTemplateColumns: showAllColumns.map((c) => c.grid).join(" "),
                gap: "12px",
                      alignItems: "center",
                      height: "100%",
                      padding: "0 16px",
                      borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                      cursor: "pointer",
                      fontFamily: "var(--font-mono)",
                      fontSize: "12px",
                    }}
                  >
                    {showAllColumns.map((c) => (
                      <div key={c.key} style={{ textAlign: c.align, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {c.render(inv)}
                      </div>
                    ))}
                  </div>
                )}
              />
            )}
          </div>
        ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                {investorColumns.map((h) => (
                  <th
                    key={h.key}
                    style={{
                      fontSize: "9px",
                      fontWeight: 600,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      color: "var(--color-text-tertiary)",
                      padding: "10px 16px",
                      textAlign: h.align,
                      background: "rgba(255, 255, 255, 0.02)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {!trimmedInvestorSearch ? (
                <tr>
                  <td colSpan={investorColumns.length} style={{ padding: "40px 16px", textAlign: "center" }}>
                    <Users2 size={24} style={{ color: "var(--color-text-tertiary)", marginBottom: "8px" }} />
                    <div style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "4px" }}>
                      {batch.investors_count} investor{batch.investors_count === 1 ? "" : "s"} in this batch
                    </div>
                    <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>
                      {batch.investors_count === 0
                        ? "No investments in this batch yet."
                        : "Search by client code, email, or phone number to find one."}
                    </div>
                  </td>
                </tr>
              ) : investorSearchLoading ? (
                <tr>
                  <td colSpan={investorColumns.length} style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                    Searching…
                  </td>
                </tr>
              ) : investments.length === 0 ? (
                <tr>
                  <td colSpan={investorColumns.length} style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                    No investors found for "{trimmedInvestorSearch}".
                  </td>
                </tr>
              ) : (
                investments.map((inv: any) => (
                  <tr
                    key={inv.id}
                    style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)", cursor: "pointer", transition: "background 0.12s" }}
                    onClick={() => inv.internal_client_code && navigate(ROUTES.INVESTOR_OVERVIEW(inv.internal_client_code))}
                  >
                    {investorColumns.map((c) => (
                      <td
                        key={c.key}
                        style={{
                          padding: "10px 16px",
                          fontFamily: c.key === "investor" ? undefined : "var(--font-mono)",
                          fontSize: c.key === "investor" ? undefined : "12px",
                          textAlign: c.align,
                        }}
                      >
                        {c.render(inv)}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        )}
        {!showAllInvestors && trimmedInvestorSearch && investorTotalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "flex-end", gap: "8px", padding: "12px 20px", borderTop: "1px solid rgba(255, 255, 255, 0.06)" }}>
            <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)", marginRight: "4px" }}>
              Page {investorPage} of {investorTotalPages}
            </span>
            <button
              onClick={() => setInvestorPage((p) => Math.max(1, p - 1))}
              disabled={investorPage <= 1 || investorSearchLoading}
              style={{
                display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
                borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                color: "var(--color-text-secondary)", fontSize: "12px",
                cursor: (investorPage <= 1 || investorSearchLoading) ? "not-allowed" : "pointer",
                opacity: (investorPage <= 1 || investorSearchLoading) ? 0.5 : 1,
              }}
            >
              <ChevronLeft size={14} /> Prev
            </button>
            <button
              onClick={() => setInvestorPage((p) => Math.min(investorTotalPages, p + 1))}
              disabled={investorPage >= investorTotalPages || investorSearchLoading}
              style={{
                display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
                borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                color: "var(--color-text-secondary)", fontSize: "12px",
                cursor: (investorPage >= investorTotalPages || investorSearchLoading) ? "not-allowed" : "pointer",
                opacity: (investorPage >= investorTotalPages || investorSearchLoading) ? 0.5 : 1,
              }}
            >
              Next <ChevronRight size={14} />
            </button>
          </div>
        )}
      </div>

      {/* Email confirmation gate — opens after stage advance or file upload */}
      <EmailConfirmationModal open={emailConfirmModalOpen} onClose={() => setEmailConfirmModalOpen(false)} batchId={batchId} />
      <DeploymentDateModal open={deployModalOpen} onClose={() => setDeployModalOpen(false)} onConfirm={handleDeployDateConfirm} isLoading={isDeploying} investments={fullInvestments} isDprpFund={batch.is_dprp_fund} />
      <TransferCostModal open={transferModalOpen} onClose={() => setTransferModalOpen(false)} investments={fullInvestments} onConfirm={handleTransferCostConfirm} isLoading={isTransferring} />
      <SharesTransferModal open={sharesTransferModalOpen} onClose={() => setSharesTransferModalOpen(false)} batchId={batchId} onConfirm={handleSharesTransferConfirm} isLoading={isSharesTransferring} />
    </div>
  );
}
