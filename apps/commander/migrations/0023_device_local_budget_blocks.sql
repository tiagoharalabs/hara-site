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
  units_reported INTEGER NOT NULL DEFAULT 0 CHECK (units_reported >= 0),
  lease_token_hash TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','EXHAUSTED','REVOKED','EXPIRED')),
  issued_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  last_reported_at_utc TEXT,
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
