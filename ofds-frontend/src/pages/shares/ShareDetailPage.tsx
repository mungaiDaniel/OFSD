import FundDetailPage from "@/pages/funds/FundDetailPage";

/** /shares/:id — same FundDetailPage, scoped to SHARES (Task 9). */
export default function ShareDetailPage() {
  return <FundDetailPage product="SHARES" />;
}
