# 🧪 Complete Testing Workflow (Step-by-Step) - REFACTORED

**Current Date:** March 16, 2026  
**Test Data:** 15 investors (Axiom: 7, Atium: 8) within **ONE BATCH**  
**Total Capital:** $750,000.00  
**Architecture:** Same Batch ID, different Fund Names (axiom/atium)

---

## 🔑 KEY CHANGE: Single Batch, Multiple Funds

**OLD MODEL (Incorrect):**
- Axiom → Batch 1 (separate batch)
- Atium → Batch 2 (separate batch)

**NEW MODEL (Correct):**
- Axiom → Batch 1, Fund "axiom"
- Atium → Batch 1, Fund "atium"
- Both funds share the same batch_id but have different fund_name fields
- Pro-rata calculations are done **per fund**, not per batch

---

## Phase 1: Authentication Setup 🔐

### Step 1.1: Register Admin User
**Endpoint:** `POST /api/v1/users`  
**JWT Required:** ❌ NO (public endpoint)  
**Purpose:** Create admin account

**Request Body:**
```json
{
  "first_name": "John",
  "last_name": "Admin",
  "email": "admin@ofds.com",
  "password": "AdminPassword123!",
  "user_role": "admin"
}
```

**Expected Response (201 Created):**
```json
{
  "status": 201,
  "message": "User created successfully",
  "data": {
    "id": 1,
    "first_name": "John",
    "last_name": "Admin",
    "email": "admin@ofds.com",
    "user_role": "admin",
    "active": true,
    "date_created": "2026-03-16T10:00:00"
  }
}
```

✅ **What to verify:**
- Status is 201
- User ID returned (e.g., 1)
- Email matches
- user_role is "admin"
- active is true

---

### Step 1.2: Login Admin User
**Endpoint:** `POST /api/v1/login`  
**JWT Required:** ❌ NO (public endpoint)  
**Purpose:** Get access token for authenticated requests

**Request Body:**
```json
{
  "email": "admin@ofds.com",
  "password": "AdminPassword123!"
}
```

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Login successful",
  "value": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTcxMDU4NDgwMCwianRpIjoiYWJjZGVmMTIzNDU2IiwidHlwZSI6ImFjY2VzcyIsInN1YiI6eyJlbWFpbCI6ImFkbWluQG9mZHMuY29tIn0sIm5iZiI6MTcxMDU4NDgwMCwiZXhwIjoxNzEwNjcxMjAwfQ.xxxxx",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user_role": "admin"
  }
}
```

✅ **What to verify:**
- Status is 200
- access_token is provided (long string)
- refresh_token is provided
- user_role is "admin"
- **SAVE THE access_token** - you'll use it for all future requests!

**Token Usage:**
```
Add to ALL future requests as header:
Authorization: Bearer {access_token}
```

---

## Phase 2: Create Single Batch & Add Investors (Fund-Partitioned) 📊

### Step 2.1: Create One Batch Container for Both Funds
**Endpoint:** `POST /api/v1/batches`  
**JWT Required:** ✅ YES  
**Purpose:** Create a single batch that will hold both Axiom and Atium investors

**Headers:**
```
Authorization: Bearer {access_token from 1.2}
Content-Type: application/json
```

**Request Body:**
```json
{
  "batch_name": "Q1-2026 Portfolio",
  "certificate_number": "Q1-2026-MASTER",
  "date_deployed": "2026-03-10T00:00:00",
  "duration_days": 30,
  "total_principal": 750000.00
}
```

**Expected Response (201 Created):**
```json
{
  "status": 201,
  "message": "Batch created successfully",
  "data": {
    "batch_id": 1,
    "batch_name": "Q1-2026 Portfolio",
    "certificate_number": "Q1-2026-MASTER",
    "date_deployed": "2026-03-10",
    "duration_days": 30,
    "total_principal": 750000.00,
    "expected_close_date": "2026-04-09",
    "date_closed": null,
    "is_active": true,
    "activation_status": "ACTIVE",
    "date_created": "2026-03-16T10:05:00"
  }
}
```

✅ **What to verify:**
- Status is 201
- batch_id = 1 (SAVE THIS - needed for all investor additions)
- batch_name matches
- total_principal = 750000.00 (sum of both funds)
- expected_close_date = 2026-04-09 (30 days from 03-10)
- is_active = true

---

### Step 2.2: Add Axiom Fund Investors (7 investors, batch_id=1, fund_name="axiom")
**Endpoint:** `POST /api/v1/batches/1/investments`  
**JWT Required:** ✅ YES  
**Purpose:** Add Axiom fund investors to the batch

**Headers:**
```
Authorization: Bearer {access_token from 1.2}
Content-Type: application/json
```

**Request 1: John Smith (AXIOM-001, fund_name="axiom")**
```json
{
  "investor_name": "John Smith",
  "investor_email": "john.smith@example.com",
  "investor_phone": "+1-555-0101",
  "internal_client_code": "AXIOM-001",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```

**Expected Response (201 Created):**
```json
{
  "status": 201,
  "message": "Investment added successfully",
  "data": {
    "investment_id": 1,
    "investor_name": "John Smith",
    "investor_email": "john.smith@example.com",
    "investor_phone": "+1-555-0101",
    "internal_client_code": "AXIOM-001",
    "amount_deposited": 50000.00,
    "date_deposited": "2026-03-10",
    "fund_name": "axiom",
    "batch_id": 1
  }
}
```

✅ **What to verify:**
- Status is 201
- investment_id = 1
- amount_deposited = 50000.00
- batch_id = 1
- fund_name = "axiom" (lowercase)
- internal_client_code saved correctly

**Request 2: Jane Doe (AXIOM-002)**
```json
{
  "investor_name": "Jane Doe",
  "investor_email": "jane.doe@example.com",
  "investor_phone": "+1-555-0102",
  "internal_client_code": "AXIOM-002",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```
Expected investment_id: 2

**Request 3: Michael Johnson (AXIOM-003)**
```json
{
  "investor_name": "Michael Johnson",
  "investor_email": "michael.j@example.com",
  "investor_phone": "+1-555-0103",
  "internal_client_code": "AXIOM-003",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```
Expected investment_id: 3

**Request 4: Sarah Williams (AXIOM-004)**
```json
{
  "investor_name": "Sarah Williams",
  "investor_email": "sarah.w@example.com",
  "investor_phone": "+1-555-0104",
  "internal_client_code": "AXIOM-004",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```
Expected investment_id: 4

**Request 5: David Brown (AXIOM-005)**
```json
{
  "investor_name": "David Brown",
  "investor_email": "david.b@example.com",
  "investor_phone": "+1-555-0105",
  "internal_client_code": "AXIOM-005",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```
Expected investment_id: 5

**Request 6: Emma Davis (AXIOM-006)**
```json
{
  "investor_name": "Emma Davis",
  "investor_email": "emma.d@example.com",
  "investor_phone": "+1-555-0106",
  "internal_client_code": "AXIOM-006",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```
Expected investment_id: 6

**Request 7: Robert Wilson (AXIOM-007)**
```json
{
  "investor_name": "Robert Wilson",
  "investor_email": "robert.w@example.com",
  "investor_phone": "+1-555-0107",
  "internal_client_code": "AXIOM-007",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "axiom"
}
```
Expected investment_id: 7

✅ **What to verify after all 7 Axiom investors:**
- All responses are 201
- investment_ids are sequential (1-7)
- All amounts = 50000.00
- All batch_id = 1
- All fund_name = "axiom"
- All dates = 2026-03-10
- All internal_client_codes are unique

---

### Step 2.3: Add Atium Fund Investors (8 investors, batch_id=1, fund_name="atium")
**Endpoint:** `POST /api/v1/batches/1/investments`  
**JWT Required:** ✅ YES  
**Purpose:** Add Atium fund investors to the same batch

**Headers:**
```
Authorization: Bearer {access_token from 1.2}
Content-Type: application/json
```

**Request 1: Lisa Anderson (ATIUM-001, fund_name="atium")**
```json
{
  "investor_name": "Lisa Anderson",
  "investor_email": "lisa.a@example.com",
  "investor_phone": "+1-555-0201",
  "internal_client_code": "ATIUM-001",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 8

**Request 2: James Taylor (ATIUM-002)**
```json
{
  "investor_name": "James Taylor",
  "investor_email": "james.t@example.com",
  "investor_phone": "+1-555-0202",
  "internal_client_code": "ATIUM-002",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 9

**Request 3: Mary Martinez (ATIUM-003)**
```json
{
  "investor_name": "Mary Martinez",
  "investor_email": "mary.m@example.com",
  "investor_phone": "+1-555-0203",
  "internal_client_code": "ATIUM-003",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 10

**Request 4: William Garcia (ATIUM-004)**
```json
{
  "investor_name": "William Garcia",
  "investor_email": "william.g@example.com",
  "investor_phone": "+1-555-0204",
  "internal_client_code": "ATIUM-004",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 11

**Request 5: Patricia Robinson (ATIUM-005)**
```json
{
  "investor_name": "Patricia Robinson",
  "investor_email": "patricia.r@example.com",
  "investor_phone": "+1-555-0205",
  "internal_client_code": "ATIUM-005",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 12

**Request 6: Christopher Lee (ATIUM-006)**
```json
{
  "investor_name": "Christopher Lee",
  "investor_email": "christopher.l@example.com",
  "investor_phone": "+1-555-0206",
  "internal_client_code": "ATIUM-006",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 13

**Request 7: Jennifer White (ATIUM-007)**
```json
{
  "investor_name": "Jennifer White",
  "investor_email": "jennifer.w@example.com",
  "investor_phone": "+1-555-0207",
  "internal_client_code": "ATIUM-007",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 14

**Request 8: Andrew Harris (ATIUM-008)**
```json
{
  "investor_name": "Andrew Harris",
  "investor_email": "andrew.h@example.com",
  "investor_phone": "+1-555-0208",
  "internal_client_code": "ATIUM-008",
  "amount_deposited": 50000.00,
  "date_deposited": "2026-03-10T00:00:00",
  "fund_name": "atium"
}
```
Expected investment_id: 15

✅ **What to verify after all 8 Atium investors:**
- All responses are 201
- investment_ids are sequential (8-15)
- All amounts = 50000.00
- All batch_id = 1 (SAME as Axiom investors!)
- All fund_name = "atium"
- All dates = 2026-03-10
- All internal_client_codes are unique

---

## Phase 3: Verify Investors by Fund 📋

### Step 3.1: Get All Axiom Investors (same batch_id, fund_name="axiom")
**Endpoint:** `GET /api/v1/batches/1/investments?fund_name=axiom` (optional filter)  
**JWT Required:** ✅ YES  
**Purpose:** Verify all 7 Axiom investors exist in the batch

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Expected Response (200 OK):** 
All 15 investors from the batch are returned. Filter locally by fund_name="axiom" to get these 7:
```json
{
  "status": 200,
  "message": "Investments retrieved successfully",
  "batch_id": 1,
  "count": 15,
  "total_principal": 750000.00,
  "data": [
    {
      "investment_id": 1,
      "investor_name": "John Smith",
      "investor_email": "john.smith@example.com",
      "investor_phone": "+1-555-0101",
      "internal_client_code": "AXIOM-001",
      "amount_deposited": 50000.00,
      "date_deposited": "2026-03-10",
      "fund_name": "axiom"
    },
    {
      "investment_id": 2,
      "investor_name": "Jane Doe",
      "investor_email": "jane.doe@example.com",
      "investor_phone": "+1-555-0102",
      "internal_client_code": "AXIOM-002",
      "amount_deposited": 50000.00,
      "date_deposited": "2026-03-10",
      "fund_name": "axiom"
    },
    // ... 5 more axiom investors ...
    // ... then 8 atium investors
  ]
}
```

✅ **What to verify:**
- Status is 200
- total_principal = 750000.00 (all investments)
- Array contains exactly 15 investors (7 axiom + 8 atium)
- Axiom investors have fund_name = "axiom"
- Axiom total capital = 7 × $50,000 = $350,000
- Internal client codes are unique

---

## Phase 4: Add Performance Data (Per Fund) 💰

### Step 4.1: Record Axiom Fund Performance
**Endpoint:** `POST /api/v1/batches/1/performance`  
**JWT Required:** ✅ YES  
**Purpose:** Record profit/loss for Axiom fund (fund_name="axiom")

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "gross_profit": 100000.00,
  "transaction_costs": 5000.00,
  "date_closed": "2026-03-31T00:00:00",
  "fund_name": "axiom"
}
```

**Expected Response (201 Created):**
```json
{
  "status": 201,
  "message": "Performance data created successfully",
  "data": {
    "performance_id": 1,
    "batch_id": 1,
    "fund_name": "axiom",
    "gross_profit": 100000.00,
    "transaction_costs": 5000.00,
    "net_profit": 95000.00,
    "cumulative_profit": 95000.00,
    "date_closed": "2026-03-31",
    "date_created": "2026-03-16T10:25:00"
  }
}
```

✅ **What to verify:**
- Status is 201
- performance_id = 1
- batch_id = 1
- fund_name = "axiom"
- gross_profit = 100000.00
- transaction_costs = 5000.00
- net_profit = 95000.00 (gross - costs)
- cumulative_profit = 95000.00 (first record)

---

### Step 4.2: Record Atium Fund Performance
**Endpoint:** `POST /api/v1/batches/1/performance`  
**JWT Required:** ✅ YES  
**Purpose:** Record profit/loss for Atium fund (fund_name="atium")

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "gross_profit": 75000.00,
  "transaction_costs": 2500.00,
  "date_closed": "2026-03-31T00:00:00",
  "fund_name": "atium"
}
```

**Expected Response (201 Created):**
```json
{
  "status": 201,
  "message": "Performance data created successfully",
  "data": {
    "performance_id": 2,
    "batch_id": 1,
    "fund_name": "atium",
    "gross_profit": 75000.00,
    "transaction_costs": 2500.00,
    "net_profit": 72500.00,
    "cumulative_profit": 72500.00,
    "date_closed": "2026-03-31",
    "date_created": "2026-03-16T10:30:00"
  }
}
```

✅ **What to verify:**
- Status is 201
- performance_id = 2
- batch_id = 1
- fund_name = "atium"
- gross_profit = 75000.00
- transaction_costs = 2500.00
- net_profit = 72500.00
- cumulative_profit = 72500.00

### Step 4.3: Get All Performance Data for Batch
**Endpoint:** `GET /api/v1/batches/1/performance`  
**JWT Required:** ✅ YES  
**Purpose:** Retrieve all performance records (both Axiom and Atium funds)

**Headers:**
```
Authorization: Bearer {access_token}
```

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Performance data retrieved successfully",
  "batch_id": 1,
  "batch_name": "Q1-2026 Portfolio",
  "count": 2,
  "data": [
    {
      "performance_id": 1,
      "batch_id": 1,
      "fund_name": "axiom",
      "gross_profit": 100000.00,
      "transaction_costs": 5000.00,
      "net_profit": 95000.00,
      "date_created": "2026-03-16T10:25:00"
    },
    {
      "performance_id": 2,
      "batch_id": 1,
      "fund_name": "atium",
      "gross_profit": 75000.00,
      "transaction_costs": 2500.00,
      "net_profit": 72500.00,
      "date_created": "2026-03-16T10:30:00"
    }
  ],
  "summary": {
    "total_gross_profit": 175000.00,
    "total_transaction_costs": 7500.00,
    "total_net_profit": 167500.00,
    "funds_count": 2
  }
}
```

✅ **What to verify:**
- Status is 200
- count = 2 (both axiom and atium)
- data array contains 2 performance records
- First: fund_name='axiom' with net_profit=$95,000
- Second: fund_name='atium' with net_profit=$72,500
- summary shows totals across both funds
- total_net_profit = $167,500 (95k + 72.5k)

---

### 🔑 CRITICAL: Pro-Rata Calculations are Per Fund, NOT Per Batch

When you calculate pro-rata for a batch with multiple funds:
- System queries ONLY investors with matching fund_name
- Axiom distribution: Uses only Axiom investors (7 total), ignores Atium
- Atium distribution: Uses only Atium investors (8 total), ignores Axiom
- Weighted capital totals are independent per fund

### Step 5.1: Calculate Axiom Fund Distributions
**Endpoint:** `POST /api/v1/batches/1/calculate-pro-rata?fund_name=axiom`  
**JWT Required:** ✅ YES  
**Purpose:** Calculate profit share for Axiom investors only

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Request Body:**
```json
{
  "fund_name": "axiom"
}
```

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Pro-rata distributions calculated successfully (fund: axiom)",
  "data": [
    {
      "distribution_id": 1,
      "investment_id": 1,
      "investor_name": "John Smith",
      "investor_email": "john.smith@example.com",
      "internal_client_code": "AXIOM-001",
      "amount_deposited": 50000.00,
      "date_deposited": "2026-03-10",
      "days_active": 6,
      "weighted_capital": 300000.00,
      "profit_share_percentage": 14.2857,
      "profit_allocated": 13571.43,
      "calculation_date": "2026-03-16"
    },
    // ... 6 more Axiom distributions
  ]
}
```

**Calculation Details for Axiom (7 investors only):**
```
Days Active (2026-03-10 to 2026-03-16): 6 days
Weighted Capital per investor: $50,000 × 6 = $300,000
Total Weighted Capital: 7 investors × $300,000 = $2,100,000 ← PER FUND

Per Investor Calculation:
Profit Share %:   ($300,000 / $2,100,000) × 100 = 14.2857%
Profit Allocated: (14.2857% / 100) × $95,000 = $13,571.43

Total Allocated: 7 × $13,571.43 = $95,000.01 ✓ (Axiom net profit)
```

✅ **What to verify:**
- Status is 200
- 7 distributions created (one per Axiom investor)
- days_active = 6
- weighted_capital = 300000.00 for each investor
- profit_share_percentage ≈ 14.2857 for each investor
- profit_allocated ≈ 13571.43 for each investor
- Sum of profit_allocated ≈ 95000.00 (Axiom net profit)
- NO Atium investors in the results

---

### Step 5.2: Calculate Atium Fund Distributions
**Endpoint:** `POST /api/v1/batches/1/calculate-pro-rata?fund_name=atium`  
**JWT Required:** ✅ YES

**Request Body:**
```json
{
  "fund_name": "atium"
}
```

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Pro-rata distributions calculated successfully (fund: atium)",
  "data": [
    {
      "distribution_id": 8,
      "investment_id": 8,
      "investor_name": "Lisa Anderson",
      "investor_email": "lisa.a@example.com",
      "internal_client_code": "ATIUM-001",
      "amount_deposited": 50000.00,
      "date_deposited": "2026-03-10",
      "days_active": 6,
      "weighted_capital": 300000.00,
      "profit_share_percentage": 12.5000,
      "profit_allocated": 9062.50,
      "calculation_date": "2026-03-16"
    },
    // ... 7 more Atium distributions
  ]
}
```

**Calculation Details for Atium (8 investors only):**
```
Days Active (2026-03-10 to 2026-03-16): 6 days
Weighted Capital per investor: $50,000 × 6 = $300,000
Total Weighted Capital: 8 investors × $300,000 = $2,400,000 ← PER FUND (different from Axiom!)

Per Investor Calculation:
Profit Share %:   ($300,000 / $2,400,000) × 100 = 12.5000%
Profit Allocated: (12.5000% / 100) × $72,500 = $9,062.50

Total Allocated: 8 × $9,062.50 = $72,500.00 ✓ (Atium net profit)
```

✅ **What to verify:**
- Status is 200
- 8 distributions created (one per Atium investor)
- days_active = 6
- weighted_capital = 300000.00 for each investor
- profit_share_percentage ≈ 12.5000 for each investor (DIFFERENT from Axiom!)
- profit_allocated ≈ 9062.50 for each investor
- Sum of profit_allocated ≈ 72500.00 (Atium net profit)
- NO Axiom investors in the results

**Key Difference (Per Fund Calculation):**
| Fund | Investors | Weighted Total | Share % | Profit Allocated |
|------|-----------|----------------|---------|------------------|
| Axiom | 7 | $2,100,000 | 14.29% per investor | $13,571.43 each |
| Atium | 8 | $2,400,000 | 12.50% per investor | $9,062.50 each |

---

## Phase 6: Retrieve Distributions by Fund 📊

### Step 6.1: Get All Axiom Fund Distributions
**Endpoint:** `GET /api/v1/batches/1/funds/axiom/distributions`  
**JWT Required:** ✅ YES  
**Purpose:** All profit allocations for Axiom investors in this batch

**Headers:**
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Fund distributions retrieved successfully",
  "data": {
    "fund_name": "axiom",
    "batch_id": 1,
    "performance_id": 1,
    "distributions": [
      {
        "distribution_id": 1,
        "investment_id": 1,
        "investor_name": "John Smith",
        "investor_email": "john.smith@example.com",
        "internal_client_code": "AXIOM-001",
        "amount_deposited": 50000.00,
        "date_deposited": "2026-03-10",
        "days_active": 6,
        "weighted_capital": 300000.00,
        "profit_share_percentage": 14.2857,
        "profit_allocated": 13571.43,
        "calculation_date": "2026-03-16"
      },
      {
        "distribution_id": 2,
        "investment_id": 2,
        "investor_name": "Jane Doe",
        "investor_email": "jane.doe@example.com",
        "internal_client_code": "AXIOM-002",
        "amount_deposited": 50000.00,
        "date_deposited": "2026-03-10",
        "days_active": 6,
        "weighted_capital": 300000.00,
        "profit_share_percentage": 14.2857,
        "profit_allocated": 13571.43,
        "calculation_date": "2026-03-16"
      },
      // ... 5 more Axiom distributions
    ],
    "summary": {
      "fund": "axiom",
      "total_investors": 7,
      "total_principal_invested": 350000.00,
      "total_weighted_capital": 2100000.00,
      "total_profit_allocated": 95000.01,
      "roi_percentage": 27.14
    }
  }
}
```

✅ **What to verify:**
- Status is 200
- 7 distributions (only Axiom fund)
- Each investor has profit_share_percentage ≈ 14.2857%
- Each investor gets profit_allocated ≈ $13,571.43
- Total allocated ≈ $95,000 (Axiom net profit)
- NO Atium investors in results
- total_weighted_capital = 2,100,000 (per-fund calculation)

---

### Step 6.2: Get All Atium Fund Distributions
**Endpoint:** `GET /api/v1/batches/1/funds/atium/distributions`  
**JWT Required:** ✅ YES  
**Purpose:** All profit allocations for Atium investors in this batch

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Fund distributions retrieved successfully",
  "data": {
    "fund_name": "atium",
    "batch_id": 1,
    "performance_id": 2,
    "distributions": [
      {
        "distribution_id": 8,
        "investment_id": 8,
        "investor_name": "Lisa Anderson",
        "investor_email": "lisa.a@example.com",
        "internal_client_code": "ATIUM-001",
        "amount_deposited": 50000.00,
        "date_deposited": "2026-03-10",
        "days_active": 6,
        "weighted_capital": 300000.00,
        "profit_share_percentage": 12.5000,
        "profit_allocated": 9062.50,
        "calculation_date": "2026-03-16"
      },
      {
        "distribution_id": 9,
        "investment_id": 9,
        "investor_name": "James Taylor",
        "investor_email": "james.t@example.com",
        "internal_client_code": "ATIUM-002",
        "amount_deposited": 50000.00,
        "date_deposited": "2026-03-10",
        "days_active": 6,
        "weighted_capital": 300000.00,
        "profit_share_percentage": 12.5000,
        "profit_allocated": 9062.50,
        "calculation_date": "2026-03-16"
      },
      // ... 6 more Atium distributions
    ],
    "summary": {
      "fund": "atium",
      "total_investors": 8,
      "total_principal_invested": 400000.00,
      "total_weighted_capital": 2400000.00,
      "total_profit_allocated": 72500.00,
      "roi_percentage": 18.13
    }
  }
}
```

✅ **What to verify:**
- Status is 200
- 8 distributions (only Atium fund)
- Each investor has profit_share_percentage = 12.5000%
- Each investor gets profit_allocated = $9,062.50
- Total allocated = $72,500 (Atium net profit)
- NO Axiom investors in results
- total_weighted_capital = 2,400,000 (per-fund calculation, different from Axiom!)

---

### Step 6.3: Get Batch Summary (All Funds)
**Endpoint:** `GET /api/v1/batches/1/summary`  
**JWT Required:** ✅ YES  
**Purpose:** Complete batch overview combining all fund data

**Expected Response (200 OK):**
```json
{
  "status": 200,
  "message": "Batch summary retrieved successfully",
  "data": {
    "batch": {
      "batch_id": 1,
      "batch_name": "Multi-Fund Batch Q1-2026",
      "certificate_number": "MF-Q1-2026",
      "date_deployed": "2026-03-10",
      "duration_days": 30,
      "expected_close_date": "2026-04-09",
      "total_principal": 750000.00,
      "is_active": true
    },
    "funds": [
      {
        "fund_name": "axiom",
        "total_investors": 7,
        "total_capital": 350000.00,
        "total_profit": 95000.00,
        "roi_percentage": 27.14
      },
      {
        "fund_name": "atium",
        "total_investors": 8,
        "total_capital": 400000.00,
        "total_profit": 72500.00,
        "roi_percentage": 18.13
      }
    ],
    "performance": {
      "total_gross_profit": 175000.00,
      "total_costs": 7500.00,
      "total_net_profit": 167500.00,
      "date_closed": "2026-03-31"
    },
    "distributions": {
      "axiom": 7,
      "atium": 8,
      "total": 15
    },
    "summary": {
      "total_investors": 15,
      "total_principal": 750000.00,
      "total_net_profit": 167500.00,
      "total_allocated": 167500.01,
      "combined_roi_percentage": 22.33,
      "status": "ACTIVE",
      "last_calculated": "2026-03-16T10:40:00"
    }
  }
}
```

✅ **What to verify:**
- Status is 200
- batch_id = 1 (single batch)
- 2 funds listed (axiom, atium)
- 15 total investors (7 + 8)
- total_principal = $750,000 (all investments)
- Axiom ROI = 27.14% (higher - fewer investors)
- Atium ROI = 18.13% (lower - more investors)
- total_net_profit = $167,500 (95k + 72.5k)
- total_allocated = $167,500.01 (all distributed)
- combined_roi_percentage = 22.33% (average across batch)

---

## Final Verification Checklist ✅

### Database State Check (Fund-Partitioned Single Batch)
```
Batches:          1 total (ID: 1)
├── Axiom Fund:   7 investors, $350k capital, $95k profit
└── Atium Fund:   8 investors, $400k capital, $72.5k profit

Investments:      15 total
├── Axiom (IDs 1-7):   fund_name='axiom'
└── Atium (IDs 8-15):  fund_name='atium'

Performance:      2 total
├── Axiom Performance:  $95k net profit
└── Atium Performance:  $72.5k net profit

Distributions:    15 total
├── Axiom:  7 @ 14.2857% = $95k
└── Atium:  8 @ 12.5000% = $72.5k
```

### Per-Fund Calculation Verification
```
AXIOM FUND (batch_id=1, fund_name="axiom"):
├── Investors: 7
├── Weighted Total: $2,100,000 (7 × $50k × 6 days)
├── Per Investor Share: 14.2857% ($300k / $2.1m)
├── Per Investor Profit: $13,571.43
├── Total Distributed: $95,000.01 ✓
└── ROI: 27.14%

ATIUM FUND (batch_id=1, fund_name="atium"):
├── Investors: 8
├── Weighted Total: $2,400,000 (8 × $50k × 6 days)
├── Per Investor Share: 12.5000% ($300k / $2.4m)
├── Per Investor Profit: $9,062.50
├── Total Distributed: $72,500.00 ✓
└── ROI: 18.13%

KEY POINT: Weighted totals calculated INDEPENDENTLY per fund
even though both use the same batch_id=1
```

COMBINED:
├── Total Capital: $750,000.00
├── Total Profit: $167,500.01
├── Overall ROI: 22.33%
└── Total Investors: 15
```

### API Authentication Check
```
✓ Public Endpoints (no JWT):
  - POST /users (registration)
  - POST /login

✓ Protected Endpoints (require JWT):
  - All Batch endpoints (6)
  - All Investment endpoints (6)
  - All Performance endpoints (4)
  - All Admin endpoints except login/register
```

---

## Test Tools to Use

**Option 1: Postman**
1. Create new Collection "OFDS Testing"
2. Add folder "Auth" → POST /users, POST /login
3. Add folder "Batches" → all batch endpoints
4. Add folder "Investments" → all investment endpoints
5. Add folder "Performance" → all performance endpoints
6. Set up token in Authorization tab (Bearer token)
7. Run requests in order

**Option 2: VS Code REST Client** (rest-client extension)
Create file `test.http`:
```
### Admin Registration
POST http://localhost:5000/api/v1/users
Content-Type: application/json

{
  "first_name": "John",
  "last_name": "Admin",
  "email": "admin@ofds.com",
  "password": "AdminPassword123!",
  "user_role": "admin"
}

### Admin Login
POST http://localhost:5000/api/v1/login
Content-Type: application/json

{
  "email": "admin@ofds.com",
  "password": "AdminPassword123!"
}

@token = eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

### Create Axiom Batch
POST http://localhost:5000/api/v1/batches
Authorization: Bearer @token
Content-Type: application/json

{
  "batch_name": "Axiom Q1-2026",
  "certificate_number": "AX-Q1-2026",
  "date_deployed": "2026-03-10T00:00:00",
  "duration_days": 30,
  "total_principal": 350000.00
}
```

**Option 3: cURL commands**
```bash
# Registration
curl -X POST http://localhost:5000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "first_name": "John",
    "last_name": "Admin",
    "email": "admin@ofds.com",
    "password": "AdminPassword123!",
    "user_role": "admin"
  }'

# Login
curl -X POST http://localhost:5000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@ofds.com",
    "password": "AdminPassword123!"
  }'

# Create Batch (with token)
curl -X POST http://localhost:5000/api/v1/batches \
  -H "Authorization: Bearer {your_token_here}" \
  -H "Content-Type: application/json" \
  -d '{
    "batch_name": "Axiom Q1-2026",
    "certificate_number": "AX-Q1-2026",
    "date_deployed": "2026-03-10T00:00:00",
    "duration_days": 30,
    "total_principal": 350000.00
  }'
```

---

## Common Issues & Solutions

| Issue | Cause | Solution |
|-------|-------|----------|
| `401 Unauthorized` | Missing or invalid token | Make sure token from login step is included in `Authorization: Bearer {token}` header |
| `400 Bad Request` | Invalid JSON or missing fields | Check request body matches expected format exactly |
| `404 Not Found` | Wrong endpoint URL | Check batch_id and endpoint path are correct |
| `422 Unprocessable Entity` | Invalid data type or value | Verify dates are ISO format (2026-03-10), amounts are decimal (50000.00) |
| `500 Internal Server Error` | Server-side error | Check server logs for detailed error message |
| Profit doesn't match expected | Wrong net profit or days calculation | Verify net_profit = gross_profit - transaction_costs |
| Different profit shares | Fund size drives shares | Axiom (7 investors) = 14.29% each, Atium (8 investors) = 12.5% each |

---

## Next: Run This Workflow!

Once you're ready to execute:

1. **Start Flask server:**
   ```bash
   python main.py
   ```

2. **Pick your test tool** (Postman, REST Client, or cURL)

3. **Follow phases 1-6 in order**

4. **Compare actual responses with expected values**

5. **Note any discrepancies** and report them

**Ready to test? Let me know when you want to start!** 🚀
