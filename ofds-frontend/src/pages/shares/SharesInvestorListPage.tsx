import InvestorDirectoryPage from "@/pages/investors/InvestorDirectoryPage";

/** /shares/investors — same InvestorDirectoryPage, scoped to SHARES holders. */
export default function SharesInvestorListPage() {
  return <InvestorDirectoryPage product="SHARES" />;
}
