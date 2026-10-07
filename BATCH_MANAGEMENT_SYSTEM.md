# Automatic Batch Management System

## Overview

The automatic batch management system handles the complete lifecycle of investor batches:
- **Auto-Batch Selection:** When adding an investor, find an open batch for their share class
- **Auto-Batch Creation:** If no open batch exists, create one with auto-generated name
- **Auto-Batch Closure:** Every Thursday at 9:00 AM EAT, close (or delete) ready batches
- **Single Share Class Constraint:** Each batch belongs to exactly ONE share class

## Architecture

### Core Services

#### 1. **BatchManagementService** (`app/logic/batch_management_service.py`)

Main service for batch operations.

**Key Methods:**

- `find_or_create_batch(share_class_id)` - Find open batch or create new one
- `create_and_assign_investor_to_batch(investment, share_class_id)` - Complete workflow
- `close_batch(batch, reason)` - Set is_open=False
- `delete_empty_batch(batch)` - Delete batch if no investors
- `process_batch_closures()` - Process all batches ready to close
- `get_batches_ready_for_closure()` - Query batches for closure

#### 2. **BatchSchedulerService** (`app/logic/batch_scheduler_service.py`)

Autonomous scheduler for batch closure.

**Key Methods:**

- `init_scheduler(app)` - Initialize APScheduler at app startup
- `shutdown_scheduler()` - Clean shutdown
- `process_batch_closures_task()` - Autonomous task (runs Thursday 9 AM EAT)
- `get_scheduler_status()` - Query scheduler status
- `trigger_batch_closures_manually()` - Manual trigger (for testing/admin)

### Timezone Handling

- **EAT (East Africa Time):** UTC+3 (used for all user-facing times)
- **Auto-Close Time:** Thursday 9:00 AM EAT = Thursday 6:00 AM UTC
- **Storage:** All `auto_close_at` timestamps stored in UTC
- **Conversion:** Service automatically converts between EAT and UTC

### Batch Naming Convention

```
{fund_code}_{class_code}_{next_thursday_date}

Examples:
- AXIOM_CI-KES_2026-04-18
- ATIUM_CI-USD_2026-04-25
```

## Data Flow

### Adding a New Investor

```
POST /api/v1/investors
├─ Create Investment record (with share_class_id)
├─ Call BatchManagementService.create_and_assign_investor_to_batch()
│  ├─ Check for open batch with matching share_class_id
│  │  └─ is_open=True AND auto_close_at > now()
│  ├─ If found:
│  │  └─ Use existing batch
│  └─ If not found:
│     ├─ Calculate next Thursday 9:00 AM EAT
│     ├─ Generate batch_name: {fund_code}_{class_code}_{thursday_date}
│     ├─ Create Batch with:
│     │  ├─ share_class_id (set once, immutable)
│     │  ├─ is_open = True
│     │  └─ auto_close_at = Thursday 9 AM UTC
│     └─ Return new batch
├─ Assign investor to batch
├─ Commit to database
└─ Return Investment + Batch details
```

### Automatic Batch Closure

```
Every Thursday 6:00 AM UTC (= 9:00 AM EAT)
├─ Query all batches WHERE is_open=True AND auto_close_at <= now()
├─ For each batch:
│  ├─ If investor_count = 0:
│  │  └─ Delete batch
│  └─ Else (investor_count > 0):
│     ├─ Set is_open = False
│     ├─ (Future) Generate Excel export
│     └─ Commit
└─ Log statistics (deleted, closed, errors)
```

## Key Constraints

### Share Class Isolation

**Rule:** A batch belongs to exactly ONE share class.

```python
# ✅ Correct - both investors in same class
batch = find_or_create_batch(share_class_id=1)  # Class I - KES
add_investor_to_batch(joy_investment, batch)     # KES
add_investor_to_batch(john_investment, batch)    # KES

# ❌ Wrong - different class, would fail
batch = find_or_create_batch(share_class_id=1)  # Class I - KES
add_investor_to_batch(adam_investment, batch)   # USD - ValueError!
```

**Enforcement:** 
- Database constraint: `share_class_id` stored on batch
- Application validation: check `investment.share_class_id == batch.share_class_id`
- Separate batch creation per share class

### Immutability

Once a batch is created with a `share_class_id`, it cannot be changed:

```python
batch.share_class_id = 999  # ❌ Should not be modified
```

Database should have a check constraint or migration to prevent updates to `share_class_id`.

## Configuration

### Timezone

All times use EAT (UTC+3):

```python
EAT_TIMEZONE_OFFSET = timedelta(hours=3)  # In batch_management_service.py
```

To change timezone, update this constant in both services.

### Closure Day/Time

Closure runs on Thursday at 9:00 AM EAT:

```python
# In batch_scheduler_service.py
BATCH_CLOSURE_HOUR_UTC = 6          # 6 AM UTC = 9 AM EAT
BATCH_CLOSURE_MINUTE_UTC = 0
BATCH_CLOSURE_WEEKDAY = 3           # 3 = Thursday
```

To change to Friday:
```python
BATCH_CLOSURE_WEEKDAY = 4  # Friday
```

## Integration Steps

### 1. Install APScheduler

```bash
pip install apscheduler
# Add to requirements.txt:
apscheduler>=3.10.0
```

### 2. Initialize Scheduler in App

In your Flask app factory:

```python
from app.logic.batch_scheduler_service import BatchSchedulerService

def create_app():
    app = Flask(__name__)
    
    # ... other initializations ...
    
    # Initialize batch scheduler
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        BatchSchedulerService.init_scheduler(app)
    
    # Register shutdown
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        BatchSchedulerService.shutdown_scheduler()
    
    return app
```

### 3. Update Investors Route

In your POST /api/v1/investors handler:

```python
from app.logic.batch_management_service import BatchManagementService

@investors_bp.route('/api/v1/investors', methods=['POST'])
def create_investor():
    data = request.get_json()
    
    # Create investment
    investment = Investment(
        investor_name=data['investor_name'],
        investor_email=data['investor_email'],
        share_class_id=data['share_class_id'],
        # ... other fields ...
    )
    
    # Assign to batch (auto-create if needed)
    investment, batch = BatchManagementService.create_and_assign_investor_to_batch(
        investment=investment,
        share_class_id=data['share_class_id'],
    )
    
    return {
        "investor_id": investment.id,
        "batch_id": batch.id,
        "batch_name": batch.batch_name,
    }, 201
```

### 4. Add Admin Endpoints (Optional)

For monitoring and manual triggers:

```python
@admin_bp.route('/batch-scheduler/status', methods=['GET'])
def get_scheduler_status():
    status = BatchSchedulerService.get_scheduler_status()
    return status, 200

@admin_bp.route('/batch-scheduler/trigger-closures', methods=['POST'])
def trigger_closures():
    stats = BatchSchedulerService.trigger_batch_closures_manually()
    return stats, 200
```

## Usage Examples

### Finding/Creating a Batch

```python
from app.logic.batch_management_service import BatchManagementService

# Find open batch for a share class (or create new)
batch = BatchManagementService.find_or_create_batch(share_class_id=1)
print(f"Using batch: {batch.batch_name}")
print(f"Auto-closes at: {batch.auto_close_at}")
```

### Adding Multiple Investors to Same Batch

```python
share_class_id = 1  # Class I - KES

# First investor creates batch
investor1, batch = BatchManagementService.create_and_assign_investor_to_batch(
    investment=inv1, share_class_id=share_class_id
)

# Second investor (same day) uses same batch
investor2, batch = BatchManagementService.create_and_assign_investor_to_batch(
    investment=inv2, share_class_id=share_class_id
)

assert investor1.batch_id == investor2.batch_id  # Same batch!
```

### Getting Batch Statistics

```python
stats = BatchManagementService.get_batch_statistics(batch_id=1)
print(f"Batch: {stats['batch_name']}")
print(f"Investors: {stats['investor_count']}")
print(f"Total Principal: ${stats['total_principal']:,.2f}")
print(f"Closes at: {stats['auto_close_at']}")
```

### Manual Batch Closure (Admin)

```python
batch = Batch.query.get(batch_id)
BatchManagementService.close_batch(batch, reason="Manual admin request")
```

### Checking Scheduler Status

```python
status = BatchSchedulerService.get_scheduler_status()
print(status)
# Output:
# {
#   'status': 'running',
#   'batch_closure_job': {
#     'id': 'batch_closure_task',
#     'name': 'Process batch closures at Thursday 9 AM EAT',
#     'trigger': 'cron[day_of_week="3", hour="6", minute="0", timezone="UTC"]',
#     'next_run_time': '2026-04-23T06:00:00+00:00'
#   }
# }
```

## Testing

### Test Next Thursday Calculation

```python
from datetime import date
from app.logic.batch_management_service import BatchManagementService

# On Monday, should return next Thursday
thursday = BatchManagementService._next_thursday_morning_eat()
assert thursday.weekday() == 3  # Thursday
assert thursday.hour == 9
```

### Test Batch Creation

```python
# First call creates batch
batch1 = BatchManagementService.find_or_create_batch(share_class_id=1)

# Second call returns same batch
batch2 = BatchManagementService.find_or_create_batch(share_class_id=1)

assert batch1.id == batch2.id
```

### Test Investor Assignment

```python
investment, batch = BatchManagementService.create_and_assign_investor_to_batch(
    investment=inv, share_class_id=1
)

assert investment.batch_id == batch.id
assert investment.share_class_id == batch.share_class_id
```

## Error Handling

### Share Class Mismatch

```python
# Will raise ValueError
try:
    investment.share_class_id = 1  # KES
    batch = Batch with share_class_id=2  # USD
    BatchManagementService.add_investor_to_batch(investment, batch)
except ValueError as e:
    print(e)
    # ValueError: Investment share class 1 does not match batch share class 2
```

### Missing Share Class

```python
try:
    batch = BatchManagementService.find_or_create_batch(share_class_id=999)
except ValueError as e:
    print(e)
    # ValueError: Share class 999 not found
```

## Logging

Enable debug logging to see batch operations:

```python
import logging
logging.getLogger('app.logic.batch_management_service').setLevel(logging.DEBUG)
logging.getLogger('app.logic.batch_scheduler_service').setLevel(logging.DEBUG)
```

Sample logs:

```
[batch_management_service] Found existing open batch: AXIOM_CI-KES_2026-04-18 (ID: 5)
[batch_management_service] Created new batch: AXIOM_CI-USD_2026-04-18 (ID: 6)
[batch_management_service] Added investor JOYK001 to batch AXIOM_CI-KES_2026-04-18 (ID: 5)
[batch_scheduler_service] Starting batch closure processing task...
[batch_management_service] Closed batch AXIOM_CI-KES_2026-04-10: Auto-closed at Thursday 9 AM EAT
[batch_management_service] Deleted empty batch AXIOM_CI-KES_2026-04-17 (ID: 3)
[batch_scheduler_service] Batch closure task completed: closed=2, deleted=1, errors=0
```

## Future Enhancements

1. **Excel Export:** Generate and export batch statements before closure
2. **Email Notifications:** Send batch closure notifications to investors
3. **Deployment Hooks:** Auto-detect when batch is deployed and set deployment date/NAV
4. **Performance Dashboard:** Real-time batch and scheduler monitoring
5. **Backfill Utility:** Migrate legacy batches to new auto-batch system
6. **Timezone Configuration:** Admin UI for changing closure time/day

## Files Overview

| File | Purpose |
|------|---------|
| `app/logic/batch_management_service.py` | Core batch management logic |
| `app/logic/batch_scheduler_service.py` | APScheduler integration for auto-closure |
| `examples/batch_management_integration.py` | Integration examples and tests |
| `NAV_VALUATION_MIGRATION.md` | Related NAV valuation documentation |

## Support

For questions about:

- **Batch creation logic:** See `find_or_create_batch()` in `batch_management_service.py`
- **Scheduling:** See `BatchSchedulerService` in `batch_scheduler_service.py`
- **Timezone handling:** See `_next_thursday_morning_eat()` in `batch_management_service.py`
- **Integration:** See `examples/batch_management_integration.py`
