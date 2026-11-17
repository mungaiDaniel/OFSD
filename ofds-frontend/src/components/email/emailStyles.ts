import type { CSSProperties } from "react";

export const inputStyle: CSSProperties = {
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.1)",
  borderRadius: "8px",
  color: "var(--color-text-primary)",
  fontSize: "12px",
  padding: "8px 10px",
  outline: "none",
};

export const selectStyle: CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
  appearance: "none",
  paddingRight: "28px",
  background: `rgba(0,0,0,0.25) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%2394A3B8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") no-repeat right 8px center`,
};

export const btn = (disabled: boolean, variant: "primary" | "ghost" = "ghost"): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 14px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: 600,
  cursor: disabled ? "not-allowed" : "pointer",
  opacity: disabled ? 0.6 : 1,
  border: variant === "primary" ? "none" : "1px solid rgba(255,255,255,0.1)",
  background: variant === "primary" ? "rgb(26, 69, 255)" : "rgba(255,255,255,0.05)",
  color: variant === "primary" ? "#fff" : "var(--color-text-secondary)",
});

export const fieldLabel: CSSProperties = {
  display: "block",
  fontSize: "11px",
  color: "var(--color-text-tertiary)",
  marginBottom: "6px",
};
