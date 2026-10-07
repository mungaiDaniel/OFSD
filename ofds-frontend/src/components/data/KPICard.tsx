import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

interface KPICardProps {
  label: string;
  value: string;
  subtitle?: string;
  trend?: { value: string; direction: "up" | "down" | "neutral" };
  className?: string;
  valueSize?: string;
  valueColor?: string;
  onClick?: () => void;
  clickable?: boolean;
}

export function KPICard({ label, value, subtitle, trend, className, valueSize = "2rem", valueColor, onClick, clickable }: KPICardProps) {
  return (
    <div 
      className={cn("card shadow p-3 p-md-4", className, clickable && "cursor-pointer hover:shadow-lg transition-shadow")}
      onClick={clickable ? onClick : undefined}
      style={clickable ? { cursor: "pointer" } : undefined}
    >
      {/* Header row */}
      <div className="d-flex align-items-center justify-content-between mb-2">
        <span
          className="small fw-bold text-uppercase"
          style={{ color: "var(--color-text-secondary)", fontSize: "11px", letterSpacing: "0.04em" }}
        >
          {label}
        </span>
        {trend && <TrendBadge trend={trend} />}
      </div>

      {/* Main value */}
      <p
        className="mb-1 kpi-value-glow fw-bold"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: valueSize,
          lineHeight: 1.1,
          color: valueColor 
            ? valueColor 
            : trend?.direction === "up"
            ? "var(--color-success)"
            : trend?.direction === "down"
            ? "var(--color-destructive)"
            : "var(--color-text-primary)",
        }}
      >
        {value}
      </p>

      {/* Subtitle */}
      {subtitle && (
        <p className="mb-0" style={{ color: "var(--color-text-tertiary)", fontSize: "11px" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}

function TrendBadge({ trend }: { trend: { value: string; direction: "up" | "down" | "neutral" } }) {
  const color =
    trend.direction === "up"
      ? "var(--color-success)"
      : trend.direction === "down"
        ? "var(--color-destructive)"
        : "var(--color-text-tertiary)";

  const Icon =
    trend.direction === "up"
      ? TrendingUp
      : trend.direction === "down"
        ? TrendingDown
        : Minus;

  return (
    <span className="d-flex align-items-center gap-1 fw-bold" style={{ color, fontSize: "11px" }}>
      <Icon size={12} />
      {trend.value}
    </span>
  );
}
