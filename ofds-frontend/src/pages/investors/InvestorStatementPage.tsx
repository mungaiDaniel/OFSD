import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { investmentService } from "@/services/investmentService";
import { formatCurrency } from "@/lib/utils";
import { ROUTES } from "@/lib/constants";
import { ArrowLeft, Download, Printer } from "lucide-react";
import { toast } from "sonner";

interface InvestorPortfolio {
  client_code: string;
  investor_name: string;
  initial_investment: number;
  total_principal: number;
  current_balance: number;
  total_profit: number;
  unique_batches: number;
  holdings: Array<{
    batch_id: number;
    batch_name: string;
    fund_id: number | null;
    fund_name: string;
    investments_count: number;
    total_principal: number;
    main_balance?: number;
    transaction_fee_usd?: number;
    entry_fee_usd?: number;
    latest_valuation: {
      epoch_start: string;
      epoch_end: string;
      start_balance: number;
      deposits: number;
      withdrawals: number;
      profit: number;
      end_balance: number;
    } | null;
  }>;
}

interface HistoricalStatement {
  date: string;
  type: "DEPOSIT" | "WITHDRAWAL" | "MONTHLY_REPORT" | string;
  label?: string;
  fund_name?: string;
  deposits?: number;
  opening_balance?: number;
  withdrawals?: number;
  profit?: number;
  performance_rate?: number;
  end_balance?: number;
  withdrawal_id?: number;
  batch_id?: number;
}

export default function InvestorStatementPage() {
  const { clientCode } = useParams<{ clientCode: string }>();
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState<InvestorPortfolio | null>(null);
  const [statements, setStatements] = useState<HistoricalStatement[]>([]);
  const [loading, setLoading] = useState(true);

  const formatStatementDate = (value: string) => {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "—";
    return dt.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
  };

  const monthYear = (value: string) => {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) return "";
    return dt.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  };

  const statementEventLabel = (stmt: HistoricalStatement) => {
    if (stmt.label) return stmt.label;
    if (stmt.type === "DEPOSIT") return `Deposit - ${monthYear(stmt.date).split(" ")[0] || "Period"}`;
    if (stmt.type === "WITHDRAWAL") return `Withdrawal - ${monthYear(stmt.date).split(" ")[0] || "Period"}`;
    if (stmt.type === "MONTHLY_REPORT") return monthYear(stmt.date) || "Monthly Report";
    return "Statement";
  };

  useEffect(() => {
    async function load() {
      if (!clientCode) return;
      setLoading(true);
      try {
        const [portfolioRes, statementsRes] = await Promise.all([
          investmentService.getInvestorPortfolio(clientCode),
          investmentService.getInvestorStatements(clientCode),
        ]);

        if (portfolioRes.status === 200 && portfolioRes.data && (portfolioRes.data as any).holdings) {
          setPortfolio(portfolioRes.data as any);
        } else {
          toast.error("Could not load investor portfolio");
        }

        const rawStatements = (statementsRes?.data as HistoricalStatement[]) || [];
        const sortedStatements = [...rawStatements].sort(
          (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()
        );
        setStatements(sortedStatements);
      } catch (err) {
        console.error("Error loading investor portfolio", err);
        toast.error("Failed to load investor data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [clientCode]);

  if (loading) {
    return (
      <div className="d-flex align-items-center justify-content-center h-64">
        <div className="spinner-border" style={{ color: "var(--color-brand-400)" }} role="status">
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
  }

  if (!portfolio) {
    return (
      <div className="text-center py-10">
        <p style={{ color: "var(--color-text-tertiary)" }}>Investor not found</p>
        <button onClick={() => navigate(ROUTES.INVESTORS)} className="btn btn-sm btn-outline-secondary mt-3">
          Back to investors
        </button>
      </div>
    );
  }

  const totalCurrentBalance =
    statements[0]?.end_balance ??
    portfolio.current_balance ??
    portfolio.holdings.reduce((sum, h) => sum + (h.latest_valuation?.end_balance ?? h.main_balance ?? h.total_principal), 0);
  const totalDeposits = statements.reduce((sum, row) => sum + Number(row.deposits || 0), 0);
  const totalWithdrawals = statements.reduce((sum, row) => sum + Number(row.withdrawals || 0), 0);
  const totalProfitFromStatements = statements
    .filter((row) => row.type === "MONTHLY_REPORT")
    .reduce((sum, row) => sum + Number(row.profit || 0), 0);
  const totalProfit = Number.isFinite(totalProfitFromStatements) && totalProfitFromStatements !== 0
    ? totalProfitFromStatements
    : (portfolio.total_profit ?? totalCurrentBalance - portfolio.total_principal);
  const uniqueFundsCount = new Set(
    portfolio.holdings.map((h) => String(h.fund_id ?? h.fund_name ?? "").trim()).filter(Boolean)
  ).size;
  const earliestDate = statements.at(-1)?.date ?? "";
  const latestDate = statements[0]?.date ?? "";
  const statementPeriod = earliestDate && latestDate
    ? `${monthYear(earliestDate)} - ${monthYear(latestDate)}`
    : "MTD";

  return (
    <div className="container-fluid px-0">
      {/* Screen-only toolbar (hidden when printing) */}
      <div className="page-header-row mb-4 d-print-none">
        <button
          onClick={() => clientCode && navigate(ROUTES.INVESTOR_OVERVIEW(clientCode))}
          className="d-flex align-items-center gap-1 btn btn-link p-0 text-decoration-none"
          style={{ fontSize: "12px", color: "var(--color-text-tertiary)" }}
        >
          <ArrowLeft size={14} /> Back to overview
        </button>
        <div className="d-flex gap-2">
          <button className="btn btn-sm" style={{ background: "#00005b", color: "#fff" }} onClick={() => window.print()}>
            <Printer size={14} /> Print
          </button>
          <button
            className="btn btn-sm btn-outline-secondary"
            onClick={async () => {
              try {
                if (!clientCode) throw new Error("Client code is missing");
                await investmentService.downloadInvestorStatementPdf(clientCode);
                toast.success("Investor statement downloaded successfully");
              } catch (error) {
                console.error("Error downloading investor statement:", error);
                toast.error("Failed to download investor statement. Please try again.");
              }
            }}
          >
            <Download size={14} /> Export
          </button>
        </div>
      </div>

      {/* Statement document — this block is what prints */}
      <div
        className="investor-statement-document"
        style={{
          background: "#fff",
          color: "#000",
          padding: "60px 40px",
          borderRadius: "8px",
          boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
          fontFamily: "Arial, sans-serif",
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: "40px", display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "2px solid #00005b", paddingBottom: "20px" }}>
          <div>
            <img src="/AIBlight.png" alt="AIBAXYS Logo" style={{ maxHeight: "60px" }} />
          </div>
          <div style={{ textAlign: "right", fontSize: "11px", color: "#333", lineHeight: "1.6" }}>
            <div style={{ fontWeight: "bold", fontSize: "12px", marginBottom: "5px" }}>HEAD OFFICE</div>
            <div>The Promenade, 5th Floor | General Mathenge Rd</div>
            <div>P.O. Box 43676-00100 | Nairobi | Kenya</div>
            <div style={{ marginTop: "5px" }}>
              <span style={{ marginRight: "15px" }}>T: 0711047000</span>
              <span style={{ marginRight: "15px" }}>M: 0790404571</span>
            </div>
            <div>W: www.aib-axysafrica.com</div>
          </div>
        </div>

        {/* Statement Title */}
        <h2 style={{ textAlign: "center", fontSize: "20px", fontWeight: "bold", marginBottom: "30px", color: "#00005b" }}>
          CLIENT STATEMENT
        </h2>

        {/* Client Information Section */}
        <div style={{ marginBottom: "30px" }}>
          <table style={{ width: "100%", marginBottom: "20px" }}>
            <tbody>
              <tr>
                <td style={{ padding: "8px 0", fontSize: "12px", fontWeight: "bold", width: "30%" }}>Client Code</td>
                <td style={{ padding: "8px 0", fontSize: "12px" }}>: {portfolio.client_code}</td>
                <td style={{ padding: "8px 0", fontSize: "12px", fontWeight: "bold", width: "30%" }}>Statement Date</td>
                <td style={{ padding: "8px 0", fontSize: "12px" }}>: {new Date().toLocaleDateString()}</td>
              </tr>
              <tr>
                <td style={{ padding: "8px 0", fontSize: "12px", fontWeight: "bold" }}>Client Name</td>
                <td style={{ padding: "8px 0", fontSize: "12px" }}>: {portfolio.investor_name}</td>
                <td style={{ padding: "8px 0", fontSize: "12px", fontWeight: "bold" }}>Number of Funds</td>
                <td style={{ padding: "8px 0", fontSize: "12px" }}>: {uniqueFundsCount}</td>
              </tr>
              <tr>
                <td style={{ padding: "8px 0", fontSize: "12px", fontWeight: "bold" }}>Statement Period</td>
                <td style={{ padding: "8px 0", fontSize: "12px" }}>: {statementPeriod}</td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Account Summary Section */}
        <div style={{ marginBottom: "30px" }}>
          <h3 style={{ fontSize: "13px", fontWeight: "bold", background: "#f5f5f5", padding: "10px", margin: "0 0 10px 0" }}>
            Account Summary
          </h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ background: "#f5f5f5", borderBottom: "2px solid #00005b" }}>
                <th style={{ padding: "10px", textAlign: "left", fontSize: "12px", fontWeight: "bold" }}>Description</th>
                <th style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontWeight: "bold" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderBottom: "1px solid #ddd" }}>
                <td style={{ padding: "10px", fontSize: "12px" }}>Total Principal Invested</td>
                <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace", fontWeight: "bold" }}>
                  {formatCurrency(portfolio.total_principal)}
                </td>
              </tr>
              <tr style={{ borderBottom: "1px solid #ddd" }}>
                <td style={{ padding: "10px", fontSize: "12px" }}>Deposits </td>
                <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace" }}>
                  {formatCurrency(totalDeposits)}
                </td>
              </tr>
              <tr style={{ borderBottom: "1px solid #ddd" }}>
                <td style={{ padding: "10px", fontSize: "12px" }}>Withdrawals </td>
                <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace" }}>
                  {formatCurrency(totalWithdrawals)}
                </td>
              </tr>
              <tr style={{ borderBottom: "2px solid #00005b", background: "#f9f9f9" }}>
                <td style={{ padding: "10px", fontSize: "12px", fontWeight: "bold" }}>Current Balance</td>
                <td
                  style={{
                    padding: "10px",
                    textAlign: "right",
                    fontSize: "12px",
                    fontFamily: "monospace",
                    fontWeight: "bold",
                    color: "#00005b",
                  }}
                >
                  {formatCurrency(totalCurrentBalance)}
                </td>
              </tr>
              <tr>
                <td style={{ padding: "10px", fontSize: "12px", fontWeight: "bold" }}>Gain/Loss</td>
                <td
                  style={{
                    padding: "10px",
                    textAlign: "right",
                    fontSize: "12px",
                    fontFamily: "monospace",
                    fontWeight: "bold",
                    color: totalProfit >= 0 ? "#00a651" : "#d32f2f",
                  }}
                >
                  {formatCurrency(totalProfit)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {/* Historical Statements Section */}
        <div style={{ marginBottom: "30px" }}>
          <h3 style={{ fontSize: "13px", fontWeight: "bold", background: "#f5f5f5", padding: "10px", margin: "0 0 10px 0" }}>
            Statements
          </h3>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", minWidth: "920px" }}>
              <thead>
                <tr style={{ background: "#f5f5f5", borderBottom: "2px solid #00005b" }}>
                  {["Date", "Statement / Event", "Fund", "Deposits", "Opening Amount", "Withdrawals", "Gain/Loss", "Performance", "Closing Balance"].map((h) => (
                    <th
                      key={h}
                      style={{
                        padding: "10px",
                        textAlign: h === "Date" || h === "Statement / Event" || h === "Fund" ? "left" : "right",
                        fontSize: "12px",
                        fontWeight: "bold",
                      }}
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {statements.map((stmt, idx) => (
                  <tr key={`${stmt.date}-${stmt.type}-${idx}`} style={{ borderBottom: "1px solid #ddd" }}>
                    <td style={{ padding: "10px", fontSize: "12px" }}>{formatStatementDate(stmt.date)}</td>
                    <td style={{ padding: "10px", fontSize: "12px", fontWeight: stmt.type === "MONTHLY_REPORT" ? "bold" : "normal" }}>
                      {statementEventLabel(stmt)}
                    </td>
                    <td style={{ padding: "10px", fontSize: "12px" }}>{stmt.fund_name || "—"}</td>
                    <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace" }}>
                      {Number(stmt.deposits || 0) > 0 ? formatCurrency(Number(stmt.deposits || 0)) : "—"}
                    </td>
                    <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace" }}>
                      {formatCurrency(Number(stmt.opening_balance || 0))}
                    </td>
                    <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace", color: Number(stmt.withdrawals || 0) > 0 ? "#d32f2f" : "#999" }}>
                      {Number(stmt.withdrawals || 0) > 0 ? formatCurrency(Number(stmt.withdrawals || 0)) : "—"}
                    </td>
                    <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace", color: Number(stmt.profit || 0) >= 0 ? "#00a651" : "#d32f2f" }}>
                      {stmt.type === "MONTHLY_REPORT" ? formatCurrency(Number(stmt.profit || 0)) : "—"}
                    </td>
                    <td
                      style={{
                        padding: "10px",
                        textAlign: "right",
                        fontSize: "12px",
                        fontFamily: "monospace",
                        color: Number(stmt.performance_rate || 0) >= 0 ? "#00a651" : "#d32f2f",
                      }}
                    >
                      {stmt.type === "MONTHLY_REPORT"
                        ? `${Number(stmt.performance_rate || 0).toFixed(2)}%`
                        : "—"}
                    </td>
                    <td style={{ padding: "10px", textAlign: "right", fontSize: "12px", fontFamily: "monospace", fontWeight: "bold" }}>
                      {formatCurrency(Number(stmt.end_balance || 0))}
                    </td>
                  </tr>
                ))}
                {statements.length === 0 && (
                  <tr>
                    <td colSpan={9} style={{ padding: "16px", textAlign: "center", fontSize: "12px", color: "#666" }}>
                      No historical statements found for this investor.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Footer */}
        <div style={{ marginTop: "40px", paddingTop: "20px", borderTop: "1px solid #ddd", fontSize: "10px", color: "#999" }}>
          <p style={{ margin: "0 0 5px 0" }}>
            <strong>Disclaimer:</strong> This statement is provided for informational purposes only. All figures are subject to change and may not reflect real-time data.
          </p>
          <p style={{ margin: "0" }}>Generated on: {new Date().toLocaleString()}</p>
        </div>
      </div>
    </div>
  );
}
