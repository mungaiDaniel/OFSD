import BatchListPage from "@/pages/batches/BatchListPage";

/**
 * /shares/deployment — SHARES batches, opened straight to "Transferred" (the
 * batches ready to deploy). The actual Task 3 allocation preview/confirm form
 * lives on the batch's own detail page (SharesDeploymentModal) — this is just
 * the entry point for picking which batch to deploy.
 */
export default function SharesDeploymentListPage() {
  return (
    <BatchListPage
      product="SHARES"
      initialFilter="Transferred"
      hideCreateButton
      title="Deployment & allocation"
      description="Transferred Shares batches ready to deploy — open one to convert deposits to NGN and allocate shares"
    />
  );
}
