import { useEffect, useState } from "react";
import { investmentService } from "@/services/investmentService";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { ROUTES } from "@/lib/constants";
import { Search, Plus, CircleUserRound, Upload, ChevronLeft, ChevronRight } from "lucide-react";

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

export default function InvestorDirectoryPage() {
  const navigate = useNavigate();
  const [investors, setInvestors] = useState<InvestorRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [hoveredRow, setHoveredRow] = useState<string | null>(null);

  // Debounce search so we're not hitting the server on every keystroke; resets to page 1.
  useEffect(() => {
    const t = setTimeout(() => setPage(1), 300);
    return () => clearTimeout(t);
  }, [search]);

  const trimmedSearch = search.trim();

  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      try {
        // With no search, don't ask the backend to build the (expensive) per-investor
        // balance list at all — just fetch the total count via per_page=1, and show a
        // "search to find someone" prompt instead of a 10,000+-row table.
        const res = await investmentService.getInvestorDirectory(
          trimmedSearch
            ? { page, per_page: PER_PAGE, search: trimmedSearch }
            : { page: 1, per_page: 1 }
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
  }, [page, trimmedSearch]);

  return (
    <div className="ofds-page">
      <div>
        <div className="page-header-row mb-4">
          <div>
            <h1
              style={{
                fontSize: "22px",
                fontWeight: 700,
                color: "var(--color-text-primary)",
                letterSpacing: "-0.02em",
                marginBottom: "4px",
              }}
            >
              Investors
            </h1>
            <p style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
              {total.toLocaleString()} registered investor{total === 1 ? "" : "s"}
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
              onClick={() => navigate(ROUTES.INVESTOR_BULK_UPLOAD)}
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
              onClick={() => navigate(ROUTES.INVESTOR_ADD)}
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

        {trimmedSearch && totalPages > 1 && (
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
