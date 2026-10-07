import WithdrawalListPage from "@/pages/withdrawals/WithdrawalListPage";

/**
 * /shares/refunds — the same Withdrawals table, locked to
 * source=oversubscription_refund (SHARES deployment refunds — see Task 3's
 * SharesDeploymentService). Same maker-checker approve/reject flow, just
 * scoped so a Shares admin doesn't have to filter it out of the full list.
 */
export default function SharesRefundsPage() {
  return (
    <WithdrawalListPage
      lockedSource="oversubscription_refund"
      title="Refunds"
      description="SHARES deployment refunds — unallocated or oversubscribed deposit value, pending approval"
    />
  );
}
