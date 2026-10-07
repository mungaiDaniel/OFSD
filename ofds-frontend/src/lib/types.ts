// ============================================================================
// OFDS TypeScript Types — mirrors Flask/SQLAlchemy backend models
// ============================================================================

// ── Auth ──

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  created: string;
}

export type UserRole = "user" | "admin" | "super_admin";
export type UserStatus = "pending" | "active";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  role: UserRole;
  name?: string;
}

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
  // role is server-controlled (defaults to user)
  role?: string;
}

// ── Batches ──

export interface Batch {
  id: number;
  batch_name: string;
  certificate_number: string | null;
  total_principal: number;
  total_net_principal?: number;
  total_capital: number;
  date_deployed: string | null;
  duration_days: number;
  active_days?: number;
  expected_close_date: string | null;
  date_closed: string | null;
  is_active: boolean;
  is_transferred: boolean;
  deployment_confirmed: boolean;
  stage: BatchStage;
  status: BatchStatus;
  transaction_cost?: number;
  transfer_transaction_cost?: number;
  transfer_entry_fee_percent?: number;
  entry_fee_percentage?: number;
  batch_type?: string; // "Carried Forward" or "Fresh Start"
  investors_count: number;
  funds: FundBreakdown[];
  created_at: string | null;
  investments?: BatchInvestor[];
  grouped_by_fund?: Record<string, BatchFundGroup>;
  // Production fields for open-batch tracking
  is_open?: boolean;
  auto_close_at?: string | null;
  share_class_id?: number | null;
  class_code?: string | null;
  class_currency?: string | null; // e.g. "KES" or "USD"
  // Deployment NAV snapshot (set once the batch reaches stage 3 — Deployed)
  deployment_nav?: number | null;
  deployment_total_nav?: number | null;
  total_shares?: number | null;
  // Cheap aggregate — the latest deposit date across the whole batch, without
  // needing to load any investment rows client-side to compute it.
  latest_deposit_date?: string | null;
  investments_pagination?: { page: number; per_page: number; total: number; total_pages: number };
  // DPRP oversubscription pro-rata allocation (see is_dangote_dprp_fund on the backend).
  // is_dprp_fund gates whether the deploy modal offers the oversubscription toggle at all.
  is_dprp_fund?: boolean;
  is_oversubscribed?: boolean;
  allocation_rate?: number | null;
}

/** Cheap-fields-only investor row from GET /batches/:id/investments-light. */
export interface BatchInvestorLight {
  id: number;
  investor_name: string;
  internal_client_code: string;
  amount_deposited: number;
  main_balance: number;
  share_class_id: number | null;
  class_code: string | null;
  class_currency: string | null;
}

export interface BatchInvestor {
  id: number;
  investor_name: string;
  investor_email?: string;
  investor_phone?: string | null;
  internal_client_code: string;
  amount_deposited: number;
  fund_name?: string | null;
  fund_id?: number | null;
  date_deposited?: string | null;
  /** Ledger-computed fields returned by GET /batches/:id */
  opening_balance?: number;   // amount_deposited at deposit time
  main_balance?: number;      // post-transfer principal after transaction + entry fee deductions
  current_balance?: number;   // EpochLedger.end_balance for this batch's period
  market_value?: number;      // same as current_balance — current standing for this holding
  withdrawals?: number;       // EpochLedger.withdrawals captured in committed epoch
  profit?: number;            // EpochLedger.profit allocated to this investor
  performance_pct?: number | null;
  transaction_fee_usd?: number;
  entry_fee_usd?: number;
  shares_owned?: number | null;
  class_code?: string | null;
  class_currency?: string | null;
}

export interface BatchFundGroup {
  fund_id: number | null;
  fund_name: string;
  investor_count: number;
  total_principal: number;
  investors: BatchInvestor[];
}

export type BatchStage = 1 | 2 | 3 | 4;
export type BatchStatus = "Pending" | "Active" | "Closed";

export interface FundBreakdown {
  fund_name: string;
  total_principal: number;
  investors_count: number;
}

export interface CreateBatchRequest {
  batch_name: string;
  date_deployed?: string;
  certificate_number?: string;
  duration_days?: number;
}

export interface PatchBatchRequest {
  is_transferred?: boolean;
  is_active?: boolean;
  date_deployed?: string;
  deployment_confirmed?: boolean;
  stage?: number;
  transfer_transaction_cost?: number;
  transfer_entry_fee_percent?: number;
  entry_fee_percentage?: number;
}

// ── Investments ──

export interface Investment {
  id: number;
  investor_name: string;
  investor_email: string;
  investor_phone: string | null;
  internal_client_code: string;
  amount_deposited: number;
  date_deposited: string;
  date_transferred: string | null;
  fund_name: string | null;
  fund_id: number | null;
  batch_id: number;
  wealth_manager: string | null;
  IFA: string | null;
  contract_note: string | null;
  valuation: number | null;
  transaction_fee_usd?: number | null;
  entry_fee_usd?: number | null;
  main_balance?: number | null;
}

export interface CreateInvestmentRequest {
  batch_id: number;
  investor_name: string;
  investor_email: string;
  investor_phone?: string;
  internal_client_code: string;
  amount_deposited: number;
  date_deposited: string;
  fund_name?: string;
  wealth_manager?: string;
  IFA?: string;
  contract_note?: string;
}

export interface CreateNewInvestorRequest {
  investor_name: string;
  investor_email: string;
  investor_phone?: string;
  internal_client_code: string;
  fund_id: number;
  share_class_id: number;
  deposit_amount: number;
  deposit_date: string;
}

export interface AddExistingDepositRequest {
  internal_client_code: string;
  fund_id: number;
  share_class_id: number;
  deposit_amount: number;
  deposit_date: string;
}

// ── Investor Overview (GET /investors/<code>/overview) ──

export interface InvestorPosition {
  batch_id: number;
  batch_name: string;
  batch_stage: number;
  batch_is_active: boolean;
  batch_is_open: boolean;
  share_class_id: number | null;
  fund_name: string;
  class_code: string | null;
  currency: string | null;
  deposit_amount: number | null;
  shares: number | null;
  market_value: number | null;
  performance_pct: number | null;
  deployment_nav: number | null;
  current_nav: number | null;
  deployment_date: string | null;
  // Only set for a position that went through DPRP-style oversubscription
  // pro-rata allocation — real money that's neither invested nor lost, so
  // it's surfaced here rather than silently vanishing from the deposit total.
  refund_amount?: number | null;
  refund_status?: string | null;
}

// ── Client Activity Report ──

export type ClientActivityEventType = "deposit" | "withdrawal" | "valuation";

export interface ClientActivityEvent {
  type: ClientActivityEventType;
  date: string | null;
  fund_name: string | null;
  class_code: string | null;
  currency: string | null;
  amount: number | null;
  status: string | null;
}

export interface ClientActivityData {
  internal_client_code: string;
  investor_name: string | null;
  investor_email: string | null;
  investor_phone: string | null;
  positions: InvestorPosition[];
  events: ClientActivityEvent[];
}

export interface ClientActivityFilters {
  deposited_from?: string;
  deposited_to?: string;
  withdrawn_from?: string;
  withdrawn_to?: string;
  valued_from?: string;
  valued_to?: string;
}

export interface DailyActivitySummary {
  date_from: string;
  date_to: string;
  counts: { deposits: number; withdrawals: number; valuations: number };
  total_deposit_amount: number;
  total_withdrawal_amount: number;
}

// ── Settings (super_admin only) ──

export interface EmailSettingsData {
  mail_server: string | null;
  mail_port: number | null;
  mail_use_tls: boolean | null;
  mail_use_ssl: boolean | null;
  mail_username: string | null;
  mail_default_sender: string | null;
  mail_bcc: string | null;
  has_password: boolean;
  email_queue_batch_size: number | null;
  email_queue_interval_minutes: number | null;
}

export interface EmailSettingsUpdate {
  mail_server?: string;
  mail_port?: number;
  mail_use_tls?: boolean;
  mail_use_ssl?: boolean;
  mail_username?: string;
  mail_password?: string;
  mail_default_sender?: string;
  mail_bcc?: string;
}

export interface EmailQueueSettingsData {
  batch_size: number;
  interval_minutes: number;
  next_run_at: string | null;
  queued_count: number;
}

export interface InvestorOverviewData {
  internal_client_code: string;
  investor_name: string;
  investor_email: string | null;
  investor_phone: string | null;
  wealth_manager?: string | null;
  IFA?: string | null;
  contract_note?: string | null;
  current_batch: {
    batch_id: number | null;
    batch_name: string | null;
    stage: number | null;
    is_active: boolean | null;
    share_class_id: number | null;
    class_code: string | null;
    currency: string | null;
  };
  positions: InvestorPosition[];
}

// ── Email ──

export type PendingEmailStatus = "Pending_Confirmation" | "Queued" | "Suppressed" | "Confirmed" | "Failed";

export interface PendingEmail {
  id: number;
  email_type: string;
  status: PendingEmailStatus | null;
  recipient_email: string;
  recipient_name: string | null;
  subject: string;
  body: string;
  batch_name: string | null;
  fund_name: string | null;
  amount: number | null;
  batch_id: number | null;
  investor_id: number | null;
  currency_type: string;
  created_at: string | null;
  processed_at: string | null;
  initial_deposit_usd?: number | null;
  transaction_fee_usd?: number | null;
  entry_fee_usd?: number | null;
  entry_fee_percent?: number | null;
  main_balance?: number | null;
}

// ── Funds ──

export interface FundBatchSummary {
  batch_id: number;
  batch_name: string;
  total_aum: number;
  investor_count: number;
  date_deployed: string | null;
  is_active: boolean;
}

export interface CoreFund {
  id: number;
  fund_name: string;
  fund_code?: string;
  is_active: boolean;
  total_aum?: number;
  investor_count?: number;
  batches?: FundBatchSummary[];
}

export interface FundShareClass {
  id: number;
  core_fund_id?: number;
  class_name: string;
  class_code: string;
  currency: string;
  is_active?: boolean;
  current_nav?: number | null;
}

export interface FundClassSummary {
  id?: number;
  class_name: string;
  class_code?: string;
  currency?: string;
  is_active?: boolean;
  total_shares?: number;
  prev_nav?: number | null;
  current_nav?: number | null;
  total_nav?: number;
  total_invested?: number;
  gross_deposited?: number;
  refunds?: number;
  unrealized_gain?: number;
  withdrawals?: number;
  performance_pct?: number;
  valuation_date?: string;
  nav_history?: Array<{ date: string; nav: number }>;
}

export interface FundSummaryItem {
  id?: number;
  fund_name: string;
  fund_code?: string;
  is_active?: boolean;
  investors_count?: number;
  classes?: FundClassSummary[];
  totals_by_currency?: Record<string, number>;
  invested_by_currency?: Record<string, number>;
  gain_by_currency?: Record<string, number>;
  // Gross/Net holdings split (Overview page fund filter) — gross_deposited is
  // the raw "total ever deposited" figure; net_principal_after_refund is gross
  // minus transfer cost, entry fee, and any oversubscription refund;
  // net_holdings = net_principal_after_refund - withdrawals. Deliberately
  // distinct from totals_by_currency (current market value) — see
  // net_holdings_by_currency comment in OverviewPage.tsx. Not the same figure
  // as Batch.total_net_principal, which excludes the refund on purpose.
  gross_deposited_by_currency?: Record<string, number>;
  net_principal_after_refund_by_currency?: Record<string, number>;
  withdrawals_by_currency?: Record<string, number>;
  refunds_by_currency?: Record<string, number>;
  net_holdings_by_currency?: Record<string, number>;
  weighted_performance_pct?: number;
}

export interface FundsSummaryResponse {
  as_of_date: string;
  funds: FundSummaryItem[];
}

export interface Fund {
  id: number;
  batch_id: number;
  fund_name: string;
  certificate_number: string;
  total_capital: number;
  date_deployed: string;
  duration_days: number;
  date_closed: string | null;
  is_active: boolean;
}

// ── Performance ──

export interface Performance {
  performance_id: number;
  batch_id: number;
  fund_name: string;
  gross_profit: number;
  transaction_costs: number;
  net_profit: number;
  date_created: string | null;
}

export interface CreatePerformanceRequest {
  gross_profit: number;
  transaction_costs: number;
  date_closed?: string;
  fund_name?: string;
}

export interface ProRataDistribution {
  id: number;
  batch_id: number;
  fund_name: string;
  investment_id: number;
  internal_client_code: string;
  investor_name: string;
  days_active: number;
  weighted_capital: number;
  profit_share_percentage: number;
  profit_allocated: number;
  calculation_date: string;
}

// ── Valuation ──

export interface ValuationRun {
  id: number;
  core_fund_id: number;
  epoch_start: string;
  epoch_end: string;
  performance_rate: number;
  head_office_total: number;
  status: "Committed" | "Failed";
  created_at: string;
}

export interface NavValuationRunItem {
  share_class_id: number;
  share_class_code: string;
  core_fund_id: number;
  fund_name: string;
  currency: string;
  valuation_date: string;
  nav_per_share: number;
  opening_aum: number;
  closing_aum: number;
  profit: number;
  performance_pct: number;
  investors: number;
}

export interface NavClassInput {
  share_class_id: number;
  nav_per_share: number;
  total_fund_nav: number;
  total_fund_nav_from_axys?: number;
}

export interface NavValuationRequest {
  valuation_date: string;
  classes: NavClassInput[];
  dry_run?: boolean;
}

export interface NavInvestorPreview {
  client_code: string;
  shares: number;
  market_value: number;
  performance_pct: number;
}

export interface NavClassPreview {
  class_code: string;
  nav_per_share: number;
  total_shares: number;
  system_total_nav: number;
  head_office_nav: number;
  difference: number;
  status: "PASS" | "FAIL";
  investors: NavInvestorPreview[];
}

export interface NavValuationPreviewResponse {
  valuation_date: string;
  classes: NavClassPreview[];
}

// Commit (POST /valuation/nav) runs as a background job — its results shape
// omits the per-investor `investors` array NavClassPreview has (that would be
// a huge payload at 100k investors); investor_count is the count instead.
export interface NavClassCommitResult {
  class_code: string;
  nav_per_share: number;
  total_shares: number;
  system_total_nav: number;
  head_office_nav: number;
  difference: number;
  status: "PASS" | "FAIL";
  snapshots_created: number;
  investor_count: number;
}

export interface NavValuationCommitResults {
  valuation_date: string;
  classes: NavClassCommitResult[];
}

export type ValuationJobState = "queued" | "running" | "completed" | "failed";

export interface ValuationJobStatus {
  id: number;
  status: ValuationJobState;
  total_investors: number;
  processed_investors: number;
  snapshots_created: number;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  results?: NavValuationCommitResults;
}

export interface CreateValuationRequest {
  fund_id: number;
  start_date: string;
  end_date: string;
  performance_rate: number;
  head_office_total: number;
}

export interface EpochLedgerEntry {
  internal_client_code: string;
  fund_name: string;
  epoch_start: string;
  epoch_end: string;
  performance_rate: number;
  start_balance: number;
  deposits: number;
  withdrawals: number;
  profit: number;
  end_balance: number;
  previous_hash: string;
  current_hash: string;
}

// ── Reports ──

export interface EligibleInvestor {
  id: number;
  investor_name: string;
  investor_email: string | null;
  internal_client_code: string;
  fund_name: string;
  class_code: string;
  currency: string;
  last_statement_date: string | null;
  closing_balance: number;
  email_status: "ready" | "no_email" | "already_sent";
}

export interface ReportRunItem {
  id: number;
  period: string;
  fund_name: string | null;
  class_code: string | null;
  recipient_count: number;
  delivered_count: number;
  failed_count: number;
  pending_count: number;
  sent_at: string;
  sent_by: string | null;
  status: "pending" | "partial" | "sent" | "failed";
}


export interface ReportSummary {
  id: number;
  fund_id: number;
  fund_name: string;
  epoch_start: string;
  epoch_end: string;
  performance_rate_percent: number;
  head_office_total: number;
  summary: LedgerAggregate;
  status: string;
  created_at: string;
}

export interface LedgerAggregate {
  total_opening_capital: number;
  total_deposits: number;
  total_withdrawals: number;
  total_profit_distributed: number;
  total_closing_aum: number;
  investor_count: number;
}

export interface ReportDetail {
  id: number;
  fund_id: number;
  fund_name: string;
  batch_id?: number;
  epoch_start: string;
  epoch_end: string;
  performance_rate_percent: number;
  head_office_total: number;
  summary: LedgerAggregate;
  investor_breakdown: InvestorBreakdownRow[];
  reconciliation_diff: number;
}

export interface InvestorBreakdownRow {
  internal_client_code: string;
  investor_name: string;
  investor_email?: string;
  batch_id?: number;
  start_balance: number;
  deposits: number;
  withdrawals: number;
  pro_rata_profit: number;
  end_balance: number;
}

// ── Withdrawals ──

export type WithdrawalSource = "investor_request" | "oversubscription_refund";

export interface Withdrawal {
  id: number;
  client_id: string;
  fund_id: number;
  fund_name: string;
  amount: number;
  status: "Pending" | "Approved" | "Rejected" | "Processed" | "Completed";
  date_withdrawn: string;
  approved_at: string | null;
  note: string | null;
  source?: WithdrawalSource;
  batch_id?: number | null;
  batch_name?: string | null;
  // Only meaningful when source === "oversubscription_refund".
  oversubscription_notice_sent?: boolean;
}

export interface CreateWithdrawalRequest {
  internal_client_code: string;
  fund_id: number;
  amount: number;
  status?: string;
}

// ── Recent Transactions ──

export interface RecentTransaction {
  id: number | string;
  type: "deposit" | "withdrawal" | "valuation";
  date: string;
  investor_name: string;
  internal_client_code: string;
  fund_name: string;
  class_code?: string | null;
  currency: "KES" | "USD" | string;
  amount: number | null;
  status: string;
}

// ── Audit ──

export interface AuditLogEntry {
  id: number;
  user_id: number | null;
  user_email?: string | null;
  user_name?: string | null;
  action: string;
  target_type: string | null;
  target_id: number | null;
  target_name: string | null;
  description: string | null;
  old_value: string | null;
  new_value: string | null;
  ip_address: string | null;
  user_agent: string | null;
  timestamp: string;
  success: boolean;
  error_message: string | null;
}

// ── Backups ──

export interface BackupLogEntry {
  id: number;
  filename: string;
  status: "running" | "success" | "failed";
  triggered_by: "scheduled" | "manual";
  triggered_by_email: string | null;
  file_size_bytes: number | null;
  onedrive_web_url: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface BackupStatus {
  enabled: boolean;
  next_run_at: string | null;
  last_backup: BackupLogEntry | null;
}

// ── API Response Wrappers ──

export interface ApiResponse<T = unknown> {
  status: number;
  message: string;
  data?: T;
  count?: number;
  pagination?: { page: number; per_page: number; total: number; total_pages: number } | null;
  status_counts?: Record<string, number>;
}

export interface ApiError {
  status: number;
  message: string;
  errors?: Record<string, string>;
}

// ── Performance Excel Upload ──

export interface PerformanceExcelRow {
  date: string;
  fund_name: string;
  duration: number;
  performance_percentage: number;
}
