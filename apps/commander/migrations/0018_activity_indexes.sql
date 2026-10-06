CREATE INDEX IF NOT EXISTS idx_device_calls_activity_tenant_created
  ON commander_device_calls(tenant_id, created_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_device_calls_activity_subject_created
  ON commander_device_calls(tenant_id, subject_id, created_at_utc DESC);
