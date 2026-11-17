import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowDownCircle, X, Check, Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { withdrawalService } from "@/services/withdrawalService";
import type { RedemptionHolding } from "@/lib/types";

export interface RedemptionPrefill {
  withdrawalId?: number;
  clientCode?: string;
  fundId?: number;
  amount?: number;
}

interface RedemptionModalProps {
  open: boolean;
  onClose: () => void;
  onDone: () => void;
  prefill?: RedemptionPrefill;
}

const fmt = (n: number, dp = 2) => n.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });

/**
 * Record a unit redemption exactly as the transfer agent's contract note books
 * it (e.g. "101.423 shares at NAV 37.96 = USD 3,850.00, trade date
 * 20/10/2026"). Executing it reduces the client's shares (oldest holding
 * first), so our records stay in line with the transfer agent's.
 */
export function RedemptionModal({ open, onClose, onDone, prefill }: RedemptionModalProps) {
  const [clientCode, setClientCode] = useState("");
  const [investorName, setInvestorName] = useState<string | null>(null);
  const [holdings, setHoldings] = useState<RedemptionHolding[]>([]);
  const [holdingKey, setHoldingKey] = useState("");
  const [loadingHoldings, setLoadingHoldings] = useState(false);
  const [shares, setShares] = useState("");
  const [nav, setNav] = useState("");
  const [gross, setGross] = useState("");
  const [exitFee, setExitFee] = useState("0");
  const [tradeDate, setTradeDate] = useState("");
  const [settlementDate, setSettlementDate] = useState("");
  const [taReference, setTaReference] = useState("");
  const [saving, setSaving] = useState(false);

  const loadHoldings = async (code: string, preferFundId?: number) => {
    if (!code.trim()) return;
    setLoadingHoldings(true);
    try {
      const res = await withdrawalService.getRedemptionHoldings(code.trim());
      setInvestorName(res.investor_name);
      setHoldings(res.holdings);
      const pick = res.holdings.find((h) => h.fund_id === preferFundId) ?? res.holdings[0];
      setHoldingKey(pick ? `${pick.fund_id}:${pick.share_class_id}` : "");
      if (!res.holdings.length) toast.error("This client has no active fund holdings to redeem");
    } catch {
      toast.error("Could not load the client's holdings");
    } finally {
      setLoadingHoldings(false);
    }
  };

  // Fresh form every time it opens; a prefill (executing a pending request) loads its client straight away.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open) return;
    setClientCode(prefill?.clientCode ?? "");
    setInvestorName(null);
    setHoldings([]);
    setHoldingKey("");
    setShares("");
    setNav("");
    setGross(prefill?.amount != null ? String(prefill.amount) : "");
    setExitFee("0");
    setTradeDate("");
    setSettlementDate("");
    setTaReference("");
    if (prefill?.clientCode) loadHoldings(prefill.clientCode, prefill.fundId);
  }, [open]);

  if (!open) return null;

  const holding = holdings.find((h) => `${h.fund_id}:${h.share_class_id}` === holdingKey);
  const sharesNum = parseFloat(shares) || 0;
  const navNum = parseFloat(nav) || 0;
  const computedGross = sharesNum * navNum;
  const grossNum = gross.trim() === "" ? computedGross : parseFloat(gross) || 0;
  const feeNum = parseFloat(exitFee) || 0;
  const remaining = holding ? holding.shares_available - sharesNum : 0;
  const grossMismatch = gross.trim() !== "" && computedGross > 0 && Math.abs(grossNum - computedGross) > Math.max(1, computedGross * 0.001);

  const errors: string[] = [];
  if (!holding) errors.push("Choose the holding");
  if (sharesNum <= 0) errors.push("Enter the shares redeemed");
  if (navNum <= 0) errors.push("Enter the NAV");
  if (!tradeDate) errors.push("Enter the trade date");
  if (holding && sharesNum > holding.shares_available + 1e-9) errors.push("More shares than the client holds");
  if (grossMismatch) errors.push("Gross amount doesn't match shares × NAV");
  if (feeNum < 0 || feeNum > grossNum) errors.push("Exit fee must be between 0 and the gross amount");

  const submit = async () => {
    if (errors.length || !holding) return;
    setSaving(true);
    try {
      const res = await withdrawalService.recordRedemption({
        client_code: clientCode.trim(),
        fund_id: holding.fund_id,
        share_class_id: holding.share_class_id,
        shares: sharesNum,
        nav: navNum,
        trade_date: tradeDate,
        ...(gross.trim() !== "" ? { gross_amount: grossNum } : {}),
        exit_fee: feeNum,
        ...(settlementDate ? { settlement_date: settlementDate } : {}),
        ...(taReference.trim() ? { ta_reference: taReference.trim() } : {}),
        ...(prefill?.withdrawalId ? { withdrawal_id: prefill.withdrawalId } : {}),
      });
      toast.success(res.message || "Redemption recorded");
      onDone();
      onClose();
    } catch (err: unknown) {
      toast.error((err as { response?: { data?: { message?: string } } })?.response?.data?.message || "Could not record the redemption");
    } finally {
      setSaving(false);
    }
  };

  const label: React.CSSProperties = { display: "block", fontSize: "11px", color: "#94A3B8", marginBottom: "6px", fontWeight: 600, letterSpacing: "0.04em" };
  const input: React.CSSProperties = {
    width: "100%", background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "8px",
    color: "#fff", padding: "10px 12px", fontSize: "13px", outline: "none", fontFamily: "var(--font-mono)", colorScheme: "dark",
  };
  const row = (n: number): React.CSSProperties => ({ display: "grid", gridTemplateColumns: `repeat(${n}, 1fr)`, gap: "12px" });

  return createPortal(
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999, padding: "20px" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: "#0B1228", borderRadius: "16px", width: "100%", maxWidth: "640px", border: "1px solid rgba(255,255,255,0.08)", boxShadow: "0 24px 48px rgba(0,0,0,0.4)", color: "#fff", fontFamily: "var(--font-sans)", maxHeight: "90vh", overflow: "hidden auto" }}
      >
        <div style={{ padding: "20px 24px", borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ width: 32, height: 32, background: "rgba(239,68,68,0.15)", color: "#F87171", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <ArrowDownCircle size={16} />
            </div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>
              {prefill?.withdrawalId ? "Execute withdrawal as redemption" : "Record redemption"}
            </h3>
          </div>
          <button onClick={onClose} disabled={saving} style={{ background: "transparent", border: "none", color: "#94A3B8", cursor: "pointer", padding: 4 }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: "16px" }}>
          <p style={{ margin: 0, fontSize: "12px", color: "rgba(255,255,255,0.6)", lineHeight: 1.5 }}>
            Enter the figures from the transfer agent's contract note. The client's shares are reduced (oldest holding
            first), so their value from now on is remaining shares × NAV — the same as the transfer agent.
          </p>

          <div>
            <label style={label}>CLIENT CODE</label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                aria-label="Client code"
                style={input}
                value={clientCode}
                onChange={(e) => setClientCode(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && loadHoldings(clientCode)}
                disabled={saving || Boolean(prefill?.withdrawalId)}
                placeholder="e.g. 145591"
              />
              <button
                type="button"
                onClick={() => loadHoldings(clientCode)}
                disabled={loadingHoldings || !clientCode.trim() || Boolean(prefill?.withdrawalId)}
                style={{ whiteSpace: "nowrap", padding: "0 14px", borderRadius: 8, border: "1px solid rgba(59,111,212,0.5)", background: "rgba(59,111,212,0.15)", color: "#93B4F5", fontSize: 12, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}
              >
                {loadingHoldings ? <Loader2 size={13} className="spin" /> : <Search size={13} />} Find
              </button>
            </div>
            {investorName && <div style={{ fontSize: 12, color: "#CBD5E1", marginTop: 6 }}>{investorName}</div>}
          </div>

          {holdings.length > 0 && (
            <div>
              <label style={label}>HOLDING</label>
              <select aria-label="Holding" style={input} value={holdingKey} onChange={(e) => setHoldingKey(e.target.value)} disabled={saving}>
                {holdings.map((h) => (
                  <option key={`${h.fund_id}:${h.share_class_id}`} value={`${h.fund_id}:${h.share_class_id}`}>
                    {h.fund_name} — {h.class_code ?? "class"} ({fmt(h.shares_available, 3)} shares available)
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={row(3)}>
            <div>
              <label style={label}>SHARES REDEEMED</label>
              <input aria-label="Shares redeemed" type="number" step="0.001" min="0" style={input} value={shares} onChange={(e) => setShares(e.target.value)} disabled={saving} placeholder="101.423" />
            </div>
            <div>
              <label style={label}>NAV PER SHARE</label>
              <input aria-label="NAV per share" type="number" step="0.0001" min="0" style={input} value={nav} onChange={(e) => setNav(e.target.value)} disabled={saving} placeholder="37.96" />
            </div>
            <div>
              <label style={label}>GROSS AMOUNT</label>
              <input aria-label="Gross amount" type="number" step="0.01" min="0" style={input} value={gross} onChange={(e) => setGross(e.target.value)} disabled={saving} placeholder={computedGross ? fmt(computedGross) : "from contract note"} />
            </div>
          </div>

          <div style={row(3)}>
            <div>
              <label style={label}>TRADE DATE</label>
              <input aria-label="Trade date" type="date" style={input} value={tradeDate} onChange={(e) => setTradeDate(e.target.value)} disabled={saving} />
            </div>
            <div>
              <label style={label}>SETTLEMENT DATE</label>
              <input aria-label="Settlement date" type="date" style={input} value={settlementDate} onChange={(e) => setSettlementDate(e.target.value)} disabled={saving} />
            </div>
            <div>
              <label style={label}>EXIT FEE</label>
              <input aria-label="Exit fee" type="number" step="0.01" min="0" style={input} value={exitFee} onChange={(e) => setExitFee(e.target.value)} disabled={saving} />
            </div>
          </div>

          <div>
            <label style={label}>TRANSFER AGENT REFERENCE (OPTIONAL)</label>
            <input aria-label="Transfer agent reference" style={input} value={taReference} onChange={(e) => setTaReference(e.target.value)} disabled={saving} placeholder="e.g. 6035089" />
          </div>

          <div style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 10, padding: 12, display: "flex", flexDirection: "column", gap: 6, fontSize: 12, fontFamily: "var(--font-mono)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#CBD5E1" }}><span>Shares × NAV</span><span>{fmt(computedGross)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#CBD5E1" }}><span>Gross amount</span><span>{fmt(grossNum)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#FBBF24" }}><span>Exit fee</span><span>-{fmt(feeNum)}</span></div>
            <div style={{ display: "flex", justifyContent: "space-between", color: "#86EFAC", fontWeight: 700, borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 6 }}>
              <span>Net paid to client</span><span>{fmt(Math.max(0, grossNum - feeNum))}</span>
            </div>
            {holding && (
              <div style={{ display: "flex", justifyContent: "space-between", color: remaining < -1e-9 ? "#F87171" : "#94A3B8" }}>
                <span>Shares remaining</span><span>{fmt(remaining, 3)}</span>
              </div>
            )}
          </div>

          {errors.length > 0 && (sharesNum > 0 || navNum > 0 || tradeDate) && (
            <div style={{ fontSize: 12, color: "#F87171" }}>{errors.join(" · ")}</div>
          )}
        </div>

        <div style={{ padding: "16px 24px", background: "rgba(0,0,0,0.2)", borderTop: "1px solid rgba(255,255,255,0.06)", display: "flex", justifyContent: "flex-end", gap: 12 }}>
          <button onClick={onClose} disabled={saving} style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.1)", color: "#fff", padding: "8px 16px", borderRadius: 6, fontSize: 13 }}>
            Cancel
          </button>
          <button
            onClick={submit}
            disabled={saving || errors.length > 0}
            style={{ background: "#DC2626", border: "none", color: "#fff", padding: "8px 16px", borderRadius: 6, fontSize: 13, fontWeight: 500, display: "flex", alignItems: "center", gap: 6, opacity: saving || errors.length ? 0.6 : 1, cursor: saving || errors.length ? "not-allowed" : "pointer" }}
          >
            {saving ? <Loader2 size={14} className="spin" /> : <Check size={14} />} Record redemption
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
