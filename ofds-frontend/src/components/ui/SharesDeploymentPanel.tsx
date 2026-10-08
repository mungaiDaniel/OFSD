import { useEffect, useState } from "react";
import { Coins, Check, Loader2 } from "lucide-react";
import { batchService } from "@/services/batchService";
import type { SharesDeploymentPreview } from "@/lib/types";

export interface SharesDeploymentConfirmPayload {
  dateString: string;
  exchangeRate: number;
  pricePerShareNgn: number;
  sharesAllocated: number;
}

interface SharesDeploymentPanelProps {
  batchId: number;
  onConfirm: (payload: SharesDeploymentConfirmPayload) => Promise<void>;
  isLoading?: boolean;
}

const PREVIEW_ROW_LIMIT = 50;

/**
 * SHARES-only Deployed-stage allocation form (Task 3): USD -> NGN conversion
 * and whole-share allocation, replacing the old flat-rate DPRP oversubscription
 * toggle in DeploymentDateModal (which this does not touch — that modal is
 * FUNDS-only now). Live preview comes straight from the backend
 * (SharesDeploymentService.preview).
 *
 * Task 9: lives inline on the Shares batch detail page (shown once the batch
 * is transferred and awaiting deployment) instead of behind a modal dialog —
 * everything else about this form (fields, preview fetch, confirm payload)
 * is unchanged from Task 2/3.
 */
export function SharesDeploymentPanel({ batchId, onConfirm, isLoading = false }: SharesDeploymentPanelProps) {
  const [selectedDate, setSelectedDate] = useState<string>("");
  const [exchangeRate, setExchangeRate] = useState<string>("");
  const [pricePerShareNgn, setPricePerShareNgn] = useState<string>("");
  const [sharesAllocated, setSharesAllocated] = useState<string>("");
  const [preview, setPreview] = useState<SharesDeploymentPreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const inputsReady = Number(exchangeRate) > 0 && Number(pricePerShareNgn) > 0 && Number(sharesAllocated) > 0;

  useEffect(() => {
    if (!inputsReady) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    const t = setTimeout(() => {
      setPreviewLoading(true);
      setPreviewError(null);
      batchService
        .previewSharesDeployment(batchId, exchangeRate, pricePerShareNgn, sharesAllocated)
        .then(setPreview)
        .catch((err) => {
          setPreview(null);
          setPreviewError(err?.response?.data?.message || "Could not compute a preview for these inputs");
        })
        .finally(() => setPreviewLoading(false));
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [batchId, exchangeRate, pricePerShareNgn, sharesAllocated, inputsReady]);

  const canConfirm = !!selectedDate && !!preview && !previewLoading && !previewError;

  const handleConfirm = async () => {
    if (!canConfirm || !preview) return;
    await onConfirm({
      dateString: new Date(selectedDate).toISOString(),
      exchangeRate: Number(exchangeRate),
      pricePerShareNgn: Number(pricePerShareNgn),
      sharesAllocated: Number(sharesAllocated),
    });
  };

  const panelStyle: React.CSSProperties = {
    background: "rgba(16, 24, 45, 0.72)",
    backdropFilter: "blur(20px) saturate(150%)",
    WebkitBackdropFilter: "blur(20px) saturate(150%)",
    borderRadius: "16px",
    border: "1px solid rgba(255, 255, 255, 0.08)",
    color: "#fff",
    fontFamily: "var(--font-sans)",
    overflow: "hidden",
  };
  const headerStyle: React.CSSProperties = {
    padding: "16px 22px", borderBottom: "1px solid rgba(255,255,255,0.06)",
    display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px",
  };
  const contentStyle: React.CSSProperties = { padding: "20px 22px", display: "flex", flexDirection: "column", gap: "16px" };
  const inputStyle: React.CSSProperties = {
    width: "100%", background: "rgba(255, 255, 255, 0.05)", border: "1px solid rgba(255, 255, 255, 0.1)",
    borderRadius: "8px", color: "#fff", padding: "12px 16px", fontSize: "14px", outline: "none",
    fontFamily: "var(--font-mono)", colorScheme: "dark",
  };
  const labelStyle: React.CSSProperties = { fontSize: "12px", color: "#94A3B8", fontWeight: 500, display: "block", marginBottom: "6px" };

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <div className="d-flex align-items-center gap-2">
          <div style={{ width: "32px", height: "32px", background: "rgba(212, 148, 11, 0.15)", color: "#D4940B", borderRadius: "8px", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Coins size={16} />
          </div>
          <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 600 }}>Deploy Shares Batch</h3>
        </div>
        <button
          onClick={handleConfirm}
          disabled={isLoading || !canConfirm}
          style={{
            background: "#D4940B", border: "none", color: "#fff", padding: "8px 16px", borderRadius: "6px",
            fontSize: "13px", fontWeight: 500, cursor: (isLoading || !canConfirm) ? "not-allowed" : "pointer",
            opacity: (isLoading || !canConfirm) ? 0.6 : 1, display: "flex", alignItems: "center", gap: "6px",
          }}
        >
          {isLoading ? <Loader2 size={14} className="spin" /> : <Check size={14} />}
          Confirm & Deploy
        </button>
      </div>

      <div style={contentStyle}>
        <p style={{ margin: 0, fontSize: "14px", color: "rgba(255,255,255,0.7)", lineHeight: 1.5 }}>
          Converts each deposit's net USD to NGN at the rate below, then allocates whole shares at the price per share. If demand exceeds what's allocated, minimums are honored first.
        </p>

        <div>
          <label style={labelStyle}>DEPLOYMENT DATE <span style={{ color: "#EF4444" }}>*</span></label>
          <input type="date" style={inputStyle} value={selectedDate} onChange={(e) => setSelectedDate(e.target.value)} disabled={isLoading} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
          <div>
            <label style={labelStyle}>EXCHANGE RATE (NGN / 1 USD)</label>
            <input type="number" step="0.000001" min="0" style={inputStyle} value={exchangeRate} onChange={(e) => setExchangeRate(e.target.value)} disabled={isLoading} placeholder="e.g. 1500" />
          </div>
          <div>
            <label style={labelStyle}>PRICE PER SHARE (NGN)</label>
            <input type="number" step="0.0001" min="0" style={inputStyle} value={pricePerShareNgn} onChange={(e) => setPricePerShareNgn(e.target.value)} disabled={isLoading} placeholder="e.g. 525" />
          </div>
          <div>
            <label style={labelStyle}>SHARES ALLOCATED (WHOLE)</label>
            <input type="number" step="1" min="0" style={inputStyle} value={sharesAllocated} onChange={(e) => setSharesAllocated(e.target.value)} disabled={isLoading} placeholder="e.g. 20000" />
          </div>
        </div>

        {previewError && (
          <div style={{ padding: "10px 12px", borderRadius: "8px", background: "rgba(239,68,68,0.1)", border: "1px solid rgba(239,68,68,0.25)", fontSize: "12px", color: "#EF4444" }}>
            {previewError}
          </div>
        )}

        {!inputsReady && !previewError && (
          <div style={{ fontSize: "12px", color: "rgba(255,255,255,0.4)" }}>
            Enter exchange rate, price per share, and shares allocated to see the allocation preview.
          </div>
        )}

        {preview && !previewError && (
          <>
            <div
              style={{
                display: "inline-flex", alignItems: "center", gap: "8px", padding: "6px 14px", borderRadius: "100px", width: "fit-content",
                background: preview.banner === "Oversubscribed" ? "rgba(239,68,68,0.12)" : "rgba(34,197,94,0.12)",
                border: preview.banner === "Oversubscribed" ? "1px solid rgba(239,68,68,0.3)" : "1px solid rgba(34,197,94,0.3)",
                color: preview.banner === "Oversubscribed" ? "#EF4444" : "#22c55e",
                fontSize: "12px", fontWeight: 700,
              }}
            >
              {preview.banner}
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
              {[
                { label: "TOTAL DEMAND (SHARES)", value: preview.totals.total_demand_shares.toLocaleString(), color: "#fff" },
                { label: "ALLOCATED (SHARES)", value: preview.totals.total_allocated_shares.toLocaleString(), color: "#86EFAC" },
                { label: "UNALLOCATED (SHARES)", value: preview.totals.unallocated_shares.toLocaleString(), color: "#F59E0B" },
                { label: "TOTAL REFUND (USD)", value: preview.totals.total_refund_usd.toLocaleString("en-US", { minimumFractionDigits: 2 }), color: "#FCA5A5" },
              ].map((s) => (
                <div key={s.label}>
                  <span style={{ fontSize: "10px", color: "#94A3B8" }}>{s.label}</span>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: "14px", fontWeight: 700, color: s.color }}>{s.value}</div>
                </div>
              ))}
            </div>

            <div style={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: "10px", overflow: "hidden" }}>
              <div style={{ maxHeight: "260px", overflowY: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "11px" }}>
                  <thead style={{ position: "sticky", top: 0, background: "#111a33" }}>
                    <tr>
                      {["Client Code", "Net USD", "Net NGN", "Max", "Tier-1", "Round-2", "Allocated", "Refund USD"].map((h) => (
                        <th key={h} style={{ padding: "8px 10px", textAlign: h === "Client Code" ? "left" : "right", color: "#94A3B8", fontWeight: 600, whiteSpace: "nowrap" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, PREVIEW_ROW_LIMIT).map((r) => (
                      <tr key={r.investment_id} style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                        <td style={{ padding: "6px 10px", color: "rgba(255,255,255,0.7)", fontFamily: "var(--font-mono)" }}>{r.internal_client_code}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: "#fff" }}>{r.net_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.7)" }}>{r.net_ngn.toLocaleString("en-US", { minimumFractionDigits: 2 })}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>{r.max_shares.toLocaleString()}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>{r.tier1_shares.toLocaleString()}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: "rgba(255,255,255,0.5)" }}>{r.round2_shares.toLocaleString()}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: "#86EFAC", fontWeight: 600 }}>{r.allocated_shares.toLocaleString()}</td>
                        <td style={{ padding: "6px 10px", textAlign: "right", color: r.refund_usd > 0 ? "#FCA5A5" : "rgba(255,255,255,0.3)" }}>
                          {r.refund_usd.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.rows.length > PREVIEW_ROW_LIMIT && (
                <div style={{ padding: "8px 10px", fontSize: "11px", color: "rgba(255,255,255,0.5)", borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                  + {preview.rows.length - PREVIEW_ROW_LIMIT} more deposit{preview.rows.length - PREVIEW_ROW_LIMIT === 1 ? "" : "s"}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
