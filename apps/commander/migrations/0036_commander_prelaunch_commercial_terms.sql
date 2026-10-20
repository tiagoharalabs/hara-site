-- Additive successor to the already-applied Free/Pro catalog migrations.
-- One organization shares the same functional MCP allowance across its users.
-- Calendar-month quota is the sole paid reset until the billing-cycle decision
-- is explicitly approved; Stripe cancellation controls access, not a second reset.
ALTER TABLE plans ADD COLUMN active_device_limit INTEGER
  CHECK (active_device_limit IS NULL OR active_device_limit BETWEEN 1 AND 5);

UPDATE plans
   SET display_name = 'Avaliação',
       period_kind = 'LIFETIME',
       unit_limit = 5000,
       active_device_limit = 5
 WHERE plan_code = 'TRIAL'
   AND meter_id = 'HARA_COMMANDER_GOVERNED_INVOKE';

UPDATE plans
   SET display_name = 'HARA Commander',
       period_kind = 'CALENDAR_MONTH',
       unit_limit = 1000000,
       active_device_limit = 5
 WHERE plan_code = 'STANDARD'
   AND meter_id = 'HARA_COMMANDER_GOVERNED_INVOKE';
