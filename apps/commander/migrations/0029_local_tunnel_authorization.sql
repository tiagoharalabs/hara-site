ALTER TABLE commander_devices ADD COLUMN local_authorized_until_utc TEXT;

CREATE TABLE IF NOT EXISTS commander_device_authorization_codes (
  authorization_id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING','CONSUMED','SUPERSEDED','EXPIRED')),
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  consumed_at_utc TEXT,
  superseded_at_utc TEXT,
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id)
);

CREATE INDEX IF NOT EXISTS idx_device_auth_codes_device_state
  ON commander_device_authorization_codes(device_id, state, expires_at_utc);
CREATE INDEX IF NOT EXISTS idx_device_auth_codes_tenant_subject
  ON commander_device_authorization_codes(tenant_id, subject_id, created_at_utc);

CREATE TABLE IF NOT EXISTS commander_device_usage_totals (
  device_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  lifetime_units INTEGER NOT NULL DEFAULT 0,
  updated_at_utc TEXT NOT NULL,
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id)
);

CREATE TABLE IF NOT EXISTS commander_device_usage_daily (
  device_id TEXT NOT NULL,
  day_key TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  units INTEGER NOT NULL DEFAULT 0,
  updated_at_utc TEXT NOT NULL,
  PRIMARY KEY (device_id, day_key),
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id)
);

CREATE INDEX IF NOT EXISTS idx_device_usage_daily_subject_day
  ON commander_device_usage_daily(tenant_id, subject_id, day_key);

ALTER TABLE commander_devices ADD COLUMN last_metering_sync_at_utc TEXT;
ALTER TABLE commander_devices ADD COLUMN last_local_mcp_started_at_utc TEXT;
ALTER TABLE commander_devices ADD COLUMN last_local_mcp_stopped_at_utc TEXT;

CREATE TABLE IF NOT EXISTS commander_device_metering_events (
  event_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('MCP_START','MCP_STOP')),
  event_at_utc TEXT NOT NULL,
  session_started_at_utc TEXT NOT NULL,
  session_duration_seconds INTEGER,
  local_lifetime_units INTEGER NOT NULL DEFAULT 0,
  agent_version TEXT,
  transport_mode TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE(device_id, session_id, event_type),
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id)
);

CREATE INDEX IF NOT EXISTS idx_device_metering_events_device_time
  ON commander_device_metering_events(device_id, event_at_utc);
CREATE INDEX IF NOT EXISTS idx_device_metering_events_tenant_time
  ON commander_device_metering_events(tenant_id, event_at_utc);
