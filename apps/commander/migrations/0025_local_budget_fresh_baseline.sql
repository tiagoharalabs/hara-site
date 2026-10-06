PRAGMA foreign_keys = ON;

-- D1 baseline for tenants that start the billing period entirely on the
-- local-budget architecture. This lets fresh Free tenants avoid a legacy
-- Durable Object read while preserving a conservative fallback for old/mixed
-- tenants.
CREATE TABLE IF NOT EXISTS commander_tenant_budget_baselines (
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  period_key TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  legacy_consumed_units INTEGER NOT NULL DEFAULT 0
    CHECK (legacy_consumed_units >= 0),
  source TEXT NOT NULL
    CHECK (source IN ('FRESH_TENANT_ZERO','TENANT_QUOTA_SNAPSHOT')),
  state TEXT NOT NULL
    CHECK (state IN ('ACTIVE','INVALIDATED')),
  established_at_utc TEXT NOT NULL,
  invalidated_at_utc TEXT,
  invalidation_reason TEXT,
  PRIMARY KEY (tenant_id, period_key, meter_id)
);

CREATE INDEX IF NOT EXISTS idx_tenant_budget_baseline_state
  ON commander_tenant_budget_baselines(period_key, state, tenant_id);
