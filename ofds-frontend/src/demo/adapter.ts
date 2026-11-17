/**
 * Axios adapter that answers every API call from an in-memory store, so the UI
 * runs with no backend. State lives in module scope: create/edit/delete work
 * for the session and reset on page reload.
 */
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import type { Batch, BatchInvestor } from "@/lib/types";
import { DEMO_USER } from "./config";
import { createSeed, investorCode, type DemoInvestment, type DemoState } from "./seed";

let S: DemoState = createSeed();
export const resetDemoState = () => {
  S = createSeed();
};

type Ctx = { params: string[]; query: URLSearchParams; body: any; method: string };
type Handler = (c: Ctx) => unknown;

const ok = (data?: unknown, message = "OK", extra: object = {}) => ({
  status: 200,
  message,
  ...(data !== undefined ? { data } : {}),
  ...extra,
});
class HttpError {
  constructor(public status: number, public message: string) {}
}
const fail = (status: number, message: string): never => {
  throw new HttpError(status, message);
};
const nextId = () => ++S.seq;
const now = () => new Date().toISOString();
const log = (action: string, description: string) =>
  S.audit.unshift({ id: nextId(), action, description, user_email: DEMO_USER.email, timestamp: now() });

// ── derived views ────────────────────────────────────────────────────────────
const cls = (id: number) => S.classes.find((c) => c.id === id)!;
const fund = (id: number) => S.funds.find((f) => f.id === id)!;
const batchOf = (id: number) => S.batches.find((b) => b.id === id);
const valued = (b: Batch | undefined) => !!b && b.stage >= 3;
const marketValue = (i: DemoInvestment) =>
  valued(batchOf(i.batch_id)) ? Math.round(i.amount * (1 + i.performance_pct / 100) * 100) / 100 : i.amount;
const codeNo = (code: string) => Number(code.replace(/\D/g, "")) || nextId();

function investorRow(i: DemoInvestment): BatchInvestor {
  const code = investorCode(i.investor_no);
  const p = S.investors[code];
  const c = cls(i.class_id);
  return {
    id: i.id,
    investor_name: p!.name,
    investor_email: p!.email,
    investor_phone: p!.phone,
    internal_client_code: code,
    amount_deposited: i.amount,
    fund_name: fund(i.fund_id).fund_name,
    fund_id: i.fund_id,
    date_deposited: i.date_deposited,
    opening_balance: i.amount,
    main_balance: i.amount,
    current_balance: marketValue(i),
    market_value: marketValue(i),
    withdrawals: 0,
    profit: marketValue(i) - i.amount,
    performance_pct: i.performance_pct,
    shares_owned: Math.round((i.amount / (c.current_nav || 1)) * 100) / 100,
    class_code: c.class_code,
    class_currency: c.currency,
  };
}

const matches = (r: BatchInvestor, search: string) =>
  !search || `${r.investor_name} ${r.internal_client_code} ${r.investor_email}`.toLowerCase().includes(search.toLowerCase());

function hydrate(b: Batch, withInvestors = false, search = ""): Batch {
  const inv = S.investments.filter((i) => i.batch_id === b.id);
  const total = inv.reduce((s, i) => s + i.amount, 0);
  const out: Batch = {
    ...b,
    total_principal: total,
    total_net_principal: total,
    total_capital: inv.reduce((s, i) => s + marketValue(i), 0),
    investors_count: inv.length,
    funds: [{ fund_name: b.funds[0]?.fund_name ?? "", total_principal: total, investors_count: inv.length }],
  };
  if (withInvestors) {
    const rows = inv.map(investorRow).filter((r) => matches(r, search));
    out.investments = rows;
    out.investments_pagination = { page: 1, per_page: 50, total: rows.length, total_pages: 1 };
    const g: Record<string, any> = {};
    rows.forEach((r) => {
      const k = r.fund_name ?? "Unassigned";
      g[k] ??= { fund_id: r.fund_id ?? null, fund_name: k, investor_count: 0, total_principal: 0, investors: [] };
      g[k].investor_count++;
      g[k].total_principal += r.amount_deposited;
      g[k].investors.push(r);
    });
    out.grouped_by_fund = g;
  }
  return out;
}

function directory(q: URLSearchParams) {
  const search = q.get("search") ?? "";
  const product = q.get("product");
  let rows = S.investments.map((i) => {
    const r = investorRow(i);
    return { ...r, shares: r.shares_owned, currency: cls(i.class_id).currency, product_type: fund(i.fund_id).product_type };
  });
  if (product) rows = rows.filter((r) => r.product_type === product);
  rows = rows.filter((r) => matches(r, search));
  const page = Number(q.get("page") ?? 1);
  const per = Number(q.get("per_page") ?? 50);
  return ok(rows.slice((page - 1) * per, page * per), "OK", {
    pagination: { page, per_page: per, total: rows.length, total_pages: Math.max(1, Math.ceil(rows.length / per)) },
  });
}

const sumBy = (a: DemoInvestment[], f: (i: DemoInvestment) => number) => a.reduce((s, i) => s + f(i), 0);

function overview() {
  const funds = S.investments.filter((i) => fund(i.fund_id).product_type === "FUNDS");
  const u = funds.filter((i) => cls(i.class_id).currency === "USD");
  const k = funds.filter((i) => cls(i.class_id).currency === "KES");
  const invUsd = sumBy(u, (i) => i.amount);
  const totUsd = sumBy(u, marketValue);
  const invKes = sumBy(k, (i) => i.amount) * 129;
  const totKes = sumBy(k, marketValue) * 129;
  const months = ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"];
  return ok({
    total_aum: totUsd,
    total_aum_usd: totUsd,
    total_aum_kes: totKes,
    invested_usd: invUsd,
    invested_kes: invKes,
    gain_usd: totUsd - invUsd,
    gain_kes: totKes - invKes,
    total_ngn: 0,
    invested_ngn: 0,
    gain_ngn: 0,
    total_withdrawals: S.withdrawals.filter((w) => w.status !== "Rejected").reduce((s, w) => s + w.amount, 0),
    total_investors: Object.keys(S.investors).length,
    total_investors_funds: funds.length,
    total_investors_shares: S.investments.length - funds.length,
    performance_pct: invUsd ? Math.round(((totUsd - invUsd) / invUsd) * 10000) / 100 : 0,
    active_batches: S.batches.filter((b) => b.is_active).length,
    open_batches: S.batches.filter((b) => b.is_open).length,
    flow_series: months.map((label, n) => ({ label, deposits: 12000 + n * 4300, withdrawals: 1500 + (n % 3) * 900 })),
    alloc_data: S.funds.map((f) => ({ name: f.fund_name, value: sumBy(S.investments.filter((i) => i.fund_id === f.id), marketValue) })),
    aum_data: {
      labels: months,
      funds: S.funds.slice(0, 2).map((f, n) => ({
        name: f.fund_name,
        data: months.map((_, m) => 40000 + n * 15000 + m * 3100),
        growth: months.map((_, m) => 1 + m * 0.4),
      })),
    },
  });
}

function fundSummary(product: string) {
  const funds = S.funds
    .filter((f) => f.product_type === product)
    .map((f) => {
      const inv = S.investments.filter((i) => i.fund_id === f.id);
      const tot = sumBy(inv, marketValue);
      const cost = sumBy(inv, (i) => i.amount);
      const cur = inv[0] ? cls(inv[0].class_id).currency : "USD";
      return {
        id: f.id,
        fund_name: f.fund_name,
        fund_code: f.fund_code,
        product_type: f.product_type,
        is_active: true,
        investors_count: inv.length,
        totals_by_currency: { [cur]: tot },
        invested_by_currency: { [cur]: cost },
        gain_by_currency: { [cur]: tot - cost },
        weighted_performance_pct: cost ? Math.round(((tot - cost) / cost) * 10000) / 100 : 0,
        classes: S.classes
          .filter((c) => c.core_fund_id === f.id)
          .map((c) => ({
            id: c.id,
            class_name: c.class_name,
            class_code: c.class_code,
            currency: c.currency,
            is_active: true,
            current_nav: c.current_nav,
            is_valued: true,
            nav_history: [0, 1, 2, 3, 4].map((m) => ({
              date: new Date(Date.now() - (4 - m) * 30 * 86_400_000).toISOString().slice(0, 10),
              nav: Math.round((c.current_nav ?? 1) * (0.95 + m * 0.0125) * 10000) / 10000,
            })),
          })),
      };
    });
  return ok({ as_of_date: now().slice(0, 10), funds });
}

const fundDetail = (f: DemoState["funds"][number]) => {
  const bs = S.batches
    .filter((b) => S.investments.some((i) => i.batch_id === b.id && i.fund_id === f.id))
    .map((b) => {
      const h = hydrate(b);
      return { batch_id: b.id, batch_name: b.batch_name, total_aum: h.total_capital, investor_count: h.investors_count, date_deployed: b.date_deployed, is_active: b.is_active };
    });
  return {
    ...f,
    total_aum: bs.reduce((s, b) => s + b.total_aum, 0),
    investor_count: bs.reduce((s, b) => s + b.investor_count, 0),
    batches: bs,
  };
};

const holdingsOf = (code: string) => S.investments.filter((i) => investorCode(i.investor_no) === code);

// ── route table ──────────────────────────────────────────────────────────────
const R: [string, RegExp, Handler][] = [];
const route = (m: string, p: string, h: Handler) => R.push([m, new RegExp(`^${p.replace(/:id/g, "([^/]+)")}/?$`), h]);
const idOf = (c: Ctx, n = 0) => Number(c.params[n]);
const codeOf = (c: Ctx) => decodeURIComponent(c.params[0] ?? "");

route("POST", "/login", () => ({
  value: { access_token: "demo-token", refresh_token: "demo-refresh", role: DEMO_USER.role, name: DEMO_USER.name },
}));
route("POST", "/users", ({ body }) => {
  const u = { id: nextId(), name: body.name, email: body.email, role: "user" as const, status: "pending" as const, created: now() };
  S.users.push(u);
  return ok(u, "Registered (demo)");
});
route("GET", "/users", () => S.users);
route("GET", "/users/:id", (c) => S.users.find((u) => u.id === idOf(c)) ?? fail(404, "User not found"));
route("PATCH", "/users/:id/approve", (c) => {
  const u = S.users.find((x) => x.id === idOf(c));
  if (u) u.status = "active";
  return u;
});
route("PATCH", "/users/:id/status", (c) => {
  const u = S.users.find((x) => x.id === idOf(c));
  if (u) u.status = c.body.status;
  return u;
});
route("PATCH", "/users/:id/role", (c) => {
  const u = S.users.find((x) => x.id === idOf(c));
  if (u) u.role = c.body.role;
  return u;
});
route("PATCH", "/users/:id/reset-password", () => ok(undefined, "Password reset (demo)"));
route("DELETE", "/users/:id", (c) => {
  S.users = S.users.filter((u) => u.id !== idOf(c));
  return ok(undefined, "Deleted");
});

route("GET", "/stats/overview", () => overview());
route("GET", "/transactions/recent", () =>
  ok(
    S.investments.slice(-8).reverse().map((i) => ({
      id: i.id,
      type: "deposit",
      date: i.date_deposited,
      investor_name: S.investors[investorCode(i.investor_no)]?.name ?? "",
      internal_client_code: investorCode(i.investor_no),
      fund_name: fund(i.fund_id).fund_name,
      class_code: cls(i.class_id).class_code,
      currency: cls(i.class_id).currency,
      amount: i.amount,
      status: "Completed",
    })),
  ),
);

route("GET", "/batches", ({ query }) => {
  const p = query.get("product");
  return ok(S.batches.filter((b) => !p || b.product_type === p).map((b) => hydrate(b)), "OK", { count: S.batches.length });
});
route("POST", "/batches", ({ body }) => {
  const c = cls(body.share_class_id ?? 1);
  const b: Batch = {
    id: nextId(), batch_name: body.batch_name, certificate_number: body.certificate_number ?? null,
    total_principal: 0, total_capital: 0, date_deployed: body.date_deployed ?? null, duration_days: body.duration_days ?? 90,
    expected_close_date: null, date_closed: null, is_active: true, is_transferred: false, deployment_confirmed: false,
    stage: 1, status: "Pending", investors_count: 0,
    funds: [{ fund_name: fund(c.core_fund_id).fund_name, total_principal: 0, investors_count: 0 }],
    created_at: now(), is_open: true, share_class_id: c.id, product_type: fund(c.core_fund_id).product_type,
  };
  S.batches.push(b);
  log("POST /api/v1/batches", `Created ${b.batch_name}`);
  return ok(b, "Batch created (demo)");
});
route("GET", "/batches/notifications/recent", () => ok([]));
route("GET", "/batches/:id", (c) => {
  const b = batchOf(idOf(c));
  return b ? ok(hydrate(b, true, c.query.get("search") ?? "")) : fail(404, "Batch not found");
});
route("GET", "/batches/:id/investments-light", (c) =>
  ok(
    S.investments.filter((i) => i.batch_id === idOf(c)).map((i) => {
      const r = investorRow(i);
      return {
        id: r.id, investor_name: r.investor_name, internal_client_code: r.internal_client_code,
        amount_deposited: r.amount_deposited, main_balance: r.main_balance, share_class_id: i.class_id,
        class_code: r.class_code, class_currency: r.class_currency, date_deposited: r.date_deposited,
        deployment_date: batchOf(i.batch_id)?.date_deployed,
      };
    }),
  ),
);
route("PATCH", "/batches/:id/toggle-active", (c) => {
  const b = batchOf(idOf(c));
  if (b) b.is_active = !b.is_active;
  return ok(b, "Toggled");
});
route("PATCH", "/batches/:id", (c) => {
  const b = batchOf(idOf(c));
  if (!b) return fail(404, "Batch not found");
  Object.assign(b, c.body);
  if (typeof c.body.stage === "number") {
    b.is_transferred = c.body.stage >= 2;
    b.deployment_confirmed = c.body.stage >= 3;
    b.is_open = c.body.stage === 1;
  }
  log(`PATCH /api/v1/batches/${b.id}`, "Updated batch");
  return ok(hydrate(b), "Batch updated (demo)");
});
route("DELETE", "/batches/:id", (c) => {
  const id = idOf(c);
  S.batches = S.batches.filter((b) => b.id !== id);
  S.investments = S.investments.filter((i) => i.batch_id !== id);
  log(`DELETE /api/v1/batches/${id}`, "Deleted batch");
  return ok(undefined, "Batch deleted (demo)");
});
route("GET", "/batches/:id/summary", (c) => ok(hydrate(batchOf(idOf(c))!)));
route("GET", "/batches/:id/funds", (c) => ok(hydrate(batchOf(idOf(c))!).funds));
route("GET", "/batches/:id/email-logs", () => ok([]));
route("GET", "/batches/:id/history", () => ok([]));
route("GET", "/batches/:id/performance", () => ok([]));
route("GET", "/batches/:id/distributions", () => ok([]));

route("GET", "/funds/summary", () => fundSummary("FUNDS"));
route("GET", "/shares/summary", () => fundSummary("SHARES"));
for (const [base, product] of [["/funds", "FUNDS"], ["/shares", "SHARES"]] as const) {
  route("GET", base, () => ok(S.funds.filter((f) => f.product_type === product).map(fundDetail)));
  route("POST", base, ({ body }) => {
    const f = { id: nextId(), fund_name: body.fund_name, fund_code: body.fund_code, description: body.description ?? null, product_type: product, is_active: true };
    S.funds.push(f);
    log(`POST /api/v1${base}`, `Created ${f.fund_name}`);
    return ok(f, "Created (demo)");
  });
  route("GET", `${base}/:id`, (c) => {
    const f = S.funds.find((x) => x.id === idOf(c));
    return f ? ok(fundDetail(f)) : fail(404, "Not found");
  });
  route("GET", `${base}/:id/edit-context`, (c) => {
    const f = S.funds.find((x) => x.id === idOf(c))!;
    return ok({
      fund: { ...f, version: 1 },
      classes: S.classes.filter((k) => k.core_fund_id === f.id).map((k) => ({ ...k, version: 1, currency_locked: true })),
      currencies: ["USD", "KES"],
    });
  });
  route("PATCH", `${base}/:id`, (c) => {
    const f = S.funds.find((x) => x.id === idOf(c));
    if (f) Object.assign(f, c.body);
    return ok({ ...f, version: 2 }, "Updated (demo)");
  });
  route("DELETE", `${base}/:id`, (c) => {
    S.funds = S.funds.filter((f) => f.id !== idOf(c));
    return ok(undefined, "Deleted (demo)");
  });
  route("GET", `${base}/:id/classes`, (c) => ok(S.classes.filter((k) => k.core_fund_id === idOf(c))));
  route("POST", `${base}/:id/classes`, (c) => {
    const k = { id: nextId(), core_fund_id: idOf(c), is_active: true, current_nav: 1, ...c.body };
    S.classes.push(k);
    return ok(k, "Created (demo)");
  });
  route("PATCH", `${base}/:id/classes/:id`, (c) => {
    const k = S.classes.find((x) => x.id === idOf(c, 1));
    if (k) Object.assign(k, c.body);
    return ok(k, "Updated (demo)");
  });
}

route("GET", "/investors", ({ query }) => directory(query));
route("POST", "/investors", ({ body }) => {
  const code = body.internal_client_code as string;
  if (S.investors[code]) return fail(409, `Client code ${code} already exists`);
  S.investors[code] = { name: body.investor_name, email: body.investor_email, phone: body.investor_phone ?? "" };
  const open = S.batches.find((b) => b.is_open && b.share_class_id === body.share_class_id) ?? S.batches.find((b) => b.is_open) ?? S.batches[0];
  S.investments.push({
    id: nextId(), batch_id: open!.id, fund_id: body.fund_id, class_id: body.share_class_id, investor_no: codeNo(code),
    amount: body.deposit_amount, date_deposited: body.deposit_date, performance_pct: 0,
  });
  log("POST /api/v1/investors", `Added ${code}`);
  return ok(undefined, "Investor created (demo)");
});
route("POST", "/investors/existing", ({ body }) => {
  const code = Object.keys(S.investors).find((k) => k.toLowerCase() === String(body.internal_client_code).toLowerCase());
  if (!code) return fail(404, "Investor not found");
  const open = S.batches.find((b) => b.is_open) ?? S.batches[0];
  S.investments.push({
    id: nextId(), batch_id: open!.id, fund_id: body.fund_id, class_id: body.share_class_id, investor_no: codeNo(code),
    amount: body.deposit_amount, date_deposited: body.deposit_date, performance_pct: 0,
  });
  return ok(undefined, "Deposit added (demo)");
});
route("GET", "/investors/:id/overview", (c) => {
  const code = codeOf(c);
  const p = S.investors[code];
  if (!p) return fail(404, "Investor not found");
  const inv = holdingsOf(code);
  const first = inv[0];
  const b = first && batchOf(first.batch_id);
  return ok({
    internal_client_code: code, investor_name: p.name, investor_email: p.email, investor_phone: p.phone,
    wealth_manager: "Sample Manager", IFA: null, contract_note: null,
    current_batch: {
      batch_id: b?.id ?? null, batch_name: b?.batch_name ?? null, stage: b?.stage ?? null, is_active: b?.is_active ?? null,
      share_class_id: first?.class_id ?? null, class_code: first ? cls(first.class_id).class_code : null,
      currency: first ? cls(first.class_id).currency : null,
    },
    positions: inv.map((i) => {
      const bb = batchOf(i.batch_id)!;
      const k = cls(i.class_id);
      return {
        batch_id: bb.id, batch_name: bb.batch_name, batch_stage: bb.stage, batch_is_active: bb.is_active, batch_is_open: !!bb.is_open,
        share_class_id: k.id, fund_name: fund(i.fund_id).fund_name, class_code: k.class_code, currency: k.currency,
        deposit_amount: i.amount, shares: Math.round((i.amount / (k.current_nav || 1)) * 100) / 100,
        market_value: marketValue(i), performance_pct: i.performance_pct, deployment_nav: 1, current_nav: k.current_nav,
        deployment_date: bb.date_deployed, product_type: fund(i.fund_id).product_type,
      };
    }),
  });
});
route("GET", "/investors/:id/deposits", (c) => ok(holdingsOf(codeOf(c)).map(investorRow)));
route("GET", "/investors/:id/portfolio", (c) => ok(holdingsOf(codeOf(c)).map(investorRow)));
route("PATCH", "/investors/:id", (c) => {
  const p = S.investors[codeOf(c)];
  if (p) {
    if (c.body.investor_name) p.name = c.body.investor_name;
    if (c.body.investor_email) p.email = c.body.investor_email;
    if (c.body.investor_phone) p.phone = c.body.investor_phone;
  }
  return ok(undefined, "Updated (demo)");
});
route("GET", "/investors/:id/history", () => ok([]));
route("GET", "/investors/:id/statements", () => ok([]));
route("GET", "/investors/:id/email-logs", () => ok([]));

route("GET", "/withdrawals", ({ query }) => {
  const st = query.get("status");
  const rows = S.withdrawals.filter((w) => !st || w.status === st);
  return ok(rows, "OK", { pagination: { page: 1, per_page: 50, total: rows.length, total_pages: 1 } });
});
route("POST", "/withdrawals", ({ body }) => {
  const w = {
    id: nextId(), client_id: body.internal_client_code, investor_name: S.investors[body.internal_client_code]?.name ?? null,
    fund_id: body.fund_id, fund_name: fund(body.fund_id)?.fund_name ?? "", amount: body.amount, status: "Pending",
    date_withdrawn: now().slice(0, 10), approved_at: null, note: null, source: "investor_request",
  } as any;
  S.withdrawals.unshift(w);
  return ok(w, "Withdrawal recorded (demo)");
});
route("PATCH", "/withdrawals/:id", (c) => {
  const w = S.withdrawals.find((x) => x.id === idOf(c));
  if (w) {
    w.status = c.body.status;
    if (c.body.note) w.note = c.body.note;
    if (c.body.status === "Approved") w.approved_at = now();
  }
  return ok(w, `Withdrawal ${String(c.body.status).toLowerCase()} (demo)`);
});

route("GET", "/emails/pending", () =>
  ok(S.emails.filter((e) => e.status === "Pending_Confirmation"), "OK", { count: S.emails.length }),
);
route("GET", "/emails/status-counts", () =>
  ok(undefined, "OK", {
    status_counts: S.emails.reduce<Record<string, number>>((a, e) => {
      const k = e.status ?? "unknown";
      a[k] = (a[k] ?? 0) + 1;
      return a;
    }, {}),
  }),
);
route("GET", "/emails/queue-status", () =>
  ok({ next_run_at: null, queued_count: S.emails.filter((e) => e.status === "Queued").length, batch_size: 100, interval_minutes: 5 }),
);
route("POST", "/emails/:id/confirm", (c) => {
  const e = S.emails.find((x) => x.id === idOf(c));
  if (e) {
    e.status = "Confirmed";
    e.processed_at = now();
  }
  return ok(e, "Email sent (demo — nothing was actually sent)");
});
route("POST", "/emails/:id/cancel", (c) => {
  const e = S.emails.find((x) => x.id === idOf(c));
  if (e) e.status = "Suppressed";
  return ok(e, "Email cancelled");
});
route("POST", "/emails/confirm-all", () => {
  S.emails.forEach((e) => {
    if (e.status === "Pending_Confirmation") e.status = "Confirmed";
  });
  return ok(undefined, "All emails confirmed (demo)");
});
route("POST", "/emails/suppress-all", () => {
  S.emails.forEach((e) => {
    if (e.status === "Pending_Confirmation") e.status = "Suppressed";
  });
  return ok(undefined, "All emails suppressed (demo)");
});

route("GET", "/audit-logs", () =>
  ok(
    S.audit.map((a) => ({
      ...a, user_id: 1, user_name: "Demo User", target_type: null, target_id: null, target_name: null,
      old_value: null, new_value: null, ip_address: "203.0.113.7", user_agent: "demo", success: true, error_message: null,
    })),
  ),
);
route("GET", "/backups/status", () => ok({ enabled: false, next_run_at: null, last_backup: null }));
route("GET", "/backups", () => ok([]));
route("POST", "/backups/run-now", () => fail(400, "Backups are disabled in demo mode"));
route("GET", "/settings/email", () =>
  ok({
    mail_server: "smtp.example.com", mail_port: 587, mail_use_tls: true, mail_use_ssl: false,
    mail_username: "noreply@example.com", mail_default_sender: "noreply@example.com", mail_bcc: null,
    has_password: false, email_queue_batch_size: 100, email_queue_interval_minutes: 5,
  }),
);
route("GET", "/settings/email/queue", () => ok({ batch_size: 100, interval_minutes: 5, next_run_at: null, queued_count: 0 }));

// ── adapter ──────────────────────────────────────────────────────────────────
export const demoAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig): Promise<AxiosResponse> => {
  const url = new URL(config.url ?? "/", "http://demo.local");
  const query = url.searchParams;
  if (config.params) Object.entries(config.params).forEach(([k, v]) => v != null && query.set(k, String(v)));
  const method = (config.method ?? "get").toUpperCase();
  let body: any = config.data;
  if (typeof body === "string") {
    try {
      body = JSON.parse(body);
    } catch {
      /* not JSON */
    }
  }
  const path = url.pathname.replace(/^\/api\/v1/, "");

  let status = 200;
  let data: unknown;
  const hit = R.find(([m, re]) => m === method && re.test(path));
  try {
    if (hit) {
      data = hit[2]({ params: (hit[1].exec(path) ?? []).slice(1), query, body, method });
    } else if (config.responseType === "blob") {
      data = new Blob(["Demo mode: file downloads are disabled."], { type: "text/plain" });
    } else {
      // Unmapped endpoint: an empty-but-valid payload so pages render an empty state.
      data = method === "GET" ? ok([]) : ok(undefined, "Saved (demo)");
    }
  } catch (e) {
    if (!(e instanceof HttpError)) throw e;
    status = e.status;
    data = { status: e.status, message: e.message };
  }
  await new Promise((r) => setTimeout(r, 120)); // feel like a network call
  const res: AxiosResponse = { data, status, statusText: String(status), headers: {}, config, request: {} };
  if (status >= 400) throw Object.assign(new Error(`Request failed with status code ${status}`), { isAxiosError: true, response: res, config });
  return res;
};
