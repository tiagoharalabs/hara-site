PRAGMA defer_foreign_keys = ON;

-- SQLite/D1 cannot widen an existing CHECK constraint in-place. Rebuild the
-- device table and its two dependent FK tables atomically so V1 and Event V2
-- transport states can coexist without losing calls, selections or FK safety.

CREATE TABLE commander_devices_v2 (
  device_id TEXT PRIMARY KEY,
  pairing_id TEXT NOT NULL UNIQUE REFERENCES device_pairing_tokens(pairing_id),
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  enrolled_by_subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_name TEXT NOT NULL,
  platform TEXT NOT NULL CHECK (platform IN ('LINUX','WINDOWS')),
  architecture TEXT,
  agent_version TEXT,
  tunnel_mode TEXT NOT NULL DEFAULT 'OUTBOUND_RELAY'
    CHECK (tunnel_mode IN ('OUTBOUND_RELAY','EVENT_V2','EVENT_V2_OFFLINE')),
  credential_hash TEXT NOT NULL UNIQUE,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','REVOKED')),
  created_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT,
  revoked_at_utc TEXT
);

INSERT INTO commander_devices_v2 (
  device_id, pairing_id, tenant_id, enrolled_by_subject_id, device_name,
  platform, architecture, agent_version, tunnel_mode, credential_hash, state,
  created_at_utc, last_seen_at_utc, revoked_at_utc
)
SELECT
  device_id, pairing_id, tenant_id, enrolled_by_subject_id, device_name,
  platform, architecture, agent_version, tunnel_mode, credential_hash, state,
  created_at_utc, last_seen_at_utc, revoked_at_utc
FROM commander_devices;

CREATE TABLE commander_device_calls_v2 (
  call_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices_v2(device_id) ON DELETE CASCADE,
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

INSERT INTO commander_device_calls_v2 (
  call_id, request_id, tenant_id, subject_id, device_id, tool_id, payload_json,
  state, created_at_utc, expires_at_utc, claimed_at_utc, completed_at_utc,
  result_json, error_code
)
SELECT
  call_id, request_id, tenant_id, subject_id, device_id, tool_id, payload_json,
  state, created_at_utc, expires_at_utc, claimed_at_utc, completed_at_utc,
  result_json, error_code
FROM commander_device_calls;

CREATE TABLE commander_device_selections_v2 (
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices_v2(device_id) ON DELETE CASCADE,
  selected_at_utc TEXT NOT NULL,
  PRIMARY KEY (tenant_id, subject_id)
);

INSERT INTO commander_device_selections_v2 (
  tenant_id, subject_id, device_id, selected_at_utc
)
SELECT tenant_id, subject_id, device_id, selected_at_utc
FROM commander_device_selections;

-- Remove old dependents first. D1 documents that ON DELETE actions are still
-- active while defer_foreign_keys is enabled.
DROP TABLE commander_device_selections;
DROP TABLE commander_device_calls;
DROP TABLE commander_devices;

ALTER TABLE commander_devices_v2 RENAME TO commander_devices;
ALTER TABLE commander_device_calls_v2 RENAME TO commander_device_calls;
ALTER TABLE commander_device_selections_v2 RENAME TO commander_device_selections;

CREATE INDEX idx_commander_devices_tenant
  ON commander_devices(tenant_id, state);

CREATE INDEX idx_commander_devices_subject
  ON commander_devices(enrolled_by_subject_id, state);

CREATE INDEX idx_commander_devices_last_seen
  ON commander_devices(last_seen_at_utc);

CREATE INDEX idx_device_calls_poll
  ON commander_device_calls(device_id, state, created_at_utc);

CREATE INDEX idx_device_calls_tenant
  ON commander_device_calls(tenant_id, state, created_at_utc);

CREATE INDEX idx_device_calls_expiry
  ON commander_device_calls(state, expires_at_utc);

CREATE INDEX idx_device_selections_device
  ON commander_device_selections(device_id);

PRAGMA defer_foreign_keys = OFF;
