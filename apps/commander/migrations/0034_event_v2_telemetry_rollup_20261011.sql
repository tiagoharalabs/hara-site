-- Latest aggregate-only Event V2 telemetry snapshot per authenticated device.
-- Existing ~6h LIVENESS carries this payload; no extra HTTP requests.
-- No tool names, arguments, outputs, file paths or customer data.
CREATE TABLE IF NOT EXISTS commander_device_telemetry_snapshot (
  tenant_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  received_at_utc TEXT NOT NULL,
  window_days INTEGER NOT NULL CHECK(window_days = 7),
  connections INTEGER NOT NULL DEFAULT 0,
  disconnects INTEGER NOT NULL DEFAULT 0,
  reconnects INTEGER NOT NULL DEFAULT 0,
  session_errors INTEGER NOT NULL DEFAULT 0,
  durable_calls INTEGER NOT NULL DEFAULT 0,
  transient_calls INTEGER NOT NULL DEFAULT 0,
  transient_failures INTEGER NOT NULL DEFAULT 0,
  liveness_attempts INTEGER NOT NULL DEFAULT 0,
  transport_pings INTEGER NOT NULL DEFAULT 0,
  connected_seconds INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (tenant_id, device_id),
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id)
);
CREATE INDEX IF NOT EXISTS idx_commander_device_telemetry_tenant
  ON commander_device_telemetry_snapshot(tenant_id, received_at_utc DESC);
