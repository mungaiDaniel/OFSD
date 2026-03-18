-- SQL Debug Script to check investment data
-- Run this in your PostgreSQL client to verify data integrity

-- 1. Check all core funds
SELECT id, fund_name, is_active FROM core_funds ORDER BY id;

-- 2. Check Axiom's test investments
SELECT 
    id,
    internal_client_code,
    amount_deposited,
    date_deposited,
    date_transferred,
    fund_id,
    fund_name,
    batch_id
FROM investments 
WHERE fund_name ILIKE 'Axiom' OR fund_id = 1
ORDER BY date_deposited;

-- 3. Check for any withdrawals that might zero out weighted capital
SELECT 
    id,
    internal_client_code,
    fund_id,
    amount,
    date_withdrawn,
    status
FROM withdrawals 
WHERE (fund_id = 1 OR fund_name ILIKE 'Axiom')
    AND status = 'Approved'
ORDER BY date_withdrawn;

-- 4. Check batch information for the test batch
SELECT id, batch_name, certificate_number FROM batches WHERE id = 1;

-- 5. Verify date ranges: investments created between March 18-19
SELECT 
    id,
    internal_client_code,
    date_deposited::date,
    DATE_PART('year', date_deposited) as year,
    DATE_PART('month', date_deposited) as month,
    DATE_PART('day', date_deposited) as day
FROM investments 
WHERE date_deposited >= '2026-03-17' AND date_deposited <= '2026-03-20'
ORDER BY date_deposited;
