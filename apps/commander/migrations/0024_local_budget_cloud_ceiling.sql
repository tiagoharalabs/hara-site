PRAGMA foreign_keys = ON;

-- Harden the local-budget optimization after 0023 was already applied in DEV.
-- The customer device keeps fast local accounting, while the already-required
-- cloud call INSERT remains the hard commercial ceiling for each block.

ALTER TABLE commander_device_calls
  ADD COLUMN usage_budget_id TEXT;

ALTER TABLE commander_device_budget_blocks
  ADD COLUMN units_issued INTEGER NOT NULL DEFAULT 0
  CHECK (units_issued >= 0 AND units_issued <= units_allocated);

CREATE TRIGGER IF NOT EXISTS trg_device_call_local_budget_validate
BEFORE INSERT ON commander_device_calls
WHEN NEW.usage_mode = 'LOCAL_BUDGET'
BEGIN
  SELECT CASE
    WHEN NEW.usage_budget_id IS NULL
      OR NEW.usage_units <= 0
      OR NEW.usage_period_key IS NULL
      OR NOT EXISTS (
        SELECT 1
          FROM commander_device_budget_blocks b
         WHERE b.budget_id = NEW.usage_budget_id
           AND b.tenant_id = NEW.tenant_id
           AND b.device_id = NEW.device_id
           AND b.period_key = NEW.usage_period_key
           AND b.state = 'ACTIVE'
           AND b.expires_at_utc > NEW.created_at_utc
           AND b.units_issued + NEW.usage_units <= b.units_allocated
      )
    THEN RAISE(ABORT, 'LOCAL_BUDGET_CAPACITY_EXHAUSTED')
  END;
END;

CREATE TRIGGER IF NOT EXISTS trg_device_call_local_budget_issue
AFTER INSERT ON commander_device_calls
WHEN NEW.usage_mode = 'LOCAL_BUDGET'
BEGIN
  UPDATE commander_device_budget_blocks
     SET units_issued = units_issued + NEW.usage_units
   WHERE budget_id = NEW.usage_budget_id
     AND tenant_id = NEW.tenant_id
     AND device_id = NEW.device_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_device_call_local_budget_release
AFTER UPDATE OF state ON commander_device_calls
WHEN OLD.usage_mode = 'LOCAL_BUDGET'
 AND OLD.state IN ('PENDING','EXECUTING')
 AND NEW.state IN ('FAILED','CANCELLED','EXPIRED')
BEGIN
  UPDATE commander_device_budget_blocks
     SET units_issued = MAX(units_issued - OLD.usage_units, 0)
   WHERE budget_id = OLD.usage_budget_id
     AND tenant_id = OLD.tenant_id
     AND device_id = OLD.device_id;
END;
