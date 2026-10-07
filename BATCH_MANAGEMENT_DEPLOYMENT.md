# Batch Management System - Deployment Checklist

## Pre-Deployment Requirements

- [ ] Python 3.8+ 
- [ ] Flask application running
- [ ] PostgreSQL or compatible database
- [ ] APScheduler library installed

## Installation Steps

### 1. Install Dependencies

```bash
pip install apscheduler>=3.10.0
```

Update `requirements.txt`:
```
apscheduler>=3.10.0
```

### 2. Create Service Files

- [ ] Copy `app/logic/batch_management_service.py` to backend
- [ ] Copy `app/logic/batch_scheduler_service.py` to backend
- [ ] Review and understand both files

### 3. Database Updates

Verify `Batch` model has required columns:
- [ ] `share_class_id` (Integer, FK to share_classes.id)
- [ ] `is_open` (Boolean, default True)
- [ ] `auto_close_at` (DateTime with timezone)
- [ ] `exported_at` (DateTime with timezone, nullable)
- [ ] `total_shares` (Numeric(20,6), nullable)
- [ ] `deployment_nav` (Numeric(20,6), nullable)
- [ ] `deployment_date_actual` (Date, nullable)

If columns missing, run migration (see NAV_VALUATION_MIGRATION.md):
```bash
flask db upgrade
```

### 4. Update Flask App Initialization

In `app/__init__.py` or `create_app()`:

```python
from app.logic.batch_scheduler_service import BatchSchedulerService

def create_app():
    app = Flask(__name__)
    
    # ... other initializations ...
    
    # Initialize batch scheduler
    logger.info("Initializing batch scheduler...")
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            BatchSchedulerService.init_scheduler(app)
            logger.info("✓ Batch scheduler initialized")
        except ImportError as e:
            logger.warning(f"APScheduler not installed, batch auto-closure disabled: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to initialize batch scheduler: {str(e)}")
            # Don't fail app startup
    
    # Register shutdown handler
    @app.teardown_appcontext
    def shutdown_scheduler(exception=None):
        BatchSchedulerService.shutdown_scheduler()
    
    return app
```

### 5. Update Investors Route

In your POST /api/v1/investors handler:

```python
from app.logic.batch_management_service import BatchManagementService

@investors_bp.route('/api/v1/investors', methods=['POST'])
@jwt_required()
def create_investor():
    """Create a new investor and assign to batch."""
    data = request.get_json()
    
    try:
        # Validate required fields
        if not data.get('share_class_id'):
            return {"error": "share_class_id is required"}, 400
        
        # Create investment record
        investment = Investment(
            investor_name=data['investor_name'],
            investor_email=data['investor_email'],
            investor_phone=data.get('investor_phone'),
            internal_client_code=data['internal_client_code'],
            amount_deposited=Decimal(str(data['amount_deposited'])),
            fund_id=data.get('fund_id'),
            share_class_id=data['share_class_id'],
            deposit_date=parse_date(data.get('deposit_date')),
            wealth_manager=data.get('wealth_manager'),
            IFA=data.get('IFA'),
        )
        
        # Use batch management to auto-assign
        investment, batch = BatchManagementService.create_and_assign_investor_to_batch(
            investment=investment,
            share_class_id=data['share_class_id'],
        )
        
        return {
            "investor_id": investment.id,
            "batch_id": batch.id,
            "batch_name": batch.batch_name,
            "auto_close_at": batch.auto_close_at.isoformat(),
            "message": "Investor created and assigned to batch",
        }, 201
        
    except ValueError as e:
        logger.warning(f"Investor creation validation error: {str(e)}")
        return {"error": str(e)}, 400
    except Exception as e:
        logger.error(f"Error creating investor: {str(e)}", exc_info=True)
        return {"error": "Internal server error"}, 500
```

### 6. Add Admin Endpoints (Optional)

For monitoring and manual operations:

```python
@admin_bp.route('/batch-scheduler/status', methods=['GET'])
@jwt_required()
@require_admin
def get_batch_scheduler_status():
    """Get current batch scheduler status and next run time."""
    status = BatchSchedulerService.get_scheduler_status()
    return status, 200

@admin_bp.route('/batch-scheduler/trigger-closures', methods=['POST'])
@jwt_required()
@require_admin
def trigger_batch_closures_manual():
    """Manually trigger batch closure processing (for testing)."""
    stats = BatchSchedulerService.trigger_batch_closures_manually()
    return stats, 200
```

### 7. Configure Logging

In logging configuration:

```python
logging.getLogger('app.logic.batch_management_service').setLevel(logging.INFO)
logging.getLogger('app.logic.batch_scheduler_service').setLevel(logging.INFO)
```

## Testing

### Unit Tests

Run test suite:
```bash
pytest tests/test_batch_management.py -v
```

### Manual Testing

1. **Create investor in new batch:**
   ```bash
   POST /api/v1/investors
   {
     "investor_name": "Test User",
     "investor_email": "test@example.com",
     "internal_client_code": "TEST001",
     "amount_deposited": "100000.00",
     "share_class_id": 1
   }
   ```
   
   Expected response:
   ```json
   {
     "investor_id": 1,
     "batch_id": 1,
     "batch_name": "AXIOM_CI-KES_2026-04-18",
     "auto_close_at": "2026-04-18T06:00:00+00:00",
     "message": "Investor created and assigned to batch"
   }
   ```

2. **Create investor in existing batch:**
   ```bash
   POST /api/v1/investors (same day, same share class)
   ```
   
   Expected: Same batch_id returned

3. **Check scheduler status:**
   ```bash
   GET /api/v1/admin/batch-scheduler/status
   ```
   
   Expected response:
   ```json
   {
     "status": "running",
     "batch_closure_job": {
       "id": "batch_closure_task",
       "name": "Process batch closures at Thursday 9 AM EAT",
       "trigger": "cron[day_of_week=\"3\", hour=\"6\", minute=\"0\", timezone=\"UTC\"]",
       "next_run_time": "2026-04-23T06:00:00+00:00"
     }
   }
   ```

4. **Manually trigger closure (testing):**
   ```bash
   POST /api/v1/admin/batch-scheduler/trigger-closures
   ```
   
   Expected response:
   ```json
   {
     "total": 0,
     "deleted": 0,
     "closed": 0,
     "errors": []
   }
   ```

## Verification Checklist

After deployment:

- [ ] Batch names follow convention `{fund_code}_{class_code}_{date}`
- [ ] auto_close_at set to next Thursday (Thursday 9 AM EAT)
- [ ] Multiple investors same day/class use same batch
- [ ] Investors different classes get different batches
- [ ] Scheduler initialized without errors in app logs
- [ ] APScheduler job visible with `get_scheduler_status()`
- [ ] Test manual closure trigger works
- [ ] Admin endpoints respond correctly

## Monitoring

### Check Batch Assignments

```sql
SELECT 
  b.batch_name,
  b.share_class_id,
  b.is_open,
  b.auto_close_at,
  COUNT(i.id) as investor_count
FROM batches b
LEFT JOIN investments i ON b.id = i.batch_id
GROUP BY b.id
ORDER BY b.created_at DESC;
```

### Check Scheduler Logs

```bash
# Enable debug logging
export FLASK_LOG_LEVEL=DEBUG

# Check logs for scheduler initialization
tail -f app.log | grep -i "batch_scheduler"
```

### Verify Next Scheduled Run

```python
from app.logic.batch_scheduler_service import BatchSchedulerService
status = BatchSchedulerService.get_scheduler_status()
print(status)
```

## Troubleshooting

### "APScheduler not installed"

**Fix:** Install dependency
```bash
pip install apscheduler>=3.10.0
```

### Scheduler not running

**Symptoms:** 
- `batch_closure_task` not in jobs list
- next_run_time is None

**Fix:**
- Check Flask app initialization (see step 4)
- Verify scheduler shutdown handler registered
- Check app logs for errors

### Batches not auto-closing

**Symptoms:**
- Batches still open after Thursday 9 AM EAT
- is_open still True

**Check:**
1. Scheduler status: `GET /api/v1/admin/batch-scheduler/status`
2. Current time vs auto_close_at in database
3. Manual trigger: `POST /api/v1/admin/batch-scheduler/trigger-closures`

### Share class mismatch error

**Error:** "Investment share class X does not match batch share class Y"

**Cause:** Investor assigned share_class_id that doesn't match batch

**Fix:** Check POST data includes matching share_class_id

## Rollback Procedure

If issues occur:

1. **Disable scheduler:**
   ```python
   BatchSchedulerService.shutdown_scheduler()
   ```

2. **Remove from app initialization** (see step 4)

3. **Revert investors route** to manual batch assignment

4. **Keep database changes** (share_class_id columns won't hurt)

## Performance Notes

- Scheduler runs at specific time (Thursday 6 AM UTC)
- Handles batches ready for closure in single task
- No continuous polling (efficient)
- Multiple app instances: scheduler uses locking (safe)

## Environment Variables

Optional configuration:

```bash
# Adjust logging level
WERKZEUG_LOG_LEVEL=DEBUG

# Flask debug mode (avoid in production)
FLASK_ENV=development
```

## Success Indicators

✅ Investors auto-assigned to batches based on share class  
✅ Batch names follow naming convention  
✅ auto_close_at set correctly (next Thursday 9 AM EAT)  
✅ Scheduler runs at correct time each Thursday  
✅ Empty batches deleted, non-empty batches closed  
✅ Admin endpoints report correct status  

## Support

For issues:
1. Check logs: `grep "batch_management" app.log`
2. Test manually: `/api/v1/admin/batch-scheduler/trigger-closures`
3. Review examples: `examples/batch_management_integration.py`
4. See documentation: `BATCH_MANAGEMENT_SYSTEM.md`
