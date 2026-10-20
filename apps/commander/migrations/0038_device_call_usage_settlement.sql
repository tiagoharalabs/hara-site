-- Track D1/DO settlement independently from the client's result read.
-- Existing terminal rows remain NULL and are reconciled idempotently.
ALTER TABLE commander_device_calls ADD COLUMN usage_settled_at_utc TEXT;

CREATE INDEX idx_device_calls_unsettled_usage
  ON commander_device_calls(state, completed_at_utc, call_id)
  WHERE usage_mode = 'CLOUD_QUOTA'
    AND usage_units > 0
    AND usage_settled_at_utc IS NULL
    AND call_result_metadata_json IS NOT NULL;
