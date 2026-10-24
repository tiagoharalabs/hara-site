-- Local-tunnel Agent lifecycle telemetry, aggregated only.
-- Keeps 0029's MCP_START/MCP_STOP history and migration hash untouched.
CREATE TABLE IF NOT EXISTS commander_device_agent_telemetry (
  event_id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  session_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN ('AGENT_START','AGENT_HEARTBEAT','AGENT_STOP')),
  event_at_utc TEXT NOT NULL,
  received_at_utc TEXT NOT NULL,
  session_duration_seconds INTEGER NOT NULL DEFAULT 0,
  local_lifetime_units INTEGER NOT NULL DEFAULT 0,
  agent_version TEXT,
  transport_mode TEXT NOT NULL CHECK (transport_mode = 'LOCAL_TUNNEL'),
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id)
);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_tenant_received
  ON commander_device_agent_telemetry(tenant_id, received_at_utc, event_id);
CREATE INDEX IF NOT EXISTS idx_agent_telemetry_device_received
  ON commander_device_agent_telemetry(device_id, received_at_utc, event_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_telemetry_one_start_stop_per_session
  ON commander_device_agent_telemetry(device_id, session_id, event_type)
  WHERE event_type IN ('AGENT_START','AGENT_STOP');
