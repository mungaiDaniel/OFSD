import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fundService } from "@/services/fundService";
import { ROUTES } from "@/lib/constants";
import { formatCurrencyCompact } from "@/lib/utils";
import type { CoreFund, ProductType } from "@/lib/types";
import { toast } from "sonner";
import { Plus, X, Landmark, Coins, ChevronRight } from "lucide-react";

// Task 9: currencies available per product in the Add/Edit Share Class forms
// — Funds keep KES/USD, Shares (DPRP) is NGN-valued (Task 7/8).
const CURRENCIES_BY_PRODUCT: Record<ProductType, string[]> = {
  FUNDS: ["KES", "USD"],
  SHARES: ["NGN"],
};

interface FundListPageProps {
  /** Scopes this page to one product — same component, same layout/forms,
   * different data/wording/currency (Task 9). Defaults to FUNDS (unchanged
   * behavior for the existing /funds page). */
  product?: ProductType;
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "8px",
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.1)",
  color: "#FFFFFF",
  fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
  fontSize: "13px",
  outline: "none",
  transition: "all 0.15s",
};

const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
  appearance: "none",
  paddingRight: "32px",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%2394A3B8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  backgroundSize: "12px",
};

const labelStyle: React.CSSProperties = {
  fontSize: "11px",
  fontWeight: 500,
  color: "#94A3B8",
  marginBottom: "6px",
  display: "block",
};

function handleFocus(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
  e.target.style.borderColor = "#3B82F6";
  e.target.style.boxShadow = "0 0 0 3px rgba(59,130,246,0.15)";
  e.target.style.background = "rgba(0,0,0,0.35)";
}

function handleBlur(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement>) {
  e.target.style.borderColor = "rgba(255,255,255,0.1)";
  e.target.style.boxShadow = "none";
  e.target.style.background = "rgba(0,0,0,0.25)";
}

export default function FundListPage({ product = "FUNDS" }: FundListPageProps) {
  const navigate = useNavigate();
  const isShares = product === "SHARES";
  const currencies = CURRENCIES_BY_PRODUCT[product];
  const noun = isShares ? "share" : "fund";
  const Noun = isShares ? "Share" : "Fund";
  const detailPath = isShares ? ROUTES.SHARE_DETAIL : ROUTES.FUND_DETAIL;

  const [funds, setFunds] = useState<CoreFund[]>([]);
  const [loading, setLoading] = useState(true);

  // Create fund/share modal/form state
  const [showCreateFund, setShowCreateFund] = useState(false);
  const [newFundName, setNewFundName] = useState("");
  const [newFundCode, setNewFundCode] = useState("");
  const [creatingFund, setCreatingFund] = useState(false);

  // Add share class modal/form state
  const [showAddClass, setShowAddClass] = useState(false);
  const [selectedFundId, setSelectedFundId] = useState<number | "">("");
  const [className, setClassName] = useState("");
  const [classCode, setClassCode] = useState("");
  const [classCurrency, setClassCurrency] = useState(currencies[0]!);
  const [addingClass, setAddingClass] = useState(false);

  const loadFunds = async () => {
    setLoading(true);
    try {
      setFunds(await fundService.getAll(product));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFunds();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [product]);

  const handleCreateFund = async () => {
    if (!newFundName.trim() || !newFundCode.trim()) {
      toast.error(`${Noun} name and code are required`);
      return;
    }
    setCreatingFund(true);
    try {
      await fundService.createFund(newFundName.trim(), newFundCode.trim(), product);
      toast.success(`${Noun} "${newFundName}" created`);
      setNewFundName("");
      setNewFundCode("");
      setShowCreateFund(false);
      await loadFunds();
    } catch (err: any) {
      toast.error(err.response?.data?.message || `Failed to create ${noun}`);
    } finally {
      setCreatingFund(false);
    }
  };

  const handleAddClass = async () => {
    if (!selectedFundId || !className.trim() || !classCode.trim()) {
      toast.error("All fields are required");
      return;
    }
    setAddingClass(true);
    try {
      await fundService.createClass(
        selectedFundId,
        {
          class_name: className.trim(),
          class_code: classCode.trim(),
          currency: classCurrency,
        },
        product
      );
      toast.success(`Share class "${className}" added`);
      setClassName("");
      setClassCode("");
      setClassCurrency(currencies[0]!);
      setShowAddClass(false);
      setSelectedFundId("");
      await loadFunds();
    } catch (err: any) {
      toast.error(err.response?.data?.message || "Failed to add share class");
    } finally {
      setAddingClass(false);
    }
  };

  return (
    <div className="container-fluid px-0">
      {/* Page Header */}
      <div className="page-header-row mb-4">
        <div>
          <h1 className="ofds-page-title">{isShares ? "Shares" : "Funds"}</h1>
          <p className="ofds-page-subtitle">
            {isShares
              ? "Shares: core shares used for performance tracking and valuation"
              : "Core funds used for performance tracking and valuation"}
          </p>
        </div>
        <button
          onClick={() => setShowCreateFund(true)}
          className="btn btn-primary btn-sm rounded-pill d-flex align-items-center gap-2 fw-bold"
          style={{
            padding: "10px 20px",
            fontSize: "13px",
            boxShadow: "0 0 20px rgba(26,69,255,0.35)",
          }}
        >
          <Plus size={16} /> New {noun}
        </button>
      </div>

      {/* Inline Create Fund Form */}
      {showCreateFund && (
        <div
          className="card shadow mb-4"
          style={{
            background: "rgba(16,24,45,0.72)",
            backdropFilter: "blur(20px) saturate(150%)",
            border: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <div className="card-body">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "20px",
              }}
            >
              <h5
                className="fw-bold mb-0"
                style={{ fontSize: "14px", color: "var(--color-text-primary)" }}
              >
                Create New {Noun}
              </h5>
              <button
                onClick={() => {
                  setShowCreateFund(false);
                  setNewFundName("");
                  setNewFundCode("");
                }}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--color-text-tertiary)",
                  cursor: "pointer",
                }}
              >
                <X size={18} />
              </button>
            </div>
            <div className="row g-3 mb-3">
              <div className="col-md-6">
                <label style={labelStyle}>{Noun} Name *</label>
                <input
                  value={newFundName}
                  onChange={(e) => setNewFundName(e.target.value)}
                  placeholder={isShares ? "e.g. Dangote Petroleum Refinery" : "e.g. Axiom"}
                  style={inputStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                  autoFocus
                />
              </div>
              <div className="col-md-6">
                <label style={labelStyle}>{Noun} Code *</label>
                <input
                  value={newFundCode}
                  onChange={(e) => setNewFundCode(e.target.value.toUpperCase())}
                  placeholder={isShares ? "e.g. DPRP" : "e.g. AXM"}
                  style={inputStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                  maxLength={10}
                />
              </div>
            </div>
            <div
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
                marginTop: "24px",
                paddingTop: "16px",
                borderTop: "1px solid rgba(255,255,255,0.07)",
              }}
            >
              <button
                onClick={() => {
                  setShowCreateFund(false);
                  setNewFundName("");
                  setNewFundCode("");
                }}
                style={{
                  padding: "11px 24px",
                  borderRadius: "8px",
                  border: "1px solid rgba(255,255,255,0.15)",
                  background: "transparent",
                  color: "var(--color-text-secondary)",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
                onMouseEnter={(e) => {
                  (e.target as HTMLElement).style.borderColor = "rgba(255,255,255,0.25)";
                  (e.target as HTMLElement).style.background = "rgba(255,255,255,0.05)";
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLElement).style.borderColor = "rgba(255,255,255,0.15)";
                  (e.target as HTMLElement).style.background = "transparent";
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreateFund}
                disabled={creatingFund || !newFundName.trim() || !newFundCode.trim()}
                style={{
                  padding: "11px 24px",
                  borderRadius: "8px",
                  border: "none",
                  background: "#1A45FF",
                  color: "#fff",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: creatingFund || !newFundName.trim() || !newFundCode.trim() ? "not-allowed" : "pointer",
                  opacity: creatingFund || !newFundName.trim() || !newFundCode.trim() ? 0.6 : 1,
                  boxShadow: "0 0 20px rgba(26,69,255,0.35)",
                }}
              >
                {creatingFund ? "Creating..." : `Create ${Noun}`}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Inline Add Share Class Form */}
      {showAddClass && (
        <div
          className="card shadow mb-4"
          style={{
            background: "rgba(16,24,45,0.72)",
            backdropFilter: "blur(20px) saturate(150%)",
            border: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <div className="card-body">
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "20px",
              }}
            >
              <h5
                className="fw-bold mb-0"
                style={{ fontSize: "14px", color: "var(--color-text-primary)" }}
              >
                Add Share Class
              </h5>
              <button
                onClick={() => {
                  setShowAddClass(false);
                  setSelectedFundId("");
                  setClassName("");
                  setClassCode("");
                }}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--color-text-tertiary)",
                  cursor: "pointer",
                }}
              >
                <X size={18} />
              </button>
            </div>
            <div className="row g-3 mb-3">
              <div className="col-md-6">
                <label style={labelStyle}>{Noun} *</label>
                <select
                  value={selectedFundId}
                  onChange={(e) => setSelectedFundId(e.target.value ? Number(e.target.value) : "")}
                  style={selectStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                >
                  <option value="">Select a {noun}...</option>
                  {funds.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.fund_name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="col-md-6">
                <label style={labelStyle}>Class Name *</label>
                <input
                  value={className}
                  onChange={(e) => setClassName(e.target.value)}
                  placeholder="e.g. Class I Participating Shares"
                  style={inputStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                  autoFocus
                />
              </div>
            </div>
            <div className="row g-3 mb-3">
              <div className="col-md-6">
                <label style={labelStyle}>Class Code *</label>
                <input
                  value={classCode}
                  onChange={(e) => setClassCode(e.target.value.toUpperCase())}
                  placeholder="e.g. KES_I"
                  style={inputStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                  maxLength={10}
                />
              </div>
              <div className="col-md-6">
                <label style={labelStyle}>Currency *</label>
                <select
                  value={classCurrency}
                  onChange={(e) => setClassCurrency(e.target.value)}
                  style={selectStyle}
                  onFocus={handleFocus}
                  onBlur={handleBlur}
                >
                  {currencies.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div
              style={{
                display: "flex",
                gap: "12px",
                justifyContent: "flex-end",
                marginTop: "24px",
                paddingTop: "16px",
                borderTop: "1px solid rgba(255,255,255,0.07)",
              }}
            >
              <button
                onClick={() => {
                  setShowAddClass(false);
                  setSelectedFundId("");
                  setClassName("");
                  setClassCode("");
                }}
                style={{
                  padding: "11px 24px",
                  borderRadius: "8px",
                  border: "1px solid rgba(255,255,255,0.15)",
                  background: "transparent",
                  color: "var(--color-text-secondary)",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s",
                }}
                onMouseEnter={(e) => {
                  (e.target as HTMLElement).style.borderColor = "rgba(255,255,255,0.25)";
                  (e.target as HTMLElement).style.background = "rgba(255,255,255,0.05)";
                }}
                onMouseLeave={(e) => {
                  (e.target as HTMLElement).style.borderColor = "rgba(255,255,255,0.15)";
                  (e.target as HTMLElement).style.background = "transparent";
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleAddClass}
                disabled={addingClass || !selectedFundId || !className.trim() || !classCode.trim()}
                style={{
                  padding: "11px 24px",
                  borderRadius: "8px",
                  border: "none",
                  background: "#1A45FF",
                  color: "#fff",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor:
                    addingClass || !selectedFundId || !className.trim() || !classCode.trim()
                      ? "not-allowed"
                      : "pointer",
                  opacity:
                    addingClass || !selectedFundId || !className.trim() || !classCode.trim()
                      ? 0.6
                      : 1,
                  boxShadow: "0 0 20px rgba(26,69,255,0.35)",
                }}
              >
                {addingClass ? "Adding..." : "Add Share Class"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons Row */}
      {!showCreateFund && !showAddClass && funds.length > 0 && (
        <div
          className="d-flex align-items-center gap-3 mb-5"
          style={{ marginLeft: 0, paddingBottom: "12px" }}
        >
          <button
            onClick={() => setShowCreateFund(true)}
            className="btn rounded-pill d-flex align-items-center gap-2 fw-bold"
            style={{
              padding: "10px 18px",
              background: "rgba(26,69,255,0.1)",
              border: "1px solid rgba(26,69,255,0.3)",
              color: "#60A5FA",
              fontSize: "13px",
              fontWeight: 600,
              transition: "all 0.2s ease",
              whiteSpace: "nowrap",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(26,69,255,0.15)";
              e.currentTarget.style.borderColor = "rgba(26,69,255,0.5)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "rgba(26,69,255,0.1)";
              e.currentTarget.style.borderColor = "rgba(26,69,255,0.3)";
            }}
          >
            <Plus size={16} /> Create {Noun}
          </button>
          <button
            onClick={() => setShowAddClass(true)}
            className="btn rounded-pill d-flex align-items-center gap-2 fw-bold"
            style={{
              padding: "10px 18px",
              background: "rgba(26,69,255,0.1)",
              border: "1px solid rgba(26,69,255,0.3)",
              color: "#60A5FA",
              fontSize: "13px",
              fontWeight: 600,
              transition: "all 0.2s ease",
              whiteSpace: "nowrap",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "rgba(26,69,255,0.15)";
              e.currentTarget.style.borderColor = "rgba(26,69,255,0.5)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "rgba(26,69,255,0.1)";
              e.currentTarget.style.borderColor = "rgba(26,69,255,0.3)";
            }}
          >
            <Plus size={16} /> Add Share Class
          </button>
        </div>
      )}

      {/* Funds Grid / Loading / Empty */}
      {loading ? (
        <div
          className="d-flex align-items-center justify-content-center"
          style={{ height: "160px" }}
        >
          <div
            className="spinner-border spinner-border-sm"
            style={{ color: "var(--color-brand-400)" }}
            role="status"
          >
            <span className="visually-hidden">Loading...</span>
          </div>
        </div>
      ) : funds.length === 0 ? (
        <div className="card shadow text-center py-5">
          <div className="card-body d-flex flex-column align-items-center">
            {isShares ? (
              <Coins size={36} className="mb-3" style={{ color: "var(--color-text-tertiary)" }} />
            ) : (
              <Landmark size={36} className="mb-3" style={{ color: "var(--color-text-tertiary)" }} />
            )}
            <p className="mb-0" style={{ color: "var(--color-text-tertiary)", fontSize: "13px" }}>
              {isShares
                ? "No shares created yet. Create a share manually."
                : "No funds created yet. Upload a batch Excel or create a fund manually."}
            </p>
          </div>
        </div>
      ) : (
        <div className="row g-3">
          {funds.map((fund) => (
            <div className="col-lg-4 col-sm-6" key={fund.id}>
              <div
                className="card shadow h-100"
                style={{ cursor: "pointer", transition: "background 0.15s" }}
                onClick={() => navigate(detailPath(fund.id))}
                onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "#243447")}
                onMouseLeave={(e) =>
                  ((e.currentTarget as HTMLElement).style.background = "var(--color-bg-surface)")
                }
              >
                <div className="card-body d-flex align-items-center justify-content-between">
                  <div className="d-flex align-items-center gap-3">
                    <div
                      className="d-flex align-items-center justify-content-center rounded-3"
                      style={{
                        width: "40px",
                        height: "40px",
                        background: "var(--color-brand-50)",
                        flexShrink: 0,
                      }}
                    >
                      {isShares ? (
                        <Coins size={18} style={{ color: "var(--color-brand-400)" }} />
                      ) : (
                        <Landmark size={18} style={{ color: "var(--color-brand-400)" }} />
                      )}
                    </div>
                    <div>
                      <h3
                        className="fw-bold mb-1"
                        style={{ fontSize: "14px", color: "var(--color-text-primary)" }}
                      >
                        {fund.fund_name}
                      </h3>
                      <span
                        className="badge rounded-pill"
                        style={{
                          fontSize: "10px",
                          fontWeight: 600,
                          background: fund.is_active
                            ? "var(--color-success-bg)"
                            : "var(--color-destructive-bg)",
                          color: fund.is_active
                            ? "var(--color-success)"
                            : "var(--color-destructive)",
                        }}
                      >
                        {fund.is_active ? "Active" : "Inactive"}
                      </span>
                      <div className="d-flex align-items-center gap-2 mt-2">
                        <span
                          className="badge rounded-pill border"
                          style={{
                            fontSize: "10px",
                            fontWeight: 500,
                            background: "transparent",
                            borderColor: "rgba(255,255,255,0.1)",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          {formatCurrencyCompact(fund.total_aum || 0)} Total
                        </span>
                        <span
                          className="badge rounded-pill border"
                          style={{
                            fontSize: "10px",
                            fontWeight: 500,
                            background: "transparent",
                            borderColor: "rgba(255,255,255,0.1)",
                            color: "var(--color-text-secondary)",
                          }}
                        >
                          {fund.investor_count || 0} Investors
                        </span>
                      </div>
                    </div>
                  </div>
                  <ChevronRight size={16} style={{ color: "var(--color-text-tertiary)" }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
