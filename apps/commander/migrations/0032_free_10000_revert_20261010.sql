PRAGMA foreign_keys = ON;

-- Owner revised the commercial Free allowance from 15,000 back to
-- 10,000 governed invocations per calendar month on 2026-10-10.
-- 0031 stays immutable because it has already been applied in D1 PROD/DEV.
-- Run once in both D1 environments; repeated use is idempotent.
UPDATE plans
   SET unit_limit = 10000
 WHERE plan_code = 'TRIAL'
   AND display_name = 'Free'
   AND meter_id = 'HARA_COMMANDER_GOVERNED_INVOKE'
   AND period_kind = 'CALENDAR_MONTH'
   AND state = 'ACTIVE'
   AND unit_limit IN (15000, 10000);
