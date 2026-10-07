import BatchListPage from "@/pages/batches/BatchListPage";
import { ROUTES } from "@/lib/constants";

/** /funds/batches — same BatchListPage, scoped to FUNDS. */
export default function FundsBatchListPage() {
  return <BatchListPage product="FUNDS" createPath={ROUTES.FUNDS_BATCH_CREATE} />;
}
