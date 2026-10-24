PRAGMA foreign_keys = ON;

-- Reconcile the commercial Standard/Pro Beta catalog state that is already
-- active in PROD. Pricing remains runtime-only (Stripe); this migration only
-- makes the plan/grant catalog reproducible from Git.
INSERT OR IGNORE INTO plans
  (plan_code, display_name, meter_id, period_kind, unit_limit, state)
VALUES
  ('STANDARD', 'Pro Beta', 'HARA_COMMANDER_GOVERNED_INVOKE', 'NONE', NULL, 'ACTIVE');

INSERT OR IGNORE INTO plan_grants (plan_code, grant_code, created_at_utc)
VALUES
  ('STANDARD', 'COMMANDER_DISCOVERY', '2026-10-05T00:00:00Z'),
  ('STANDARD', 'COMMANDER_READ_ONLY_INVOKE', '2026-10-05T00:00:00Z'),
  ('STANDARD', 'COMMANDER_RECEIPT_READ', '2026-10-05T00:00:00Z'),
  ('STANDARD', 'COMMANDER_MUTATION_INVOKE', '2026-10-05T00:00:00Z'),
  ('STANDARD', 'COMMANDER_PROCESS_EXECUTION', '2026-10-05T00:00:00Z');
