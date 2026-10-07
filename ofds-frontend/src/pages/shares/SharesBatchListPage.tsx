import BatchListPage from "@/pages/batches/BatchListPage";
import { ROUTES } from "@/lib/constants";

/** /shares/batches — same BatchListPage, scoped to SHARES. */
export default function SharesBatchListPage() {
  return <BatchListPage product="SHARES" createPath={ROUTES.SHARES_BATCH_CREATE} />;
}
