import { useState } from "react";
import { inputStyle, selectStyle, hintTextStyle } from "@/components/funds/formStyles";

// Shares (DPRP) holdings are NGN after deployment. This is a display-only
// "view in USD" switch: the user types an NGN-per-USD rate and NGN figures are
// divided by it on screen. Nothing is saved server-side; the rate is
// remembered per browser so it doesn't have to be retyped on every page.

const RATE_STORAGE_KEY = "ofds.sharesNgnPerUsdRate";

function readStoredRate(): string {
  try {
    return localStorage.getItem(RATE_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export interface NgnUsdView {
  viewCurrency: "NGN" | "USD";
  setViewCurrency: (c: "NGN" | "USD") => void;
  rateText: string;
  setRateText: (r: string) => void;
  /** True when USD is selected and a usable rate has been entered. */
  showingUsd: boolean;
  /** Currency the converted figures are in ("NGN" until a valid rate is set). */
  displayCurrency: "NGN" | "USD";
  /** NGN amount -> amount in displayCurrency. */
  convert: (ngn: number) => number;
}

export function useNgnUsdView(): NgnUsdView {
  const [viewCurrency, setViewCurrency] = useState<"NGN" | "USD">("NGN");
  const [rateText, setRateTextState] = useState<string>(readStoredRate);

  const setRateText = (r: string) => {
    setRateTextState(r);
    try {
      localStorage.setItem(RATE_STORAGE_KEY, r);
    } catch {
      // storage unavailable — the rate just won't be remembered
    }
  };

  const rate = Number(rateText);
  const showingUsd = viewCurrency === "USD" && Number.isFinite(rate) && rate > 0;

  return {
    viewCurrency,
    setViewCurrency,
    rateText,
    setRateText,
    showingUsd,
    displayCurrency: showingUsd ? "USD" : "NGN",
    convert: (ngn: number) => (showingUsd ? ngn / rate : ngn),
  };
}

export function NgnUsdViewControl({ view, compact = false }: { view: NgnUsdView; compact?: boolean }) {
  const needsRate = view.viewCurrency === "USD" && !view.showingUsd;
  const fieldStyle = compact ? { padding: "6px 10px", fontSize: "12px" } : {};
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px" }}>
      <label style={{ fontSize: "11px", color: "var(--color-text-tertiary)" }} htmlFor="ngn-usd-view-currency">
        View in
      </label>
      <select
        id="ngn-usd-view-currency"
        aria-label="View shares values in"
        value={view.viewCurrency}
        onChange={(e) => view.setViewCurrency(e.target.value as "NGN" | "USD")}
        style={{ ...selectStyle, ...fieldStyle, width: "auto", paddingRight: "28px" }}
      >
        <option value="NGN">NGN</option>
        <option value="USD">USD</option>
      </select>
      {view.viewCurrency === "USD" && (
        <>
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            placeholder="NGN per 1 USD"
            aria-label="Exchange rate, NGN per 1 USD"
            value={view.rateText}
            onChange={(e) => view.setRateText(e.target.value)}
            style={{ ...inputStyle, ...fieldStyle, width: "140px" }}
          />
          <span style={{ ...hintTextStyle, marginTop: 0, color: needsRate ? "#F59E0B" : hintTextStyle.color }}>
            {needsRate ? "Enter a rate to convert" : `₦${Number(view.rateText).toLocaleString("en-US")} = $1`}
          </span>
        </>
      )}
    </div>
  );
}
