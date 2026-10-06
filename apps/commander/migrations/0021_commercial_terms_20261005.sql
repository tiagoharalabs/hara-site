PRAGMA foreign_keys = ON;

-- Commercial terms approved by the product owner on 2026-10-05.
-- Keep stable internal plan codes so existing entitlements/billing mappings remain valid.
INSERT INTO plans
  (plan_code, display_name, meter_id, period_kind, unit_limit, state)
VALUES
  ('TRIAL', 'Free', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 10000, 'ACTIVE')
ON CONFLICT(plan_code) DO UPDATE SET
  display_name = excluded.display_name,
  meter_id = excluded.meter_id,
  period_kind = excluded.period_kind,
  unit_limit = excluded.unit_limit,
  state = excluded.state;

INSERT INTO plans
  (plan_code, display_name, meter_id, period_kind, unit_limit, state)
VALUES
  ('STANDARD', 'Pro', 'HARA_COMMANDER_GOVERNED_INVOKE', 'NONE', NULL, 'ACTIVE')
ON CONFLICT(plan_code) DO UPDATE SET
  display_name = excluded.display_name,
  meter_id = excluded.meter_id,
  period_kind = excluded.period_kind,
  unit_limit = excluded.unit_limit,
  state = excluded.state;
