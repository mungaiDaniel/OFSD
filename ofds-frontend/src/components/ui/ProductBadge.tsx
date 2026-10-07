import type { ProductType } from "@/lib/types";

/**
 * Small "Funds" / "Shares" badge for page headers — lets an admin always tell
 * which area (NAV-based Funds vs. price-per-share Shares) they're looking at.
 */
export function ProductBadge({ product }: { product: ProductType }) {
  const isShares = product === "SHARES";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 9px",
        borderRadius: "100px",
        fontSize: "10px",
        fontWeight: 700,
        letterSpacing: "0.04em",
        textTransform: "uppercase",
        background: isShares ? "rgba(212, 148, 11, 0.12)" : "rgba(59, 130, 246, 0.12)",
        border: isShares ? "1px solid rgba(212, 148, 11, 0.3)" : "1px solid rgba(59, 130, 246, 0.3)",
        color: isShares ? "#D4940B" : "#60A5FA",
      }}
    >
      {isShares ? "Shares" : "Funds"}
    </span>
  );
}
