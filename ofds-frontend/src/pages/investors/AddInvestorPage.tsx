import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { fundService } from "@/services/fundService";
import { investmentService } from "@/services/investmentService";
import { ROUTES } from "@/lib/constants";
import type { CoreFund, FundShareClass } from "@/lib/types";

interface DirectoryEntry {
  internal_client_code: string;
  investor_name: string | null;
  investor_email: string | null;
  investor_phone: string | null;
}

interface SuccessData {
  investorName: string;
  clientCode: string;
  fundName: string;
  classCode: string;
  currency: string;
  depositAmount: number;
  depositDate: string;
  batchId: number;
  batchName: string;
  batchCloseAt: string | null;
}

const today = () => new Date().toISOString().slice(0, 10);

function formatBatchCloseAt(iso: string): string {
  const d = new Date(iso);
  const datePart = d.toLocaleDateString("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Africa/Nairobi",
  });
  const timePart = d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Africa/Nairobi",
  });
  return `${datePart} at ${timePart} EAT`;
}

function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] ?? "") + (words[1]?.[0] ?? "")).toUpperCase() || "?";
}

function Dot() {
  return <span style={{ width: "2px", height: "2px", background: "rgb(71, 85, 105)", borderRadius: "50%", flexShrink: 0 }} />;
}

const labelStyle: React.CSSProperties = {
  fontSize: "11px",
  fontWeight: 500,
  color: "rgb(148, 163, 184)",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const fieldWrapStyle: React.CSSProperties = { display: "flex", flexDirection: "column", gap: "6px" };

const inputBase: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "8px",
  background: "rgba(0, 0, 0, 0.25)",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  color: "rgb(255, 255, 255)",
  fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
  fontSize: "13px",
  outline: "none",
  transition: "0.15s",
};

const monoInput: React.CSSProperties = {
  ...inputBase,
  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
};

const selectChevron =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%2394A3B8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\") right 12px center / 12px auto no-repeat rgba(0, 0, 0, 0.25)";

const selectBase: React.CSSProperties = {
  width: "100%",
  padding: "10px 32px 10px 12px",
  borderRadius: "8px",
  background: selectChevron,
  border: "1px solid rgba(255, 255, 255, 0.1)",
  color: "rgb(255, 255, 255)",
  fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
  fontSize: "13px",
  outline: "none",
  transition: "0.15s",
  cursor: "pointer",
  appearance: "none",
};

function SectionHeader({ step, title }: { step: number; title: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "7px",
          fontSize: "10px",
          fontWeight: 600,
          color: "rgb(71, 85, 105)",
          textTransform: "uppercase",
          letterSpacing: "0.1em",
        }}
      >
        <span
          style={{
            width: "18px",
            height: "18px",
            borderRadius: "50%",
            background: "rgba(26, 69, 255, 0.15)",
            border: "1px solid rgba(59, 130, 246, 0.35)",
            color: "rgb(96, 165, 250)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: "10px",
            fontWeight: 600,
            fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
            flexShrink: 0,
          }}
        >
          {step}
        </span>
        {title}
      </div>
    </div>
  );
}

export default function AddInvestorPage() {
  const navigate = useNavigate();

  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [funds, setFunds] = useState<CoreFund[]>([]);
  const [fundsLoading, setFundsLoading] = useState(true);
  const [classes, setClasses] = useState<FundShareClass[]>([]);
  const [classesLoading, setClassesLoading] = useState(false);

  const [clientCode, setClientCode] = useState("");
  const [investorName, setInvestorName] = useState("");
  const [investorEmail, setInvestorEmail] = useState("");
  const [investorPhone, setInvestorPhone] = useState("");
  const [fundId, setFundId] = useState("");
  const [classId, setClassId] = useState("");
  const [depositAmount, setDepositAmount] = useState("");
  const [depositDate, setDepositDate] = useState(today());
  const [submitting, setSubmitting] = useState(false);
  const [successData, setSuccessData] = useState<SuccessData | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [fundList, dirRes] = await Promise.all([
          fundService.getAll(),
          investmentService.getInvestorDirectory(),
        ]);
        setFunds(fundList.filter((f) => f.is_active));
        setDirectory(((dirRes.data as DirectoryEntry[]) || []));
      } catch {
        toast.error("Failed to load funds");
      } finally {
        setFundsLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!fundId) {
      setClasses([]);
      setClassId("");
      return;
    }
    setClassesLoading(true);
    setClassId("");
    fundService
      .getClasses(Number(fundId))
      .then((res) => setClasses(res.filter((c) => c.is_active !== false)))
      .catch(() => toast.error("Failed to load share classes"))
      .finally(() => setClassesLoading(false));
  }, [fundId]);

  const selectedClass = useMemo(
    () => classes.find((c) => String(c.id) === classId) || null,
    [classes, classId]
  );

  const existingInvestor = useMemo(() => {
    const code = clientCode.trim().toLowerCase();
    if (!code) return null;
    return directory.find((d) => String(d.internal_client_code || "").trim().toLowerCase() === code) || null;
  }, [clientCode, directory]);

  useEffect(() => {
    if (existingInvestor) {
      setInvestorName(existingInvestor.investor_name || "");
      setInvestorEmail(existingInvestor.investor_email || "");
      setInvestorPhone(existingInvestor.investor_phone || "");
    }
  }, [existingInvestor]);

  const depositAmountValid = depositAmount.trim() !== "" && Number(depositAmount) > 0;

  const isValid =
    clientCode.trim() !== "" &&
    (existingInvestor || (investorName.trim() !== "" && investorEmail.trim() !== "")) &&
    fundId !== "" &&
    classId !== "" &&
    depositAmountValid &&
    depositDate !== "" &&
    !submitting;

  const handleSubmit = async () => {
    if (!isValid) return;
    setSubmitting(true);
    try {
      const payload = {
        internal_client_code: clientCode.trim().toUpperCase(),
        fund_id: Number(fundId),
        share_class_id: Number(classId),
        deposit_amount: Number(depositAmount),
        deposit_date: depositDate,
      };

      const res = existingInvestor
        ? await investmentService.addExistingDeposit(payload)
        : await investmentService.createNewInvestor({
            ...payload,
            investor_name: investorName.trim(),
            investor_email: investorEmail.trim(),
            investor_phone: investorPhone.trim() || undefined,
          });

      if (res.status === 201 || res.status === 200) {
        toast.success(existingInvestor ? "Deposit added" : "Investor created");
        const d = res.data as {
          batch_id: number;
          batch_name: string;
          fund_name: string;
          class_code: string;
          currency: string;
          deposit_amount: number;
          batch_close_at?: string | null;
        };
        setSuccessData({
          investorName: existingInvestor ? existingInvestor.investor_name || investorName.trim() : investorName.trim(),
          clientCode: payload.internal_client_code,
          fundName: d.fund_name,
          classCode: d.class_code,
          currency: d.currency,
          depositAmount: d.deposit_amount,
          depositDate: payload.deposit_date,
          batchId: d.batch_id,
          batchName: d.batch_name,
          batchCloseAt: d.batch_close_at ?? null,
        });
      } else {
        toast.error(res.message || "Failed to add investor");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to add investor");
    } finally {
      setSubmitting(false);
    }
  };

  const isKES = selectedClass?.currency === "KES";
  const currencyVar = isKES ? "var(--color-kes)" : "var(--color-usd)";

  const handleUseDifferentCode = () => {
    setClientCode("");
    setInvestorName("");
    setInvestorEmail("");
    setInvestorPhone("");
  };

  const handleAddAnother = () => {
    setSuccessData(null);
    setClientCode("");
    setInvestorName("");
    setInvestorEmail("");
    setInvestorPhone("");
    setFundId("");
    setClassId("");
    setDepositAmount("");
    setDepositDate(today());
  };

  if (successData) {
    const successIsKES = successData.currency === "KES";
    const successCurrencyVar = successIsKES ? "var(--color-kes)" : "var(--color-usd)";
    return (
      <div
        style={{
          position: "relative",
          zIndex: 1,
          padding: "24px 32px 48px",
          maxWidth: "800px",
          margin: "0 auto",
          fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
          color: "rgb(255, 255, 255)",
        }}
      >
        <div style={{ textAlign: "center" }}>
          <div
            style={{
              width: "64px",
              height: "64px",
              borderRadius: "50%",
              background: "rgba(16, 185, 129, 0.12)",
              border: "1px solid rgba(16, 185, 129, 0.35)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 20px",
              boxShadow: "0 0 30px rgba(16, 185, 129, 0.15)",
            }}
          >
            <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
              <path d="M9 16l5 5 9-10" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>

          <div style={{ fontSize: "22px", fontWeight: 700, color: "rgb(255, 255, 255)", letterSpacing: "-0.02em", marginBottom: "8px" }}>
            Investor added
          </div>
          <div style={{ fontSize: "13px", color: "rgb(148, 163, 184)", lineHeight: 1.6, margin: "0 auto 28px", maxWidth: "420px" }}>
            {successData.investorName} has been assigned to the open batch. No further action is required until the batch closes.
          </div>

          <div
            style={{
              background: "rgba(16, 24, 45, 0.72)",
              backdropFilter: "blur(20px) saturate(150%)",
              WebkitBackdropFilter: "blur(20px) saturate(150%)",
              border: "1px solid rgba(255, 255, 255, 0.07)",
              borderRadius: "16px",
              boxShadow: "0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05)",
              overflow: "hidden",
              maxWidth: "480px",
              margin: "0 auto 24px",
              textAlign: "left",
            }}
          >
            <div style={{ padding: "14px 18px", borderBottom: "1px solid rgba(255, 255, 255, 0.07)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: "10px", fontWeight: 600, color: "rgb(71, 85, 105)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                Investor Details
              </span>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  padding: "3px 10px",
                  borderRadius: "6px",
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  fontSize: "11px",
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                  background: successIsKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
                  color: successCurrencyVar,
                  border: `1px solid ${successIsKES ? "var(--color-kes-border)" : "var(--color-usd-border)"}`,
                }}
              >
                {successData.currency}
              </span>
            </div>

            <div style={{ padding: "4px 0" }}>
              {[
                { label: "Name", value: successData.investorName },
                { label: "Fund", value: successData.fundName },
                { label: "Share Class", value: successData.classCode, mono: true },
                { label: "Client Code", value: successData.clientCode, mono: true },
              ].map((row) => (
                <div
                  key={row.label}
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 18px", borderBottom: "1px solid rgba(255,255,255,0.04)" }}
                >
                  <span style={{ fontSize: "11px", color: "rgb(71, 85, 105)" }}>{row.label}</span>
                  <span style={{ fontSize: "12px", color: "rgb(255, 255, 255)", fontFamily: row.mono ? "var(--font-mono, 'JetBrains Mono', monospace)" : undefined }}>
                    {row.value}
                  </span>
                </div>
              ))}

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "11px 18px",
                  borderBottom: "1px solid rgba(255,255,255,0.04)",
                  background: "rgba(255,255,255,0.016)",
                }}
              >
                <span style={{ fontSize: "11px", color: "rgb(71, 85, 105)" }}>Deposit amount</span>
                <span style={{ fontSize: "13px", fontWeight: 600, color: successCurrencyVar, fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                  {successData.currency} {successData.depositAmount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "9px 18px" }}>
                <span style={{ fontSize: "11px", color: "rgb(71, 85, 105)" }}>Deposit date</span>
                <span style={{ fontSize: "12px", color: "rgb(255, 255, 255)", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)" }}>
                  {new Date(successData.depositDate).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}
                </span>
              </div>
            </div>

            <div style={{ margin: "0 14px 14px", padding: "12px 14px", background: "rgba(26, 69, 255, 0.06)", border: "1px solid rgba(59, 130, 246, 0.2)", borderRadius: "10px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "9px", fontWeight: 600, color: "rgb(71, 85, 105)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "6px" }}>
                <svg width="11" height="11" viewBox="0 0 12 12" fill="none">
                  <rect x="1.5" y="2.5" width="9" height="7" rx="1" stroke="currentColor" strokeWidth="1.2" />
                  <line x1="1.5" y1="5" x2="10.5" y2="5" stroke="currentColor" strokeWidth="1.2" />
                  <line x1="4" y1="1.5" x2="4" y2="3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  <line x1="8" y1="1.5" x2="8" y2="3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                </svg>
                Auto-assigned to batch
              </div>
              <div style={{ fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)", fontSize: "13px", fontWeight: 600, color: "rgb(255, 255, 255)", marginBottom: "6px" }}>
                {successData.batchName}
              </div>
              <div style={{ fontSize: "11px", color: "rgb(148, 163, 184)", lineHeight: 1.55 }}>
                {successData.batchCloseAt ? (
                  <>
                    Batch closes <strong style={{ color: "rgb(255, 255, 255)" }}>{formatBatchCloseAt(successData.batchCloseAt)}</strong>. Shares will be purchased at that week's deployment NAV. Deposit statement will be generated after deployment.
                  </>
                ) : (
                  <>Shares will be purchased at that week's deployment NAV. Deposit statement will be generated after deployment.</>
                )}
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
            <button
              onClick={() => navigate(ROUTES.BATCH_DETAIL(successData.batchId))}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "9px 16px",
                borderRadius: "8px",
                background: "transparent",
                border: "1px solid rgba(255,255,255,0.1)",
                color: "rgb(148, 163, 184)",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
                transition: "0.15s",
              }}
            >
              View batch
            </button>
            <button
              onClick={handleAddAnother}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                padding: "9px 16px",
                borderRadius: "8px",
                background: "rgb(26, 69, 255)",
                color: "rgb(255, 255, 255)",
                border: "none",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
                boxShadow: "0 0 16px rgba(26,69,255,0.3)",
                transition: "0.15s",
              }}
            >
              <svg width="12" height="12" viewBox="0 0 13 13" fill="none">
                <path d="M6.5 2v9M2 6.5h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Add another
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        position: "relative",
        zIndex: 1,
        padding: "24px 32px 48px",
        maxWidth: "800px",
        margin: "0 auto",
        fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
        color: "rgb(255, 255, 255)",
      }}
    >
      {/* Breadcrumb */}
      <div style={{ display: "flex", alignItems: "center", gap: "7px", fontSize: "11px", color: "rgb(71, 85, 105)", marginBottom: "14px" }}>
        <a
          href={ROUTES.INVESTORS}
          onClick={(e) => {
            e.preventDefault();
            navigate(ROUTES.INVESTORS);
          }}
          style={{ color: "rgb(148, 163, 184)", textDecoration: "none", transition: "color 0.15s" }}
        >
          Investors
        </a>
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ opacity: 0.5 }}>
          <path d="M4 2l3 3-3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span>Add investor</span>
      </div>

      {/* Header */}
      <div style={{ marginBottom: "22px" }}>
        <h1 style={{ fontSize: "22px", fontWeight: 700, color: "rgb(255, 255, 255)", letterSpacing: "-0.02em", margin: 0 }}>
          Add investor
        </h1>
        <div style={{ fontSize: "12px", color: "rgb(148, 163, 184)", marginTop: "4px" }}>
          Register a new client or add a deposit for an existing investor.
        </div>
      </div>

      {/* Card */}
      <div
        style={{
          background: "rgba(16, 24, 45, 0.72)",
          backdropFilter: "blur(20px) saturate(150%)",
          WebkitBackdropFilter: "blur(20px) saturate(150%)",
          border: "1px solid rgba(255, 255, 255, 0.07)",
          borderRadius: "16px",
          boxShadow: "rgba(0, 0, 0, 0.3) 0px 8px 32px, rgba(255, 255, 255, 0.05) 0px 1px 0px inset",
          overflow: "hidden",
        }}
      >
        {/* Section 1: Investor identity */}
        <div style={{ padding: "18px 22px", borderBottom: "1px solid rgba(255, 255, 255, 0.07)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "7px",
                fontSize: "10px",
                fontWeight: 600,
                color: "rgb(71, 85, 105)",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              <span
                style={{
                  width: "18px",
                  height: "18px",
                  borderRadius: "50%",
                  background: existingInvestor ? "rgba(16, 185, 129, 0.12)" : "rgba(26, 69, 255, 0.15)",
                  border: existingInvestor ? "1px solid rgba(16, 185, 129, 0.4)" : "1px solid rgba(59, 130, 246, 0.35)",
                  color: existingInvestor ? "rgb(16, 185, 129)" : "rgb(96, 165, 250)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "10px",
                  fontWeight: 600,
                  fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                  flexShrink: 0,
                }}
              >
                {existingInvestor ? "✓" : "1"}
              </span>
              Investor identity
            </div>
            {existingInvestor && (
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "3px 10px",
                  borderRadius: "100px",
                  background: "rgba(16, 185, 129, 0.12)",
                  border: "1px solid rgba(16, 185, 129, 0.3)",
                  fontSize: "10px",
                  fontWeight: 600,
                  color: "rgb(16, 185, 129)",
                  letterSpacing: "0.02em",
                }}
              >
                <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
                  <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M4 6l1.5 1.5L8 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Existing investor
              </span>
            )}
          </div>

          {existingInvestor ? (
            <>
              <div
                style={{
                  padding: "12px 14px",
                  background: "rgba(16, 185, 129, 0.06)",
                  border: "1px solid rgba(16, 185, 129, 0.25)",
                  borderRadius: "10px",
                  display: "flex",
                  gap: "10px",
                  alignItems: "flex-start",
                  marginBottom: "14px",
                }}
              >
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" style={{ color: "rgb(16, 185, 129)", flexShrink: 0, marginTop: "1px" }}>
                  <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" />
                  <path d="M5 8l2 2 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <div style={{ fontSize: "12px", color: "rgba(167, 243, 208, 0.95)", lineHeight: 1.55 }}>
                  <strong style={{ color: "rgb(110, 231, 183)", fontWeight: 600 }}>
                    Client code {existingInvestor.internal_client_code} found.
                  </strong>{" "}
                  Details have been auto-filled from their existing record. Only deposit information is required to add a new contribution.
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "14px",
                  padding: "12px 14px",
                  background: "rgba(0, 0, 0, 0.2)",
                  border: "1px solid rgba(255, 255, 255, 0.07)",
                  borderRadius: "10px",
                }}
              >
                <div
                  style={{
                    width: "38px",
                    height: "38px",
                    borderRadius: "50%",
                    background: "linear-gradient(135deg, rgba(16, 185, 129, 0.3), rgba(16, 185, 129, 0.1))",
                    border: "1px solid rgba(16, 185, 129, 0.3)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "13px",
                    fontWeight: 600,
                    color: "rgb(110, 231, 183)",
                    flexShrink: 0,
                  }}
                >
                  {initialsOf(existingInvestor.investor_name || "")}
                </div>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: "13px", fontWeight: 600, color: "rgb(255, 255, 255)", marginBottom: "2px" }}>
                    {existingInvestor.investor_name}
                  </div>
                  <div style={{ fontSize: "11px", color: "rgb(148, 163, 184)", display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
                    <span style={{ fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)", fontSize: "10px" }}>
                      {existingInvestor.internal_client_code}
                    </span>
                    {existingInvestor.investor_email && (
                      <>
                        <Dot />
                        <span>{existingInvestor.investor_email}</span>
                      </>
                    )}
                    {existingInvestor.investor_phone && (
                      <>
                        <Dot />
                        <span>{existingInvestor.investor_phone}</span>
                      </>
                    )}
                  </div>
                </div>
                <button
                  onClick={handleUseDifferentCode}
                  style={{
                    fontSize: "10px",
                    color: "rgb(59, 130, 246)",
                    background: "transparent",
                    border: "none",
                    padding: "4px 8px",
                    borderRadius: "6px",
                    cursor: "pointer",
                    fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                    transition: "background 0.15s",
                    flexShrink: 0,
                  }}
                >
                  Use different code
                </button>
              </div>
            </>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
              <div style={fieldWrapStyle}>
                <label style={labelStyle}>
                  Client Code <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
                </label>
                <input
                  placeholder="e.g. INV-001"
                  autoComplete="off"
                  value={clientCode}
                  onChange={(e) => setClientCode(e.target.value)}
                  style={{ ...monoInput, textTransform: "uppercase", letterSpacing: "0.04em" }}
                />
              </div>
              <div style={fieldWrapStyle}>
                <label style={labelStyle}>
                  Investor Name <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
                </label>
                <input
                  placeholder="Full name"
                  autoComplete="off"
                  value={investorName}
                  onChange={(e) => setInvestorName(e.target.value)}
                  style={inputBase}
                />
              </div>
              <div style={fieldWrapStyle}>
                <label style={labelStyle}>
                  Email <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
                </label>
                <input
                  placeholder="investor@example.com"
                  autoComplete="off"
                  type="email"
                  value={investorEmail}
                  onChange={(e) => setInvestorEmail(e.target.value)}
                  style={inputBase}
                />
              </div>
              <div style={fieldWrapStyle}>
                <label style={labelStyle}>
                  Phone <span style={{ fontSize: "10px", color: "rgb(71, 85, 105)", fontWeight: 400 }}>Optional</span>
                </label>
                <input
                  placeholder="+254 7XX XXX XXX"
                  autoComplete="off"
                  type="tel"
                  value={investorPhone}
                  onChange={(e) => setInvestorPhone(e.target.value)}
                  style={inputBase}
                />
              </div>
            </div>
          )}
        </div>

        {/* Section 2: Fund & class */}
        <div style={{ padding: "18px 22px", borderBottom: "1px solid rgba(255, 255, 255, 0.07)" }}>
          <SectionHeader step={2} title="Fund & class" />
          <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr", gap: "14px" }}>
            <div style={fieldWrapStyle}>
              <label style={labelStyle}>
                Fund <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
              </label>
              <select value={fundId} onChange={(e) => setFundId(e.target.value)} disabled={fundsLoading} style={selectBase}>
                <option value="">{fundsLoading ? "Loading funds…" : "Select a fund…"}</option>
                {funds.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.fund_name}{f.fund_code ? ` (${f.fund_code})` : ""}
                  </option>
                ))}
              </select>
            </div>
            <div style={fieldWrapStyle}>
              <label style={labelStyle}>
                Share Class <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
              </label>
              <select
                value={classId}
                onChange={(e) => setClassId(e.target.value)}
                disabled={!fundId || classesLoading}
                style={{ ...selectBase, cursor: !fundId || classesLoading ? "not-allowed" : "pointer", opacity: !fundId || classesLoading ? 0.5 : 1 }}
              >
                <option value="">
                  {!fundId ? "Select a fund first" : classesLoading ? "Loading…" : "Select a class…"}
                </option>
                {classes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.class_code} — {c.class_name} ({c.currency})
                  </option>
                ))}
              </select>
            </div>
            <div style={fieldWrapStyle}>
              <label style={labelStyle}>
                Currency <span style={{ fontSize: "10px", color: "rgb(71, 85, 105)", fontWeight: 400 }}>Auto</span>
              </label>
              {selectedClass ? (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "10px 12px",
                    borderRadius: "8px",
                    background: "rgba(0, 0, 0, 0.2)",
                    border: "1px solid rgba(255, 255, 255, 0.1)",
                    fontSize: "12px",
                    color: "var(--color-text-secondary)",
                    minHeight: "41px",
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "3px 10px",
                      borderRadius: "6px",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      fontSize: "11px",
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                      background: isKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
                      color: currencyVar,
                      border: `1px solid ${isKES ? "var(--color-kes-border)" : "var(--color-usd-border)"}`,
                    }}
                  >
                    {selectedClass.currency}
                  </span>
                  <span>set by class</span>
                </div>
              ) : (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "10px 12px",
                    borderRadius: "8px",
                    background: "rgba(0, 0, 0, 0.2)",
                    border: "1px dashed rgba(255, 255, 255, 0.1)",
                    fontSize: "12px",
                    color: "rgb(71, 85, 105)",
                    minHeight: "41px",
                  }}
                >
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      padding: "3px 10px",
                      borderRadius: "6px",
                      fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                      fontSize: "11px",
                      fontWeight: 600,
                      letterSpacing: "0.04em",
                      background: "rgba(255, 255, 255, 0.04)",
                      color: "rgb(71, 85, 105)",
                      border: "1px solid rgba(255, 255, 255, 0.07)",
                    }}
                  >
                    —
                  </span>
                  <span>set by class</span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Section 3: Deposit */}
        <div style={{ padding: "18px 22px" }}>
          <SectionHeader step={3} title="Deposit" />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
            <div style={fieldWrapStyle}>
              <label style={labelStyle}>
                Deposit Amount <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
              </label>
              <div style={{ position: "relative" }}>
                <span
                  style={{
                    position: "absolute",
                    left: "12px",
                    top: "50%",
                    transform: "translateY(-50%)",
                    fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)",
                    fontSize: "12px",
                    fontWeight: 600,
                    color: selectedClass ? currencyVar : "rgb(71, 85, 105)",
                    pointerEvents: "none",
                    paddingRight: "10px",
                    borderRight: "1px solid rgba(255, 255, 255, 0.1)",
                  }}
                >
                  {selectedClass ? selectedClass.currency : "—"}
                </span>
                <input
                  placeholder="0.00"
                  disabled={!selectedClass}
                  value={depositAmount}
                  onChange={(e) => setDepositAmount(e.target.value)}
                  style={{
                    ...monoInput,
                    padding: "10px 12px 10px 58px",
                    opacity: selectedClass ? 1 : 0.5,
                    cursor: selectedClass ? "text" : "not-allowed",
                  }}
                />
              </div>
              <div style={{ fontSize: "10px", color: "rgb(71, 85, 105)" }}>
                Currency prefix updates once a share class is selected.
              </div>
            </div>
            <div style={fieldWrapStyle}>
              <label style={labelStyle}>
                Deposit Date <span style={{ color: "rgb(239, 68, 68)", marginLeft: "3px" }}>*</span>
              </label>
              <input
                type="date"
                value={depositDate}
                onChange={(e) => setDepositDate(e.target.value)}
                style={{ ...inputBase, colorScheme: "dark" }}
              />
              <div style={{ fontSize: "10px", color: "rgb(71, 85, 105)" }}>Actual date client made the deposit.</div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "16px 22px",
            background: "rgba(0, 0, 0, 0.15)",
            borderTop: "1px solid rgba(255, 255, 255, 0.07)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
          }}
        >
          <div style={{ fontSize: "10px", color: "rgb(71, 85, 105)", fontFamily: "var(--font-mono, 'JetBrains Mono', monospace)", letterSpacing: "0.04em" }}>
            {existingInvestor ? "Adding new contribution for existing investor" : "All fields marked * are required"}
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={() => navigate(ROUTES.INVESTORS)}
              style={{
                background: "transparent",
                border: "none",
                color: "rgb(148, 163, 184)",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: "pointer",
                padding: "9px 16px",
                borderRadius: "8px",
                transition: "color 0.15s",
              }}
            >
              Cancel
            </button>
            <button
              disabled={!isValid}
              onClick={handleSubmit}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "7px",
                background: isValid ? "rgb(26, 69, 255)" : "rgba(255, 255, 255, 0.06)",
                color: isValid ? "rgb(255, 255, 255)" : "rgb(71, 85, 105)",
                border: "none",
                fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
                fontSize: "12px",
                fontWeight: 500,
                cursor: isValid ? "pointer" : "not-allowed",
                padding: "9px 16px",
                borderRadius: "8px",
                boxShadow: isValid ? "rgba(26, 69, 255, 0.3) 0px 0px 16px" : "none",
                transition: "0.15s",
              }}
            >
              {submitting ? "Adding…" : existingInvestor ? "Add deposit" : "Add investor"}
              <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
                <path d="M3 7h8M8 4l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
