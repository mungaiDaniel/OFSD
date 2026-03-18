-- ============================================================================
-- SQL Migration: Add fund_id column to withdrawals table
-- Date: March 17, 2026
-- ============================================================================
-- This file documents the exact SQL statements executed by the migration script.
-- You can use this as a reference or to manually run the migration if needed.
-- ============================================================================

-- Step 1: Add fund_id column (if it doesn't already exist)
-- This allows NULL values initially so existing rows don't break
ALTER TABLE withdrawals
ADD COLUMN IF NOT EXISTS fund_id INTEGER;

-- Step 2: Set default values for existing rows
-- Assumes fund_id = 1 is 'Axiom' (the default fund)
-- IMPORTANT: Verify that CoreFund with id=1 exists before running!
UPDATE withdrawals
SET fund_id = 1
WHERE fund_id IS NULL;

-- Step 3: Add NOT NULL constraint
-- After existing rows have fund_id values, enforce the constraint
ALTER TABLE withdrawals
ALTER COLUMN fund_id SET NOT NULL;

-- Step 4: Add foreign key constraint
-- This ensures all fund_id values reference valid CoreFund records
-- If constraint already exists, this will fail gracefully (caught in Python script)
ALTER TABLE withdrawals
ADD CONSTRAINT fk_withdrawals_core_funds
FOREIGN KEY (fund_id) REFERENCES core_funds(id)
ON DELETE RESTRICT
ON UPDATE CASCADE;

-- Step 5: Create/ensure composite index for performance
-- This index improves queries filtering by code, fund, and date
CREATE INDEX IF NOT EXISTS ix_withdrawals_code_fund_date
ON withdrawals (internal_client_code, fund_id, date_withdrawn);

-- ============================================================================
-- Verification Queries (run these to verify the migration)
-- ============================================================================

-- Check 1: Verify fund_id column exists and is NOT NULL
SELECT 
  column_name, 
  data_type, 
  is_nullable
FROM information_schema.columns
WHERE table_name = 'withdrawals' AND column_name = 'fund_id';

-- Expected output:
-- column_name | data_type | is_nullable
-- fund_id     | integer   | NO

-- Check 2: View all columns in withdrawals table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'withdrawals'
ORDER BY ordinal_position;

-- Check 3: Verify foreign key constraint
SELECT constraint_name, table_name, column_name
FROM information_schema.key_column_usage
WHERE table_name = 'withdrawals' AND column_name = 'fund_id';

-- Check 4: Verify index exists
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'withdrawals' AND indexname = 'ix_withdrawals_code_fund_date';

-- Check 5: Verify all withdrawals have valid fund_ids
SELECT COUNT(*) as total_withdrawals,
       COUNT(fund_id) as with_fund_id,
       COUNT(*) - COUNT(fund_id) as null_fund_ids
FROM withdrawals;

-- Check 6: Show withdrawal-fund relationships
SELECT w.id, w.internal_client_code, w.fund_id, cf.fund_name, w.amount, w.status
FROM withdrawals w
LEFT JOIN core_funds cf ON w.fund_id = cf.id
ORDER BY w.date_withdrawn DESC
LIMIT 10;

-- ============================================================================
-- Rollback (if needed - use with caution!)
-- ============================================================================

-- Option 1: Drop column (DESTRUCTIVE - loses all fund_id data)
-- ALTER TABLE withdrawals DROP COLUMN fund_id;

-- Option 2: Drop only the foreign key constraint
-- ALTER TABLE withdrawals DROP CONSTRAINT fk_withdrawals_core_funds;

-- Option 3: Drop the index
-- DROP INDEX IF EXISTS ix_withdrawals_code_fund_date;

-- Option 4: Complete rollback (removes everything)
-- BEGIN;
-- ALTER TABLE withdrawals DROP CONSTRAINT fk_withdrawals_core_funds;
-- DROP INDEX IF EXISTS ix_withdrawals_code_fund_date;
-- ALTER TABLE withdrawals DROP COLUMN fund_id;
-- COMMIT;

-- ============================================================================
-- Manual Migration Steps (if using the Python script fails)
-- ============================================================================

-- 1. Connect to your PostgreSQL database:
--    psql -U <username> -d ofds_db -h localhost

-- 2. Run each SQL statement in order (Step 1 through 5 above)

-- 3. Run verification queries (Check 1-6 above) to confirm

-- 4. If any step fails, note the error message and contact support

-- ============================================================================
