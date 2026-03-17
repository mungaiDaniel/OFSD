# OFDS Backend - Complete Project Walkthrough

## 📋 Table of Contents
1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Architecture](#architecture)
4. [Database Schema](#database-schema)
5. [Module Structure](#module-structure)
6. [Authentication & Authorization](#authentication--authorization)
7. [API Endpoints](#api-endpoints)
8. [Business Logic: Pro-Rata Distribution](#business-logic-pro-rata-distribution)
9. [Setting Up & Running](#setting-up--running)
10. [Complete Workflow Example](#complete-workflow-example)

---

## 🎯 Project Overview

### What is OFDS?
**OFDS** is an **Offshore Fund Distribution System** - a Flask-based backend application that manages:

- **Investment Batches**: Groups of investments deployed at a specific time
- **Investments**: Individual investor capital contributions to batches
- **Performance Tracking**: Profit/loss data for closed batches
- **Pro-Rata Distribution**: Automatic profit allocation to investors based on their contribution weight and active participation days

### Core Purpose
The system calculates fair profit distributions to investors using a weighted capital formula that considers:
- Time invested (days active in the batch)
- Amount invested
- Batch performance (gross profit - costs)

---

## 🛠️ Technology Stack

| Component | Technology |
|-----------|-----------|
| **Framework** | Flask 3.1.3 |
| **Database** | PostgreSQL (SQLAlchemy 2.0) |
| **Authentication** | JWT (Flask-JWT-Extended 4.7.1) |
| **CORS** | Flask-CORS 6.0.2 |
| **Data Validation** | Marshmallow 4.2.2 |
| **File Handling** | OpenPyXL (Excel files) |
| **Data Processing** | Pandas, NumPy |
| **Migrations** | Alembic 1.18.4 |
| **Password Hashing** | Passlib 1.7.4 |

### Key Dependencies
```
Flask==3.1.3
Flask-SQLAlchemy==3.1.1
Flask-JWT-Extended==4.7.1
psycopg2-binary==2.9.11  (PostgreSQL adapter)
marshmallow==4.2.2  (Serialization)
openpyxl==3.1.5  (Excel support)
```

---

## 🏗️ Architecture

### Design Pattern: MVC (Model-View-Controller)

```
┌─────────────────────────────────────────┐
│          Flask Application              │
├─────────────────────────────────────────┤
│  API Routes Layer (route.py files)      │
├─────────────────────────────────────────┤
│  Controllers (Business Logic)           │
├─────────────────────────────────────────┤
│  Services (Pro-Rata Calculation)        │
├─────────────────────────────────────────┤
│  Models (Database Schema)               │
├─────────────────────────────────────────┤
│  Database Layer (SQLAlchemy ORM)        │
├─────────────────────────────────────────┤
│  PostgreSQL Database                    │
└─────────────────────────────────────────┘
```

### Module Organization

```
app/
├── Admin/                 # User Management & Authentication
│   ├── model.py          # User model with auth token generation
│   ├── controllers.py     # User CRUD operations
│   └── route.py          # Auth endpoints (/login, /users)
│
├── Batch/                # Investment Batch Management
│   ├── model.py          # Batch model with date calculations
│   ├── controllers.py     # Batch CRUD operations
│   └── route.py          # Batch endpoints
│
├── Investments/          # Individual Investment Tracking
│   ├── model.py          # Investment model
│   ├── controllers.py     # Investment CRUD operations
│   └── route.py          # Investment endpoints
│
├── Performance/          # Batch Performance & Distributions
│   ├── model.py          # Performance metrics model
│   ├── pro_rata_distribution.py  # Distribution model
│   ├── controllers.py     # Performance operations
│   └── route.py          # Performance endpoints
│
├── logic/
│   └── pro_rata_service.py       # Core pro-rata calculation logic
│
├── schemas/
│   └── schemas.py        # Data validation schemas (Marshmallow)
│
├── utils/
│   ├── decorators.py     # JWT permission checks
│   ├── responses.py      # Standardized API responses
│   └── __init__.py
│
└── database/
    └── database.py       # SQLAlchemy initialization
```

---

## 💾 Database Schema

### 1. **Users Table**
```sql
CREATE TABLE "user" (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    password VARCHAR(1000),
    user_role ENUM('super_admin', 'admin', 'user') DEFAULT 'user',
    date_created TIMESTAMP DEFAULT NOW(),
    date_updated TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'SYSTEM',
    active BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMP NULL
);
```

**Fields:**
- `id`: Unique identifier
- `name`: User full name
- `email`: Unique email (login credential)
- `password`: MD5-hashed password
- `user_role`: Access level (super_admin=2, admin=1, user=0)
- Audit fields: date_created, date_updated, created_by, active, deleted_at

---

### 2. **Batches Table**
```sql
CREATE TABLE batches (
    id SERIAL PRIMARY KEY,
    batch_name VARCHAR(100) NOT NULL,
    certificate_number VARCHAR(100) UNIQUE NOT NULL,
    total_principal NUMERIC(20,2) DEFAULT 0.00,
    date_deployed TIMESTAMP NOT NULL,
    duration_days INTEGER DEFAULT 30,
    date_closed TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    date_created TIMESTAMP DEFAULT NOW(),
    date_updated TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'SYSTEM',
    active BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMP NULL
);
```

**Key Concept:**
- `date_deployed`: Batch start date (Day 0)
- `duration_days`: How long the batch runs (e.g., 30 days)
- Calculated property: `expected_close_date` = date_deployed + duration_days

**Example:**
- Batch created on Mar 1, 2026 with 30-day duration
- Expected close: Mar 31, 2026
- Investors depositing Mar 10-Mar 20 have active participation from their deposit date to Mar 31

---

### 3. **Investments Table**
```sql
CREATE TABLE investments (
    id SERIAL PRIMARY KEY,
    investor_name VARCHAR(100) NOT NULL,
    investor_email VARCHAR(100) NOT NULL,
    investor_phone VARCHAR(20),
    amount_deposited NUMERIC(20,2) NOT NULL,
    date_deposited TIMESTAMP DEFAULT NOW(),
    batch_id INTEGER NOT NULL FOREIGN KEY -> batches.id,
    date_created TIMESTAMP DEFAULT NOW(),
    date_updated TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'SYSTEM',
    active BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMP NULL
);
```

**Fields:**
- `investor_*`: Contact information
- `amount_deposited`: Capital contribution (must be > 0)
- `date_deposited`: When investor put money in
- `batch_id`: Links to parent batch

---

### 4. **Performance Table**
```sql
CREATE TABLE performance (
    id SERIAL PRIMARY KEY,
    batch_id INTEGER NOT NULL UNIQUE FOREIGN KEY -> batches.id,
    gross_profit NUMERIC(20,2) NOT NULL,
    transaction_costs NUMERIC(20,2) DEFAULT 0.00,
    date_created TIMESTAMP DEFAULT NOW(),
    date_updated TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'SYSTEM',
    active BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMP NULL
);
```

**Calculation:**
- `net_profit` (calculated property) = gross_profit - transaction_costs
- This profit is distributed among investors

**Example:**
- Gross profit: $150,000
- Transaction costs: $5,000
- Net profit available for distribution: $145,000

---

### 5. **Pro-Rata Distributions Table**
```sql
CREATE TABLE pro_rata_distributions (
    id SERIAL PRIMARY KEY,
    investment_id INTEGER NOT NULL FOREIGN KEY -> investments.id,
    performance_id INTEGER NOT NULL FOREIGN KEY -> performance.id,
    days_active INTEGER,
    weighted_capital NUMERIC(20,2),
    profit_share_percentage NUMERIC(10,4),
    profit_allocated NUMERIC(20,2),
    calculation_date TIMESTAMP DEFAULT NOW(),
    date_created TIMESTAMP DEFAULT NOW(),
    date_updated TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100) DEFAULT 'SYSTEM',
    active BOOLEAN DEFAULT TRUE,
    deleted_at TIMESTAMP NULL
);
```

**Fields (Calculated):**
- `days_active`: How many days investor's capital was in the fund
- `weighted_capital`: Amount × Days Active
- `profit_share_percentage`: Investor's share of total capital-days (0-100)
- `profit_allocated`: Their portion of net profit ($)

---

## 👥 Authentication & Authorization

### User Roles & Permission Levels

| Role | Level | Permissions |
|------|-------|-------------|
| **super_admin** | 2 | All operations, user management, batch operations |
| **admin** | 1 | Batch operations, investment management |
| **user** | 0 | View-only access to their own investments |

### JWT Token Management

**Token Format:**
```json
{
    "identity": "user@example.com",
    "admin": 2,  // Permission level
    "exp": 1234567890,
    "type": "access"
}
```

**Token Expiration:**
- Access tokens: 1 day
- Refresh tokens: 1 day

**Login Flow:**
1. POST `/api/v1/login` with email & password
2. Verify password hash (MD5-crypt)
3. Build JWT token with user role
4. Return both access and refresh tokens
5. Client includes token in `Authorization: Bearer <token>` header

**Permission Decorator:**
```python
@permission(arg)  # arg = minimum required permission level
def my_endpoint():
    pass
```

Example: `@permission(1)` requires admin level (1 or higher)

---

## 🔌 API Endpoints

### Base URL
```
http://localhost:5000/api/v1
```

### Authentication Required
Most endpoints require JWT token in header:
```
Authorization: Bearer <access_token>
```

---

### 📝 USER MANAGEMENT (Admin Module)

#### 1. **Register User**
```
POST /users
Headers: None (public endpoint)
Body:
{
    "name": "John Admin",
    "email": "john@example.com",
    "password": "securepass123"
}

Response (201):
{
    "message": "Registration completed"
}
```

#### 2. **Login**
```
POST /login
Headers: None (public endpoint)
Body:
{
    "email": "john@example.com",
    "password": "securepass123"
}

Response (200):
{
    "message": "SUCCESS",
    "value": {
        "access_token": "eyJ...",
        "refresh_token": "eyJ...",
        "user_role": "admin"
    }
}
```

#### 3. **Get User by ID**
```
GET /users/<id>
Headers: Authorization: Bearer <token>

Response (200):
{
    "id": 1,
    "name": "John Admin",
    "email": "john@example.com",
    "user_role": "admin"
}
```

#### 4. **Get All Users**
```
GET /users
Headers: None

Response (200):
[
    {
        "id": 1,
        "name": "John Admin",
        "email": "john@example.com",
        "user_role": "admin"
    },
    ...
]
```

#### 5. **Promote User to Admin**
```
PUT /admin/<id>
Headers: Authorization: Bearer <token> (admin required)

Response (200): Updated user object
```

#### 6. **Promote User to Super Admin**
```
PUT /super_admin/<id>
Headers: None

Response (200): Updated user object
```

#### 7. **Get All Admin/Employees**
```
GET /employees
Headers: Authorization: Bearer <token> (admin required)

Response (200): List of admin users
```

---

### 📦 BATCH MANAGEMENT (Batch Module)

#### 1. **Create Batch**
```
POST /batches
Headers: Authorization: Bearer <token> (admin required)
Body:
{
    "batch_name": "MAR-2026-OFFSHORE",
    "certificate_number": "CERT-001",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30
}

Response (201):
{
    "id": 1,
    "batch_name": "MAR-2026-OFFSHORE",
    "certificate_number": "CERT-001",
    "total_principal": 0.00,
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30,
    "expected_close_date": "2026-03-31T00:00:00",
    "is_active": true
}
```

#### 2. **Get All Batches**
```
GET /batches
Headers: Authorization: Bearer <token>

Response (200):
[
    { batch objects },
    ...
]
```

#### 3. **Get Batch by ID**
```
GET /batches/<batch_id>
Headers: Authorization: Bearer <token>

Response (200):
{ batch object }
```

#### 4. **Update Batch**
```
PUT /batches/<batch_id>
Headers: Authorization: Bearer <token> (admin required)
Body:
{
    "batch_name": "APR-2026-OFFSHORE",
    "duration_days": 30,
    "date_closed": "2026-03-31T00:00:00",
    "is_active": false
}

Response (200): Updated batch object
```

#### 5. **Get Batch Summary** ⭐
```
GET /batches/<batch_id>/summary
Headers: Authorization: Bearer <token>

Response (200):
{
    "batch": { batch details },
    "total_principal": 500000.00,
    "investments": [
        {
            "id": 1,
            "investor_name": "John Doe",
            "amount_deposited": 50000.00,
            "date_deposited": "2026-03-10T00:00:00"
        },
        ...
    ],
    "performance": { performance data if exists },
    "distributions": [ distributions if calculated ]
}
```

---

### 💰 INVESTMENT MANAGEMENT (Investments Module)

#### 1. **Add Investment**
```
POST /investments
Headers: Authorization: Bearer <token> (admin required)
Body:
{
    "batch_id": 1,
    "investor_name": "John Doe",
    "investor_email": "john@example.com",
    "investor_phone": "+1234567890",
    "amount_deposited": 50000.00,
    "date_deposited": "2026-03-10T00:00:00"
}

Response (201): Investment object
```

#### 2. **Get Investment by ID**
```
GET /investments/<investment_id>
Headers: Authorization: Bearer <token>

Response (200): Investment object
```

#### 3. **Get All Investments for Batch**
```
GET /batches/<batch_id>/investments
Headers: Authorization: Bearer <token>

Response (200):
[
    { investment objects },
    ...
]
```

#### 4. **Add Investment to Batch (Shortcut)**
```
POST /batches/<batch_id>/investments
Headers: Authorization: Bearer <token> (admin required)
Body:
{
    "investor_name": "Jane Doe",
    "investor_email": "jane@example.com",
    "investor_phone": "+0987654321",
    "amount_deposited": 75000.00,
    "date_deposited": "2026-03-15T00:00:00"
}

Response (201): Investment object
```

#### 5. **Update Investment**
```
PUT /investments/<investment_id>
Headers: Authorization: Bearer <token> (admin required)
Body:
{
    "investor_name": "Jane Updated",
    "amount_deposited": 80000.00
}

Response (200): Updated investment object
```

#### 6. **Delete Investment**
```
DELETE /investments/<investment_id>
Headers: Authorization: Bearer <token> (admin required)

Response (202): Deletion success message
```

---

### 📊 PERFORMANCE & PRO-RATA CALCULATION (Performance Module)

#### 1. **Create Performance (Close Batch)**
```
POST /batches/<batch_id>/performance
Headers: Authorization: Bearer <token> (admin required)
Body:
{
    "gross_profit": 150000.00,
    "transaction_costs": 5000.00,
    "date_closed": "2026-03-31T00:00:00"
}

Response (201):
{
    "id": 1,
    "batch_id": 1,
    "gross_profit": 150000.00,
    "transaction_costs": 5000.00,
    "net_profit": 145000.00
}
```

#### 2. **Get Performance for Batch**
```
GET /batches/<batch_id>/performance
Headers: Authorization: Bearer <token>

Response (200): Performance object
```

#### 3. **Calculate Pro-Rata Distributions** ⭐⭐⭐
```
POST /batches/<batch_id>/calculate-pro-rata
Headers: Authorization: Bearer <token> (admin required)
Body: {} (empty or omitted)

Response (200):
{
    "message": "Pro-rata distributions calculated successfully",
    "batch_id": 1,
    "distribution_count": 3,
    "total_distributed": 145000.00,
    "distributions": [
        {
            "investor_name": "John Doe",
            "amount_deposited": 50000.00,
            "date_deposited": "2026-03-10T00:00:00",
            "days_active": 21,
            "weighted_capital": 1050000.00,
            "profit_share_percentage": 45.65,
            "profit_allocated": 66191.75
        },
        ...
    ]
}
```

**NOTE:** This endpoint must only be called AFTER performance data is entered!

#### 4. **Get All Distributions for Batch**
```
GET /batches/<batch_id>/distributions
Headers: Authorization: Bearer <token>

Response (200):
[
    {
        distribution details with investor info
    },
    ...
]
```

---

## ⚙️ Business Logic: Pro-Rata Distribution

### The "Active Money Rule"

This is the core algorithm for fair profit distribution.

#### **Rule Definition:**
```
Client Active Days = Batch End - Max(Client Deposit Date, Batch Start Date)
```

### Step-by-Step Calculation

**Given:**
- Batch: Mar 1 - Mar 31, 2026 (30 days)
- Net Profit: $145,000
- Investors:
  - Alice: $50,000 deposited Mar 10
  - Bob: $75,000 deposited Mar 1 (on batch start)
  - Charlie: $25,000 deposited Mar 20

---

#### **Step 1: Calculate Days Active**

```
Batch End = Mar 1 + 30 days = Mar 31
Batch Start = Mar 1

Alice:
  Start = Max(Mar 10, Mar 1) = Mar 10
  Days Active = Mar 31 - Mar 10 = 21 days

Bob:
  Start = Max(Mar 1, Mar 1) = Mar 1
  Days Active = Mar 31 - Mar 1 = 30 days

Charlie:
  Start = Max(Mar 20, Mar 1) = Mar 20
  Days Active = Mar 31 - Mar 20 = 11 days
```

---

#### **Step 2: Calculate Weighted Capital**

**Formula:** Weighted Capital = Amount × Days Active

```
Alice:   $50,000 × 21 days = $1,050,000
Bob:     $75,000 × 30 days = $2,250,000
Charlie: $25,000 × 11 days = $275,000

Total Weighted Capital = $1,050,000 + $2,250,000 + $275,000 = $3,575,000
```

---

#### **Step 3: Calculate Profit Share Percentage**

**Formula:** Profit Share % = (Weighted Capital / Total Weighted Capital) × 100

```
Alice:   ($1,050,000 / $3,575,000) × 100 = 29.37%
Bob:     ($2,250,000 / $3,575,000) × 100 = 62.93%
Charlie: ($275,000 / $3,575,000) × 100 = 7.70%

Total = 100% ✓
```

---

#### **Step 4: Calculate Profit Allocated**

**Formula:** Profit Allocated = (Profit Share % / 100) × Net Profit

```
Alice:   (0.2937) × $145,000 = $42,586.50
Bob:     (0.6293) × $145,000 = $91,249.50
Charlie: (0.0770) × $145,000 = $11,165.00

Total Distributed = $145,000 ✓
```

---

### Code Implementation

**Source File:** `app/logic/pro_rata_service.py`

```python
class ProRataCalculationService:
    
    @staticmethod
    def calculate_days_active(deposit_date, batch):
        """Returns days investor's capital was in fund"""
        batch_end = batch.date_deployed + timedelta(days=batch.duration_days)
        start_date = max(deposit_date, batch.date_deployed)
        return max(0, (batch_end - start_date).days)
    
    @staticmethod
    def calculate_weighted_capital(amount_deposited, days_active):
        """Returns amount × days"""
        return Decimal(str(amount_deposited)) * Decimal(str(days_active))
    
    @staticmethod
    def calculate_profit_share(investor_weighted_capital, total_weighted_capital):
        """Returns percentage (0-100)"""
        if total_weighted_capital == 0:
            return Decimal('0.00')
        return (investor_weighted_capital / total_weighted_capital) * Decimal('100')
    
    @staticmethod
    def calculate_profit_allocated(profit_share_percentage, net_profit):
        """Returns actual dollar amount"""
        return (profit_share_percentage / Decimal('100')) * net_profit
    
    @classmethod
    def calculate_pro_rata_distributions(cls, batch_id, performance_id):
        """Main orchestration method - calculates and creates distribution records"""
        # Implementation details...
```

---

## 🚀 Setting Up & Running

### Prerequisites
- Python 3.8+
- PostgreSQL 12+
- Git

### Installation Steps

#### **1. Clone & Navigate to Project**
```bash
cd c:\Users\Dantez\Documents\ofds\backend
```

#### **2. Create Virtual Environment**
```bash
python -m venv venv
```

#### **3. Activate Virtual Environment**

**Windows PowerShell:**
```bash
& venv\Scripts\Activate.ps1
```

**Windows CMD:**
```bash
venv\Scripts\activate.bat
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

#### **4. Install Dependencies**
```bash
pip install -r requirements.txt
```

#### **5. Configure Database**

Edit `config.py` with your PostgreSQL credentials:

```python
class DevelopmentConfig():
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:password@localhost/offshow-dev"
    DEBUG = True
```

#### **6. Initialize Database**
```bash
python
>>> from main import app
>>> with app.app_context():
...     from app.database.database import db
...     db.create_all()
>>> exit()
```

#### **7. Run the Application**
```bash
python main.py
```

Server runs on `http://localhost:5000`

---

## 📋 Complete Workflow Example

### Scenario: Manage a Single Investment Batch

---

### **Phase 1: System Setup**

#### Step 1.1: Create Admin User
```bash
curl -X POST http://localhost:5000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Alice Manager",
    "email": "alice@company.com",
    "password": "admin123"
  }'
```

#### Step 1.2: Login to Get Token
```bash
curl -X POST http://localhost:5000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "alice@company.com",
    "password": "admin123"
  }'

# Response:
{
    "message": "SUCCESS",
    "value": {
        "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "user_role": "admin"
    }
}
```

Store this token for all subsequent requests.

---

### **Phase 2: Create Batch**

#### Step 2.1: Create Investment Batch
```bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -X POST http://localhost:5000/api/v1/batches \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "batch_name": "MAR-2026-OFFSHORE",
    "certificate_number": "CERT-MAR-001",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30
  }'

# Response:
{
    "id": 1,
    "batch_name": "MAR-2026-OFFSHORE",
    "certificate_number": "CERT-MAR-001",
    "date_deployed": "2026-03-01T00:00:00",
    "duration_days": 30,
    "expected_close_date": "2026-03-31T00:00:00",
    "is_active": true
}
```

---

### **Phase 3: Add Investors**

#### Step 3.1: Add First Investor (Alice)
```bash
curl -X POST http://localhost:5000/api/v1/investments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "batch_id": 1,
    "investor_name": "Alice Investor",
    "investor_email": "alice.investor@example.com",
    "investor_phone": "+1-555-0101",
    "amount_deposited": 50000.00,
    "date_deposited": "2026-03-10T00:00:00"
  }'

# Response:
{
    "id": 1,
    "investor_name": "Alice Investor",
    "investor_email": "alice.investor@example.com",
    "amount_deposited": 50000.00,
    "date_deposited": "2026-03-10T00:00:00",
    "batch_id": 1
}
```

#### Step 3.2: Add Second Investor (Bob)
```bash
curl -X POST http://localhost:5000/api/v1/investments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "batch_id": 1,
    "investor_name": "Bob Investor",
    "investor_email": "bob.investor@example.com",
    "investor_phone": "+1-555-0102",
    "amount_deposited": 75000.00,
    "date_deposited": "2026-03-01T00:00:00"
  }'
```

#### Step 3.3: Add Third Investor (Charlie)
```bash
curl -X POST http://localhost:5000/api/v1/investments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "batch_id": 1,
    "investor_name": "Charlie Investor",
    "investor_email": "charlie.investor@example.com",
    "investor_phone": "+1-555-0103",
    "amount_deposited": 25000.00,
    "date_deposited": "2026-03-20T00:00:00"
  }'
```

#### Step 3.4: Verify Batch Summary
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/summary \
  -H "Authorization: Bearer $TOKEN"

# Response shows all investments and totals
```

---

### **Phase 4: Batch Execution & Closing**

#### Step 4.1: Time Passes... (Mar 1 - Mar 31)
The batch is active during this period. Investors' capital is generating returns.

#### Step 4.2: Record Performance (Close Batch)
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/performance \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "gross_profit": 150000.00,
    "transaction_costs": 5000.00,
    "date_closed": "2026-03-31T00:00:00"
  }'

# Response:
{
    "id": 1,
    "batch_id": 1,
    "gross_profit": 150000.00,
    "transaction_costs": 5000.00,
    "net_profit": 145000.00
}
```

---

### **Phase 5: Calculate & Distribute Profits**

#### Step 5.1: Trigger Pro-Rata Calculation ⭐
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/calculate-pro-rata \
  -H "Authorization: Bearer $TOKEN"

# Response:
{
    "message": "Pro-rata distributions calculated successfully",
    "batch_id": 1,
    "distribution_count": 3,
    "total_distributed": 145000.00,
    "distributions": [
        {
            "id": 1,
            "investor_name": "Alice Investor",
            "investor_email": "alice.investor@example.com",
            "amount_deposited": 50000.00,
            "date_deposited": "2026-03-10T00:00:00",
            "days_active": 21,
            "weighted_capital": 1050000.00,
            "profit_share_percentage": 29.37,
            "profit_allocated": 42567.15
        },
        {
            "id": 2,
            "investor_name": "Bob Investor",
            "investor_email": "bob.investor@example.com",
            "amount_deposited": 75000.00,
            "date_deposited": "2026-03-01T00:00:00",
            "days_active": 30,
            "weighted_capital": 2250000.00,
            "profit_share_percentage": 62.93,
            "profit_allocated": 91284.85
        },
        {
            "id": 3,
            "investor_name": "Charlie Investor",
            "investor_email": "charlie.investor@example.com",
            "amount_deposited": 25000.00,
            "date_deposited": "2026-03-20T00:00:00",
            "days_active": 11,
            "weighted_capital": 275000.00,
            "profit_share_percentage": 7.69,
            "profit_allocated": 11165.00
        }
    ]
}
```

#### Step 5.2: View Final Distributions
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/distributions \
  -H "Authorization: Bearer $TOKEN"

# Same detailed response as above
```

#### Step 5.3: Final Summary
```bash
curl -X GET http://localhost:5000/api/v1/batches/1/summary \
  -H "Authorization: Bearer $TOKEN"

# Shows batch, investments, performance, and all distributions
```

---

### **Results Summary**

```
BATCH: MAR-2026-OFFSHORE
├─ Duration: Mar 1 - Mar 31, 2026 (30 days)
├─ Total Capital: $150,000
├─ Gross Profit: $150,000
├─ Transaction Costs: $5,000
└─ Net Profit (Distributed): $145,000

DISTRIBUTIONS:
├─ Alice Investor: $42,567.15 (29.37%)
├─ Bob Investor: $91,284.85 (62.93%)  ← Largest share (earliest depositor)
└─ Charlie Investor: $11,165.00 (7.69%)  ← Smallest share (latest depositor)

KEY INSIGHT:
Bob received the largest profit share (62.93%) because:
- He deposited $75,000 × 30 active days = $2,250,000 weighted capital
- This is the largest weighted capital contribution
- His 30 days active > Alice's 21 days > Charlie's 11 days
```

---

## 🔧 Common Operations

### Add More Investors to Existing Batch
```bash
curl -X POST http://localhost:5000/api/v1/batches/1/investments \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{ investment data }'
```

### Update Investor Information
```bash
curl -X PUT http://localhost:5000/api/v1/investments/1 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "investor_name": "New Name",
    "investor_phone": "+1-555-9999"
  }'
```

### Delete Investment (Before Profit Calculation)
```bash
curl -X DELETE http://localhost:5000/api/v1/investments/1 \
  -H "Authorization: Bearer $TOKEN"
```

### View All Batches
```bash
curl -X GET http://localhost:5000/api/v1/batches \
  -H "Authorization: Bearer $TOKEN" | jq '.'
```

---

## ⚠️ Important Notes

1. **Pro-Rata Calculation** should only be done AFTER:
   - Batch duration has ended
   - Performance data (profit/costs) has been entered
   - No new investments should be added after performance entry

2. **Password Security**: Currently uses MD5-crypt. Consider upgrading to bcrypt.

3. **Database**: Uses PostgreSQL. Ensure connection string is correct in `config.py`

4. **CORS**: Currently allows all origins (`"*"`). Restrict for production.

5. **Decimal Precision**: Uses `Decimal` type for financial calculations to avoid floating-point errors

---

## 📚 File Reference Quick Guide

| File | Purpose |
|------|---------|
| [main.py](main.py) | Application entry point, Flask app setup |
| [config.py](config.py) | Database & environment configuration |
| [base_model.py](base_model.py) | Base SQLAlchemy model with audit fields |
| [app/Admin/model.py](app/Admin/model.py) | User model with JWT generation |
| [app/Batch/model.py](app/Batch/model.py) | Batch/investment pool model |
| [app/Investments/model.py](app/Investments/model.py) | Individual investment model |
| [app/Performance/model.py](app/Performance/model.py) | Batch performance/profit model |
| [app/Performance/pro_rata_distribution.py](app/Performance/pro_rata_distribution.py) | Distribution tracking model |
| [app/logic/pro_rata_service.py](app/logic/pro_rata_service.py) | Core pro-rata calculation logic |
| [app/utils/decorators.py](app/utils/decorators.py) | JWT permission checker |
| [app/utils/responses.py](app/utils/responses.py) | Standard API response formatter |

---

## 🎓 Next Steps for Learning

1. **Database Design**: Review the schema in PostgreSQL
2. **Business Logic**: Study `pro_rata_service.py` to understand calculations
3. **API Testing**: Use Postman or curl to test endpoints
4. **Code Walkthrough**: Read through controllers to see how requests are handled
5. **Extensions**: Add features like batch history, investor settlements, etc.

---

**Document Generated:** March 16, 2026  
**Project:** OFDS Backend - Offshore Fund Distribution System
