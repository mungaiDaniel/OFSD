# Fix for "No Movable Investor Records Found" & Share Class Code Updates

## Problem Statement

1. **"No movable investor records found (current holdings may already be deployed)"** error when trying to update an investor's share class/currency after the holdings were deployed.
2. **Cannot fix share class code** (e.g., `kes_r` → `kes_I`) once a batch is deployed.
3. **Multiple deposits from one investor** need selective currency/share class updating, but current system doesn't allow picking specific deposits.

---

## Root Cause

The original `/api/v1/investors/<client_code>` PATCH endpoint applied share class updates to **ALL** investments for that investor, regardless of deployment status. This created a risky situation where:
- Deployed holdings couldn't be safely updated
- System returned error instead of offering alternatives
- Investor with multiple deposits couldn't selectively move one deposit to a different share class

---

## Solution: Three-Part Fix

### 1. **Restrict Share Class Updates to Movable Deposits Only**
**File:** `app/Investments/route.py` (Line ~3560)

**What changed:**
- Share class/currency updates now apply **ONLY** to non-deployed (movable) investments
- Deployed holdings are silently skipped (not errored out)
- Added internal helper `_get_movable_investments()` to identify movable rows consistently

**Before:**
```python
q.update(share_class_updates, synchronize_session=False)  # Updates ALL rows
```

**After:**
```python
def _get_movable_investments():
    # Filters for non-deployed batches
    return (
        session.query(Investment)
        .join(Batch, Batch.id == Investment.batch_id)
        .filter(
            Investment.internal_client_code == client_code,
            func.coalesce(Batch.stage, 1) < 3,
            func.coalesce(Batch.deployment_confirmed, False).is_(False),
            Batch.deployment_date_actual.is_(None),
            Batch.deployment_nav.is_(None),
            func.coalesce(Batch.is_active, False).is_(False),
        )
        .all()
    )

movable_rows_for_update = _get_movable_investments()
if movable_rows_for_update:
    # Updates ONLY movable rows
    session.query(Investment).filter(
        Investment.id.in_([inv.id for inv in movable_rows_for_update])
    ).update(share_class_updates, synchronize_session=False)
```

---

### 2. **New Endpoint: List Investor's Multiple Deposits**
**Endpoint:** `GET /api/v1/investors/<client_code>/deposits`

**Purpose:** Show all deposits for an investor with deployment status and movability flag.

**Response:**
```json
{
  "status": 200,
  "data": [
    {
      "investment_id": 1,
      "amount_deposited": 100000,
      "date_deposited": "2026-04-10",
      "batch_id": 1,
      "batch_name": "AXM_KES_I_2026-04-10",
      "share_class_id": 1,
      "class_code": "KES_I",
      "currency": "KES",
      "is_deployed": false,
      "is_movable": true
    },
    {
      "investment_id": 2,
      "amount_deposited": 50000,
      "date_deposited": "2026-04-15",
      "batch_id": 2,
      "batch_name": "AXM_KES_I_2026-04-15",
      "share_class_id": 1,
      "class_code": "KES_I",
      "currency": "KES",
      "is_deployed": true,
      "is_movable": false
    }
  ]
}
```

**Use case:** Investor deposited twice. First deposit is still pending (movable), second was already deployed. Want to change first deposit's share class to USD_I.

---

### 3. **New Endpoint: Bulk Update Specific Deposits**
**Endpoint:** `PATCH /api/v1/investors/<client_code>/deposits/bulk-update`

**Purpose:** Selectively update share class/currency for chosen investments only.

**Request:**
```json
{
  "investment_ids": [1],
  "share_class_id": 2,
  "move_to_batch_id": 7
}
```

**Response:**
```json
{
  "status": 200,
  "message": "Deposits updated successfully",
  "data": {
    "updated_count": 1,
    "batch_id": 7,
    "share_class_id": 2,
    "currency": "USD"
  }
}
```

**Safeguards:**
- Only updates **movable** (non-deployed) investments
- Rejects if target batch is deployed
- Auto-selects or creates appropriate batch if not specified
- Validates share class currency is supported (KES or USD)

---

### 4. **New Endpoint: Force-Fix Deployed Share Class Code**
**Endpoint:** `PATCH /api/v1/funds/<fund_id>/classes/<class_id>/force-update-code`

**Purpose:** Correct a share class code (e.g., `kes_r` → `kes_I`) for already-deployed batches only.

**Request:**
```json
{
  "new_class_code": "KES_I"
}
```

**Response:**
```json
{
  "status": 200,
  "message": "Share class code updated for deployed batches only",
  "data": {
    "updated_batches": 2,
    "updated_investments": 15,
    "old_code": "kes_r",
    "new_code": "KES_I"
  }
}
```

**Safeguards:**
- **Only touches deployed batches** (deployment_confirmed = true)
- Leaves pending/movable batches unchanged
- Returns error if no deployed batches exist for that share class

---

## Deployment Criteria for Movable Investments

An investment is considered **movable** if its batch meets ALL these conditions:
```python
(batch.stage or 1) < 3                           # Stage < 3 (not yet at Deployed stage)
and not (batch.deployment_confirmed or False)   # NOT confirmed deployed
and batch.deployment_date_actual is None        # No actual deployment date set
and batch.deployment_nav is None                # No NAV locked in
and not (batch.is_active or False)              # NOT marked as active
```

An investment is **deployed** if ANY of these are true:
```python
(batch.stage or 1) >= 3                    # At stage 3 or higher
or batch.deployment_confirmed              # Marked as deployed
or batch.deployment_date_actual is not None # Has deployment date
or batch.deployment_nav is not None        # NAV is locked
or batch.is_active                         # Marked active (post-deployment)
```

---

## Usage Workflow

### Scenario: Investor with 2 deposits, wants to change first one to different share class

**Step 1:** List all deposits
```bash
GET /api/v1/investors/INV-12345/deposits
```

Response shows:
- Deposit 1 (ID: 100): KES_I, pending (movable)
- Deposit 2 (ID: 101): KES_I, deployed (not movable)

**Step 2:** Bulk update only the movable deposit
```bash
PATCH /api/v1/investors/INV-12345/deposits/bulk-update
Body: {
  "investment_ids": [100],
  "share_class_id": 2  # USD_I
}
```

Result: Deposit 1 moved to USD_I; Deposit 2 stays KES_I.

---

### Scenario: Fix deployed share class code

**Step 1:** Fix the code retroactively
```bash
PATCH /api/v1/funds/1/classes/1/force-update-code
Body: {
  "new_class_code": "KES_I"
}
```

Result: All deployed batches for that share class now show "KES_I" instead of "kes_r".

---

## Error Handling

| Endpoint | Error | Status | Resolution |
|----------|-------|--------|-----------|
| PATCH `/investors/<code>` | No movable records | 409 | Use bulk-update or check deployment status |
| PATCH `/deposits/bulk-update` | All selected deployed | 409 | Pick only movable deposits from list endpoint |
| PATCH `/classes/<id>/force-update-code` | No deployed batches | 409 | Use regular update endpoint for pending share classes |

---

## Files Modified

1. **`app/Investments/route.py`**
   - ✅ Restricted share class updates to movable investments only
   - ✅ Added `_get_movable_investments()` helper
   - ✅ Added `GET /api/v1/investors/<code>/deposits` endpoint
   - ✅ Added `PATCH /api/v1/investors/<code>/deposits/bulk-update` endpoint

2. **`app/Funds/routes.py`**
   - ✅ Added `PATCH /api/v1/funds/<id>/classes/<id>/force-update-code` endpoint

---

## Testing Checklist

- [ ] Investor with pending deposit: can update share class via PATCH `/investors/<code>`
- [ ] Investor with deployed deposit: cannot update directly (returns 409)
- [ ] Investor with 2 deposits (1 pending, 1 deployed): can list both
- [ ] Bulk update: only moves selected movable deposits
- [ ] Bulk update: rejects if target batch is deployed
- [ ] Force-update share class code: only affects deployed batches
- [ ] Force-update: leaves pending batches unchanged

