PRAGMA foreign_keys = ON;

-- Owner-approved 2026-10-10 commercial adjustment.
-- The historical 0021 migration (Free=10000) remains immutable.
-- The new canonical Free/TRIAL allowance is 15,000 governed calls per
-- calendar month; paid Pro and other plan codes are never modified.
UPDATE plans
   SET unit_limit = 15000
 WHERE plan_code = 'TRIAL'
   AND display_name = 'Free'
   AND meter_id = 'HARA_COMMANDER_GOVERNED_INVOKE'
   AND period_kind = 'CALENDAR_MONTH'
   AND state = 'ACTIVE'
   AND unit_limit IN (10000, 15000);
