-- Approval profile is captured at enqueue; result metadata contains no customer content.
ALTER TABLE commander_device_calls ADD COLUMN approval_timeout_seconds INTEGER NOT NULL DEFAULT 0 CHECK (approval_timeout_seconds IN (0,900));
ALTER TABLE commander_device_calls ADD COLUMN execution_budget_ms INTEGER NOT NULL DEFAULT 0 CHECK (execution_budget_ms BETWEEN 0 AND 10000);
ALTER TABLE commander_device_calls ADD COLUMN call_result_metadata_json TEXT;
CREATE INDEX IF NOT EXISTS idx_device_calls_approval_active
  ON commander_device_calls(tenant_id,device_id,state,approval_timeout_seconds,expires_at_utc);
