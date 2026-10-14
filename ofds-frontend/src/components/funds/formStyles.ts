import type React from "react";

// Shared input styling for the Fund/Share and Share Class forms — moved here
// unchanged from FundListPage (Task 12) so the Create and Edit forms on the
// list and detail pages render identically.

export const inputStyle: React.CSSProperties = {
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

export const selectStyle: React.CSSProperties = {
  ...inputStyle,
  cursor: "pointer",
  appearance: "none",
  paddingRight: "32px",
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none'%3E%3Cpath d='M3 5L6 8L9 5' stroke='%2394A3B8' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E")`,
  backgroundRepeat: "no-repeat",
  backgroundPosition: "right 12px center",
  backgroundSize: "12px",
};

export const readOnlyStyle: React.CSSProperties = {
  ...inputStyle,
  background: "rgba(255,255,255,0.03)",
  color: "var(--color-text-tertiary)",
  cursor: "not-allowed",
};

export const labelStyle: React.CSSProperties = {
  fontSize: "11px",
  fontWeight: 500,
  color: "#94A3B8",
  marginBottom: "6px",
  display: "block",
};

export const errorTextStyle: React.CSSProperties = {
  fontSize: "11px",
  color: "#f87171",
  marginTop: "6px",
};

export const hintTextStyle: React.CSSProperties = {
  fontSize: "11px",
  color: "var(--color-text-tertiary)",
  marginTop: "6px",
};

export const formCardStyle: React.CSSProperties = {
  background: "rgba(16,24,45,0.72)",
  backdropFilter: "blur(20px) saturate(150%)",
  border: "1px solid rgba(255,255,255,0.07)",
};

export const cancelButtonStyle: React.CSSProperties = {
  padding: "11px 24px",
  borderRadius: "8px",
  border: "1px solid rgba(255,255,255,0.15)",
  background: "transparent",
  color: "var(--color-text-secondary)",
  fontSize: "13px",
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.15s",
};

export function primaryButtonStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "11px 24px",
    borderRadius: "8px",
    border: "none",
    background: "#1A45FF",
    color: "#fff",
    fontSize: "13px",
    fontWeight: 600,
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1,
    boxShadow: "0 0 20px rgba(26,69,255,0.35)",
  };
}

export function withError(style: React.CSSProperties, hasError: boolean): React.CSSProperties {
  return hasError ? { ...style, borderColor: "rgba(239,68,68,0.6)" } : style;
}

export function handleFocus(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
  e.target.style.borderColor = "#3B82F6";
  e.target.style.boxShadow = "0 0 0 3px rgba(59,130,246,0.15)";
  e.target.style.background = "rgba(0,0,0,0.35)";
}

export function handleBlur(e: React.FocusEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) {
  e.target.style.borderColor = "rgba(255,255,255,0.1)";
  e.target.style.boxShadow = "none";
  e.target.style.background = "rgba(0,0,0,0.25)";
}

export function hoverCancel(e: React.MouseEvent<HTMLButtonElement>, on: boolean) {
  const el = e.currentTarget;
  el.style.borderColor = on ? "rgba(255,255,255,0.25)" : "rgba(255,255,255,0.15)";
  el.style.background = on ? "rgba(255,255,255,0.05)" : "transparent";
}

/** Normalised API error (Flask returns {message, errors?, code?, blockers?}). */
export interface ApiFormError {
  status?: number;
  message: string;
  code?: string;
  errors: Record<string, string>;
  blockers: string[];
  canOverride: boolean;
}

export function parseApiError(err: unknown, fallback: string): ApiFormError {
  const res = (err as { response?: { status?: number; data?: any } })?.response;
  const data = res?.data ?? {};
  return {
    status: res?.status,
    message: typeof data.message === "string" && data.message ? data.message : fallback,
    code: typeof data.code === "string" ? data.code : undefined,
    errors: data.errors && typeof data.errors === "object" ? data.errors : {},
    blockers: Array.isArray(data.blockers) ? data.blockers : [],
    canOverride: data.can_override === true,
  };
}
