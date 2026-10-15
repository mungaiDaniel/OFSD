import api from "./api";
import { API } from "@/lib/constants";
import type { RecentTransaction } from "@/lib/types";

export interface FlowPoint {
  label: string;
  deposits: number;
  withdrawals: number;
}

export interface OverviewStats {
  total_aum: number;
  total_aum_kes?: number;
  total_aum_usd?: number;
  invested_kes?: number;
  invested_usd?: number;
  gain_kes?: number;
  gain_usd?: number;
  /** Task 10: Shares (SHARES/DPRP) NGN totals — a separate product/currency
   * from the FUNDS figures above (see app/Stats/route.py). */
  total_ngn?: number;
  invested_ngn?: number;
  gain_ngn?: number;
  total_withdrawals?: number;
  total_profit?: number;
  total_invested?: number;
  total_investors: number;
  /** Distinct investors with a deposit in a FUNDS / SHARES batch (Overview product tabs). */
  total_investors_funds?: number;
  total_investors_shares?: number;
  performance_pct: number;
  active_batches: number;
  open_batches?: number;
  latest_epoch_end?: string;
  max_chart_epoch?: string;
  previous_epoch_end?: string;
  flow_series?: FlowPoint[];
  flow_by_batch?: {
    labels: string[];
    batches: { batch_id: number; batch_name: string; deposits: number[] }[];
    withdrawals: number[];
  };
  alloc_data?: { name: string; value: number }[];
  aum_data?: { labels: string[]; funds: { name: string; data: number[]; growth: number[] }[] };
  /** Latest balance per batch from batch_valuations (authoritative AUM building blocks) */
  batch_contributions?: Record<
    number,
    { balance: number; profit: number; period_end: string | null }
  >;
}

export const dashboardService = {
  async getOverviewStats(): Promise<OverviewStats> {
    const res = await api.get<{ status: number; data: OverviewStats }>(API.OVERVIEW_STATS);
    return res.data.data;
  },

  async getRecentTransactions(): Promise<RecentTransaction[]> {
    try {
      const res = await api.get<{ status: number; data: RecentTransaction[] }>(
        API.TRANSACTIONS_RECENT
      );
      return res.data.data ?? [];
    } catch {
      return [];
    }
  },
};

