import { useEffect, useMemo, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Download } from "lucide-react";
import { investmentService } from "@/services/investmentService";
import { fundService } from "@/services/fundService";
import { batchService } from "@/services/batchService";
import { reportService } from "@/services/reportService";
import { NAVLineChart } from "@/components/charts/NAVLineChart";
import { ROUTES } from "@/lib/constants";
import type { InvestorOverviewData, InvestorPosition, FundClassSummary, CoreFund, FundShareClass, Batch } from "@/lib/types";

interface HistoryPoint {
  epoch_end: string | null;
  end_balance: number;
}

interface StatementRow {
  date: string;
  type: string;
  label?: string;
  fund_name?: string;
  deposits?: number;
  withdrawals?: number;
  opening_balance?: number;
  end_balance?: number;
  batch_id?: number;
  withdrawal_id?: number;
}

// GET /investors/<code>/overview only sets market_value/performance_pct when a
// ValuationSnapshot exists for that specific position — it leaves both null otherwise,
// even though it already fetches current_nav (the share class's latest NAV) regardless.
// The Directory/Batch endpoints (_calculate_batch_investment_values) DO fall back to
// shares × latest NAV in that case, which is why the same investor's total differs
// between the Investors list and this page. Mirroring that fallback here client-side
// (backend intentionally left untouched) keeps both views consistent.
function withMarketValueFallback(p: InvestorPosition): InvestorPosition {
  if (p.market_value != null) return p;
  if (p.shares == null || p.current_nav == null) return p;
  const marketValue = p.shares * p.current_nav;
  // Performance baseline must be what was actually DEPLOYED, not the full
  // gross deposit — shares × deployment_nav already reflects the deployed
  // amount net of transfer cost, entry fee, AND any oversubscription refund
  // (shares are only ever purchased with what's left after those deductions),
  // so it's mathematically the same as net_principal × allocation_rate
  // without needing either figure directly. Comparing against the raw
  // deposit instead manufactured a false loss for every oversubscribed
  // investor, since part of their deposit was never meant to be deployed.
  const deployedBasis = p.shares != null && p.deployment_nav != null ? p.shares * p.deployment_nav : null;
  const performancePct =
    p.performance_pct != null
      ? p.performance_pct
      : deployedBasis
        ? ((marketValue / deployedBasis) - 1) * 100
        : null;
  return { ...p, market_value: marketValue, performance_pct: performancePct };
}

function currencyBadgeColors(currency: string | null) {
  const isKES = currency === "KES";
  return {
    color: isKES ? "var(--color-kes)" : "var(--color-usd)",
    bg: isKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
    border: isKES ? "var(--color-kes-border)" : "var(--color-usd-border)",
  };
}

function CurrencyBadge({ currency }: { currency: string | null }) {
  if (!currency) return null;
  const c = currencyBadgeColors(currency);
  return (
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
        background: c.bg,
        color: c.color,
        border: `1px solid ${c.border}`,
      }}
    >
      {currency}
    </span>
  );
}

function formatStatementDate(d: string | null | undefined): string {
  if (!d) return "—";
  const dt = new Date(d);
  if (Number.isNaN(dt.getTime())) return "—";
  return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function statementTypeLabel(stmt: StatementRow): string {
  if (stmt.label) return stmt.label;
  if (stmt.type === "DEPLOYMENT") return "Deployment Statement";
  if (stmt.type === "DEPOSIT") return "Deposit";
  if (stmt.type === "WITHDRAWAL") return "Withdrawal";
  if (stmt.type === "VALUATION") return "Valuation Report";
  return stmt.type || "Statement";
}

// ── Current + Previous Holdings — per-position market value & gain ──
function CurrentHoldingsCard({ positions }: { positions: InvestorPosition[] }) {
  return (
    <div>
      <div
        style={{
          fontSize: "10px",
          fontWeight: 600,
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          color: "var(--color-text-tertiary)",
          marginBottom: "14px",
        }}
      >
        Current + Previous Holdings
      </div>
      {positions.length === 0 ? (
        <div style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}>No holdings yet</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column" }}>
          {positions.map((p, i) => {
            // market_value is null until this position has actually been valued
            // (transferred/deployed + a valuation run) — treating that as $0 made
            // a freshly-deposited investor with no valuation yet show a large,
            // completely fabricated loss (0 - deposit_amount). Only compute a
            // gain/loss once there's a real market value to compare against.
            //
            // The baseline must be what was actually DEPLOYED (shares ×
            // deployment_nav), not the raw gross deposit — same fix as
            // withMarketValueFallback above, just not previously applied here.
            // For an oversubscribed investor, part of the gross deposit was
            // refunded and never deployed at all; comparing market_value
            // against the full deposit manufactured a "loss" exactly equal to
            // the refund amount, even on a freshly deployed position with zero
            // real gain/loss.
            const hasValuation = p.market_value != null;
            const deployedBasis = p.shares != null && p.deployment_nav != null ? p.shares * p.deployment_nav : null;
            const gain = hasValuation && deployedBasis != null ? (p.market_value ?? 0) - deployedBasis : null;
            const isKES = p.currency === "KES";
            const symbol = isKES ? "KES" : "$";
            return (
              <div
                key={`${p.batch_id}-${p.class_code}-${i}`}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "10px",
                  padding: i === 0 ? "0 0 12px" : "12px 0",
                  borderTop: i === 0 ? undefined : "1px solid rgba(255,255,255,0.05)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 700, color: currencyBadgeColors(p.currency).color }}>
                    {p.class_code || "—"}
                  </span>
                  <CurrencyBadge currency={p.currency} />
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "13px", fontWeight: 700, color: "var(--color-text-primary)" }}>
                    {p.market_value != null ? `${symbol} ${p.market_value.toLocaleString("en-US", { maximumFractionDigits: 0 })}` : "—"}
                  </div>
                  <div style={{ fontSize: "10px", color: gain == null ? "var(--color-text-tertiary)" : gain >= 0 ? "var(--color-success)" : "var(--color-destructive)" }}>
                    {gain == null
                      ? "Awaiting valuation"
                      : `${gain >= 0 ? "+" : ""}${symbol} ${gain.toLocaleString("en-US", { maximumFractionDigits: 0 })}`}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const glassCard: React.CSSProperties = {
  background: "rgba(16, 24, 45, 0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255, 255, 255, 0.07)",
};

const actionBtnBase: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 14px",
  borderRadius: "8px",
  fontFamily: "var(--font-sans)",
  fontSize: "12px",
  cursor: "pointer",
  transition: "0.15s",
};

function fmtMoney(v: number): string {
  return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function initialsOf(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return (words[0]?.[0] ?? "") .concat(words[1]?.[0] ?? "").toUpperCase() || "?";
}

// ── Standing — Deposit + Valuations (single amber line) ──
function StandingChart({ history }: { history: HistoryPoint[] }) {
  const data = history
    .filter((h) => h.epoch_end)
    .map((h) => ({ date: h.epoch_end as string, value: h.end_balance }));

  if (data.length === 0) {
    return (
      <div style={{ padding: "32px", textAlign: "center", color: "var(--color-text-tertiary)", fontSize: "12px" }}>
        No valuation history yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
        <XAxis
          dataKey="date"
          tickFormatter={(d) => new Date(d).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}
          tick={{ fontSize: 10, fill: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "var(--color-text-tertiary)", fontFamily: "var(--font-mono)" }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v) => v.toLocaleString("en-US", { maximumFractionDigits: 0 })}
          width={60}
        />
        <Tooltip
          content={({ active, payload, label }: any) => {
            if (!active || !payload?.length) return null;
            return (
              <div style={{ background: "#1e293b", border: "1px solid rgba(255,255,255,0.08)", borderRadius: "8px", padding: "10px 14px", fontSize: "11px" }}>
                <div style={{ color: "#94a3b8", marginBottom: "6px", fontFamily: "var(--font-mono)" }}>
                  {new Date(label).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                </div>
                <div style={{ color: "#F59E0B", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                  Standing: {Number(payload[0].value).toLocaleString("en-US", { maximumFractionDigits: 0 })}
                </div>
              </div>
            );
          }}
          cursor={{ stroke: "rgba(255,255,255,0.12)", strokeWidth: 1, strokeDasharray: "4 2" }}
        />
        <Line
          type="monotone"
          dataKey="value"
          name="Standing"
          stroke="#F59E0B"
          strokeWidth={2}
          dot={{ r: 3, fill: "#F59E0B", strokeWidth: 0 }}
          activeDot={{ r: 5, fill: "#F59E0B", strokeWidth: 0 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div style={{ ...glassCard, borderRadius: "12px", padding: "16px 18px" }}>
      <div style={{ fontSize: "9px", fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: "rgb(71, 85, 105)", marginBottom: "6px" }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "18px", fontWeight: 700, color, letterSpacing: "-0.02em", marginBottom: "3px" }}>
        {value}
      </div>
      <div style={{ fontSize: "10px", color: "rgb(71, 85, 105)" }}>{sub}</div>
    </div>
  );
}

interface FlatShareClass extends FundShareClass {
  fund_id: number;
  fund_name: string;
}

function EditInvestorModal({
  overview,
  onClose,
  onSaved,
}: {
  overview: InvestorOverviewData;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(overview.investor_name || "");
  const [email, setEmail] = useState(overview.investor_email || "");
  const [phone, setPhone] = useState(overview.investor_phone || "");
  const [wealthManager, setWealthManager] = useState(overview.wealth_manager || "");
  const [ifa, setIfa] = useState(overview.IFA || "");
  const [contractNote, setContractNote] = useState(overview.contract_note || "");
  const [saving, setSaving] = useState(false);

  // Share class picker — flattened across every fund (no single "all share
  // classes" endpoint exists, so we fetch funds then each fund's classes).
  const [shareClasses, setShareClasses] = useState<FlatShareClass[]>([]);
  const [loadingShareClasses, setLoadingShareClasses] = useState(true);
  const currentShareClassId = overview.current_batch?.share_class_id ?? null;
  const [selectedShareClassId, setSelectedShareClassId] = useState<number | "">(currentShareClassId ?? "");

  // Batch movement — only relevant once a share class is chosen.
  const [movementMode, setMovementMode] = useState<"none" | "existing" | "new">("none");
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loadingBatches, setLoadingBatches] = useState(false);
  const [targetBatchId, setTargetBatchId] = useState<number | "">("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoadingShareClasses(true);
      try {
        const funds = await fundService.getAll();
        const activeFunds = funds.filter((f: CoreFund) => f.is_active !== false);
        const perFund = await Promise.all(
          activeFunds.map(async (f) => {
            try {
              const classes = await fundService.getClasses(f.id);
              return classes
                .filter((c) => c.is_active !== false)
                .map((c) => ({ ...c, fund_id: f.id, fund_name: f.fund_name }));
            } catch {
              return [];
            }
          })
        );
        if (!cancelled) setShareClasses(perFund.flat());
      } catch {
        if (!cancelled) toast.error("Failed to load share classes");
      } finally {
        if (!cancelled) setLoadingShareClasses(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Load batches once a share class differs from the investor's current one —
  // that's the only time "move to an existing batch" is meaningful.
  useEffect(() => {
    if (movementMode !== "existing") return;
    let cancelled = false;
    (async () => {
      setLoadingBatches(true);
      try {
        const all = await batchService.getAll();
        if (!cancelled) setBatches(all);
      } catch {
        if (!cancelled) toast.error("Failed to load batches");
      } finally {
        if (!cancelled) setLoadingBatches(false);
      }
    })();
    return () => { cancelled = true; };
  }, [movementMode]);

  const effectiveShareClassId = selectedShareClassId !== "" ? selectedShareClassId : currentShareClassId;

  // Client-side approximation of the rule the backend enforces authoritatively
  // (app/Investments/route.py: update_investor_profile) — not yet deployed, and
  // matching the effective share class. GET /api/v1/batches doesn't return
  // deployment_confirmed, so `stage` (kept in sync with it by the deploy flow)
  // is the only signal available here; the backend still re-validates on save
  // and rejects an ineligible target with a clear error either way.
  const eligibleBatches = useMemo(
    () =>
      batches.filter(
        (b) =>
          (b.stage ?? 1) < 3 &&
          (effectiveShareClassId == null || b.share_class_id == null || b.share_class_id === effectiveShareClassId)
      ),
    [batches, effectiveShareClassId]
  );

  const fieldStyle: React.CSSProperties = {
    width: "100%",
    padding: "10px 12px",
    borderRadius: "8px",
    background: "rgba(0, 0, 0, 0.25)",
    border: "1px solid rgba(255, 255, 255, 0.1)",
    color: "rgb(255, 255, 255)",
    fontSize: "13px",
    outline: "none",
  };
  const labelStyle: React.CSSProperties = { fontSize: "11px", color: "rgb(148,163,184)", display: "block", marginBottom: "6px" };

  const save = async () => {
    if (movementMode === "existing" && targetBatchId === "") {
      toast.error("Choose a batch to move the investor into, or switch back to “No change”.");
      return;
    }
    setSaving(true);
    try {
      const payload: Parameters<typeof investmentService.updateInvestorProfile>[1] = {
        investor_name: name.trim(),
        investor_email: email.trim(),
        investor_phone: phone.trim(),
        wealth_manager: wealthManager.trim(),
        IFA: ifa.trim(),
        contract_note: contractNote.trim(),
      };
      if (selectedShareClassId !== "" && selectedShareClassId !== currentShareClassId) {
        payload.share_class_id = selectedShareClassId;
      }
      if (movementMode === "existing" && targetBatchId !== "") {
        payload.batch_id = targetBatchId;
      } else if (movementMode === "new") {
        payload.create_new_batch = true;
      }

      const res = await investmentService.updateInvestorProfile(overview.internal_client_code, payload);
      if (res.status === 200) {
        toast.success("Investor updated");
        onSaved();
      } else {
        toast.error(res.message || "Failed to update investor");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to update investor");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{ position: "fixed", inset: 0, zIndex: 9998, display: "flex", alignItems: "center", justifyContent: "center", background: "rgba(6,11,26,0.75)", backdropFilter: "blur(4px)", padding: "16px" }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div style={{ ...glassCard, width: "100%", maxWidth: "460px", maxHeight: "88vh", overflowY: "auto", borderRadius: "16px", padding: "22px 24px" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "4px" }}>
          <div style={{ fontSize: "16px", fontWeight: 700 }}>Edit investor</div>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-brand-400)", marginBottom: "16px" }}>
          {overview.internal_client_code}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "18px" }}>
          <div>
            <label style={labelStyle}>Investor Name *</label>
            <input value={name} onChange={(e) => setName(e.target.value)} style={fieldStyle} />
          </div>
          <div>
            <label style={labelStyle}>Email *</label>
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={fieldStyle} />
          </div>
          <div>
            <label style={labelStyle}>Phone</label>
            <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} style={fieldStyle} />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div>
              <label style={labelStyle}>Wealth Manager</label>
              <input value={wealthManager} onChange={(e) => setWealthManager(e.target.value)} style={fieldStyle} />
            </div>
            <div>
              <label style={labelStyle}>IFA</label>
              <input value={ifa} onChange={(e) => setIfa(e.target.value)} style={fieldStyle} />
            </div>
          </div>
          <div>
            <label style={labelStyle}>Contract Note</label>
            <input value={contractNote} onChange={(e) => setContractNote(e.target.value)} style={fieldStyle} />
          </div>
        </div>

        <div style={{ borderTop: "1px solid rgba(255,255,255,0.07)", paddingTop: "16px", marginBottom: "18px" }}>
          <label style={labelStyle}>Share Class</label>
          <select
            value={selectedShareClassId}
            disabled={loadingShareClasses}
            onChange={(e) => {
              const val = e.target.value ? Number(e.target.value) : "";
              setSelectedShareClassId(val);
              setMovementMode("none");
              setTargetBatchId("");
            }}
            style={{ ...fieldStyle, appearance: "auto" as const }}
          >
            <option value="">{loadingShareClasses ? "Loading…" : "— Unchanged —"}</option>
            {shareClasses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.fund_name} — {c.class_code} ({c.currency})
                {c.id === currentShareClassId ? " (current)" : ""}
              </option>
            ))}
          </select>

          {selectedShareClassId !== "" && selectedShareClassId !== currentShareClassId && (
            <div style={{ marginTop: "14px" }}>
              <label style={labelStyle}>Batch Movement</label>
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {([
                  ["none", "No change — keep current holdings where they are"],
                  ["existing", "Move to an existing open batch for this share class"],
                  ["new", "Create a new batch for this share class"],
                ] as const).map(([value, labelText]) => (
                  <label key={value} style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "12px", color: "rgb(203,213,225)", cursor: "pointer" }}>
                    <input
                      type="radio"
                      name="movementMode"
                      value={value}
                      checked={movementMode === value}
                      onChange={() => { setMovementMode(value); setTargetBatchId(""); }}
                    />
                    {labelText}
                  </label>
                ))}
              </div>

              {movementMode === "existing" && (
                <div style={{ marginTop: "10px" }}>
                  <select
                    value={targetBatchId}
                    disabled={loadingBatches}
                    onChange={(e) => setTargetBatchId(e.target.value ? Number(e.target.value) : "")}
                    style={{ ...fieldStyle, appearance: "auto" as const }}
                  >
                    <option value="">{loadingBatches ? "Loading…" : "Select a batch…"}</option>
                    {eligibleBatches.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.batch_name}{b.class_code ? ` — ${b.class_code}` : ""}
                      </option>
                    ))}
                  </select>
                  {!loadingBatches && eligibleBatches.length === 0 && (
                    <div style={{ fontSize: "11px", color: "rgb(148,163,184)", marginTop: "6px" }}>
                      No open, non-deployed batches found for this share class — create a new one instead.
                    </div>
                  )}
                </div>
              )}

              <div style={{ fontSize: "11px", color: "rgb(148,163,184)", marginTop: "8px" }}>
                Only holdings that haven't been deployed yet can move. Deployed batches are left untouched.
              </div>
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
          <button onClick={onClose} style={{ ...actionBtnBase, background: "transparent", border: "none", color: "rgb(148,163,184)" }}>
            Cancel
          </button>
          <button
            onClick={save}
            disabled={saving}
            style={{ ...actionBtnBase, background: "rgb(26,69,255)", border: "none", color: "#fff", fontWeight: 600, opacity: saving ? 0.7 : 1 }}
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function InvestorOverviewPage() {
  const { clientCode } = useParams<{ clientCode: string }>();
  const navigate = useNavigate();

  const [overview, setOverview] = useState<InvestorOverviewData | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [statements, setStatements] = useState<StatementRow[]>([]);
  const [classesByCurrency, setClassesByCurrency] = useState<Record<string, FundClassSummary[]>>({});
  const [asOfDate, setAsOfDate] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);

  useEffect(() => {
    if (!clientCode) return;
    load(decodeURIComponent(clientCode));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientCode]);

  async function load(code: string) {
    setLoading(true);
    try {
      const [ovRes, histRes, stmtRes, summary] = await Promise.all([
        investmentService.getInvestorOverview(code),
        investmentService.getInvestorHistory(code),
        investmentService.getInvestorStatements(code),
        fundService.getSummary(),
      ]);

      if (ovRes.status !== 200 || !ovRes.data) {
        toast.error(ovRes.message || "Investor not found");
        setOverview(null);
        return;
      }
      setOverview(ovRes.data);
      setHistory(((histRes.data as HistoryPoint[]) || []));

      // MONTHLY_REPORT rows come from the legacy epoch-ledger and duplicate what
      // VALUATION rows (from the share-based ValuationSnapshot system) already show
      // for the same period — prod's statements table hides them, so we do too.
      const statementsData = ((stmtRes.data as StatementRow[]) || []).filter(
        (s) => s.type !== "MONTHLY_REPORT"
      );
      const sortedStatements = [...statementsData].sort((a, b) => {
        const at = new Date(a?.date).getTime();
        const bt = new Date(b?.date).getTime();
        if (!Number.isFinite(at) || !Number.isFinite(bt)) return 0;
        return bt - at;
      });
      setStatements(sortedStatements);

      // Resolve the investor's held classes' NAV history from the funds summary,
      // matched by fund name + class code (no dedicated backend endpoint for this).
      const positions = ovRes.data.positions || [];
      const byCurrency: Record<string, FundClassSummary[]> = { USD: [], KES: [] };
      if (summary) {
        for (const pos of positions) {
          const cur = (pos.currency || "").toUpperCase();
          if (!byCurrency[cur]) byCurrency[cur] = [];
          const fund = summary.funds.find(
            (f) => f.fund_name?.trim().toLowerCase() === (pos.fund_name || "").trim().toLowerCase()
          );
          const cls = fund?.classes?.find(
            (c) => (c.class_code || "").trim().toLowerCase() === (pos.class_code || "").trim().toLowerCase()
          );
          if (cls && !byCurrency[cur].some((c) => (c.class_code ?? c.class_name) === (cls.class_code ?? cls.class_name))) {
            byCurrency[cur].push(cls);
          }
        }
        setAsOfDate(summary.as_of_date);
      }
      setClassesByCurrency(byCurrency);
    } catch (err) {
      console.error("Failed to load investor overview:", err);
      toast.error("Failed to load investor overview");
      setOverview(null);
    } finally {
      setLoading(false);
    }
  }

  const positions: InvestorPosition[] = (overview?.positions ?? []).map(withMarketValueFallback);

  const kesTotal = useMemo(
    () => positions.filter((p) => p.currency === "KES").reduce((s, p) => s + (p.market_value ?? 0), 0),
    [positions]
  );
  const usdTotal = useMemo(
    () => positions.filter((p) => p.currency === "USD").reduce((s, p) => s + (p.market_value ?? 0), 0),
    [positions]
  );
  const hasKes = positions.some((p) => p.currency === "KES");
  const hasUsd = positions.some((p) => p.currency === "USD");
  const totalShares = useMemo(() => positions.reduce((s, p) => s + (p.shares ?? 0), 0), [positions]);

  const handleGenerateStatement = async () => {
    if (!overview) return;
    setDownloadingPdf(true);
    try {
      await investmentService.downloadInvestorStatementPdf(overview.internal_client_code);
      toast.success("Statement downloaded");
    } catch {
      toast.error("Failed to generate statement");
    } finally {
      setDownloadingPdf(false);
    }
  };

  const handleSendStatementEmail = async () => {
    if (!overview) return;
    setSendingEmail(true);
    try {
      const res = await investmentService.queueStatementEmail(overview.internal_client_code);
      if (res.status === 200 || res.status === 201) {
        toast.success("Statement email queued — confirm it from the pending emails queue");
      } else {
        toast.error(res.message || "Failed to queue statement email");
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || "Failed to queue statement email");
    } finally {
      setSendingEmail(false);
    }
  };

  const handleDownloadStatement = async (stmt: StatementRow) => {
    if (!overview) return;
    const code = overview.internal_client_code;
    try {
      toast.loading("Preparing PDF...");
      if (stmt.type === "WITHDRAWAL" && stmt.withdrawal_id) {
        await reportService.downloadWithdrawalReceipt(code, stmt.withdrawal_id);
      } else if ((stmt.type === "DEPOSIT" || stmt.type === "DEPLOYMENT") && stmt.batch_id) {
        await reportService.downloadDepositReceipt(code, stmt.batch_id);
      } else if (stmt.type === "VALUATION") {
        await reportService.downloadInvestorStatementByClientCode(code, stmt.date, { periodOnly: true });
      } else {
        toast.dismiss();
        toast.error("Cannot download this statement type");
        return;
      }
      toast.dismiss();
      toast.success("Downloaded successfully");
    } catch {
      toast.dismiss();
      toast.error("Failed to download PDF");
    }
  };

  if (loading) {
    return (
      <div className="d-flex align-items-center justify-content-center" style={{ height: "256px" }}>
        <div
          className="spinner-border"
          style={{ color: "var(--color-brand-400)", width: "1.5rem", height: "1.5rem" }}
          role="status"
        >
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div style={{ padding: "48px 24px", textAlign: "center" }}>
        <p style={{ color: "var(--color-text-tertiary)" }}>Investor not found</p>
        <button
          onClick={() => navigate(ROUTES.INVESTORS)}
          className="btn btn-sm btn-outline-secondary mt-3"
        >
          Back to investors
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        padding: "24px 32px 48px",
        display: "flex",
        position: "relative",
        zIndex: 1,
        maxWidth: "1200px",
        margin: "0 auto",
        fontFamily: "var(--font-sans, 'Plus Jakarta Sans', sans-serif)",
        color: "rgb(255, 255, 255)",
        flexDirection: "column",
        gap: "20px",
      }}
    >
      {/* Back button */}
      <button
        onClick={() => navigate(ROUTES.INVESTORS)}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          background: "transparent",
          border: "none",
          color: "rgb(71, 85, 105)",
          fontFamily: "var(--font-sans)",
          fontSize: "12px",
          cursor: "pointer",
          padding: 0,
          alignSelf: "flex-start",
          transition: "color 0.15s",
        }}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path d="M9 6H3M5 8L3 6l2-2" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Back to investors
      </button>

      {/* Header card */}
      <div style={{ ...glassCard, borderRadius: "16px", padding: "20px 24px" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "14px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
            <div
              style={{
                width: "52px",
                height: "52px",
                borderRadius: "50%",
                background: "rgba(59, 130, 246, 0.15)",
                border: "1px solid rgba(59, 130, 246, 0.35)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "16px",
                fontWeight: 700,
                color: "rgb(96, 165, 250)",
                flexShrink: 0,
                fontFamily: "var(--font-mono)",
              }}
            >
              {initialsOf(overview.investor_name)}
            </div>
            <div>
              <div style={{ fontSize: "20px", fontWeight: 700, letterSpacing: "-0.02em", marginBottom: "4px" }}>
                {overview.investor_name}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "11px", color: "rgb(59, 130, 246)", letterSpacing: "0.04em", fontWeight: 600 }}>
                  {overview.internal_client_code}
                </span>
                <span style={{ color: "rgb(30, 41, 59)", fontSize: "8px" }}>•</span>
                <span style={{ fontSize: "12px", color: "rgb(148, 163, 184)" }}>{overview.investor_email || "—"}</span>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button
              onClick={() => setEditOpen(true)}
              style={{ ...actionBtnBase, background: "rgba(16, 185, 129, 0.1)", border: "1px solid rgba(16, 185, 129, 0.22)", color: "rgb(52, 211, 153)", fontWeight: 600 }}
            >
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <path d="M9.7 2.3l2 2-6.9 6.9H2.8V9.2L9.7 2.3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
                <path d="M8.9 3.1l2 2" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              Edit
            </button>

            <button
              onClick={handleGenerateStatement}
              disabled={downloadingPdf}
              style={{ ...actionBtnBase, background: "rgba(59, 130, 246, 0.12)", border: "1px solid rgba(59, 130, 246, 0.25)", color: "rgb(96, 165, 250)", fontWeight: 500, opacity: downloadingPdf ? 0.7 : 1 }}
            >
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <rect x="2" y="1" width="10" height="12" rx="1.5" stroke="currentColor" strokeWidth="1.3" />
                <line x1="4.5" y1="4.5" x2="9.5" y2="4.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
                <line x1="4.5" y1="7" x2="9.5" y2="7" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
                <line x1="4.5" y1="9.5" x2="7.5" y2="9.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
              </svg>
              {downloadingPdf ? "Generating…" : "Generate Statement"}
            </button>

            <button
              onClick={handleSendStatementEmail}
              disabled={sendingEmail}
              style={{ ...actionBtnBase, background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.26)", color: "rgb(52, 211, 153)", fontWeight: 600, opacity: sendingEmail ? 0.7 : 1 }}
            >
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <path d="M2 3.5A1.5 1.5 0 0 1 3.5 2h7A1.5 1.5 0 0 1 12 3.5v7A1.5 1.5 0 0 1 10.5 12h-7A1.5 1.5 0 0 1 2 10.5v-7z" stroke="currentColor" strokeWidth="1.2" />
                <path d="M3.5 4l3.5 2.6L10.5 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {sendingEmail ? "Sending…" : "Send Statement Email"}
            </button>

            <button
              onClick={() => navigate(ROUTES.INVESTOR_STATEMENT(overview.internal_client_code))}
              style={{ ...actionBtnBase, background: "transparent", border: "1px solid rgba(255, 255, 255, 0.1)", color: "rgb(148, 163, 184)", fontWeight: 500 }}
            >
              <svg width="13" height="13" viewBox="0 0 14 14" fill="none">
                <path d="M1 4h12M1 8h8M1 12h6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
              </svg>
              View Transactions
            </button>
          </div>
        </div>
      </div>

      {/* Stat cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "12px" }}>
        <StatCard
          label="Total KES Market Value"
          value={hasKes ? `KES ${fmtMoney(kesTotal)}` : "—"}
          sub={hasKes ? "as of last valuation" : "no KES positions"}
          color="var(--color-kes)"
        />
        <StatCard
          label="Total USD Market Value"
          value={hasUsd ? `$ ${fmtMoney(usdTotal)}` : "—"}
          sub={hasUsd ? "as of last valuation" : "no USD positions"}
          color="var(--color-usd)"
        />
        <StatCard
          label="Total Shares"
          value={totalShares > 0 ? totalShares.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}
          sub="across all classes"
          color="rgb(255, 255, 255)"
        />
        <StatCard
          label="Active Holdings"
          value={String(positions.length)}
          sub={`${positions.length} total position${positions.length !== 1 ? "s" : ""}`}
          color="rgb(255, 255, 255)"
        />
      </div>

      {/* Charts grid — left column: Standing chart stacked above per-currency NAV charts;
          right column: Current + Previous Holdings alone, spanning the full row height. */}
      <div style={{ display: "grid", gridTemplateColumns: "3fr 2fr", gap: "14px" }} className="investor-overview-charts">
        <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
          <div style={{ ...glassCard, borderRadius: "12px", padding: "20px 24px" }}>
            <div
              style={{
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "var(--color-text-tertiary)",
                marginBottom: "12px",
              }}
            >
              Standing — Deposit + Valuations
            </div>
            <StandingChart history={history} />
          </div>

          {(["USD", "KES"] as const)
            .filter((cur) => (classesByCurrency[cur] || []).length > 0)
            .map((cur) => (
              <div key={cur} style={{ ...glassCard, borderRadius: "12px", padding: "20px 24px" }}>
                <NAVLineChart
                  classes={classesByCurrency[cur] ?? []}
                  currency={cur}
                  title={`${cur} Holdings — NAV / Share`}
                  asOfDate={asOfDate}
                />
              </div>
            ))}
        </div>

        <div style={{ ...glassCard, borderRadius: "12px", padding: "20px 24px" }}>
          {!hasKes && !hasUsd ? (
            <div style={{ padding: "12px 0", textAlign: "center", color: "var(--color-text-tertiary)", fontSize: "12px" }}>
              No active holdings yet
            </div>
          ) : (
            <CurrentHoldingsCard positions={positions} />
          )}
        </div>
      </div>

      {/* All Positions */}
      <div style={{ ...glassCard, borderRadius: "16px", boxShadow: "rgba(0, 0, 0, 0.25) 0px 4px 24px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          }}
        >
          <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--color-text-primary)" }}>All Positions</div>
          <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>
            {positions.length} holding{positions.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
                {["Batch", "Fund / Class", "Deposited", "Shares", "Market Value", "NAV / Share", "Performance", "Deployed", "Refund"].map((h) => (
                  <th
                    key={h}
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
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={9} style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                    No positions found.
                  </td>
                </tr>
              ) : (
                positions.map((p, i) => (
                  <tr
                    key={`${p.batch_id}-${i}`}
                    onClick={() => p.batch_id != null && navigate(ROUTES.BATCH_DETAIL(p.batch_id))}
                    style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)", cursor: p.batch_id != null ? "pointer" : "default" }}
                    onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(255,255,255,0.03)"; }}
                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                  >
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "11px", color: "var(--color-text-secondary)" }}>
                      {p.batch_name}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                        <span style={{ fontSize: "12px", color: "var(--color-text-secondary)" }}>{p.fund_name}</span>
                        {p.class_code && (
                          <>
                            <span style={{ color: "rgba(255, 255, 255, 0.2)", fontSize: "10px" }}>›</span>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: "10px", fontWeight: 700, color: currencyBadgeColors(p.currency).color }}>
                              {p.class_code}
                            </span>
                          </>
                        )}
                        <CurrencyBadge currency={p.currency} />
                      </div>
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                      {p.deposit_amount != null ? `${p.currency === "KES" ? "KES" : "$"} ${fmtMoney(p.deposit_amount)}` : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                      {p.shares != null ? p.shares.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                      {p.market_value != null ? `${p.currency === "KES" ? "KES" : "$"} ${fmtMoney(p.market_value)}` : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                      {p.current_nav != null ? p.current_nav.toFixed(4) : "—"}
                    </td>
                    <td
                      style={{
                        padding: "12px 16px",
                        fontFamily: "var(--font-mono)",
                        fontSize: "12px",
                        color: (p.performance_pct ?? 0) >= 0 ? "var(--color-success)" : "var(--color-destructive)",
                      }}
                    >
                      {p.performance_pct != null ? `${p.performance_pct >= 0 ? "+" : ""}${p.performance_pct.toFixed(2)}%` : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
                      {formatStatementDate(p.deployment_date)}
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: "11px" }}>
                      {p.refund_amount != null ? (
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <span style={{ fontFamily: "var(--font-mono)", color: "var(--color-text-primary)" }}>
                            {p.currency === "KES" ? "KES" : "$"} {fmtMoney(p.refund_amount)}
                          </span>
                          <span
                            style={{
                              padding: "1px 7px",
                              borderRadius: "999px",
                              fontSize: "9px",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              background: p.refund_status === "Pending" ? "rgba(245,158,11,0.14)" : "rgba(16,185,129,0.14)",
                              color: p.refund_status === "Pending" ? "#F59E0B" : "#10B981",
                            }}
                          >
                            {p.refund_status || "Pending"}
                          </span>
                        </div>
                      ) : (
                        <span style={{ color: "var(--color-text-tertiary)" }}>—</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Historical Statements */}
      <div style={{ ...glassCard, borderRadius: "16px", boxShadow: "rgba(0, 0, 0, 0.25) 0px 4px 24px" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "16px 20px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          }}
        >
          <div style={{ fontSize: "13px", fontWeight: 700, color: "var(--color-text-primary)" }}>Historical Statements</div>
          <button
            onClick={() => navigate(ROUTES.INVESTOR_STATEMENT(overview.internal_client_code))}
            style={{ background: "none", border: "none", color: "rgb(96, 165, 250)", fontSize: "12px", cursor: "pointer", padding: 0 }}
          >
            View full statement →
          </button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.06)" }}>
                {["Date", "Type", "Deposit", "Withdrawal", "Previous Value", "Current Value", ""].map((h) => (
                  <th
                    key={h}
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
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {statements.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ padding: "24px 16px", textAlign: "center", fontSize: "13px", color: "var(--color-text-tertiary)" }}>
                    No historical statements found.
                  </td>
                </tr>
              ) : (
                statements.slice(0, 8).map((stmt, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.04)" }}>
                    <td style={{ padding: "12px 16px", fontSize: "12px", color: "var(--color-text-secondary)" }}>
                      {formatStatementDate(stmt.date)}
                    </td>
                    <td style={{ padding: "12px 16px", fontSize: "12px", color: "var(--color-text-primary)", fontWeight: stmt.type === "VALUATION" ? 600 : 400 }}>
                      {statementTypeLabel(stmt)}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: (stmt.deposits ?? 0) > 0 ? "var(--color-success)" : "var(--color-text-tertiary)" }}>
                      {(stmt.deposits ?? 0) > 0 ? fmtMoney(stmt.deposits!) : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: (stmt.withdrawals ?? 0) > 0 ? "var(--color-destructive)" : "var(--color-text-tertiary)" }}>
                      {(stmt.withdrawals ?? 0) > 0 ? fmtMoney(stmt.withdrawals!) : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", color: "var(--color-text-primary)" }}>
                      {stmt.opening_balance != null ? fmtMoney(stmt.opening_balance) : "—"}
                    </td>
                    <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 600, color: "var(--color-text-primary)" }}>
                      {stmt.end_balance != null ? fmtMoney(stmt.end_balance) : "—"}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <button
                        onClick={() => handleDownloadStatement(stmt)}
                        title="Download"
                        style={{ background: "rgba(255,255,255,0.05)", border: "none", borderRadius: "6px", padding: "5px", color: "var(--color-brand-400)", cursor: "pointer", display: "flex" }}
                      >
                        <Download size={14} />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {editOpen && (
        <EditInvestorModal
          overview={overview}
          onClose={() => setEditOpen(false)}
          onSaved={() => {
            setEditOpen(false);
            load(overview.internal_client_code);
          }}
        />
      )}
    </div>
  );
}
