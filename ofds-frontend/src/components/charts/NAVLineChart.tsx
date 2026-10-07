import { useState, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { FundClassSummary } from "@/lib/types";

// ── Color palettes per currency ──────────────────────────────────────────────
const KES_COLORS = ["#F59E0B", "#FBBF24", "#D97706", "#FCD34D", "#92400E"];
const USD_COLORS = ["#3B82F6", "#60A5FA", "#2563EB", "#93C5FD", "#1D4ED8"];

// ── Date formatter for X axis ─────────────────────────────────────────────────
// Includes the day — "month + 2-digit year" alone (e.g. "Sep 26") reads as
// "26th of some month" when it actually means "September '26", which is
// exactly backwards from what a viewer expects on a day-level NAV chart.
function formatDateLabel(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "2-digit" });
  } catch {
    return dateStr;
  }
}

// ── Friendly date display ─────────────────────────────────────────────────────
function formatFriendlyDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  } catch {
    return dateStr;
  }
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
function NAVTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: "#1e293b",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: "8px",
        padding: "10px 14px",
        fontSize: "11px",
      }}
    >
      <div style={{ color: "#94a3b8", marginBottom: "6px", fontFamily: "var(--font-mono)" }}>
        {label}
      </div>
      {payload.map((p: any) => (
        <div
          key={p.dataKey}
          style={{ color: p.color, fontFamily: "var(--font-mono)", fontWeight: 600 }}
        >
          {p.name}: {p.value != null ? Number(p.value).toFixed(4) : "—"}
        </div>
      ))}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────
interface NAVLineChartProps {
  classes: FundClassSummary[];
  currency: "KES" | "USD";
  title?: string;
  asOfDate?: string;
}

export function NAVLineChart({ classes, currency, title, asOfDate }: NAVLineChartProps) {
  const isKES = currency === "KES";
  const palette = isKES ? KES_COLORS : USD_COLORS;
  const currencyColor = isKES ? "var(--color-kes)" : "var(--color-usd)";

  // Only classes with at least one nav_history point
  const activeClasses = classes
    .filter((c) => c.nav_history && c.nav_history.length >= 1)
    .map((c, idx) => ({
      ...c,
      color: palette[idx % palette.length] ?? palette[0],
    }));

  // Visibility state per class id
  const [visible, setVisible] = useState<Record<number | string, boolean>>(
    () => Object.fromEntries(activeClasses.map((c) => [c.id ?? c.class_code ?? c.class_name, true]))
  );

  const toggleClass = useCallback((id: number | string) => {
    setVisible((prev) => {
      const visibleCount = Object.values(prev).filter(Boolean).length;
      // Never hide the last visible class
      if (prev[id] && visibleCount <= 1) return prev;
      return { ...prev, [id]: !prev[id] };
    });
  }, []);

  // Build recharts data: one row per date, columns = class_code
  const allDates = new Set<string>();
  activeClasses.forEach((c) => c.nav_history?.forEach((h) => allDates.add(h.date)));
  const sortedDates = [...allDates].sort();

  const chartData = sortedDates.map((date) => {
    const row: Record<string, any> = { date };
    activeClasses.forEach((c) => {
      const entry = c.nav_history?.find((h) => h.date === date);
      const key = c.class_code ?? c.class_name;
      row[key] = entry?.nav ?? null;
    });
    return row;
  });

  if (activeClasses.length === 0) {
    return (
      <div
        style={{
          padding: "32px",
          textAlign: "center",
          color: "var(--color-text-tertiary)",
          fontSize: "12px",
        }}
      >
        No {currency} valuation history yet
      </div>
    );
  }

  // With a single NAV point, a line chart has nothing to draw a trend across —
  // Recharts still renders an axis with two ticks in that case, and since both
  // ticks land on the one real date, it shows that same date twice, which
  // reads as wrong/duplicated dates rather than "only one valuation so far."
  if (sortedDates.length === 1) {
    return (
      <div style={{ padding: "12px 0" }}>
        {(title || asOfDate) && (
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px" }}>
            <div>
              {title && (
                <div style={{ fontSize: "10px", fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-text-tertiary)", marginBottom: "2px" }}>
                  {title}
                </div>
              )}
              {asOfDate && (
                <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>as of {formatFriendlyDate(asOfDate)}</div>
              )}
            </div>
          </div>
        )}
        <div style={{ textAlign: "center", padding: "24px 0", color: "var(--color-text-tertiary)", fontSize: "12px" }}>
          Only one {currency} valuation on file so far ({formatFriendlyDate(sortedDates[0] ?? "")}) — a trend line
          will appear once there's more than one.
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", justifyContent: "center" }}>
          {activeClasses.map((c) => {
            const key = c.class_code ?? c.class_name;
            const point = c.nav_history?.find((h) => h.date === sortedDates[0]);
            return (
              <span key={c.id ?? key} style={{ fontFamily: "var(--font-mono)", fontSize: "12px", fontWeight: 700, color: c.color }}>
                {key}: {point?.nav != null ? point.nav.toFixed(4) : "—"}
              </span>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      {(title || asOfDate) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "16px",
          }}
        >
          <div>
            {title && (
              <div
                style={{
                  fontSize: "10px",
                  fontWeight: 600,
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: "var(--color-text-tertiary)",
                  marginBottom: "2px",
                }}
              >
                {title}
              </div>
            )}
            {asOfDate && (
              <div style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }}>
                as of {formatFriendlyDate(asOfDate)}
              </div>
            )}
          </div>
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
              background: isKES ? "var(--color-kes-bg)" : "var(--color-usd-bg)",
              color: currencyColor,
              border: isKES
                ? "1px solid var(--color-kes-border)"
                : "1px solid var(--color-usd-border)",
            }}
          >
            {currency}
          </span>
        </div>
      )}

      {/* Chart */}
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDateLabel}
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
            content={<NAVTooltip />}
            cursor={{ stroke: "rgba(255,255,255,0.12)", strokeWidth: 1, strokeDasharray: "4 2" }}
          />
          {activeClasses.map((c) => {
            const key = c.class_code ?? c.class_name;
            const id = c.id ?? key;
            const isVisible = visible[id] ?? true;
            return (
              <Line
                key={id}
                type="monotone"
                dataKey={key}
                name={key}
                stroke={c.color}
                strokeWidth={isVisible ? 2 : 0}
                dot={{ r: 3, fill: c.color, strokeWidth: 0 }}
                activeDot={{ r: 5, fill: c.color, strokeWidth: 0 }}
                opacity={isVisible ? 1 : 0}
                connectNulls
              />
            );
          })}
        </LineChart>
      </ResponsiveContainer>

      {/* Legend toggles */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "10px", marginTop: "12px" }}>
        {activeClasses.map((c) => {
          const key = c.class_code ?? c.class_name;
          const id = c.id ?? key;
          const isVisible = visible[id] ?? true;
          const visibleCount = Object.values(visible).filter(Boolean).length;
          const isLast = isVisible && visibleCount <= 1;
          return (
            <button
              key={id}
              onClick={() => toggleClass(id)}
              title={isLast ? "At least one class must remain visible" : ""}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "7px",
                padding: "4px 10px",
                borderRadius: "6px",
                background: isVisible ? "rgba(255,255,255,0.05)" : "transparent",
                border: `1px solid ${isVisible ? c.color + "44" : "rgba(255,255,255,0.06)"}`,
                cursor: isLast ? "not-allowed" : "pointer",
                opacity: isVisible ? 1 : 0.4,
                transition: "all 0.15s",
              }}
            >
              <span
                style={{
                  width: "20px",
                  height: "2px",
                  borderRadius: "1px",
                  background: c.color,
                  textDecoration: isVisible ? "none" : "line-through",
                }}
              />
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "10px",
                  fontWeight: 700,
                  color: isVisible ? c.color : "var(--color-text-tertiary)",
                  textDecoration: isVisible ? "none" : "line-through",
                }}
              >
                {key}
              </span>
              {c.current_nav != null && (
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "10px",
                    color: "var(--color-text-tertiary)",
                  }}
                >
                  {c.current_nav.toFixed(4)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
