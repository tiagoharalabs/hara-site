PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS commander_device_selections (
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  selected_at_utc TEXT NOT NULL,
  PRIMARY KEY (tenant_id, subject_id)
);

CREATE INDEX IF NOT EXISTS idx_device_selections_device
  ON commander_device_selections(device_id);
