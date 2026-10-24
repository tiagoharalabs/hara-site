PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO plans
  (plan_code, display_name, meter_id, period_kind, unit_limit, state)
VALUES
  ('FOUNDER_INTERNAL', 'H.A.R.A. Labs Founder/Internal', 'HARA_COMMANDER_GOVERNED_INVOKE', 'NONE', NULL, 'ACTIVE');

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
VALUES
  ('FOUNDER_INTERNAL', 'COMMANDER_DISCOVERY', '2026-09-29T00:00:00Z'),
  ('FOUNDER_INTERNAL', 'COMMANDER_READ_ONLY_INVOKE', '2026-09-29T00:00:00Z'),
  ('FOUNDER_INTERNAL', 'COMMANDER_RECEIPT_READ', '2026-09-29T00:00:00Z');
