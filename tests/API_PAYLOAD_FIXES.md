# Test Payload Fixes Based on Actual API Analysis

## Key Findings from Endpoint Analysis

### 1. **User/Auth Endpoints** (`/api/v1/users`, `/api/v1/login`)
- **POST /users**: Expects `email`, `password`, `user_role` (NOT `name`)
- **POST /login**: Expects `email`, `password` → Returns `{"access_token": "...", "refresh_token": "...", "user_role": "..."}`
- **Response format**: User object directly (NOT wrapped in `{"status": ..., "data": ...}`)

### 2. **Batch Endpoints** (`/api/v1/batches`)
- **POST /batches**: Expects `batch_name`, `certificate_number`, `date_deployed`, `duration_days`
- **PUT /batches/<id>**: Expects `batch_name`, `date_closed`, `duration_days`, `is_active` (optional)
- **PATCH /batches/<id>**: Expects `batch_name`, `certificate_number`, `date_deployed`, `is_active` (optional)
- **PATCH /batches/<id>/update_status**: Expects `is_transferred`, `date_deployed`, or `is_active` (at least one)
- **Response format**: `{"status": 201, "data": {...}}` for POST; updated object for PATCH

### 3. **Valuation Endpoints** (`/api/v1/valuation`)
- **POST /valuation/dry-run**: Expects `fund_name`, `start_date`, `end_date`, `performance_rate_percent` (as %), `head_office_total`
- **POST /valuation/confirm**: Same fields as dry-run - COMMITS to DB
- **GET /batches/<id>/valuation-summary**: No params, returns valuation summary
- **Response format**: `{"status": 200, "data": {...}}` with `calculated_total`, `diff`, `is_reconciled`

### 4. **Performance Endpoints** (`/api/v1/batches/<id>/performance`)
- **POST /batches/<id>/performance**: Expects `gross_profit`, `transaction_costs`, `date_closed`
- **POST /batches/<id>/calculate-pro-rata**: Query param `fund_name` (REQUIRED as query string or body)
- **GET /batches/<id>/distributions**: No params, returns distributions grouped by fund
- **Response format**: Performance object or distribution array

### 5. **Reports Endpoints** (`/api/v1/reports`)
- **GET /reports**: NO PARAMS REQUIRED - just returns list (simple endpoint!)
- **GET /reports/portfolio**: Query param `as_of` (optional ISO date)
- **GET /batch/<id>/reconciliation**: Path param only
- **GET /batch/<id>/summary**: Returns Excel file or JSON

### 6. **Investments Endpoints** (`/api/v1/investments`)
- **POST /investments**: Expects `batch_id`, `investor_name`, `investor_email`, `investor_phone`, `amount_deposited`, `date_deposited`
- **PUT /investments/<id>**: Same fields but `date_deposited` optional
- **Response format**: Investment object directly

## Critical Issues to Fix

1. ✅ **Batch ID NULLs** - ALREADY FIXED (flush before using ID)
2. ⏳ **Valuation payloads** - Using `batch_id` but endpoint expects `fund_name`
3. ⏳ **Performance payloads** - Missing proper fields
4. ⏳ **Report tests** - Trying to POST to GET endpoints
5. ⏳ **Admin tests** - Wrong request/response formats

## Test Failure Root Causes

- 422 errors = Endpoint not recognizing the payload fields
- Tests sending `batch_id` when endpoint expects `fund_name`
- Tests using response format `data['status']` when status is HTTP code
- GET endpoints receiving POST/PUT methods
