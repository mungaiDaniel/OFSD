import BatchCreatePage from "@/pages/batches/BatchCreatePage";
import { ROUTES } from "@/lib/constants";

/** /funds/batches/new — creates a FUNDS batch automatically. */
export default function FundsBatchCreatePage() {
  return <BatchCreatePage product="FUNDS" backPath={ROUTES.FUNDS_BATCHES} />;
}
