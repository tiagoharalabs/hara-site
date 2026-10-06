PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS commander_support_reports (
  support_report_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  subject_id TEXT NOT NULL REFERENCES users(subject_id),
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id),
  schema_version TEXT NOT NULL,
  platform TEXT NOT NULL,
  agent_version TEXT,
  captured_at_utc TEXT,
  submitted_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  slo_status TEXT,
  last_runtime_error_code TEXT,
  report_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commander_support_reports_tenant_time
  ON commander_support_reports(tenant_id, submitted_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_commander_support_reports_device_time
  ON commander_support_reports(device_id, submitted_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_commander_support_reports_expiry
  ON commander_support_reports(expires_at_utc);
