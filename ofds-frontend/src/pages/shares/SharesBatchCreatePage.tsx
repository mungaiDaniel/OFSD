import BatchCreatePage from "@/pages/batches/BatchCreatePage";
import { ROUTES } from "@/lib/constants";

/** /shares/batches/new — creates a SHARES batch automatically. */
export default function SharesBatchCreatePage() {
  return <BatchCreatePage product="SHARES" backPath={ROUTES.SHARES_BATCHES} />;
}
