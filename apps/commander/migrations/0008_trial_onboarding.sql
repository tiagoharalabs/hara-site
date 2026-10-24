PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO plans
  (plan_code, display_name, meter_id, period_kind, unit_limit, state)
VALUES
  ('TRIAL', 'Trial', 'HARA_COMMANDER_GOVERNED_INVOKE', 'CALENDAR_MONTH', 100, 'ACTIVE');

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
VALUES
  ('TRIAL', 'COMMANDER_DISCOVERY', '2026-09-23T00:00:00Z'),
  ('TRIAL', 'COMMANDER_READ_ONLY_INVOKE', '2026-09-23T00:00:00Z'),
  ('TRIAL', 'COMMANDER_RECEIPT_READ', '2026-09-23T00:00:00Z');
