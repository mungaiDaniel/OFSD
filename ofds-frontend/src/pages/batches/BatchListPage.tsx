import { useEffect, useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { batchService } from "@/services/batchService";
import { formatDate } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import type { Batch, BatchStage } from "@/lib/types";
import { Plus, Search } from "lucide-react";

// ── Filter options matching production ──────────────────────────────────────
type FilterKey = "All" | "Open" | "Deployed" | "Closed" | "Transferred";
const FILTERS: FilterKey[] = ["Open", "Deployed", "Closed", "Transferred", "All"];

// ── Glassmorphism card style (matches production) ───────────────────────────
const CARD_STYLE: React.CSSProperties = {
  background: "rgba(16,24,45,0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  WebkitBackdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.07)",
  borderRadius: "16px",
  boxShadow: "0 4px 24px rgba(0,0,0,0.25)",
};

// ── Stage label badge ────────────────────────────────────────────────────────
const STAGE_META: Record<number, { label: string; bg: string; color: string }> = {
  1: { label: "Deposited",   bg: "rgba(59,130,246,0.1)",   color: "#60A5FA" },
  2: { label: "Transferred", bg: "rgba(245,158,11,0.1)",   color: "#F59E0B" },
  3: { label: "Deployed",    bg: "rgba(168,85,247,0.1)",   color: "#C084FC" },
  4: { label: "Active",      bg: "rgba(34,197,94,0.1)",    color: "#22c55e" },
};

function StageBadge({ stage }: { stage: BatchStage }) {
  const meta = STAGE_META[stage] ?? {
    label: "Unknown",
    bg: "rgba(59,130,246,0.1)",
    color: "#60A5FA",
  };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 8px",
        borderRadius: "100px",
        fontSize: "9px",
        fontWeight: 600,
        letterSpacing: "0.05em",
        background: meta.bg,
        color: meta.color,
      }}
    >
      {meta.label}
    </span>
  );
}

// ── Currency pill badge ──────────────────────────────────────────────────────
function CurrencyBadge({ currency }: { currency?: string | null }) {
  if (!currency) return null;
  const isKes = currency === "KES";
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
        background: isKes ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
        color: isKes ? "var(--color-kes)" : "var(--color-usd)",
        border: isKes ? "1px solid var(--color-kes-border)" : "1px solid var(--color-usd-border)",
      }}
    >
      {currency}
    </span>
  );
}

// ── Class code label ─────────────────────────────────────────────────────────
function ClassCodeLabel({ code, currency }: { code?: string | null; currency?: string | null }) {
  if (!code) return null;
  const isKes = currency === "KES";
  return (
    <span
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "10px",
        fontWeight: 700,
        color: isKes ? "var(--color-kes)" : "var(--color-usd)",
      }}
    >
      {code}
    </span>
  );
}

// ── "Closes in Xd Yh" countdown ─────────────────────────────────────────────
function getCountdown(dateStr: string) {
  const ms = new Date(dateStr).getTime() - Date.now();
  if (ms <= 0) return null;
  const totalHours = Math.floor(ms / 3_600_000);
  return { days: Math.floor(totalHours / 24), hours: totalHours % 24 };
}

function CloseCountdown({ closeAt }: { closeAt: string }) {
  const cd = getCountdown(closeAt);
  return cd ? (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "2px 8px",
        borderRadius: "100px",
        background: "rgba(245,158,11,0.1)",
        border: "1px solid rgba(245,158,11,0.25)",
        fontSize: "10px",
        fontWeight: 600,
        color: "#F59E0B",
      }}
    >
      Closes in {cd.days > 0 ? `${cd.days}d ${cd.hours}h` : `${cd.hours}h`}
    </span>
  ) : (
    <span style={{ fontSize: "10px", color: "#475569" }}>Closing soon</span>
  );
}

// ── BatchCard compact stepper ────────────────────────────────────────────────
function CompactStepper({ currentStage }: { currentStage: BatchStage }) {
  const stages = [1, 2, 3, 4] as BatchStage[];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
      {stages.map((stage, i) => (
        <div key={stage} style={{ display: "flex", alignItems: "center" }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background:
                stage <= currentStage
                  ? "var(--color-brand-400)"
                  : "var(--color-border-default)",
            }}
          />
          {i < stages.length - 1 && (
            <div
              style={{
                width: 22,
                height: 2,
                background:
                  stage < currentStage
                    ? "var(--color-brand-400)"
                    : "var(--color-border-default)",
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ── Individual batch card ────────────────────────────────────────────────────
function BatchCard({ batch, onClick }: { batch: Batch; onClick: () => void }) {
  const hasClass = !!((batch as any).class_code);
  const classCode: string | null = (batch as any).class_code ?? null;
  const classCurrency: string | null = batch.class_currency ?? null;
  const fundName = batch.funds?.[0]?.fund_name ?? "—";

  // Format the deposited amount with currency prefix
  const depositedLabel = (() => {
    if (batch.total_capital == null) return "—";
    const prefix =
      classCurrency === "KES"
        ? "KES "
        : classCurrency === "USD"
        ? "$ "
        : "";
    return prefix + batch.total_capital.toLocaleString("en-US", { maximumFractionDigits: 0 });
  })();

  return (
    <div
      onClick={onClick}
      style={{ ...CARD_STYLE, padding: "18px 20px", cursor: "pointer", transition: "border-color 0.15s, box-shadow 0.15s" }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "rgba(59,130,246,0.25)";
        e.currentTarget.style.boxShadow = "0 8px 32px rgba(0,0,0,0.35)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)";
        e.currentTarget.style.boxShadow = "0 4px 24px rgba(0,0,0,0.25)";
      }}
    >
      {/* Top row: name + stage badge */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: "12px" }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Batch name */}
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "12px",
              fontWeight: 700,
              color: "var(--color-text-primary)",
              marginBottom: "4px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {batch.batch_name}
          </div>
          {/* Fund name + class code + currency */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
              {fundName}
            </span>
            {hasClass && (
              <>
                <span style={{ color: "rgba(255,255,255,0.2)", fontSize: "10px" }}>›</span>
                <ClassCodeLabel code={classCode} currency={classCurrency} />
                <span style={{ color: "rgba(255,255,255,0.2)", fontSize: "10px" }}>›</span>
                <CurrencyBadge currency={classCurrency} />
              </>
            )}
          </div>
        </div>
        <StageBadge stage={batch.stage} />
      </div>

      {/* Compact stage stepper */}
      <div style={{ marginBottom: "12px" }}>
        <CompactStepper currentStage={batch.stage} />
      </div>

      {/* Bottom row: stats + close countdown / status */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          borderTop: "1px solid rgba(255,255,255,0.05)",
          paddingTop: "10px",
        }}
      >
        <div style={{ display: "flex", gap: "18px" }}>
          {/* Investors */}
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--color-text-tertiary)",
              }}
            >
              Investors
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "13px",
                fontWeight: 600,
                color: "var(--color-text-primary)",
                marginTop: "2px",
              }}
            >
              {batch.investors_count}
            </div>
          </div>

          {/* Deposited */}
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 600,
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--color-text-tertiary)",
              }}
            >
              Deposited
            </div>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "12px",
                color: "var(--color-text-secondary)",
                marginTop: "2px",
              }}
            >
              {depositedLabel}
            </div>
          </div>

          {/* Deployed date (if available) */}
          {batch.date_deployed && (
            <div>
              <div
                style={{
                  fontSize: "9px",
                  fontWeight: 600,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  color: "var(--color-text-tertiary)",
                }}
              >
                Deployed
              </div>
              <div
                style={{
                  fontSize: "11px",
                  color: "var(--color-text-secondary)",
                  marginTop: "2px",
                }}
              >
                {formatDate(batch.date_deployed)}
              </div>
            </div>
          )}
        </div>

        {/* Right side: countdown or status pill */}
        {batch.is_open && batch.auto_close_at ? (
          <CloseCountdown closeAt={batch.auto_close_at} />
        ) : (
          <span
            style={{
              fontSize: "9px",
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: "100px",
              background: "rgba(255,255,255,0.04)",
              color: "var(--color-text-tertiary)",
              border: "1px solid rgba(255,255,255,0.07)",
            }}
          >
            {batch.status}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function BatchListPage() {
  const navigate = useNavigate();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterKey>("All");
  const [search, setSearch] = useState("");

  useEffect(() => {
    batchService
      .getAll()
      .then(setBatches)
      .catch(() => setBatches([]))
      .finally(() => setLoading(false));
  }, []);

  const openCount = batches.filter((b) => b.is_open).length;

  const filtered = useMemo(() => {
    let r = batches;
    if (filter === "Open")        r = r.filter((b) => b.is_open);
    else if (filter === "Closed") r = r.filter((b) => !b.is_open && b.status === "Closed");
    else if (filter === "Transferred") r = r.filter((b) => b.stage >= 2 && b.stage < 3);
    else if (filter === "Deployed")    r = r.filter((b) => b.stage >= 3);

    if (search.trim()) {
      const q = search.toLowerCase();
      r = r.filter(
        (b) =>
          b.batch_name.toLowerCase().includes(q) ||
          ((b as any).class_code ?? "").toLowerCase().includes(q) ||
          (b.certificate_number ?? "").toLowerCase().includes(q)
      );
    }
    return r;
  }, [batches, filter, search]);

  return (
    <div>
      {/* ── Page Header ── */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: "28px",
          gap: "20px",
        }}
      >
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
            Batches
          </h1>
          <p style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>
            {batches.length} batch{batches.length !== 1 ? "es" : ""} — Weekly investment groups sent to AXYS
          </p>
        </div>

        <button
          onClick={() => navigate(ROUTES.BATCH_CREATE)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            padding: "8px 18px",
            borderRadius: "8px",
            background: "#1A45FF",
            border: "none",
            color: "#fff",
            fontSize: "12px",
            fontWeight: 500,
            cursor: "pointer",
            boxShadow: "0 0 16px rgba(26,69,255,0.3)",
            flexShrink: 0,
          }}
        >
          <Plus size={14} /> New batch
        </button>
      </div>

      {/* ── Filter + Search bar ── */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "12px",
          marginBottom: "24px",
        }}
      >
        {/* Filter pills */}
        <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
          {FILTERS.map((f) => {
            const isActive = f === filter;
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  padding: "6px 14px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 600,
                  border: isActive
                    ? "1px solid rgba(59,130,246,0.5)"
                    : "1px solid rgba(255,255,255,0.08)",
                  background: isActive ? "rgba(59,130,246,0.12)" : "transparent",
                  color: isActive ? "#60A5FA" : "var(--color-text-secondary)",
                  cursor: "pointer",
                  transition: "all 0.15s",
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                }}
              >
                {f}
                {f === "Open" && openCount > 0 && (
                  <span
                    style={{
                      fontSize: "9px",
                      padding: "1px 5px",
                      borderRadius: "4px",
                      background: "rgba(245,158,11,0.15)",
                      color: "#F59E0B",
                    }}
                  >
                    {openCount}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Search input */}
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
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search batches…"
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: "8px",
              paddingLeft: "30px",
              paddingRight: "12px",
              paddingTop: "6px",
              paddingBottom: "6px",
              fontSize: "12px",
              color: "var(--color-text-primary)",
              outline: "none",
              minWidth: "200px",
            }}
          />
        </div>
      </div>

      {/* ── Content ── */}
      {loading ? (
        /* Spinner */
        <div style={{ display: "flex", justifyContent: "center", padding: "60px 0" }}>
          <div
            style={{
              width: "24px",
              height: "24px",
              border: "2px solid rgba(255,255,255,0.08)",
              borderTopColor: "#3B82F6",
              borderRadius: "50%",
              animation: "spin 0.8s linear infinite",
            }}
          />
        </div>
      ) : filtered.length === 0 ? (
        /* Empty state */
        <div
          style={{
            ...CARD_STYLE,
            padding: "48px",
            textAlign: "center",
            color: "var(--color-text-tertiary)",
            fontSize: "13px",
          }}
        >
          {search ? "No batches match your search." : "No batches in this category."}
        </div>
      ) : (
        /* Card grid */
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(380px, 1fr))",
            gap: "14px",
          }}
        >
          {filtered.map((b) => (
            <BatchCard
              key={b.id}
              batch={b}
              onClick={() => navigate(ROUTES.BATCH_DETAIL(b.id))}
            />
          ))}
        </div>
      )}

      {/* Spin animation */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
