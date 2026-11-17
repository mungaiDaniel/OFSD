/**
 * Seed data for Demo Mode. Everything here is fictional: invented fund names,
 * "Demo Investor NNN" people and reserved example.com addresses.
 */
import type { Batch, BatchInvestor, CoreFund, FundShareClass, User, Withdrawal, PendingEmail } from "@/lib/types";

export interface DemoInvestment {
  id: number;
  batch_id: number;
  fund_id: number;
  class_id: number;
  investor_no: number;
  amount: number;
  date_deposited: string;
  performance_pct: number;
}

export interface DemoState {
  users: User[];
  funds: CoreFund[];
  classes: (FundShareClass & { core_fund_id: number })[];
  batches: Batch[];
  investments: DemoInvestment[];
  investors: Record<string, { name: string; email: string; phone: string }>;
  withdrawals: Withdrawal[];
  emails: PendingEmail[];
  audit: { id: number; action: string; description: string; user_email: string; timestamp: string }[];
  seq: number;
}

const iso = (daysAgo: number) => new Date(Date.now() - daysAgo * 86_400_000).toISOString();
const day = (daysAgo: number) => iso(daysAgo).slice(0, 10);
export const investorCode = (n: number) => `DEMO-${String(n).padStart(3, "0")}`;

export function createSeed(): DemoState {
  const users: User[] = [
    { id: 1, name: "Demo User", email: "demo@example.com", role: "super_admin", status: "active", created: iso(200) },
    { id: 2, name: "Sample Admin", email: "admin@example.com", role: "admin", status: "active", created: iso(150) },
    { id: 3, name: "Sample Analyst", email: "analyst@example.com", role: "user", status: "active", created: iso(90) },
    { id: 4, name: "Pending Person", email: "pending@example.com", role: "user", status: "pending", created: iso(2) },
  ];

  const funds: CoreFund[] = [
    { id: 1, fund_name: "Northwind Growth Fund", fund_code: "NWG", product_type: "FUNDS", is_active: true, description: "Sample diversified growth fund." },
    { id: 2, fund_name: "Harbor Income Fund", fund_code: "HIF", product_type: "FUNDS", is_active: true, description: "Sample income-focused fund." },
    { id: 3, fund_name: "Summit Equity Shares", fund_code: "SES", product_type: "SHARES", is_active: true, description: "Sample share-based equity product." },
  ];
  const classes = [
    { id: 1, core_fund_id: 1, class_name: "Class A", class_code: "NWG-A", currency: "USD", is_active: true, current_nav: 1.0842 },
    { id: 2, core_fund_id: 1, class_name: "Class B", class_code: "NWG-B", currency: "KES", is_active: true, current_nav: 1.0391 },
    { id: 3, core_fund_id: 2, class_name: "Class A", class_code: "HIF-A", currency: "USD", is_active: true, current_nav: 1.0215 },
    { id: 4, core_fund_id: 3, class_name: "Class I", class_code: "SES-I", currency: "USD", is_active: true, current_nav: 12.4 },
  ];

  const mk = (id: number, name: string, stage: 1 | 2 | 3 | 4, cls: number, fundName: string, deployedDaysAgo: number | null, product: "FUNDS" | "SHARES"): Batch => ({
    id, batch_name: name, certificate_number: `CERT-${1000 + id}`, total_principal: 0, total_capital: 0,
    date_deployed: deployedDaysAgo === null ? null : day(deployedDaysAgo), duration_days: 90, expected_close_date: day(-30),
    date_closed: null, is_active: stage < 4 || id !== 1, is_transferred: stage >= 2, deployment_confirmed: stage >= 3,
    stage, status: stage === 1 ? "Pending" : "Active", investors_count: 0, funds: [{ fund_name: fundName, total_principal: 0, investors_count: 0 }],
    created_at: iso(120 - id * 15), is_open: stage === 1, share_class_id: cls, product_type: product,
  });
  const batches: Batch[] = [
    mk(1, "Batch 2026-Q1", 3, 1, "Northwind Growth Fund", 90, "FUNDS"),
    mk(2, "Batch 2026-Q2", 3, 3, "Harbor Income Fund", 45, "FUNDS"),
    mk(3, "Batch 2026-Q3 (open)", 1, 1, "Northwind Growth Fund", null, "FUNDS"),
    mk(4, "Shares Batch 1", 2, 4, "Summit Equity Shares", null, "SHARES"),
  ];

  const investors: DemoState["investors"] = {};
  const investments: DemoInvestment[] = [];
  const spec: [number, number, number][] = [[1, 1, 9], [2, 3, 7], [3, 1, 4], [4, 4, 4]]; // batch, class, count
  let n = 0;
  spec.forEach(([batch_id, class_id, count]) => {
    for (let i = 0; i < count; i++) {
      n += 1;
      const cls = classes.find((c) => c.id === class_id)!;
      investors[investorCode(n)] = { name: `Demo Investor ${String(n).padStart(3, "0")}`, email: `demo.investor${String(n).padStart(3, "0")}@example.com`, phone: `+000 555 01${String(n).padStart(2, "0")}` };
      investments.push({
        id: n, batch_id, fund_id: cls.core_fund_id, class_id, investor_no: n,
        amount: 2000 + ((n * 7919) % 18) * 500, date_deposited: day(100 - batch_id * 8 - i),
        performance_pct: batch_id === 3 ? 0 : Math.round((1.2 + ((n * 37) % 90) / 10) * 100) / 100,
      });
    }
  });

  const withdrawals: Withdrawal[] = [
    { id: 1, client_id: investorCode(2), investor_name: investors[investorCode(2)]?.name, fund_id: 1, fund_name: "Northwind Growth Fund", amount: 1500, status: "Pending", date_withdrawn: day(3), approved_at: null, note: null, source: "investor_request" },
    { id: 2, client_id: investorCode(5), investor_name: investors[investorCode(5)]?.name, fund_id: 2, fund_name: "Harbor Income Fund", amount: 3000, status: "Approved", date_withdrawn: day(10), approved_at: iso(8), note: "Sample note", source: "investor_request" },
  ] as Withdrawal[];

  const emails: PendingEmail[] = [1, 2, 3].map((i) => ({
    id: i, email_type: "INVESTOR_STATEMENT", status: "Pending_Confirmation", recipient_email: `demo.investor00${i}@example.com`,
    recipient_name: `Demo Investor 00${i}`, subject: "Your sample statement", body: "<p>This is a sample email. Nothing is sent in demo mode.</p>",
    batch_name: "Batch 2026-Q1", fund_name: "Northwind Growth Fund", amount: 2500 * i, batch_id: 1, investor_id: i,
    currency_type: "USD", created_at: iso(1), processed_at: null,
  }));

  const audit = [
    { id: 1, action: "POST /api/v1/login", description: "Demo login", user_email: "demo@example.com", timestamp: iso(0.1) },
    { id: 2, action: "POST /api/v1/batches", description: "Created Batch 2026-Q3 (open)", user_email: "admin@example.com", timestamp: iso(5) },
    { id: 3, action: "PATCH /api/v1/withdrawals/2", description: "Approved withdrawal", user_email: "admin@example.com", timestamp: iso(8) },
  ];

  return { users, funds, classes, batches, investments, investors, withdrawals, emails, audit, seq: 1000 };
}

export type { BatchInvestor };
