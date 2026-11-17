import { DEMO_MODE } from "./config";

/** Thin strip shown above the app shell while Demo Mode is on. */
export function DemoBanner() {
  if (!DEMO_MODE) return null;
  return (
    <div
      role="status"
      style={{
        background: "rgba(245, 158, 11, 0.15)",
        borderBottom: "1px solid rgba(245, 158, 11, 0.4)",
        color: "rgb(252, 211, 77)",
        fontSize: "12px",
        fontWeight: 500,
        padding: "6px 16px",
        textAlign: "center",
      }}
    >
      Demo mode — sample data, changes are not saved.
    </div>
  );
}
