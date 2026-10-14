import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fundService } from "@/services/fundService";
import { ROUTES } from "@/lib/constants";
import { formatCurrencyCompact } from "@/lib/utils";
import type { CoreFund, ProductType } from "@/lib/types";
import { toast } from "sonner";
import { Plus, Landmark, Coins, ChevronRight } from "lucide-react";
import { FundForm, type FundFormValues } from "@/components/funds/FundForm";
import { ShareClassForm, type ShareClassFormValues } from "@/components/funds/ShareClassForm";
import { parseApiError } from "@/components/funds/formStyles";

// Currencies offered in the Add/Edit Share Class forms — Funds keep KES/USD;
// Shares (DPRP) deposits default to USD (converted to NGN at deployment), with
// NGN/KES also allowed. First entry is the create-form default.
const CURRENCIES_BY_PRODUCT: Record<ProductType, string[]> = {
  FUNDS: ["KES", "USD"],
  SHARES: ["USD", "NGN", "KES"],
};

interface FundListPageProps {
  /** Scopes this page to one product — same component, same layout/forms,
   * different data/wording/currency (Task 9). Defaults to FUNDS (unchanged
   * behavior for the existing /funds page). */
  product?: ProductType;
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

  // Create fund/share form state (Task 12: shared FundForm component)
  const [showCreateFund, setShowCreateFund] = useState(false);
  const [creatingFund, setCreatingFund] = useState(false);
  const [createFundErrors, setCreateFundErrors] = useState<Record<string, string>>({});

  // Add share class form state (Task 12: shared ShareClassForm component)
  const [showAddClass, setShowAddClass] = useState(false);
  const [addingClass, setAddingClass] = useState(false);
  const [addClassErrors, setAddClassErrors] = useState<Record<string, string>>({});

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

  const closeCreateFund = () => {
    setShowCreateFund(false);
    setCreateFundErrors({});
  };

  const handleCreateFund = async (values: FundFormValues) => {
    setCreatingFund(true);
    setCreateFundErrors({});
    try {
      await fundService.createFund(values.fund_name, values.fund_code, product, values.description || undefined);
      toast.success(`${Noun} "${values.fund_name}" created`);
      closeCreateFund();
      await loadFunds();
    } catch (err: unknown) {
      const e = parseApiError(err, `Failed to create ${noun}`);
      setCreateFundErrors(e.errors);
      toast.error(e.message);
    } finally {
      setCreatingFund(false);
    }
  };

  const closeAddClass = () => {
    setShowAddClass(false);
    setAddClassErrors({});
  };

  const handleAddClass = async (values: ShareClassFormValues) => {
    if (!values.fund_id) {
      toast.error("All fields are required");
      return;
    }
    setAddingClass(true);
    setAddClassErrors({});
    try {
      await fundService.createClass(
        values.fund_id,
        {
          class_name: values.class_name,
          class_code: values.class_code,
          currency: values.currency,
        },
        product
      );
      toast.success(`Share class "${values.class_name}" added`);
      closeAddClass();
      await loadFunds();
    } catch (err: unknown) {
      const e = parseApiError(err, "Failed to add share class");
      setAddClassErrors(e.errors);
      toast.error(e.message);
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
        <FundForm
          mode="create"
          product={product}
          submitting={creatingFund}
          errors={createFundErrors}
          onSubmit={handleCreateFund}
          onCancel={closeCreateFund}
        />
      )}

      {/* Inline Add Share Class Form */}
      {showAddClass && (
        <ShareClassForm
          mode="create"
          product={product}
          currencies={currencies}
          funds={funds}
          submitting={addingClass}
          errors={addClassErrors}
          onSubmit={handleAddClass}
          onCancel={closeAddClass}
        />
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
