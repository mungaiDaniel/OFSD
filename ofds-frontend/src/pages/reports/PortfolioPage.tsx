import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { KPICard } from "@/components/data/KPICard";
import { ChartCard } from "@/components/charts/ChartCard";
import { PortfolioAUMChart } from "@/components/charts/PortfolioAUMChart";
import { FundAllocationDoughnut } from "@/components/charts/FundAllocationDoughnut";
import { DepositsWithdrawalsBarChart } from "@/components/charts/DepositsWithdrawalsBarChart";
import { reportService } from "@/services/reportService";
import { formatCurrencyCompact } from "@/lib/utils";
import { getFundColor, FLOW_COLORS } from "@/lib/chartConfig";
import type { ReportSummary } from "@/lib/types";
import { ArrowLeft, Download } from "lucide-react";

export default function PortfolioPage() {
  const navigate = useNavigate();
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    reportService.getAll().then(setReports).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const sorted = [...reports].sort((a, b) => new Date(a.epoch_end).getTime() - new Date(b.epoch_end).getTime());
  const fundNames = [...new Set(sorted.map((r) => r.fund_name))];
  const labels = [...new Set(sorted.map((r) => new Date(r.epoch_end).toLocaleDateString("en-GB", { month: "short", day: "2-digit" })))];

  const latestPerFund = fundNames.map((n) => {
    const fr = sorted.filter((r) => r.fund_name === n);
    return { name: n, value: fr[fr.length - 1]?.summary?.total_closing_aum || 0 };
  });
  const totalAUM = latestPerFund.reduce((s, f) => s + f.value, 0);
  const totalInvestors = sorted.length > 0 ? sorted[sorted.length - 1]?.summary?.investor_count || 0 : 0;

  const handleExport = () => {
    const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:5000/api/v1";
    window.open(`${baseUrl}/reports/portfolio/multi-batch?batch_ids=all`, "_blank");
  };

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: "var(--color-border-subtle)", borderTopColor: "var(--color-brand-400)" }} /></div>;

  return (
    <div className="container-fluid px-0">
      <button onClick={() => navigate("/reports")} className="d-flex align-items-center gap-1 mb-3 btn btn-link p-0 text-decoration-none" style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}><ArrowLeft size={14} /> Back to reports</button>

      <div className="page-header-row mb-4">
        <div>
          <h1 className="fw-bold mb-1" style={{ fontSize: "22px", color: "var(--color-text-primary)" }}>Portfolio</h1>
          <p className="mb-0" style={{ fontSize: "13px", color: "var(--color-text-secondary)" }}>Global AUM and performance across all active funds</p>
        </div>
        <button onClick={handleExport} className="btn btn-sm d-flex align-items-center gap-2 px-3 py-2 fw-bold" style={{ border: "1px solid rgba(255,255,255,0.15)", color: "var(--color-text-secondary)", background: "transparent", fontSize: "12px", borderRadius: "8px" }}><Download size={14} /> Export Excel</button>
      </div>

      <div className="row g-3 mb-4">
        <div className="col-lg-4 col-sm-6">
          <KPICard label="Total AUM" value={formatCurrencyCompact(totalAUM)} />
        </div>
        <div className="col-lg-4 col-sm-6">
          <KPICard label="Active funds" value={String(fundNames.length)} />
        </div>
        <div className="col-lg-4 col-sm-6">
          <KPICard label="Total investors" value={String(totalInvestors)} />
        </div>
      </div>

      <div className="row g-4 mb-4">
        <div className="col-lg-6">
          <ChartCard title="Portfolio AUM over time" legend={fundNames.map((n) => ({ label: `${n} ${formatCurrencyCompact(latestPerFund.find((f) => f.name === n)?.value || 0)}`, color: getFundColor(n) }))}>
            <PortfolioAUMChart data={{ labels: labels.length ? labels : ["—"], funds: fundNames.map((n) => ({ name: n, data: sorted.filter((r) => r.fund_name === n).map((r) => r.summary.total_closing_aum), growth: sorted.filter((r) => r.fund_name === n).map((r) => r.performance_rate_percent || 0) })) }} height={300} />
          </ChartCard>
        </div>

        <div className="col-lg-6">
          <ChartCard title="Fund allocation" legend={latestPerFund.map((f) => ({ label: `${f.name} ${totalAUM > 0 ? ((f.value / totalAUM) * 100).toFixed(1) : "0"}%`, color: getFundColor(f.name) }))}>
            <FundAllocationDoughnut data={{ funds: latestPerFund.length > 0 ? latestPerFund : [{ name: "—", value: 0 }] }} />
          </ChartCard>
        </div>

        <div className="col-lg-6">
          <ChartCard title="Deposits vs withdrawals" legend={[{ label: "Deposits", color: FLOW_COLORS.deposit }, { label: "Withdrawals", color: FLOW_COLORS.withdrawal }]}>
            <DepositsWithdrawalsBarChart data={{
              labels: labels.length ? labels : ["—"],
              deposits: labels.map((l) => sorted.filter((r) => new Date(r.epoch_end).toLocaleDateString("en-GB", { month: "short", day: "2-digit" }) === l).reduce((s, r) => s + (r.summary?.total_deposits || 0), 0)),
              withdrawals: labels.map((l) => sorted.filter((r) => new Date(r.epoch_end).toLocaleDateString("en-GB", { month: "short", day: "2-digit" }) === l).reduce((s, r) => s + (r.summary?.total_withdrawals || 0), 0)),
            }} height={300} />
          </ChartCard>
        </div>
      </div>
    </div>
  );
}
