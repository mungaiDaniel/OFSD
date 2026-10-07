/**
 * Shared batch calculation utilities
 * 
 * Provides consistent batch-level and global aggregation logic
 * used by both Overview and Batch Detail pages.
 * 
 * This ensures that Overview totals = SUM(BatchDetail totals)
 */

import type { Batch, Investment, BatchInvestor } from "@/lib/types";
import { getEntryFeePercent } from "@/lib/transferDeductions";

export interface BatchCalculations {
  totalAUM: number;
  totalDeposits: number;
  totalWithdrawals: number;
  totalProfit: number;
  percentageGain: number; // as percentage, e.g., 5.50
}

export interface GlobalCalculations extends BatchCalculations {
  totalInvestors: number;
  activeBatchCount: number;
}

/**
 * Investment-like type that works with both Investment and BatchInvestor
 * (both contain the fields needed for calculations)
 */
type InvestmentLike = Investment | BatchInvestor | { 
  current_balance?: number;
  opening_balance?: number;
  main_balance?: number;
  amount_deposited?: number;
  withdrawals?: number;
  internal_client_code: string;
};

/**
 * Calculate batch-level totals from its investments
 * 
 * This is the SAME logic used in BatchDetailPage:
 * - totalAUM: SUM(investments[].current_balance)
 * - totalDeposits: SUM(investments[].amount_deposited) or opening_balance
 * - totalWithdrawals: SUM(investments[].withdrawals)
 * - profit: totalAUM - totalDeposits
 * 
 * @param investments - Array of investments in the batch (enriched with current_balance, etc.)
 * @returns Batch-level calculation object
 */
export function calculateBatchTotals(investments: InvestmentLike[] | undefined): BatchCalculations {
  if (!investments || investments.length === 0) {
    return {
      totalAUM: 0,
      totalDeposits: 0,
      totalWithdrawals: 0,
      totalProfit: 0,
      percentageGain: 0,
    };
  }

  // Use the EXACT same calculation as in BatchDetailPage.tsx (line 263-267)
  // current_balance: enriched by batch controller, falls back to amount_deposited
  // withdrawals: enriched by batch controller, falls back to 0
  const totalAUM = investments.reduce((sum, inv) => {
    const current = (inv as any).current_balance !== undefined ? (inv as any).current_balance : (inv as any).amount_deposited || 0;
    return sum + current;
  }, 0);
  
  const totalDeposits = investments.reduce((sum, inv) => {
    const principalBase = (inv as any).main_balance ?? (inv as any).opening_balance ?? (inv as any).amount_deposited ?? 0;
    return sum + principalBase;
  }, 0);
  
  const totalWithdrawals = investments.reduce((sum, inv) => {
    const wd = (inv as any).withdrawals !== undefined ? (inv as any).withdrawals : 0;
    return sum + wd;
  }, 0);
  
  const totalProfit = totalAUM - totalDeposits;
  const percentageGain = totalDeposits > 0 ? (totalProfit / totalDeposits) * 100 : 0;

  return {
    totalAUM,
    totalDeposits,
    totalWithdrawals,
    totalProfit,
    percentageGain: parseFloat(percentageGain.toFixed(2)),
  };
}

/**
 * Calculate global totals from all batches.
 *
 * ── Atomic Batch Architecture ─────────────────────────────────────────────────
 * Global AUM is the SUM of each batch's backend-computed `total_capital` field,
 * which is itself the SUM of EpochLedger.end_balance per investor/fund scoped
 * to that batch's valuation period (via BATCH_EPOCH_CUTOFFS on the backend).
 *
 * This eliminates client-side re-computation and keeps Overview totals
 * identical to what each BatchDetail page shows.
 *
 * Fallback: if a batch has no total_capital (e.g. brand-new), uses total_principal.
 *
 * @param batches - Array of batches from the API (list or detail responses)
 */
export function calculateGlobalTotals(batches: Batch[]): GlobalCalculations {
  if (!batches || batches.length === 0) {
    return {
      totalAUM: 0,
      totalDeposits: 0,
      totalWithdrawals: 0,
      totalProfit: 0,
      percentageGain: 0,
      totalInvestors: 0,
      activeBatchCount: 0,
    };
  }

  let globalAUM = 0;
  let globalDeposits = 0;
  let globalWithdrawals = 0;
  const totalInvestorCodes = new Set<string>();
  let activeBatchCount = 0;

  for (const batch of batches) {
    if (batch.is_active || batch.status === "Active") activeBatchCount++;

    // PRIMARY: use backend-computed total_capital (from EpochLedger atomic summation)
    // FALLBACK: total_principal (raw deposits) if capital not yet computed
    globalAUM += batch.total_capital ?? batch.total_principal ?? 0;
    const basePrincipal = Number(batch.total_principal ?? 0);
    const txCost = Number(batch.transfer_transaction_cost ?? 0);
    const entryFeePercent = getEntryFeePercent(batch as any);
    const netAfterTx = Math.max(0, basePrincipal - txCost);
    const principalAfterFees =
      Number(batch.stage ?? 1) >= 2
        ? Math.max(0, netAfterTx * (1 - entryFeePercent / 100))
        : basePrincipal;
    globalDeposits += principalAfterFees;

    // Collect unique investor codes for distinct investor count.
    // If detailed investment data is available (from getById), use it;
    // otherwise investors_count from the list endpoint is used below.
    if (batch.investments && batch.investments.length > 0) {
      for (const inv of batch.investments) {
        totalInvestorCodes.add(inv.internal_client_code);
        // Sum ledger-captured withdrawals from enriched investment data
        globalWithdrawals += inv.withdrawals ?? 0;
      }
    }
  }

  // If no investment detail was available, rough withdrawal sum is 0 (acceptable for overview)
  const globalProfit = globalAUM - globalDeposits;
  const globalPercentageGain =
    globalDeposits > 0 ? (globalProfit / globalDeposits) * 100 : 0;

  // Fall back to investors_count from the list endpoint when no detail data
  const investorCountFromDetail = totalInvestorCodes.size;
  const investorCountFromList = batches.reduce(
    (max, b) => Math.max(max, b.investors_count ?? 0),
    0
  );
  const totalInvestors =
    investorCountFromDetail > 0 ? investorCountFromDetail : investorCountFromList;

  return {
    totalAUM: globalAUM,
    totalDeposits: globalDeposits,
    totalWithdrawals: globalWithdrawals,
    totalProfit: globalProfit,
    percentageGain: parseFloat(globalPercentageGain.toFixed(2)),
    totalInvestors,
    activeBatchCount,
  };
}

/**
 * Get per-batch performance metrics for charts
 * Used when rendering fund-specific performance across all batches
 */
export interface PerFundMetrics {
  name: string;
  totalAUM: number;
  performance: number;
  deposits: number;
  withdrawals: number;
}

/**
 * Aggregate fund metrics across all batches from their holdings
 * @param batches - Array of batches with investments
 * @returns Map of fund name → aggregated metrics
 */
export function aggregateFundMetrics(batches: Batch[]): Record<string, PerFundMetrics> {
  const fundMetrics: Record<string, PerFundMetrics> = {};

  for (const batch of batches) {
    if (!batch.investments) continue;

    // Group investments by fund (works with both Investment and BatchInvestor types)
    const byFund: Record<string, InvestmentLike[]> = {};
    for (const inv of batch.investments) {
      const fundName = (inv as any).fund_name || "Unallocated";
      if (!byFund[fundName]) byFund[fundName] = [];
      byFund[fundName].push(inv as InvestmentLike);
    }

    // Calculate metrics per fund
    for (const [fundName, fundInvests] of Object.entries(byFund)) {
      if (!fundMetrics[fundName]) {
        fundMetrics[fundName] = {
          name: fundName,
          totalAUM: 0,
          performance: 0,
          deposits: 0,
          withdrawals: 0,
        };
      }

      const fundCalcs = calculateBatchTotals(fundInvests);
      fundMetrics[fundName].totalAUM += fundCalcs.totalAUM;
      fundMetrics[fundName].deposits += fundCalcs.totalDeposits;
      fundMetrics[fundName].withdrawals += fundCalcs.totalWithdrawals;
    }
  }

  // Calculate performance % for each fund
  for (const metric of Object.values(fundMetrics)) {
    if (metric.deposits > 0) {
      metric.performance = ((metric.totalAUM - metric.deposits) / metric.deposits) * 100;
    }
  }

  return fundMetrics;
}
