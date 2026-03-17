# OFDS Multi-Fund API - Complete Endpoint Test Guide

**Base URL:** `http://localhost:5000/api/v1`  
**Authentication:** JWT Bearer Token (required for all endpoints)

---

## 📋 Quick Reference

| # | Method | Endpoint | Purpose | Auth |
|-|-|-|-|-|
| 1 | GET | `/batches/{id}/funds` | List all funds in batch | JWT |
| 2 | GET | `/batches/{id}/funds/{name}` | Get fund details + summary | JWT |
| 3 | POST | `/batches/{id}/funds/{name}/performance` | Record fund performance | JWT |
| 4 | POST | `/batches/{id}/upload-excel` | Bulk upload investors | JWT |
| 5 | GET | `/batches/{id}/funds/{name}/weekly-update` | Get live weekly position | JWT |
| 6 | POST | `/batches/{id}/calculate-all-funds` | Calculate all distributions | JWT |
| 7 | GET | `/batches/{id}/summary` | Batch summary overview | JWT |
| 8 | GET | `/batches/{id}/report/pdf` | Generate PDF statement | JWT |

---

## 🔐 Step 0: Get Auth Token (Run First)

```bash
curl -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@ofds.com",
    "password": "your_password"
  }'
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "Bearer"
}
```

**Save token:** Store in env variable or use in all subsequent requests
```bash
TOKEN="your_token_here"
BATCH_ID="1"  # After creating batch
```

---

## ✅ ENDPOINT 1: List All Funds in Batch

**Get all funds (Axiom, Atium) in a specific batch**

### Request
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### Response (200 OK)
```json
{
  "status": "success",
  "data": {
    "batch_id": 1,
    "batch_name": "Q1-2026 Portfolio",
    "funds": [
      {
        "id": 101,
        "batch_id": 1,
        "fund_name": "Axiom",
        "certificate_number": "AX-Q1-2026",
        "total_capital": "350000.00",
        "date_deployed": "2026-03-10",
        "duration_days": 30,
        "date_closed": null,
        "is_active": true
      },
      {
        "id": 102,
        "batch_id": 1,
        "fund_name": "Atium",
        "certificate_number": "AT-Q1-2026",
        "total_capital": "250000.00",
        "date_deployed": "2026-03-10",
        "duration_days": 30,
        "date_closed": null,
        "is_active": true
      }
    ],
    "total_funds": 2,
    "total_capital": "600000.00"
  }
}
```

**What to check:**
- ✅ Both funds present
- ✅ Capital amounts match Excel upload
- ✅ date_deployed = today's date
- ✅ is_active = true

---

## ✅ ENDPOINT 2: Get Fund Details & Summary

**Get specific fund + all investments + performance history**

### Request
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds/Axiom \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### Response (200 OK)
```json
{
  "status": "success",
  "data": {
    "fund": {
      "id": 101,
      "fund_name": "Axiom",
      "certificate_number": "AX-Q1-2026",
      "total_capital": "350000.00",
      "date_deployed": "2026-03-10",
      "duration_days": 30,
      "is_active": true,
      "expected_close_date": "2026-04-09"
    },
    "investments": [
      {
        "id": 501,
        "investor_name": "John Smith",
        "investor_email": "john@example.com",
        "internal_client_code": "AXIOM-001",
        "amount_deposited": "50000.00",
        "date_deposited": "2026-03-10",
        "status": "active"
      },
      {
        "id": 502,
        "investor_name": "Jane Doe",
        "investor_email": "jane@example.com",
        "internal_client_code": "AXIOM-002",
        "amount_deposited": "50000.00",
        "date_deposited": "2026-03-10",
        "status": "active"
      }
    ],
    "total_investors": 7,
    "performance_records": [],
    "summary": {
      "total_capital": "350000.00",
      "investor_count": 7,
      "performance_uploaded": false,
      "last_performance_date": null
    }
  }
}
```

**What to check:**
- ✅ All 7 Axiom investors listed
- ✅ internal_client_code mapped correctly
- ✅ Amounts total to fund capital
- ✅ expected_close_date = deployed + 30 days

---

## ✅ ENDPOINT 3: Record Fund Performance

**Upload monthly performance for a specific fund**

### Request
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/funds/Axiom/performance \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "gross_profit": "100000.00",
    "transaction_costs": "5000.00",
    "report_date": "2026-03-31",
    "reporting_period": "March 2026"
  }'
```

### Response (201 Created)
```json
{
  "status": "success",
  "message": "Performance recorded for fund Axiom",
  "data": {
    "performance_id": 201,
    "fund_name": "Axiom",
    "gross_profit": "100000.00",
    "transaction_costs": "5000.00",
    "net_profit": "95000.00",
    "report_date": "2026-03-31",
    "reporting_period": "March 2026",
    "cumulative_profit": "95000.00"
  }
}
```

**What to check:**
- ✅ Net profit = Gross - Costs
- ✅ cumulative_profit = net_profit (first record)
- ✅ report_date stored correctly
- ✅ performance_id created

**For Second Performance (Next Month):**
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/funds/Axiom/performance \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "gross_profit": "85000.00",
    "transaction_costs": "4000.00",
    "report_date": "2026-04-30",
    "reporting_period": "April 2026"
  }'
```

**Response should show:**
```json
"cumulative_profit": "176000.00"  // 95,000 + 81,000
```

---

## ✅ ENDPOINT 4: Bulk Upload from Excel

**Upload 15 investors from Excel file**

### Request
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/upload-excel \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@investors_test_15.xlsx"
```

### Response (201 Created)
```json
{
  "status": "success",
  "message": "Excel upload completed successfully",
  "data": {
    "batch_id": 1,
    "total_investors_uploaded": 15,
    "funds_created": 2,
    "funds_detail": {
      "Axiom": {
        "fund_id": 101,
        "investors_added": 7,
        "total_capital": "350000.00"
      },
      "Atium": {
        "fund_id": 102,
        "investors_added": 8,
        "total_capital": "400000.00"
      }
    },
    "validation_errors": []
  }
}
```

**What to check:**
- ✅ 15 investors total
- ✅ 7 investors in Axiom
- ✅ 8 investors in Atium
- ✅ No validation errors
- ✅ Totals match Excel

---

## ✅ ENDPOINT 5: Get Live Weekly Update

**Real-time position without waiting for performance upload**

### Request
```bash
curl -X GET "http://localhost:5000/api/v1/batches/1/funds/Axiom/weekly-update" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### Response (200 OK)
```json
{
  "status": "success",
  "data": {
    "batch_id": 1,
    "fund_name": "Axiom",
    "as_of_date": "2026-03-16T10:30:00.000000",
    "total_capital": "350000.00",
    "total_days_active": 42,
    "investors": [
      {
        "investor_name": "John Smith",
        "investor_email": "john@example.com",
        "internal_client_code": "AXIOM-001",
        "amount_deposited": "50000.00",
        "date_deposited": "2026-03-10",
        "days_active": 6,
        "expected_close_date": "2026-04-09"
      },
      {
        "investor_name": "Jane Doe",
        "investor_email": "jane@example.com",
        "internal_client_code": "AXIOM-002",
        "amount_deposited": "50000.00",
        "date_deposited": "2026-03-10",
        "days_active": 6,
        "expected_close_date": "2026-04-09"
      }
    ]
  }
}
```

**What to check:**
- ✅ Days active = today - deploy_date (LIVE calculation)
- ✅ As of date = current datetime
- ✅ All 7 investors listed
- ✅ No performance data required

**Try calling this endpoint again in a week - days_active will increment!**

---

## ✅ ENDPOINT 6: Calculate All Fund Distributions

**Calculate pro-rata profit distributions for ALL funds**

### Request
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/calculate-all-funds \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "performance_data": {
      "Axiom": 201,
      "Atium": 202
    }
  }'
```

**What is `performance_data`?**
- Key = fund_name (e.g., "Axiom")
- Value = performance_id from previous endpoint

### Response (200 OK)
```json
{
  "status": "success",
  "message": "All fund distributions calculated successfully",
  "data": {
    "batch_id": 1,
    "calculation_date": "2026-03-16T10:35:00.000000",
    "funds": {
      "Axiom": {
        "investor_count": 7,
        "total_allocated": 95000.00,
        "distributions": [
          {
            "investment_id": 501,
            "investor_name": "John Smith",
            "investor_email": "john@example.com",
            "internal_client_code": "AXIOM-001",
            "fund_name": "Axiom",
            "amount_deposited": "50000.00",
            "date_deposited": "2026-03-10",
            "days_active": 6,
            "weighted_capital": "300000.00",
            "profit_share_percentage": "14.2857",
            "profit_allocated": "13571.43"
          }
        ]
      },
      "Atium": {
        "investor_count": 8,
        "total_allocated": 72500.00,
        "distributions": [...]
      }
    },
    "total_batch_value": 167500.00,
    "distribution_count": 15
  }
}
```

**What to check:**
- ✅ 15 total distributions (7 + 8)
- ✅ Profit share % for each fund sums to 100%
- ✅ Allocated profits match fund net profits
- ✅ weighted_capital = amount × days_active
- ✅ profit_share_percentage = (weighted / total) × 100
- ✅ profit_allocated = (share / 100) × net_profit

**Sample Calculation Verification:**
```
Axiom: 7 investors, each $50k, each same deposit date
- Each weighted_capital = $50k × 6 days = $300k
- Total weighted = $2.1M
- Each profit share = $300k / $2.1M × 100 = 14.2857%
- Each allocated = 14.2857% × $95k = $13,571.43
- Total allocated = $13,571.43 × 7 = $95,000 ✓
```

---

## ✅ ENDPOINT 7: Get Batch Summary

**Overview of entire batch with all funds**

### Request
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/summary \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json"
```

### Response (200 OK)
```json
{
  "status": "success",
  "data": {
    "batch_id": 1,
    "batch_name": "Q1-2026 Portfolio",
    "date_deployed": "2026-03-10",
    "duration_days": 30,
    "expected_close_date": "2026-04-09",
    "batch_status": "active",
    "total_capital": "600000.00",
    "total_investors": 15,
    "funds": [
      {
        "fund_name": "Axiom",
        "total_capital": "350000.00",
        "investor_count": 7,
        "performance_status": "recorded",
        "latest_gross_profit": "100000.00",
        "latest_net_profit": "95000.00",
        "cumulative_profit": "95000.00"
      },
      {
        "fund_name": "Atium",
        "total_capital": "250000.00",
        "investor_count": 8,
        "performance_status": "recorded",
        "latest_gross_profit": "75000.00",
        "latest_net_profit": "72500.00",
        "cumulative_profit": "72500.00"
      }
    ],
    "batch_totals": {
      "total_gross": "175000.00",
      "total_costs": "9500.00",
      "total_net": "167500.00",
      "roi_percentage": "27.92"
    },
    "calculations": {
      "last_calculated": "2026-03-16T10:35:00.000000",
      "distribution_count": 15,
      "distributions_by_fund": {
        "Axiom": 7,
        "Atium": 8
      }
    }
  }
}
```

**What to check:**
- ✅ Both funds shown
- ✅ 15 total investors
- ✅ Batch totals = sum of fund totals
- ✅ ROI = (Total Net / Total Capital) × 100
- ✅ Expected close date correct

---

## ✅ ENDPOINT 8: Generate PDF Report

**Download investor statement PDF grouped by fund**

### Request
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/report/pdf \
  -H "Authorization: Bearer $TOKEN" \
  --output batch_1_report.pdf
```

**Or with download option:**
```bash
curl -X GET "http://localhost:5000/api/v1/batches/1/report/pdf?download=true" \
  -H "Authorization: Bearer $TOKEN" \
  --output "Q1-2026_Portfolio_Statement.pdf"
```

### Response (200 OK with PDF file)
```
Binary PDF Content
```

**What to check (open PDF):**
- ✅ Title: "Q1-2026 Batch Report"
- ✅ Header with batch info
- ✅ Section 1: Axiom Fund
  - Investment table with 7 rows
  - Distribution table with 7 rows (includes profit allocated)
- ✅ Section 2: Atium Fund
  - Investment table with 8 rows
  - Distribution table with 8 rows
- ✅ Summary statistics: total capital, total profit, ROI
- ✅ All amounts shown with 2 decimal places
- ✅ Percentages shown with 4 decimal places

---

## 🧪 Complete Test Workflow (In Order)

### 1. Authenticate
```bash
TOKEN=$(curl -s -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ofds.com","password":"password"}' | jq -r '.access_token')
echo "Token: $TOKEN"
```

### 2. Create Batch (Existing endpoint, not listed above)
```bash
BATCH_ID=$(curl -s -X POST http://localhost:5000/api/v1/batches \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_name": "Q1-2026 Portfolio",
    "certificate_number": "Q1-2026",
    "date_deployed": "2026-03-10",
    "duration_days": 30
  }' | jq -r '.data.id')
echo "Batch ID: $BATCH_ID"
```

### 3. Upload Excel (ENDPOINT 4)
```bash
curl -X POST http://localhost:5000/api/v1/batches/$BATCH_ID/upload-excel \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@investors_test_15.xlsx"
```

### 4. List Funds (ENDPOINT 1)
```bash
curl -X GET http://localhost:5000/api/v1/batches/$BATCH_ID/funds \
  -H "Authorization: Bearer $TOKEN"
```

### 5. Get Fund Details (ENDPOINT 2)
```bash
curl -X GET http://localhost:5000/api/v1/batches/$BATCH_ID/funds/Axiom \
  -H "Authorization: Bearer $TOKEN"
```

### 6. Get Weekly Update (ENDPOINT 5)
```bash
curl -X GET http://localhost:5000/api/v1/batches/$BATCH_ID/funds/Axiom/weekly-update \
  -H "Authorization: Bearer $TOKEN"
```

### 7. Record Performance Axiom (ENDPOINT 3)
```bash
AXIOM_PERF=$(curl -s -X POST http://localhost:5000/api/v1/batches/$BATCH_ID/funds/Axiom/performance \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "gross_profit": "100000.00",
    "transaction_costs": "5000.00",
    "report_date": "2026-03-31",
    "reporting_period": "March 2026"
  }' | jq -r '.data.performance_id')
echo "Axiom Performance ID: $AXIOM_PERF"
```

### 8. Record Performance Atium (ENDPOINT 3)
```bash
ATIUM_PERF=$(curl -s -X POST http://localhost:5000/api/v1/batches/$BATCH_ID/funds/Atium/performance \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "gross_profit": "75000.00",
    "transaction_costs": "2500.00",
    "report_date": "2026-03-31",
    "reporting_period": "March 2026"
  }' | jq -r '.data.performance_id')
echo "Atium Performance ID: $ATIUM_PERF"
```

### 9. Calculate All Distributions (ENDPOINT 6)
```bash
curl -X POST http://localhost:5000/api/v1/batches/$BATCH_ID/calculate-all-funds \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"performance_data\": {
      \"Axiom\": $AXIOM_PERF,
      \"Atium\": $ATIUM_PERF
    }
  }"
```

### 10. Get Batch Summary (ENDPOINT 7)
```bash
curl -X GET http://localhost:5000/api/v1/batches/$BATCH_ID/summary \
  -H "Authorization: Bearer $TOKEN"
```

### 11. Generate PDF (ENDPOINT 8)
```bash
curl -X GET http://localhost:5000/api/v1/batches/$BATCH_ID/report/pdf \
  -H "Authorization: Bearer $TOKEN" \
  --output batch_summary.pdf
```

---

## 🔍 Error Scenarios to Test

### Missing Batch
```bash
curl -X GET http://localhost:5000/api/v1/batches/999/funds \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response (404):**
```json
{
  "status": "error",
  "message": "Batch 999 not found",
  "error_code": "BATCH_NOT_FOUND"
}
```

### Missing Fund
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds/NonExistent \
  -H "Authorization: Bearer $TOKEN"
```

**Expected Response (404):**
```json
{
  "status": "error",
  "message": "Fund NonExistent not found in batch 1",
  "error_code": "FUND_NOT_FOUND"
}
```

### Missing Auth Token
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds
```

**Expected Response (401):**
```json
{
  "status": "error",
  "message": "Missing authorization token",
  "error_code": "UNAUTHORIZED"
}
```

### Invalid Excel Format
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/upload-excel \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@invalid.txt"
```

**Expected Response (400):**
```json
{
  "status": "error",
  "message": "Invalid file format. Only .xlsx files allowed",
  "error_code": "INVALID_FILE"
}
```

---

## 📊 Key Validation Points

| Aspect | What to Verify |
|--------|-----------------|
| **Fund Creation** | Both Axiom & Atium created automatically, IDs assigned |
| **Investor Count** | Axiom: 7, Atium: 8 (based on position in Excel) |
| **Capital Totals** | Axiom: $350k, Atium: $250k (match Excel) |
| **Days Active** | Current date - deploy date (live calculation) |
| **Weighted Capital** | Amount × Days (decimals preserved) |
| **Profit Share %** | Sum to exactly 100.0000% per fund |
| **Allocated Profit** | Total allocated = Net profit (within rounding) |
| **Cumulative Profit** | Increases with subsequent uploads |
| **PDF Generation** | Grouped by fund, all amounts 2 decimals, % 4 decimals |
| **Decimal Precision** | No floating-point errors in calculations |

---

## 💾 Making Requests Easier

**Save this as `test_endpoints.sh`:**
```bash
#!/bin/bash

# Configuration
API_URL="http://localhost:5000/api/v1"
EMAIL="admin@ofds.com"
PASSWORD="password"

# Get token
echo "Getting auth token..."
TOKEN=$(curl -s -X POST $API_URL/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | jq -r '.access_token')

echo "Token: $TOKEN"
echo ""

# Function to make API calls
api_call() {
  local method=$1
  local endpoint=$2
  local data=$3
  
  if [ -z "$data" ]; then
    curl -s -X $method "$API_URL$endpoint" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json"
  else
    curl -s -X $method "$API_URL$endpoint" \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d "$data"
  fi
}

# Test endpoints
echo "Testing Endpoint 1: List Funds"
api_call GET "/batches/1/funds" | jq .

echo ""
echo "Testing Endpoint 2: Fund Details"
api_call GET "/batches/1/funds/Axiom" | jq .

echo ""
echo "Testing Endpoint 5: Weekly Update"
api_call GET "/batches/1/funds/Axiom/weekly-update" | jq .
```

**Run with:**
```bash
chmod +x test_endpoints.sh
./test_endpoints.sh
```

---

**Ready to test? Use `investors_test_15.xlsx` file included!**
