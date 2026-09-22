PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS device_pairing_tokens (
  pairing_id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  consumed_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_pairing_subject
  ON device_pairing_tokens(subject_id, expires_at_utc);

CREATE TABLE IF NOT EXISTS commander_devices (
  device_id TEXT PRIMARY KEY,
  pairing_id TEXT NOT NULL UNIQUE REFERENCES device_pairing_tokens(pairing_id),
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  enrolled_by_subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_name TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('LINUX','WINDOWS')),
  architecture TEXT,
  agent_version TEXT,
  tunnel_mode TEXT NOT NULL DEFAULT 'OUTBOUND_RELAY' CHECK (tunnel_mode IN ('OUTBOUND_RELAY')),
  credential_hash TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','REVOKED')),
  created_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT,
  revoked_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_commander_devices_tenant
  ON commander_devices(tenant_id, state);

CREATE INDEX IF NOT EXISTS idx_commander_devices_subject
  ON commander_devices(enrolled_by_subject_id, state);

CREATE INDEX IF NOT EXISTS idx_commander_devices_last_seen
  ON commander_devices(last_seen_at_utc);
