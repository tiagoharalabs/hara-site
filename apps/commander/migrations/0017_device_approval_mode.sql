ALTER TABLE commander_devices
ADD COLUMN approval_mode TEXT NOT NULL DEFAULT 'ASK_EVERY_ACTION';

CREATE INDEX IF NOT EXISTS idx_commander_devices_approval_mode
  ON commander_devices(tenant_id, approval_mode, state);
