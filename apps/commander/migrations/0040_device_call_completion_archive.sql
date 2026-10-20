-- Keep a minimal authenticated completion proof after the full call row ages out.
-- A result without a redacted marker is not eligible for archival.
CREATE TABLE IF NOT EXISTS commander_device_call_completion_archive (
  call_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  device_id TEXT NOT NULL,
  state TEXT NOT NULL,
  result_marker TEXT NOT NULL,
  error_code TEXT,
  retired_at_utc TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_device_call_completion_archive_delete
AFTER DELETE ON commander_device_calls
WHEN OLD.state IN ('COMPLETED', 'FAILED')
  AND OLD.result_json LIKE 'HARA_REDACTED_SHA256:%'
BEGIN
  INSERT INTO commander_device_call_completion_archive
    (call_id, tenant_id, device_id, state, result_marker, error_code, retired_at_utc)
  VALUES (OLD.call_id, OLD.tenant_id, OLD.device_id, OLD.state,
          OLD.result_json, OLD.error_code, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
END;
