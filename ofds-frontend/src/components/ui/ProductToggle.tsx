export type ProductFilterValue = "ALL" | "FUNDS" | "SHARES";

interface ProductToggleOption {
  value: ProductFilterValue;
  label: string;
}

const DEFAULT_OPTIONS: ProductToggleOption[] = [
  { value: "FUNDS", label: "Funds" },
  { value: "SHARES", label: "Shares" },
];

export const OVERVIEW_PRODUCT_OPTIONS: ProductToggleOption[] = [
  { value: "ALL", label: "All" },
  { value: "FUNDS", label: "Funds" },
  { value: "SHARES", label: "Shares" },
];

interface ProductToggleProps {
  value: ProductFilterValue;
  onChange: (value: ProductFilterValue) => void;
  /** Defaults to Funds | Shares (no "All"); pass OVERVIEW_PRODUCT_OPTIONS for a 3-way toggle. */
  options?: ProductToggleOption[];
  label?: string;
}

/**
 * Funds | Shares segmented control — reused by the Overview product filter
 * (3-way, with "All") and the Add Investor / Bulk Upload product selector
 * (2-way). Picking a value is a deliberate step, never defaulted silently to
 * one product without the caller choosing it first.
 */
export function ProductToggle({ value, onChange, options = DEFAULT_OPTIONS, label }: ProductToggleProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      {label && (
        <label
          style={{
            fontSize: "10px",
            fontWeight: 600,
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: "var(--color-text-tertiary)",
          }}
        >
          {label}
        </label>
      )}
      <div
        role="group"
        aria-label={label || "Product"}
        style={{
          display: "inline-flex",
          padding: "3px",
          borderRadius: "10px",
          background: "rgba(0,0,0,0.25)",
          border: "1px solid rgba(255,255,255,0.08)",
          gap: "2px",
        }}
      >
        {options.map((opt) => {
          const active = opt.value === value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(opt.value)}
              style={{
                padding: "6px 14px",
                borderRadius: "7px",
                border: "none",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s",
                background: active ? "var(--color-brand-400, #3B82F6)" : "transparent",
                color: active ? "#fff" : "var(--color-text-secondary)",
              }}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
