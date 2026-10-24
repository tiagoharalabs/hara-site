-- H.A.R.A. Commander recovery alerts v1. SOURCE ONLY: deploy requires owner approval.
-- Tenant/device identity comes from the authenticated device credential.
CREATE TABLE commander_device_recovery_events (
  event_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  incident_id TEXT NOT NULL,
  generation INTEGER NOT NULL CHECK (generation >= 1),
  sequence INTEGER NOT NULL CHECK (sequence >= 1),
  event_state TEXT NOT NULL CHECK (event_state IN ('STALLED','RECOVERING','RECOVERED','DEGRADED')),
  origin TEXT NOT NULL CHECK (origin IN ('AGENT','SERVER')),
  client_event_id TEXT,
  worker TEXT CHECK (worker IS NULL OR worker IN ('heartbeat','executor')),
  detector TEXT CHECK (detector IS NULL OR detector IN ('LINUX_PROCESS_GUARDIAN','WINDOWS_JOB_GUARDIAN')),
  error_code TEXT,
  event_at_utc TEXT NOT NULL,
  heartbeat_anchor_at_utc TEXT,
  payload_sha256 TEXT NOT NULL,
  persisted_at_utc TEXT NOT NULL,
  portal_ack_at_utc TEXT,
  portal_ack_subject_id TEXT,
  UNIQUE (tenant_id,device_id,incident_id,generation,sequence),
  FOREIGN KEY (device_id) REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX idx_recovery_event_client_identity
  ON commander_device_recovery_events(tenant_id,device_id,client_event_id)
  WHERE client_event_id IS NOT NULL;
CREATE INDEX idx_recovery_events_tenant_time
  ON commander_device_recovery_events(tenant_id,persisted_at_utc DESC,event_id);
CREATE INDEX idx_recovery_events_device_incident
  ON commander_device_recovery_events(device_id,incident_id,generation,sequence);
CREATE INDEX idx_recovery_events_server_anchor
  ON commander_device_recovery_events(device_id,heartbeat_anchor_at_utc)
  WHERE origin='SERVER' AND event_state='DEGRADED';
CREATE INDEX idx_recovery_watch_devices
  ON commander_devices(state,approval_mode,tunnel_mode,last_seen_at_utc);
