-- 0036: Revoked-device HISTORY is an independent user-facing projection.
-- Deleting rows from this table really removes portal history entries.
-- Canonical commander_devices tombstones, calls, usage and receipts remain intact.
CREATE TABLE IF NOT EXISTS commander_device_history (
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  device_id TEXT NOT NULL REFERENCES commander_devices(device_id) ON DELETE CASCADE,
  revoked_at_utc TEXT NOT NULL,
  PRIMARY KEY (tenant_id,device_id)
);
CREATE INDEX IF NOT EXISTS idx_commander_device_history_tenant_revoked
  ON commander_device_history(tenant_id,revoked_at_utc DESC);

-- One-time migration backfills prior revocations; NEVER auto-backfill on reads
-- or later deployments, otherwise a cleared history would reappear.
INSERT OR IGNORE INTO commander_device_history (tenant_id,device_id,revoked_at_utc)
SELECT tenant_id,device_id,COALESCE(revoked_at_utc,created_at_utc)
  FROM commander_devices
 WHERE state='REVOKED';

CREATE TABLE IF NOT EXISTS commander_device_history_clears (
  clearance_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  actor_subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  deleted_count INTEGER NOT NULL CHECK (deleted_count > 0),
  cleared_at_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_commander_device_history_clears_tenant_time
  ON commander_device_history_clears(tenant_id,cleared_at_utc DESC);
