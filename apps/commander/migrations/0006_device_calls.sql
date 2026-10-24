PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS commander_device_calls (
  call_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  tool_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (
    state IN ('PENDING','EXECUTING','COMPLETED','FAILED','CANCELLED','EXPIRED')
  ),
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  claimed_at_utc TEXT,
  completed_at_utc TEXT,
  result_json TEXT,
  error_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_calls_poll
  ON commander_device_calls(device_id, state, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_device_calls_tenant
  ON commander_device_calls(tenant_id, state, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_device_calls_expiry
  ON commander_device_calls(state, expires_at_utc);
