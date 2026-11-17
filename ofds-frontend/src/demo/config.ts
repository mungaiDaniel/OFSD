/** Demo mode serves every API call from an in-memory mock (see ./adapter.ts). */
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";

export const DEMO_USER = {
  email: "demo@example.com",
  name: "Demo User",
  role: "super_admin" as const,
};
