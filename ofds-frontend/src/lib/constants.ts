import type { BatchStage, UserRole } from "./types";

// ── Roles ──

export const ROLES = {
  USER: "user" as UserRole,
  ADMIN: "admin" as UserRole,
  SUPER_ADMIN: "super_admin" as UserRole,
} as const;

// ── Batch Stages ──

export const STAGE_LABELS: Record<BatchStage, string> = {
  1: "Deposited",
  2: "Transferred",
  3: "Deployed",
  4: "Active",
};

export const STAGE_DESCRIPTIONS: Record<BatchStage, string> = {
  1: "Investments deposited into batch",
  2: "Funds transferred to custodian",
  3: "Deployment confirmed with date",
  4: "Batch is actively trading",
};

// ── Routes ──

export const ROUTES = {
  // Public
  LANDING: "/",

  // Auth
  LOGIN: "/login",
  REGISTER: "/register",

  // Dashboard
  OVERVIEW: "/overview",

  // Batches
  BATCHES: "/batches",
  BATCH_CREATE: "/batches/new",
  BATCH_DETAIL: (id: number | string) => `/batches/${id}`,
  BATCH_PERFORMANCE: (id: number | string) => `/batches/${id}/performance`,

  // Funds area (product_type = FUNDS)
  FUNDS: "/funds",
  FUND_MANAGE: "/funds",
  FUND_DETAIL: (id: number | string) => `/funds/${id}`,
  FUNDS_BATCHES: "/funds/batches",
  FUNDS_BATCH_CREATE: "/funds/batches/new",
  FUNDS_INVESTORS: "/funds/investors",
  FUNDS_VALUATIONS: "/funds/valuations",
  FUNDS_VALUATION_CREATE: "/funds/valuations/new",

  // Shares area (product_type = SHARES, i.e. DPRP)
  SHARES: "/shares",
  SHARE_DETAIL: (id: number | string) => `/shares/${id}`,
  SHARES_BATCHES: "/shares/batches",
  SHARES_BATCH_CREATE: "/shares/batches/new",
  SHARES_INVESTORS: "/shares/investors",
  SHARES_VALUATIONS: "/shares/valuations",
  SHARES_VALUATION_CREATE: "/shares/valuations/new",

  // Valuations — legacy combined paths, redirected into /funds/valuations (see routes/index.tsx)
  VALUATIONS: "/valuations",
  VALUATION_CREATE: "/valuations/new",

  // Reports
  REPORTS: "/reports",
  REPORT_DETAIL: (id: number | string) => `/reports/${id}`,
  PORTFOLIO: "/reports/portfolio",

  // Withdrawals
  WITHDRAWALS: "/withdrawals",

  // Email
  EMAIL: "/email",

  // Users
  USERS: "/users",
  INVESTORS: "/investors",
  INVESTOR_ADD: "/investors/add",
  INVESTOR_BULK_UPLOAD: "/investors/bulk-upload",
  INVESTOR_OVERVIEW: (clientCode: string) => `/investors/${encodeURIComponent(clientCode)}`,
  INVESTOR_STATEMENT: (clientCode: string) => `/investors/${encodeURIComponent(clientCode)}/statement`,

  // Super Admin
  AUDIT_LOG: "/audit-log",
  BACKUPS: "/backups",

  // Settings
  SETTINGS: "/settings",
} as const;

// ── API Paths ──

export const API = {
  // Auth
  LOGIN: "/login",
  REGISTER: "/users",
  USERS: "/users",
  USER_BY_ID: (id: number) => `/users/${id}`,
  APPROVE_USER: (id: number) => `/users/${id}/approve`,
  SET_USER_ROLE: (id: number) => `/users/${id}/role`,
  SET_USER_STATUS: (id: number) => `/users/${id}/status`,
  RESET_USER_PASSWORD: (id: number) => `/users/${id}/reset-password`,
  EMPLOYEES: "/employees",

  // Batches
  BATCHES: "/batches",
  BATCH_BY_ID: (id: number) => `/batches/${id}`,
  BATCH_INVESTMENTS_LIGHT: (id: number) => `/batches/${id}/investments-light`,
  BATCH_SUMMARY: (id: number) => `/batches/${id}/summary`,
  BATCH_FUNDS: (id: number) => `/batches/${id}/funds`,
  BATCH_UPLOAD_EXCEL: (id: number) => `/batches/${id}/upload-excel`,
  BATCH_TOGGLE_ACTIVE: (id: number) => `/batches/${id}/toggle-active`,
  BATCH_EMAIL_LOGS: (id: number) => `/batches/${id}/email-logs`,
  SHARES_TRANSFER_PREVIEW: (id: number) => `/batches/${id}/shares-transfer-preview`,
  SHARES_DEPLOYMENT_PREVIEW: (id: number) => `/batches/${id}/shares-deployment-preview`,
  BATCH_INVESTMENTS_EXPORT: (id: number) => `/batches/${id}/investments/export`,

  // Investments
  INVESTMENTS: "/investments",
  INVESTOR_DIRECTORY: "/investors",
  INVESTOR_DIRECTORY_EXPORT: "/investors/export",
  INVESTOR_CREATE: "/investors",
  INVESTOR_EXISTING_DEPOSIT: "/investors/existing",
  BULK_UPLOAD_TEMPLATE: "/bulk-upload/template",
  BULK_UPLOAD_MAPPING: "/bulk-upload/mapping",
  BULK_UPLOAD_VALIDATE: "/bulk-upload/validate",
  BULK_UPLOAD_COMMIT: "/bulk-upload/commit",
  BULK_UPLOAD_JOBS: "/bulk-upload/jobs",
  INVESTOR_EMAIL_LOGS: (clientCode: string) => `/investors/${encodeURIComponent(clientCode)}/email-logs`,
  INVESTOR_DEPOSITS: (clientCode: string) => `/investors/${encodeURIComponent(clientCode)}/deposits`,

  // Withdrawals
  WITHDRAWALS: "/withdrawals",
  WITHDRAWALS_UPLOAD: "/withdrawals/upload",

  // Emails
  EMAILS_PENDING: "/emails/pending",
  EMAILS_INBOX: "/emails/inbox",
  EMAILS_PROCESSED: "/emails/processed",
  EMAIL_CONFIRM: (id: number) => `/emails/${id}/confirm`,
  EMAIL_CANCEL: (id: number) => `/emails/${id}/cancel`,
  EMAIL_CONFIRM_BATCH: "/emails/confirm-batch",
  EMAIL_CONFIRM_ALL: "/emails/confirm-all",
  EMAIL_SUPPRESS_ALL: "/emails/suppress-all",
  EMAIL_CANCEL_BATCH: "/emails/cancel-batch",
  EMAIL_QUEUE_STATUS: "/emails/queue-status",
  EMAIL_STATEMENTS_QUEUE_BATCH: "/emails/statements/queue-batch",

  // Funds
  FUNDS: "/funds",
  FUNDS_SUMMARY: "/funds/summary",
  FUND_CLASSES: (fundId: number | string) => `/funds/${fundId}/classes`,

  // Shares (Task 8/9 — same endpoints as Funds, product=SHARES)
  SHARES: "/shares",
  SHARES_SUMMARY: "/shares/summary",
  SHARE_CLASSES: (fundId: number | string) => `/shares/${fundId}/classes`,

  // Performance
  BATCH_PERFORMANCE: (batchId: number) => `/batches/${batchId}/performance`,
  BATCH_PRO_RATA: (batchId: number) => `/batches/${batchId}/calculate-pro-rata`,
  BATCH_DISTRIBUTIONS: (batchId: number) => `/batches/${batchId}/distributions`,
  PERFORMANCE_UPLOAD_EXCEL: "/performance/upload-excel",

  // Valuation
  VALUATION_EPOCH: "/valuation/epoch",
  VALUATION_CONFIRM: "/valuation/confirm",
  VALUATION_DRY_RUN: "/valuation/dry-run",
  VALUATION_FUNDS: "/valuation/funds",
  VALUATION_PREVIEW: "/valuation/preview",
  VALUATION_NAV: "/valuation/nav",
  VALUATION_JOBS: "/valuation/jobs",
  VALUATION_NAV_RUNS: "/valuation/nav/runs",
  VALUATION_NAV_RUN_DATE: "/valuation/nav/runs/date",
  VALUATION_BATCH_HISTORY: (batchId: number) => `/valuation/batch/${batchId}`,

  // Reports
  REPORTS: "/reports",
  REPORT_BY_ID: (id: number) => `/reports/${id}`,
  REPORT_PDF: (id: number) => `/reports/${id}/pdf`,
  INVESTOR_STATEMENT: (batchId: number, email: string) => `/reports/investor-statement/${batchId}/${encodeURIComponent(email)}`,
  INVESTOR_STATEMENT_PDF: (email: string) => `/reports/investor/${email}/pdf`,
  INVESTOR_STATEMENT_PDF_CLIENT: (clientCode: string) => `/investors/${encodeURIComponent(clientCode)}/statement/pdf`,
  INVESTOR_WITHDRAWAL_PDF: (clientCode: string, withdrawalId: number) => `/investors/${encodeURIComponent(clientCode)}/withdrawals/${withdrawalId}/pdf`,
  INVESTOR_DEPOSIT_PDF: (clientCode: string, batchId: number) => `/investors/${encodeURIComponent(clientCode)}/deposits/${batchId}/pdf`,
  VERIFY_HASH_CHAIN: (investorCode: string, fundName: string) => `/reports/verify-hash-chain/${investorCode}/${fundName}`,
  PORTFOLIO: "/reports/portfolio",
  PORTFOLIO_MULTI_BATCH: "/reports/portfolio/multi-batch",
  BATCH_SUMMARY_EXCEL: (id: number) => `/reports/batch/${id}/summary-excel`,
  BATCH_RECONCILIATION: (id: number) => `/reports/batch/${id}/reconciliation`,

  // Report statement generation (BLOCKING features)
  REPORTS_ELIGIBLE_INVESTORS: "/reports/eligible-investors",
  REPORTS_GENERATE: "/reports/generate",
  REPORTS_RUNS: "/reports/runs",
  REPORTS_RUN_BY_ID: (id: number | string) => `/reports/runs/${id}`,

  // Overview statistics
  OVERVIEW_STATS: "/stats/overview",
  TRANSACTIONS_RECENT: "/transactions/recent",

  // Audit (backend dependency — endpoint may not exist yet)
  AUDIT_LOGS: "/audit-logs",
  AUDIT_LOGS_EXPORT: "/audit-logs/export",
  RECENT_NOTIFICATIONS: "/batches/notifications/recent",

  // Backups
  BACKUPS: "/backups",
  BACKUPS_STATUS: "/backups/status",
  BACKUPS_RUN_NOW: "/backups/run-now",

  // Client Activity
  CLIENT_ACTIVITY: "/reports/client-activity",
  CLIENT_ACTIVITY_EXCEL: "/reports/client-activity/excel",
  CLIENT_ACTIVITY_PDF: "/reports/client-activity/pdf",

  // Daily Activity (all investors, one date)
  DAILY_ACTIVITY: "/reports/daily-activity",
  DAILY_ACTIVITY_EXCEL: "/reports/daily-activity/excel",
  DAILY_ACTIVITY_PDF: "/reports/daily-activity/pdf",

  // Withdrawals export (filterable by fund, status, source, date range)
  WITHDRAWALS_EXPORT_EXCEL: "/reports/withdrawals/excel",
  WITHDRAWALS_EXPORT_PDF: "/reports/withdrawals/pdf",

  // Settings (super_admin only)
  SETTINGS_EMAIL: "/settings/email",
  SETTINGS_EMAIL_TEST: "/settings/email/test",
  SETTINGS_EMAIL_QUEUE: "/settings/email-queue",
} as const;

// ── Chart Colors (mapped to fund identity) ──

export const FUND_COLORS: Record<string, string> = {
  axiom: "#3B6FD4",
  atium: "#3DBB78",
  default: "#D4940B",
};

export const CHART_COLORS = {
  deposit: "#3DBB78",
  withdrawal: "#D44B4B",
  grid: "#1E293B",
  label: "#94A3B8",
  tooltipBg: "#0B1228",
  tooltipBorder: "#1E293B",
} as const;
