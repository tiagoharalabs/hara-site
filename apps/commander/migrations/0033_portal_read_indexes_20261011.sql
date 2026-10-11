-- Additive, compatible with prior Worker versions. No customer data changed.
-- Avoid scanning every tenant's lifetime usage on each dashboard read.
CREATE INDEX IF NOT EXISTS idx_device_usage_totals_subject_units
  ON commander_device_usage_totals(tenant_id, subject_id, lifetime_units);

-- Serve each tenant's device list in requested order without a temporary sort.
CREATE INDEX IF NOT EXISTS idx_commander_devices_tenant_created
  ON commander_devices(tenant_id, created_at_utc DESC);
