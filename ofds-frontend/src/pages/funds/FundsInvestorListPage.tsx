import InvestorDirectoryPage from "@/pages/investors/InvestorDirectoryPage";

/** /funds/investors — same InvestorDirectoryPage, scoped to FUNDS holders. */
export default function FundsInvestorListPage() {
  return <InvestorDirectoryPage product="FUNDS" />;
}
