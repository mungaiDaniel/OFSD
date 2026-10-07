import { useCallback, useEffect, useRef, useState } from "react";
import { investmentService } from "@/services/investmentService";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "@/lib/constants";
import type { ProductType } from "@/lib/types";
import { ProductBadge } from "@/components/ui/ProductBadge";
import { VirtualizedList } from "@/components/ui/VirtualizedList";
import { Search, Plus, CircleUserRound, Upload, ChevronLeft, ChevronRight, Rows3, Download } from "lucide-react";

interface InvestorRow {
  investor_name: string | null;
  internal_client_code: string;
  investor_email: string | null;
  fund_name: string | null;
  class_code: string | null;
  currency: string | null;
  shares: number | null;
  market_value: number | null;
  performance_pct: number | null;
}

const PER_PAGE = 50;
// "Show all" chunk size — the frontend loads this many rows per request,
// virtualizing so only the rows actually on screen are ever mounted, rather
// than fetching every investor (which could be 100,000+) in one request.
const SHOW_ALL_CHUNK = 200;
const ROW_HEIGHT = 54;
const GRID_TEMPLATE = "2.2fr 1.2fr 1.6fr 0.9fr 1fr 0.8fr";

interface InvestorDirectoryPageProps {
  /** Scopes the directory to investors holding this product. Omit for the
   * (legacy) combined view across both products. */
  product?: ProductType;
}

export default function InvestorDirectoryPage({ product }: InvestorDirectoryPageProps) {
  const navigate = useNavigate();
  const [investors, setInvestors] = useState<InvestorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);

  // "Show all": chunk-loaded + virtualized, bypassing the small table's
  // search-first gate — never fetches everything in one request (see
  // SHOW_ALL_CHUNK), and only the rows scrolled into view are ever mounted.
  const [showAll, setShowAll] = useState(false);
  const [allRows, setAllRows] = useState<InvestorRow[]>([]);
  const [allRowsLoading, setAllRowsLoading] = useState(false);
  const [allRowsLoadingMore, setAllRowsLoadingMore] = useState(false);
  const [allRowsHasMore, setAllRowsHasMore] = useState(true);
  const allRowsPageRef = useRef(1);
  const allRowsFetchingRef = useRef(false);
  const [exporting, setExporting] = useState(false);

  // Debounce search so we're not hitting the server on every keystroke; resets to page 1.
  useEffect(() => {
    const t = setTimeout(() => setPage(1), 300);
    return () => clearTimeout(t);
  }, [search]);

  const trimmedSearch = search.trim();

  // Reset and reload the first chunk whenever "Show all" turns on, or the
  // filters change while it's already on.
  useEffect(() => {
    if (!showAll) return;
    let alive = true;
    allRowsPageRef.current = 1;
    allRowsFetchingRef.current = true;
    setAllRows([]);
    setAllRowsHasMore(true);
    setAllRowsLoading(true);
    (async () => {
      try {
        const res = await investmentService.getInvestorDirectory({
          page: 1, per_page: SHOW_ALL_CHUNK, search: trimmedSearch || undefined, product,
        });
        if (!alive) return;
        if (res.status === 200) {
          const rows = (res.data as InvestorRow[]) || [];
          setAllRows(rows);
          setTotal(res.pagination?.total ?? rows.length);
          setAllRowsHasMore((res.pagination?.total_pages ?? 1) > 1);
        } else {
          toast.error(res.message || "Failed to load investors");
        }
      } catch {
        if (alive) toast.error("Failed to load investors");
      } finally {
        if (alive) {
          setAllRowsLoading(false);
          allRowsFetchingRef.current = false;
        }
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showAll, trimmedSearch, product]);

  const loadMoreRows = useCallback(() => {
    if (!showAll || !allRowsHasMore || allRowsFetchingRef.current) return;
    allRowsFetchingRef.current = true;
    const nextPage = allRowsPageRef.current + 1;
    setAllRowsLoadingMore(true);
    investmentService
      .getInvestorDirectory({ page: nextPage, per_page: SHOW_ALL_CHUNK, search: trimmedSearch || undefined, product })
      .then((res) => {
        if (res.status === 200) {
          const rows = (res.data as InvestorRow[]) || [];
          allRowsPageRef.current = nextPage;
          setAllRows((prev) => [...prev, ...rows]);
          setAllRowsHasMore(nextPage < (res.pagination?.total_pages ?? 1));
        }
      })
      .catch(() => toast.error("Failed to load more investors"))
      .finally(() => {
        setAllRowsLoadingMore(false);
        allRowsFetchingRef.current = false;
      });
  }, [showAll, allRowsHasMore, trimmedSearch, product]);

  async function handleExport() {
    setExporting(true);
    try {
      await investmentService.exportInvestorDirectory({ search: trimmedSearch || undefined, product });
    } catch {
      toast.error("Failed to export investors to Excel");
    } finally {
      setExporting(false);
    }
  }

  useEffect(() => {
    if (showAll) return; // the dedicated "show all" effect above owns fetching in this mode
    let alive = true;
    async function load() {
      setLoading(true);
      try {
        // With no search, don't ask the backend to build the (expensive) per-investor
        // balance list at all — just fetch the total count via per_page=1, and show a
        // "search to find someone" prompt instead of a 10,000+-row table.
        const res = await investmentService.getInvestorDirectory(
          trimmedSearch
            ? { page, per_page: PER_PAGE, search: trimmedSearch, product }
            : { page: 1, per_page: 1, product }
        );
        if (!alive) return;
        if (res.status === 200) {
          setInvestors(trimmedSearch ? ((res.data as InvestorRow[]) || []) : []);
          setTotalPages(res.pagination?.total_pages ?? 1);
          setTotal(res.pagination?.total ?? (res.data as InvestorRow[])?.length ?? 0);
        } else {
          toast.error(res.message || "Failed to load investor directory");
        }
      } catch (err) {
        if (alive) toast.error("Failed to load investor directory");
      } finally {
        if (alive) setLoading(false);
      }
    }

    load();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, trimmedSearch, product, showAll]);

  return (
    <div className="ofds-page">
      <div>
        <div className="page-header-row mb-4">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "4px" }}>
              <h1
                style={{
                  fontSize: "22px",
                  fontWeight: 700,
                  color: "var(--color-text-primary)",
                  letterSpacing: "-0.02em",
                  margin: 0,
                }}
              >
                Investors
              </h1>
              {product && <ProductBadge product={product} />}
            </div>
            <p style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
              {showAll
                ? `Showing ${allRows.length.toLocaleString()} of ${total.toLocaleString()} investor${total === 1 ? "" : "s"}`
                : `${total.toLocaleString()} registered investor${total === 1 ? "" : "s"}`}
              {product ? ` holding ${product === "SHARES" ? "Shares" : "Funds"}` : ""}
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
            <div style={{ position: "relative" }}>
              <Search
                size={12}
                style={{
                  position: "absolute",
                  left: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--color-text-tertiary)",
                  pointerEvents: "none",
                }}
              />
              <input
                placeholder="Search by client code, email, or phone…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  background: "rgba(255, 255, 255, 0.04)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: "8px",
                  padding: "6px 12px 6px 30px",
                  fontSize: "12px",
                  color: "var(--color-text-primary)",
                  width: "240px",
                  outline: "none",
                }}
              />
            </div>
            <button
              onClick={() => setShowAll((v) => !v)}
              title={showAll ? "Back to search mode" : "Show every investor (virtualized list)"}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                borderRadius: "8px",
                background: showAll ? "rgba(26, 69, 255, 0.15)" : "transparent",
                border: `1px solid ${showAll ? "rgba(26, 69, 255, 0.4)" : "rgba(255, 255, 255, 0.1)"}`,
                color: showAll ? "rgb(96, 148, 255)" : "var(--color-text-secondary)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              <Rows3 size={14} /> {showAll ? "Showing all" : "Show all"}
            </button>
            <button
              onClick={handleExport}
              disabled={exporting}
              title="Export every matching investor to Excel"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                borderRadius: "8px",
                background: "transparent",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "var(--color-text-secondary)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: exporting ? "not-allowed" : "pointer",
                opacity: exporting ? 0.6 : 1,
              }}
            >
              <Download size={14} /> {exporting ? "Exporting…" : "Export to Excel"}
            </button>
            <button
              onClick={() => navigate(product ? `${ROUTES.INVESTOR_BULK_UPLOAD}?product=${product}` : ROUTES.INVESTOR_BULK_UPLOAD)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 16px",
                borderRadius: "8px",
                background: "transparent",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: "var(--color-text-secondary)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              <Upload size={14} /> Bulk upload
            </button>
            <button
              onClick={() => navigate(product ? `${ROUTES.INVESTOR_ADD}?product=${product}` : ROUTES.INVESTOR_ADD)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 18px",
                borderRadius: "8px",
                background: "rgb(26, 69, 255)",
                border: "none",
                color: "rgb(255, 255, 255)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
                boxShadow: "rgba(26, 69, 255, 0.3) 0px 0px 16px",
              }}
            >
              <Plus size={14} /> Add investor
            </button>
          </div>
        </div>

        {!showAll && (
        <div
          style={{
            background: "rgba(16, 24, 45, 0.72)",
            backdropFilter: "blur(20px) saturate(150%)",
            WebkitBackdropFilter: "blur(20px) saturate(150%)",
            border: "1px solid rgba(255, 255, 255, 0.07)",
            borderRadius: "16px",
            boxShadow: "rgba(0, 0, 0, 0.25) 0px 4px 24px",
          }}
        >
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
                  {["Investor", "Client Code", "Fund / Class", "Shares", "Market Value", "Performance"].map((col) => (
                    <th
                      key={col}
                      style={{
                        padding: "10px 16px",
                        textAlign: "left",
                        fontSize: "9px",
                        fontWeight: 700,
                        letterSpacing: "0.08em",
                        textTransform: "uppercase",
                        color: "var(--color-text-tertiary)",
                      }}
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!trimmedSearch ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "48px 16px", textAlign: "center" }}>
                      <CircleUserRound size={28} style={{ color: "var(--color-text-tertiary)", marginBottom: "10px" }} />
                      <div style={{ fontSize: "13px", color: "var(--color-text-secondary)", marginBottom: "4px" }}>
                        {total.toLocaleString()} investor{total === 1 ? "" : "s"} on file
                      </div>
                      <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>
                        Search by client code, email, or phone number to find one.
                      </div>
                    </td>
                  </tr>
                ) : loading ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "32px 16px", textAlign: "center" }}>
                      <div
                        className="w-5 h-5 border-2 rounded-full animate-spin"
                        style={{ display: "inline-block", borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }}
                      />
                    </td>
                  </tr>
                ) : investors.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                      No investors found for "{trimmedSearch}".
                    </td>
                  </tr>
                ) : (
                  investors.map((inv) => {
                    const isKES = inv.currency === "KES";
                    const currencyVar = isKES ? "var(--color-kes)" : "var(--color-usd)";
                    const currencyBg = isKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)";
                    const currencyBorder = isKES ? "var(--color-kes-border)" : "var(--color-usd-border)";
                    const code = inv.internal_client_code;

                    return (
                      <tr
                        key={code}
                        onClick={() => navigate(ROUTES.INVESTOR_OVERVIEW(code))}
                        onMouseEnter={() => setHoveredRow(code)}
                        onMouseLeave={() => setHoveredRow((cur) => (cur === code ? null : cur))}
                        style={{
                          cursor: "pointer",
                          borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                          transition: "background 0.1s",
                          background: hoveredRow === code ? "rgba(255, 255, 255, 0.02)" : "transparent",
                        }}
                      >
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                            <div
                              style={{
                                width: "28px",
                                height: "28px",
                                borderRadius: "50%",
                                background: "rgba(59, 130, 246, 0.15)",
                                border: "1px solid rgba(59, 130, 246, 0.3)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                flexShrink: 0,
                              }}
                            >
                              <CircleUserRound size={14} style={{ color: "rgb(96, 165, 250)" }} />
                            </div>
                            <div>
                              <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)" }}>
                                {inv.investor_name || "—"}
                              </div>
                              <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}>
                                {inv.investor_email || "—"}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700, color: "var(--color-text-secondary)" }}>
                            {code}
                          </span>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
                              {inv.fund_name || "—"}
                            </span>
                            {inv.class_code && (
                              <>
                                <span style={{ color: "rgba(255, 255, 255, 0.2)", fontSize: "10px" }}>›</span>
                                <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 700, color: currencyVar }}>
                                  {inv.class_code}
                                </span>
                              </>
                            )}
                            {inv.currency && (
                              <span
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  padding: "2px 7px",
                                  borderRadius: "5px",
                                  fontSize: "9px",
                                  fontWeight: 700,
                                  letterSpacing: "0.06em",
                                  fontFamily: "var(--font-mono)",
                                  background: currencyBg,
                                  color: currencyVar,
                                  border: `1px solid ${currencyBorder}`,
                                }}
                              >
                                {inv.currency}
                              </span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                            {inv.shares != null ? inv.shares.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}
                          </span>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                            {inv.market_value != null
                              ? `${isKES ? "KES" : "$"} ${inv.market_value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`
                              : "—"}
                          </span>
                        </td>
                        <td style={{ padding: "12px 16px" }}>
                          <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                            {inv.performance_pct != null ? `${inv.performance_pct.toFixed(2)}%` : "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
        )}

        {showAll && (
          <div
            style={{
              background: "rgba(16, 24, 45, 0.72)",
              backdropFilter: "blur(20px) saturate(150%)",
              WebkitBackdropFilter: "blur(20px) saturate(150%)",
              border: "1px solid rgba(255, 255, 255, 0.07)",
              borderRadius: "16px",
              boxShadow: "rgba(0, 0, 0, 0.25) 0px 4px 24px",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                display: "grid",
                gridTemplateColumns: GRID_TEMPLATE,
                gap: "12px",
                borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                padding: "10px 16px",
              }}
            >
              {["Investor", "Client Code", "Fund / Class", "Shares", "Market Value", "Performance"].map((col) => (
                <span
                  key={col}
                  style={{
                    fontSize: "9px", fontWeight: 700, letterSpacing: "0.08em",
                    textTransform: "uppercase", color: "var(--color-text-tertiary)",
                  }}
                >
                  {col}
                </span>
              ))}
            </div>

            {allRowsLoading ? (
              <div style={{ padding: "32px 16px", textAlign: "center" }}>
                <div
                  className="w-5 h-5 border-2 rounded-full animate-spin"
                  style={{ display: "inline-block", borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }}
                />
              </div>
            ) : (
              <VirtualizedList
                items={allRows}
                rowHeight={ROW_HEIGHT}
                height={560}
                onEndReached={loadMoreRows}
                loadingMore={allRowsLoadingMore}
                emptyState={
                  <div style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                    No investors found{trimmedSearch ? ` for "${trimmedSearch}"` : ""}.
                  </div>
                }
                renderRow={(inv) => {
                  const isKES = inv.currency === "KES";
                  const code = inv.internal_client_code;
                  return (
                    <div
                      onClick={() => navigate(ROUTES.INVESTOR_OVERVIEW(code))}
                      style={{
                        display: "grid",
                        gridTemplateColumns: GRID_TEMPLATE,
                gap: "12px",
                        alignItems: "center",
                        height: "100%",
                        padding: "0 16px",
                        borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "10px", minWidth: 0 }}>
                        <div
                          style={{
                            width: "24px", height: "24px", borderRadius: "50%", flexShrink: 0,
                            background: "rgba(59, 130, 246, 0.15)", border: "1px solid rgba(59, 130, 246, 0.3)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                          }}
                        >
                          <CircleUserRound size={12} style={{ color: "rgb(96, 165, 250)" }} />
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: "13px", fontWeight: 600, color: "var(--color-text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {inv.investor_name || "—"}
                          </div>
                          <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {inv.investor_email || "—"}
                          </div>
                        </div>
                      </div>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", fontWeight: 700, color: "var(--color-text-secondary)" }}>
                        {code}
                      </span>
                      <span style={{ fontSize: "12px", color: "var(--color-text-secondary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {inv.fund_name || "—"}{inv.class_code ? ` › ${inv.class_code}` : ""}
                      </span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                        {inv.shares != null ? inv.shares.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}
                      </span>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                        {inv.market_value != null ? `${isKES ? "KES" : "$"} ${inv.market_value.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—"}
                      </span>
                      <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                        {inv.performance_pct != null ? `${inv.performance_pct.toFixed(2)}%` : "—"}
                      </span>
                    </div>
                  );
                }}
              />
            )}
          </div>
        )}

        {!showAll && trimmedSearch && totalPages > 1 && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: "14px" }}>
            <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
              {total.toLocaleString()} investor{total !== 1 ? "s" : ""} — page {page} of {totalPages}
            </span>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                style={{
                  display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
                  borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                  color: "var(--color-text-secondary)", fontSize: "12px", cursor: (page <= 1 || loading) ? "not-allowed" : "pointer",
                  opacity: (page <= 1 || loading) ? 0.5 : 1,
                }}
              >
                <ChevronLeft size={14} /> Prev
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || loading}
                style={{
                  display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px",
                  borderRadius: "6px", background: "transparent", border: "1px solid rgba(255,255,255,0.1)",
                  color: "var(--color-text-secondary)", fontSize: "12px", cursor: (page >= totalPages || loading) ? "not-allowed" : "pointer",
                  opacity: (page >= totalPages || loading) ? 0.5 : 1,
                }}
              >
                Next <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
