# Multi-Fund API Reference Documentation

## 📍 Base URL
```
http://localhost:5000/api/v1
```

## 🔐 Authentication
All endpoints (except `/login` and `/users` POST) require JWT token:
```
Authorization: Bearer <access_token>
```

---

## 🏦 FUND MANAGEMENT ENDPOINTS

### 1. Get All Funds in Batch
```
GET /batches/{batch_id}/funds
```

**Parameters:**
- `batch_id` (path): Batch ID

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
    "status": 200,
    "message": "Funds retrieved successfully",
    "data": [
        {
            "id": 1,
            "fund_name": "Axiom",
            "certificate_number": "CERT-Q1-001",
            "total_capital": 350000.00,
            "date_deployed": "2026-03-01T00:00:00",
            "expected_close_date": "2026-03-31T00:00:00",
            "investor_count": 7,
            "is_active": true
        },
        {
            "id": 2,
            "fund_name": "Atium",
            "certificate_number": "CERT-Q1-001",
            "total_capital": 250000.00,
            "date_deployed": "2026-03-01T00:00:00",
            "expected_close_date": "2026-03-31T00:00:00",
            "investor_count": 5,
            "is_active": true
        }
    ]
}
```

**Status Codes:**
- `200`: Success
- `404`: Batch not found
- `500`: Server error

---

### 2. Get Fund Details
```
GET /batches/{batch_id}/funds/{fund_name}
```

**Parameters:**
- `batch_id` (path): Batch ID
- `fund_name` (path): Fund name (e.g., "Axiom")

**Response (200):**
```json
{
    "status": 200,
    "message": "Fund summary retrieved",
    "data": {
        "fund_name": "Axiom",
        "total_capital": 350000.00,
        "expected_close_date": "2026-03-31T00:00:00",
        "investor_count": 7,
        "investments": [
            {
                "id": 1,
                "investor_name": "John Doe",
                "internal_client_code": "AXIOM-001",
                "amount_deposited": 50000.00,
                "date_deposited": "2026-03-10T00:00:00"
            }
        ],
        "performance_records": [
            {
                "id": 1,
                "report_date": "2026-03-31T00:00:00",
                "gross_profit": 100000.00,
                "transaction_costs": 5000.00,
                "net_profit": 95000.00,
                "cumulative_profit": 95000.00
            }
        ],
        "distributions": [
            {
                "investor_name": "John Doe",
                "internal_client_code": "AXIOM-001",
                "days_active": 21,
                "profit_share_percentage": 26.53,
                "profit_allocated": 25203.50
            }
        ]
    }
}
```

---

## 📊 PERFORMANCE ENDPOINTS

### 3. Record Fund Performance
```
POST /batches/{batch_id}/funds/{fund_name}/performance
```

**Parameters:**
- `batch_id` (path): Batch ID
- `fund_name` (path): Fund name (e.g., "Axiom")

**Request Body:**
```json
{
    "gross_profit": 100000.00,
    "transaction_costs": 5000.00,
    "reporting_period": "MONTHLY"
}
```

**Request Headers:**
```
Content-Type: application/json
Authorization: Bearer <token>
```

**Response (201):**
```json
{
    "status": 201,
    "message": "Performance recorded for fund Axiom",
    "data": {
        "id": 1,
        "fund_name": "Axiom",
        "gross_profit": 100000.00,
        "transaction_costs": 5000.00,
        "net_profit": 95000.00,
        "cumulative_profit": 95000.00,
        "report_date": "2026-03-31T00:00:00"
    }
}
```

**Validation:**
- `gross_profit` and `transaction_costs` must be numeric
- Fund must exist in batch
- Batch must exist

**Notes:**
- Records are INDEPENDENT per fund
- Can record Axiom performance without Atium
- `cumulative_profit` sums previous periods

---

## 📤 EXCEL UPLOAD ENDPOINT

### 4. Bulk Upload Investments from Excel
```
POST /batches/{batch_id}/upload-excel
```

**Parameters:**
- `batch_id` (path): Batch ID

**Request Headers:**
```
Content-Type: multipart/form-data
Authorization: Bearer <token>
```

**Request Body:**
```
file: <Excel file (.xlsx)>
```

**Excel Format (Required Columns):**
```
investor_name | investor_email | internal_client_code | amount(usd) | fund | date_transferred
```

**Excel Example:**
```
John Doe       | john@ex.com    | AXIOM-001           | 50000.00    | Axiom | 2026-03-10
Jane Smith     | jane@ex.com    | AXIOM-002           | 40000.00    | Axiom | 2026-03-01
Bob Wilson     | bob@ex.com     | ATIUM-008           | 75000.00    | Atium | 2026-03-05
```

**Response (201):**
```json
{
    "status": 201,
    "message": "Successfully created 12 investments",
    "data": {
        "created_count": 12,
        "funds": {
            "Axiom": {
                "fund_id": 1,
                "investor_count": 7,
                "total_capital": 350000.00
            },
            "Atium": {
                "fund_id": 2,
                "investor_count": 5,
                "total_capital": 250000.00
            }
        }
    }
}
```

**Auto-Assignment (if 'fund' column missing):**
```
Row 1-7   → Investors assigned to 'Axiom'
Row 8-12  → Investors assigned to 'Atium'
```

**Error Responses:**
- `400`: Invalid file format or missing columns
- `404`: Batch not found
- `500`: Processing error

**Validation:**
- File must be `.xlsx` (Excel 2016+)
- All required columns must be present
- `amount(usd)` must be numeric
- `internal_client_code` must be unique
- `investor_email` must be valid email format

---

## 📅 LIVE WEEKLY CALCULATION ENDPOINTS

### 5. Get Live Weekly Update
```
GET /batches/{batch_id}/funds/{fund_name}/weekly-update
```

**Parameters:**
- `batch_id` (path): Batch ID
- `fund_name` (path): Fund name (e.g., "Axiom")

**Response (200):**
```json
{
    "status": 200,
    "message": "Weekly update calculated",
    "data": {
        "batch_id": 1,
        "fund_name": "Axiom",
        "as_of_date": "2026-03-23T00:00:00",
        "total_capital": 350000.00,
        "total_days_active": 13,
        "investor_count": 7,
        "investors": [
            {
                "investor_name": "John Doe",
                "internal_client_code": "AXIOM-001",
                "amount_deposited": 50000.00,
                "date_deposited": "2026-03-10T00:00:00",
                "days_active": 13,
                "expected_close_date": "2026-03-31T00:00:00"
            },
            {
                "investor_name": "Jane Smith",
                "internal_client_code": "AXIOM-002",
                "amount_deposited": 40000.00,
                "date_deposited": "2026-03-01T00:00:00",
                "days_active": 22,
                "expected_close_date": "2026-03-31T00:00:00"
            }
        ]
    }
}
```

**Key Difference:**
- Does NOT require performance data
- Shows LIVE accrually (as of today)
- Use for weekly investor statements before month-end

---

## 🧮 PRO-RATA CALCULATION ENDPOINTS

### 6. Calculate All Funds Distributions
```
POST /batches/{batch_id}/calculate-all-funds
```

**Parameters:**
- `batch_id` (path): Batch ID

**Request Headers:**
```
Content-Type: application/json
Authorization: Bearer <token>
```

**Request Body:**
```json
{
    "performance_data": {
        "Axiom": 1,
        "Atium": 2
    }
}
```

**Explanation of Body:**
- `performance_data`: Object mapping fund names to performance record IDs
- Get performance IDs from performance recording responses
- MUST include all funds in batch

**Response (200):**
```json
{
    "status": 200,
    "message": "All fund distributions calculated successfully",
    "data": {
        "batch_id": 1,
        "calculation_date": "2026-03-31T00:00:00",
        "distribution_count": 12,
        "total_batch_value": 167500.00,
        "funds": {
            "Axiom": {
                "investor_count": 7,
                "total_allocated": 95000.00,
                "distributions": [
                    {
                        "investment_id": 1,
                        "investor_name": "John Doe",
                        "investor_email": "john@ex.com",
                        "internal_client_code": "AXIOM-001",
                        "fund_name": "Axiom",
                        "amount_deposited": 50000.00,
                        "date_deposited": "2026-03-10T00:00:00",
                        "days_active": 21,
                        "weighted_capital": 1050000.00,
                        "profit_share_percentage": 26.53,
                        "profit_allocated": 25203.50
                    }
                ]
            },
            "Atium": {
                "investor_count": 5,
                "total_allocated": 72500.00,
                "distributions": [
                    {
                        "investment_id": 8,
                        "investor_name": "Bob Wilson",
                        "investor_email": "bob@ex.com",
                        "internal_client_code": "ATIUM-008",
                        "fund_name": "Atium",
                        "amount_deposited": 75000.00,
                        "date_deposited": "2026-03-05T00:00:00",
                        "days_active": 26,
                        "weighted_capital": 1950000.00,
                        "profit_share_percentage": 63.22,
                        "profit_allocated": 45855.50
                    }
                ]
            }
        }
    }
}
```

**Calculation Logic:**
1. For each fund, gets all investments
2. Calculates days_active for each investor
3. Calculates weighted_capital (amount × days)
4. Calculates profit_share_percentage (weighted / total × 100)
5. Allocates profit (share % × fund net profit)
6. Creates ProRataDistribution records

**Validation:**
- Batch must exist
- All funds must have performance data
- Fund must have at least one investment

**Important Notes:**
- Creates permanent distribution records
- Can be recalculated (old records removed first)
- Days active uses LIVE current date calculation
- Profit shares sum to 100% per fund

---

## 📋 BATCH SUMMARY ENDPOINTS

### 7. Get Comprehensive Batch Summary
```
GET /batches/{batch_id}/summary
```

**Parameters:**
- `batch_id` (path): Batch ID

**Response (200):**
```json
{
    "status": 200,
    "message": "Batch summary retrieved",
    "data": {
        "batch_id": 1,
        "batch_name": "Q1-2026-OFFSHORE",
        "certificate_number": "CERT-Q1-001",
        "date_deployed": "2026-03-01T00:00:00",
        "expected_close_date": "2026-03-31T00:00:00",
        "total_batch_capital": 600000.00,
        "fund_count": 2,
        "funds": [
            {
                "fund_name": "Axiom",
                "total_capital": 350000.00,
                "investor_count": 7,
                "performance_records": 1,
                "total_distributed": 95000.00,
                "expected_close_date": "2026-03-31T00:00:00"
            },
            {
                "fund_name": "Atium",
                "total_capital": 250000.00,
                "investor_count": 5,
                "performance_records": 1,
                "total_distributed": 72500.00,
                "expected_close_date": "2026-03-31T00:00:00"
            }
        ]
    }
}
```

**Use Cases:**
- Dashboard overview
- Portfolio summary
- Batch status check

---

## 📄 REPORTING ENDPOINTS

### 8. Generate PDF Statement
```
GET /batches/{batch_id}/report/pdf?download=true
```

**Parameters:**
- `batch_id` (path): Batch ID
- `download` (query): "true" to save file, "false" for JSON response

**Response (200):**
```json
{
    "status": 200,
    "message": "PDF generated successfully",
    "data": {
        "batch_id": 1,
        "result": "PDF saved to reports/batch_1_20260331_143022.pdf"
    }
}
```

**PDF Contents:**
- Batch summary header
- Per-fund sections with:
  - Fund metadata
  - Investment table (investor details)
  - Distribution table (profit allocations)
- Summary statistics

**File Location:**
- Saved to: `reports/batch_{id}_{timestamp}.pdf`
- Automatically creates reports/ directory

---

## ⚠️ ERROR RESPONSES

### Standard Error Format
All error responses follow this format:

```json
{
    "status": <http_code>,
    "message": "<error description>"
}
```

### Common Error Codes

| Code | Scenario | Example |
|------|----------|---------|
| 400 | Bad Request | Invalid file format, missing fields |
| 401 | Invalid Token | Token expired, signature invalid |
| 403 | Permission Denied | Insufficient access level |
| 404 | Not Found | Batch/Fund/Investment doesn't exist |
| 409 | Conflict | Duplicate certificate number |
| 500 | Server Error | Database connection, processing error |

### Example Error Response (400)
```json
{
    "status": 400,
    "message": "File must be Excel (.xlsx or .xls)"
}
```

---

## 🔄 Workflow Example (Curl Commands)

### Complete Setup Sequence

```bash
# 1. Create batch
curl -X POST http://localhost:5000/api/v1/batches \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "batch_name": "Q1-2026",
    "certificate_number": "CERT-Q1",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30
  }'
# Save batch_id (e.g., 1)

# 2. Upload Excel
curl -X POST http://localhost:5000/api/v1/batches/1/upload-excel \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@investors.xlsx"

# 3. Record Axiom performance
curl -X POST http://localhost:5000/api/v1/batches/1/funds/Axiom/performance \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "gross_profit": 100000.00,
    "transaction_costs": 5000.00
  }'
# Save performance_id (e.g., 1)

# 4. Record Atium performance
curl -X POST http://localhost:5000/api/v1/batches/1/funds/Atium/performance \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "gross_profit": 75000.00,
    "transaction_costs": 2500.00
  }'
# Save performance_id (e.g., 2)

# 5. Calculate distributions
curl -X POST http://localhost:5000/api/v1/batches/1/calculate-all-funds \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "performance_data": {
      "Axiom": 1,
      "Atium": 2
    }
  }'

# 6. Get summary
curl http://localhost:5000/api/v1/batches/1/summary \
  -H "Authorization: Bearer $TOKEN"

# 7. Generate PDF
curl "http://localhost:5000/api/v1/batches/1/report/pdf?download=true" \
  -H "Authorization: Bearer $TOKEN" \
  -o batch_statement.pdf
```

---

## 📊 Data Types & Validation

### Numeric Fields
- **Decimal Amounts**: `Numeric(20, 2)` - Up to 20 digits, 2 decimals
  - Examples: `50000.00`, `95000.50`, `1234567.89`
  - Min: `0.01`, Max: `99999999999999999.99`

- **Percentages**: `Numeric(10, 4)` - Up to 10 digits, 4 decimals
  - Examples: `26.5300`, `0.0001`, `100.0000`
  - Range: 0.0000 to 100.0000

### Date/Time Fields
- Format: `ISO 8601` (RFC 3339)
- Example: `2026-03-31T00:00:00` or `2026-03-31T14:30:00`
- Timezone: UTC (assumed)

### String Fields
- `fund_name`: Max 100 chars, case-sensitive
- `investor_name`: Max 100 chars
- `investor_email`: Valid email format
- `internal_client_code`: Max 50 chars, must be unique

---

## 🔐 Permission Levels

All `/api/v1` endpoints require JWT token with appropriate level:

| Endpoint | Min Level | Role |
|----------|-----------|------|
| GET /funds | 0 | user, admin, super_admin |
| POST /upload-excel | 1 | admin, super_admin |
| POST /performance | 1 | admin, super_admin |
| POST /calculate-all-funds | 1 | admin, super_admin |
| GET /summary | 0 | user, admin, super_admin |
| GET /report/pdf | 1 | admin, super_admin |

---

**API Reference Version:** 2.0  
**Last Updated:** March 16, 2026  
**Base Version:** OFDS Multi-Fund System
