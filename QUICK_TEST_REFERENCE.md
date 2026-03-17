# 🧪 OFDS API Test Quick Reference

## 📦 Setup (Run Once)

### 1. Generate Test Excel File
```powershell
cd c:\Users\Dantez\Documents\ofds\backend
python create_test_excel.py
```

**Output:** `investors_test_15.xlsx` (15 investors, 2 funds)

### 2. Get Your Auth Token
```bash
$API_URL = "http://localhost:5000/api/v1"
$response = curl -s -X POST "$API_URL/auth/login" `
  -H "Content-Type: application/json" `
  -d '{"email":"admin@ofds.com","password":"password"}' | ConvertFrom-Json

$TOKEN = $response.access_token
Write-Host "Token: $TOKEN"
```

### 3. Create a Batch
```bash
curl -X POST http://localhost:5000/api/v1/batches `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{
    "batch_name": "Q1-2026 Portfolio",
    "certificate_number": "Q1-2026",
    "date_deployed": "2026-03-10",
    "duration_days": 30
  }'
```

**Save the batch ID** from response → `BATCH_ID = 1`

---

## 🚀 Quick Test Commands

### Test #1: List All Funds
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds `
  -H "Authorization: Bearer $TOKEN"
```
**Expect:** Two funds (Axiom, Atium) with empty investors list

---

### Test #2: Upload Excel (All 15 Investors)
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/upload-excel `
  -H "Authorization: Bearer $TOKEN" `
  -F "file=@investors_test_15.xlsx"
```
**Expect:** 
- 15 investors uploaded
- 2 funds created (Axiom, Atium)
- 7 in Axiom, 8 in Atium

---

### Test #3: Get Axiom Fund Details
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds/Axiom `
  -H "Authorization: Bearer $TOKEN"
```
**Expect:** All 7 Axiom investors listed

---

### Test #4: Get Live Weekly Update
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/funds/Axiom/weekly-update `
  -H "Authorization: Bearer $TOKEN"
```
**Expect:** Days active = today - 2026-03-10

---

### Test #5: Record Axiom Performance
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/funds/Axiom/performance `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{
    "gross_profit": "100000.00",
    "transaction_costs": "5000.00",
    "report_date": "2026-03-31",
    "reporting_period": "March 2026"
  }'
```
**Save response:** `AXIOM_PERF_ID = 201` (or whatever ID returned)

---

### Test #6: Record Atium Performance
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/funds/Atium/performance `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{
    "gross_profit": "75000.00",
    "transaction_costs": "2500.00",
    "report_date": "2026-03-31",
    "reporting_period": "March 2026"
  }'
```
**Save response:** `ATIUM_PERF_ID = 202` (or whatever ID returned)

---

### Test #7: Calculate All Distributions
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/calculate-all-funds `
  -H "Authorization: Bearer $TOKEN" `
  -H "Content-Type: application/json" `
  -d '{
    "performance_data": {
      "Axiom": 201,
      "Atium": 202
    }
  }'
```

**Verify in response:**
- ✅ 15 total distributions (7 + 8)
- ✅ Axiom allocated = $95,000 (100k - 5k)
- ✅ Atium allocated = $72,500 (75k - 2.5k)
- ✅ Total batch value = $167,500

---

### Test #8: Get Batch Summary
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/summary `
  -H "Authorization: Bearer $TOKEN"
```

**Verify in response:**
- ✅ 15 total investors
- ✅ Axiom: $350k capital, 7 investors
- ✅ Atium: $250k capital, 8 investors
- ✅ Total capital: $600k
- ✅ Total net profit: $167.5k
- ✅ ROI: 27.92%

---

### Test #9: Download PDF Report
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/report/pdf `
  -H "Authorization: Bearer $TOKEN" `
  --output "batch_1_report.pdf"
```

**Verify in PDF:**
- ✅ Title: "Q1-2026 Batch Report"
- ✅ Axiom section with 7 investors
- ✅ Atium section with 8 investors
- ✅ Distribution details for each investor
- ✅ Summary statistics at bottom

---

## ✅ Validation Checklist

| Item | Expected | Command to Check |
|------|----------|------------------|
| Axiom Investors | 7 | GET /funds/Axiom |
| Atium Investors | 8 | GET /funds/Atium |
| Total Capital | $600,000 | GET /summary |
| Axiom Capital | $350,000 | GET /funds/Axiom |
| Atium Capital | $250,000 | GET /funds/Atium |
| Axiom Profit Share % | 100.0000% (sum) | POST /calculate-all-funds |
| Atium Profit Share % | 100.0000% (sum) | POST /calculate-all-funds |
| Total Allocated | $167,500 | POST /calculate-all-funds |
| Days Active | 6 (today - 03/10) | GET /weekly-update |
| ROI % | 27.92% | GET /summary |

---

## 🔍 Key Things to Check

### Decimal Precision
```
Each Axiom investor:
- Weighted capital = $50,000 × 6 days = $300,000
- Share % = $300,000 / $2,100,000 × 100 = 14.2857%
- Allocated = 14.2857% / 100 × $95,000 = $13,571.43
- Check: $13,571.43 × 7 = $95,000.01 (within rounding) ✓
```

### Fund Independence
- Axiom performance upload doesn't affect Atium until calculation
- Atium can have different performance dates than Axiom
- Each fund's profit allocated independently

### Live Calculation
- Call /weekly-update multiple times in different days
- Days active should increment by 1 each day
- No performance data needed for weekly-update

---

## 🐛 Troubleshooting

### "Fund not found"
- Make sure you uploaded Excel BEFORE trying to get fund details
- Fund names are case-sensitive: "Axiom" not "axiom"

### "No investments found"
- Check that Excel uploaded successfully (Test #2)
- Verify all 15 rows were imported

### "Performance not recorded"
- Make sure performance_id is correct from previous response
- Fund must exist before recording performance

### "Bad calculation results"
- Verify all 15 investors uploaded
- Check that performances recorded for BOTH funds
- Use correct performance IDs in calculate-all-funds

### PDF won't download
- Make sure calculations ran successfully
- Try using `--output filename.pdf` flag
- Check that batch ID is correct

---

## 💾 Save These Environment Variables

```bash
# PowerShell
$API_URL = "http://localhost:5000/api/v1"
$TOKEN = "your_token_here"
$BATCH_ID = "1"
$AXIOM_PERF_ID = "201"
$ATIUM_PERF_ID = "202"
```

---

## 📝 Test Results Template

```
=== TEST RUN: Q1-2026 Portfolio ===

✅ Test 1: List Funds
   - Axiom found: YES
   - Atium found: YES
   
✅ Test 2: Upload Excel
   - 15 investors uploaded: YES
   - 7 Axiom: YES
   - 8 Atium: YES
   
✅ Test 3: Axiom Details
   - All 7 investors shown: YES
   - Total capital: $350,000
   
✅ Test 4: Weekly Update
   - Days active: 6
   - Total capital: $350,000
   
✅ Test 5: Axiom Performance
   - Gross: $100,000
   - Costs: $5,000
   - Net: $95,000
   
✅ Test 6: Atium Performance
   - Gross: $75,000
   - Costs: $2,500
   - Net: $72,500
   
✅ Test 7: Calculate All
   - 15 distributions: YES
   - 7 Axiom allocated: $95,000
   - 8 Atium allocated: $72,500
   - Total: $167,500
   
✅ Test 8: Batch Summary
   - Total investors: 15
   - Total capital: $600,000
   - Total profit: $167,500
   - ROI: 27.92%
   
✅ Test 9: PDF Report
   - Downloaded: YES
   - Axiom section: YES
   - Atium section: YES
   
=== ALL TESTS PASSED ===
```

---

**Ready to test!** Follow the commands in order above. 🚀
