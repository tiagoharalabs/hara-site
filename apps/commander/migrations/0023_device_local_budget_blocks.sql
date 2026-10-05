PRAGMA foreign_keys = ON;

-- Local-budget optimization for metered plans.
-- Cloud remains authoritative for the monthly allocation. The device consumes
-- one bounded block locally and reconciles before another block is issued.

ALTER TABLE commander_device_calls
  ADD COLUMN usage_mode TEXT NOT NULL DEFAULT 'CLOUD_QUOTA';

ALTER TABLE commander_device_calls
  ADD COLUMN usage_units INTEGER NOT NULL DEFAULT 0;

ALTER TABLE commander_device_calls
  ADD COLUMN usage_period_key TEXT;

ALTER TABLE commander_device_calls
  ADD COLUMN usage_budget_id TEXT;

CREATE TABLE IF NOT EXISTS commander_device_budget_blocks (
  budget_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  entitlement_id TEXT NOT NULL REFERENCES entitlements(entitlement_id) ON DELETE CASCADE,
  plan_code TEXT NOT NULL REFERENCES plans(plan_code),
  meter_id TEXT NOT NULL,
  period_key TEXT NOT NULL,
  allocation_sequence INTEGER NOT NULL,
  units_allocated INTEGER NOT NULL CHECK (units_allocated > 0),
  units_issued INTEGER NOT NULL DEFAULT 0 CHECK (units_issued >= 0),
  units_reported INTEGER NOT NULL DEFAULT 0 CHECK (units_reported >= 0),
  lease_token_hash TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','EXHAUSTED','REVOKED','EXPIRED')),
  issued_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  last_reported_at_utc TEXT,
  CHECK (units_issued <= units_allocated),
  CHECK (units_reported <= units_allocated)
);

CREATE INDEX IF NOT EXISTS idx_device_budget_tenant_period
  ON commander_device_budget_blocks(tenant_id, period_key, issued_at_utc);

CREATE INDEX IF NOT EXISTS idx_device_budget_device_period
  ON commander_device_budget_blocks(device_id, period_key, state, issued_at_utc);

CREATE UNIQUE INDEX IF NOT EXISTS idx_device_budget_tenant_period_sequence
  ON commander_device_budget_blocks(tenant_id, period_key, allocation_sequence);

CREATE UNIQUE INDEX IF NOT EXISTS idx_device_budget_one_active
  ON commander_device_budget_blocks(device_id, period_key)
  WHERE state = 'ACTIVE';


-- LOCAL_BUDGET cloud ceiling. Every local-budget call consumes a cloud slot
-- in the same D1 transaction as the already-required call insert.
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

-- Failed/cancelled/expired calls do not consume monthly quota. Release the
-- cloud slot exactly on the active -> non-chargeable terminal transition.
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
