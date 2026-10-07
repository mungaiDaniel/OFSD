type InvestorLike = {
  opening_balance?: number | null;
  amount_deposited?: number | null;
  main_balance?: number | null;
};

type BatchLike = {
  stage?: number | null;
  transfer_transaction_cost?: number | null;
  transfer_entry_fee_percent?: number | null;
  entry_fee_percentage?: number | null;
};

export function getBatchDepositBaseTotal(investments: InvestorLike[]): number {
  return investments.reduce((sum, inv) => {
    const base = Number(inv.main_balance ?? inv.opening_balance ?? inv.amount_deposited ?? 0);
    return sum + (Number.isFinite(base) ? base : 0);
  }, 0);
}

export function getEntryFeePercent(batch?: BatchLike | null): number {
  const configured = Number(batch?.transfer_entry_fee_percent ?? batch?.entry_fee_percentage ?? 0);
  if (configured > 0) return configured;
  return Number(batch?.stage ?? 1) >= 2 ? 1.5 : 0;
}

export function getInvestorPrincipalAfterTransfer(
  investor: InvestorLike,
  params: {
    stage?: number | null;
    batchTotalDepositBase: number;
    transferTransactionCost?: number | null;
    entryFeePercent?: number | null;
  }
): number {
  const stage = Number(params.stage ?? 1);
  const persistedMainBalance = Number(investor.main_balance ?? 0);
  if (persistedMainBalance > 0) return persistedMainBalance;

  const baseDeposit = Number(investor.main_balance ?? investor.opening_balance ?? investor.amount_deposited ?? 0);
  if (!Number.isFinite(baseDeposit) || baseDeposit <= 0) return 0;
  if (stage < 2) return baseDeposit;

  const batchTotal = Number(params.batchTotalDepositBase ?? 0);
  const transactionCost = Number(params.transferTransactionCost ?? 0);
  const entryFeePercent = Number(params.entryFeePercent ?? 0);

  const weight = batchTotal > 0 ? baseDeposit / batchTotal : 0;
  const allocatedTransaction = transactionCost > 0 ? transactionCost * weight : 0;
  const netAfterTransaction = Math.max(0, baseDeposit - allocatedTransaction);
  const entryFeeUsd = entryFeePercent > 0 ? netAfterTransaction * (entryFeePercent / 100) : 0;

  return Math.max(0, netAfterTransaction - entryFeeUsd);
}
