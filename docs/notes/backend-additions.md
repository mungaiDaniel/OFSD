# Backend Additions — Requests for Daniel

This document tracks everything the frontend needs from the backend that was **not** in the original Development Guide. Update this whenever a new frontend requirement creates a backend dependency.

Daniel — please review this doc at the start of each sprint slot. Each entry has the current status, what's needed, and why.

**Legend:**
- 🔴 **Blocking** — frontend cannot proceed without this
- 🟡 **Soft** — frontend has a fallback but would benefit from this
- 🟢 **Done** — built and deployed
- ⚪ **Deferred** — agreed to defer, not needed yet

---

## 1. 🟡 GET /api/v1/funds/summary

**Added:** April 18, 2026 (D1 AM)
**Requested by:** Landing page Fund Performance card, Fund Management page
**Status:** Soft — frontend has fallback to "not yet valued" states if endpoint returns empty or 404

### Why this is needed

The Fund Management page and Landing page both need to display per-class NAV, total NAV, and performance data. These values come from joining `share_classes` with their latest `nav_history` row and the corresponding `valuation_snapshots` aggregation. Computing this on the frontend would:
1. Duplicate the valuation math that already exists on the backend
2. Require multiple round-trips (funds → classes → nav_history → snapshots)
3. Risk drift if the join logic differs from the valuation engine

A single summary endpoint makes both pages simple reads.

### Proposed contract

```
GET /api/v1/funds/summary

Response: {
  "status": 200,
  "data": {
    "as_of_date": "2026-04-10",
    "funds": [{
      "id": 1,
      "fund_name": "Axiom",
      "fund_code": "AXM",
      "is_active": true,
      "classes": [{
        "id": 1,
        "class_name": "Class I Participating Shares",
        "class_code": "KES_I",
        "currency": "KES",
        "is_active": true,
        "total_shares": 771.92,
        "prev_nav": 1329.4779,
        "current_nav": 1389.5737,
        "total_nav": 1072636.69,
        "performance_pct": 4.52,
        "valuation_date": "2026-04-10"
      }],
      "totals_by_currency": {
        "KES": 1072636.69,
        "USD": 220113.60
      },
      "weighted_performance_pct": 4.77
    }]
  }
}
```

### Implementation notes

- For classes with no valuations yet, return `null` for `prev_nav`, `current_nav`, `total_nav`, `performance_pct`, and `valuation_date`. Frontend will render "Not yet valued".
- `weighted_performance_pct` is `sum(class.total_nav * class.performance_pct) / sum(class.total_nav)` — but if classes span currencies, compute per-currency weights and then average, OR just weight globally (simpler, and acceptable since the frontend shows both per-class and per-currency totals anyway). Pick whichever, document the choice in the response.
- `as_of_date` should be the latest `valuation_date` across all included classes. If mixed, take the most recent.
- Query should use a single SQL statement with a window function / lateral join to pick the latest NAV per class. Avoid N+1 loops.

### Authorization

The landing page is public (`/`). Two options:
1. Make this endpoint public (no JWT required). Safe because it returns aggregate NAV only — no PII.
2. Keep it authenticated. Landing page shows fallback content for anonymous users; authenticated users see live data.

**Recommendation:** option 2 — keep it authenticated. Landing page is a splash screen, real data is for logged-in users.

---

## 2. 🟡 GET /api/v1/investors/:client_code (lookup endpoint)

**Added:** April 18, 2026 (D1 PM)
**Requested by:** Add Investor page, debounced client code lookup
**Status:** Need confirmation — may already exist via existing investor search endpoints

### Why this is needed

The Add Investor form does a debounced lookup (300ms) as the user types a client code. If the code already exists, the form auto-populates name/email/phone and switches to "existing investor" mode (which uses `POST /investors/existing`). If not, it stays in "new investor" mode.

The original dev doc mentions this behavior but doesn't specify the lookup endpoint.

### Proposed contract

```
GET /api/v1/investors/:client_code

Response (found): {
  "status": 200,
  "data": {
    "internal_client_code": "INV-001",
    "investor_name": "Jane Doe",
    "investor_email": "jane@example.com",
    "investor_phone": "+254700000000"
  }
}

Response (not found): {
  "status": 404,
  "message": "Investor not found"
}
```

Returns the first match (client codes are unique). Keep the response minimal — don't include investments list, just identity. The Add Investor form doesn't need anything else.

### Implementation notes

- Case-insensitive match on `internal_client_code`
- Return only the fields above, do not expose `is_admin`, tokens, or audit data
- No pagination needed (single result)

---

## 3. ⚪ Batch close confirmation / "close time" in POST /investors response

**Added:** April 18, 2026 (D1 PM)
**Requested by:** Add Investor success state
**Status:** Deferred — frontend can compute "next Thursday 9 AM" client-side if backend doesn't include it

### Why it would be nice

The Add Investor success state shows: *"Batch will close Thursday 23 April 2026 at 09:00 EAT"*. This is derived from the batch's `auto_close_at` field, which the backend already sets. Returning it in the `POST /investors` response saves the frontend from computing it.

### Proposed addition to POST /investors response

Add `"batch_close_at"` field to the existing response:

```json
{
  "status": 201,
  "data": {
    "investment_id": 42,
    "batch_id": 7,
    "batch_name": "AXM_KES_I_2026-04-23",
    "fund_name": "Axiom",
    "class_code": "KES_I",
    "currency": "KES",
    "deposit_amount": 1000000.00,
    "batch_close_at": "2026-04-23T09:00:00+03:00"   ← NEW
  }
}
```

Deferred because frontend can compute next-Thursday-9am from the batch_name date suffix. But including it is cleaner and avoids timezone edge cases.

---

## 4. 🟡 Landing page fund performance — connect to dashboard data source

**Added:** April 2026
**Requested by:** Sam
**Status:** Deferred — landing page currently uses GET /api/v1/funds/summary.

Once the dashboard is redesigned and its chart endpoints are finalised, the landing page Fund Performance card should be updated to fetch from the same endpoint as the dashboard performance charts, so both surfaces show identical data.

Action for Daniel: when dashboard chart endpoints are confirmed, notify Sam so LandingPage.tsx can be updated to point at the same source. No frontend change needed now — this is a future alignment task.

---

## 5. 🟡 GET /api/v1/transactions/recent

**Added:** April 2026
**Requested by:** Dashboard recent transactions table (OverviewPage redesign)
**Status:** Soft — dashboard shows empty state "No recent transactions" if endpoint not ready

### Why this is needed

The dashboard recent transactions table shows the last 10 transactions across all types (deposits, withdrawals, valuations) for a live activity feed. Requires a single endpoint that aggregates across tables.

### Proposed contract

```
GET /api/v1/transactions/recent

Response: { "status": 200, "data": [
  {
    "id": 1,
    "type": "deposit" | "withdrawal" | "valuation",
    "date": "2026-04-17",
    "investor_name": "Jane Doe",
    "internal_client_code": "INV-001",
    "fund_name": "Axiom",
    "class_code": "KES_I",
    "currency": "KES",
    "amount": 1014178.42,
    "status": "Completed"
  }
]}
```

### Implementation notes

- Return last 10 entries ordered by date DESC
- Aggregate from: investments (deposits), withdrawals, valuation_snapshots
- For valuations: use market_value as amount, status "Committed"
- No pagination needed for now

---

## 6. 🟡 GET /api/v1/investors/:client_code/overview

**Added:** April 19, 2026
**Requested by:** InvestorOverviewPage (`/investors/:code`)
**Status:** Soft — page shows empty state if endpoint not ready

### Why this is needed

The Investor Overview page shows an investor's full position: their identity info plus all batch positions with shares, market value, performance, and deployment NAV. This requires a join across `investments`, `investor_shares`, `valuation_snapshots`, and `nav_history`.

### Proposed contract

```
GET /api/v1/investors/:client_code/overview

Response: { "status": 200, "data": {
  "internal_client_code": "INV-001",
  "investor_name": "Jane Doe",
  "investor_email": "jane@example.com",
  "investor_phone": "+254700000001",
  "positions": [
    {
      "batch_id": 7,
      "batch_name": "AXM_KES_I_2026-04-10",
      "fund_name": "Axiom",
      "class_code": "KES_I",
      "currency": "KES",
      "deposit_amount": 1000000.00,
      "shares": 729.86,               // null if not yet deployed
      "market_value": 1014178.42,      // null if not yet valued
      "performance_pct": 4.52,         // null if not yet valued
      "deployment_nav": 1370.65,       // null if not yet deployed
      "current_nav": 1389.5737,        // null if not yet valued
      "deployment_date": "2026-04-10"  // null if not yet deployed
    }
  ]
}}
```

### Implementation notes

- One position per batch the investor participated in
- Shares/market_value/performance_pct come from most recent `valuation_snapshots` row for this investor+class
- `null` values for all fields if the batch hasn't been deployed yet (stage < 3)
- Ordered by deployment_date DESC

---

## 7. 🔴 GET /api/v1/reports/eligible-investors

**Added:** April 19, 2026
**Requested by:** ReportListPage — Generate & Send section
**Status:** Blocking — page shows empty state without this

### Why this is needed

The Generate & Send panel needs a list of investors eligible to receive a statement for a given period, filtered by fund/class. This is not derivable from the existing `/investors` list because it requires joining with `investments` (to confirm participation in the period) and checking statement history (to compute `last_statement_date` and `email_status`).

### Proposed contract

```
GET /api/v1/reports/eligible-investors?period=2026-04&fund_id=1&share_class_id=2

Response: { "status": 200, "data": [
  {
    "id": 1,
    "investor_name": "Jane Doe",
    "internal_client_code": "INV-001",
    "fund_name": "Axiom",
    "class_code": "KES_I",
    "currency": "KES",
    "investor_email": "jane@example.com",        // null if no email on file
    "last_statement_date": "2026-03-31",          // null if never sent
    "email_status": "ready" | "no_email" | "already_sent"
  }
]}
```

### Implementation notes
- `fund_id` and `share_class_id` are optional filters; if omitted, return all investors with at least one investment in the period
- `email_status`: "ready" = has email + not yet sent this period; "no_email" = no email address; "already_sent" = statement already sent for this period/class combo
- Order by investor_name ASC

---

## 8. 🔴 POST /api/v1/reports/generate

**Added:** April 19, 2026
**Requested by:** ReportListPage — "Send to N selected" action
**Status:** Blocking

### Why this is needed

The Generate & Send footer button submits a batch generation job for selected investors.

### Proposed contract

```
POST /api/v1/reports/generate

Body: {
  "period": "2026-04",
  "share_class_id": 2,             // optional — if omitted, use each investor's own class
  "investor_ids": [1, 3, 7, 11],
  "send_email": true
}

Response: { "status": 201, "data": { "report_run_id": 42 } }
```

### Implementation notes
- Generates one PDF per investor and emails it if `send_email: true`
- Creates a `report_runs` record tracking this batch
- Returns immediately with `report_run_id`; delivery status is async (email provider webhook)

---

## 9. 🔴 GET /api/v1/reports/runs

**Added:** April 19, 2026
**Requested by:** ReportListPage — Recent Report Runs table
**Status:** Blocking

### Proposed contract

```
GET /api/v1/reports/runs

Response: { "status": 200, "data": [
  {
    "id": 1,
    "sent_at": "2026-03-31T14:22:00+03:00",
    "period": "2026-03",
    "fund_name": "Axiom",
    "class_code": "KES_I",
    "recipient_count": 12,
    "sent_by": "sk@horizonafrica.com",
    "status": "sent" | "partial" | "failed"
  }
]}
```

- `sent`: all emails delivered; `partial`: some failed; `failed`: all failed or generation error
- Order by sent_at DESC, limit 50

---

## 10. 🔴 GET /api/v1/reports/runs/:id

**Added:** April 19, 2026
**Requested by:** ReportDetailPage
**Status:** Blocking

### Proposed contract

```
GET /api/v1/reports/runs/42

Response: { "status": 200, "data": {
  "id": 42,
  "period": "2026-03",
  "generated_at": "2026-03-31T14:22:00+03:00",
  "sent_by": "sk@horizonafrica.com",
  "fund_name": "Axiom",
  "class_code": "KES_I",
  "currency": "KES",
  "recipient_count": 12,
  "status": "sent",
  "recipients": [
    {
      "id": 1,
      "investor_name": "Jane Doe",
      "internal_client_code": "INV-001",
      "investor_email": "jane@example.com",
      "delivery": "delivered" | "failed" | "pending",
      "opened": true
    }
  ]
}}
```

### Implementation notes
- `opened` requires an email tracking pixel or link click callback; return false if tracking not implemented
- `delivery` is updated async by the email provider webhook

---

## 11. ⚪ GET /api/v1/reports/preview

**Added:** April 19, 2026
**Requested by:** ReportListPage — optional statement preview panel
**Status:** Deferred — panel is mocked as a placeholder for now; implement when PDF generation is ready

### Proposed contract

```
GET /api/v1/reports/preview?investor_code=INV-001&period=2026-04

Response: { "status": 200, "data": { "preview_url": "https://..." } }
// OR: stream the PDF directly as application/pdf
```

---

## MOCK DATA LAYER — How to remove when backend is ready

**Status:** 🟡 Active in dev. Remove once Daniel's endpoints are live.

The mock system lives entirely in `src/mocks/`. Nothing outside that folder is part of the mock system except one block in `api.ts`.

**TO DISABLE** (keep files, just turn off):
- Set `VITE_USE_MOCKS=false` in `.env.local` and restart dev server.

**TO REMOVE PERMANENTLY** (when all endpoints are live):
1. Delete `src/mocks/` folder entirely
2. Remove `VITE_USE_MOCKS` from `.env.local` and `.env.example`
3. In `src/services/api.ts`, delete the block marked: `// ── MOCK INTERCEPTOR (remove when backend ready) ──`
4. Remove the `import { USE_MOCKS }` line from `api.ts`
5. Run: `npm run build` — build must pass with zero errors. If it does, removal is complete.

The mock system adds zero overhead in production. When `VITE_USE_MOCKS !== 'true'`, mock handlers are never imported and are removed from the bundle by tree-shaking.

---

## Template for new entries

When adding a new requirement, use this format:

```markdown
## N. 🔴/🟡/🟢/⚪ <endpoint or change>

**Added:** <date> (<sprint slot>)
**Requested by:** <which page / feature>
**Status:** <current status>

### Why this is needed
<one paragraph explaining the frontend need>

### Proposed contract
<endpoint signature, request, response>

### Implementation notes
<any constraints, edge cases, or hints for Daniel>
```

---

## Questions open to Daniel (not requests, just clarifications)

1. **Batch auto-generation timezone** — is `auto_close_at` stored as UTC with tz info, or naive UTC, or local EAT? Frontend needs to know for display formatting.
2. **Valuation snapshot lookup** — when a statement is generated, do we look up the snapshot by `(investor_shares_id, valuation_date)` exact match, or do we take the most recent snapshot ≤ the statement period end? Affects "as of" date display on statements.
3. **Share class deactivation** — when `is_active` is flipped to false, does that cascade to any related records, or is it purely a UI-level filter? Relevant for the Add Investor fund/class dropdowns.

---

*Last updated: April 18, 2026*
