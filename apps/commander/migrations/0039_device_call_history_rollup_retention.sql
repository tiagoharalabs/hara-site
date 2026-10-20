-- Keep lifetime history while old terminal call payload/rows are compacted.
CREATE TABLE IF NOT EXISTS commander_device_call_history_totals (
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  calls_total INTEGER NOT NULL DEFAULT 0 CHECK (calls_total >= 0),
  PRIMARY KEY (tenant_id, subject_id)
);

CREATE TABLE IF NOT EXISTS commander_device_call_history_hourly (
  tenant_id TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  hour_key TEXT NOT NULL,
  calls_count INTEGER NOT NULL DEFAULT 0 CHECK (calls_count >= 0),
  PRIMARY KEY (tenant_id, subject_id, hour_key)
);

CREATE TABLE IF NOT EXISTS commander_device_call_history_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  backfilled_at_utc TEXT NOT NULL
);

INSERT INTO commander_device_call_history_totals (tenant_id, subject_id, calls_total)
SELECT tenant_id, subject_id, COUNT(*)
  FROM commander_device_calls
 WHERE NOT EXISTS (SELECT 1 FROM commander_device_call_history_meta WHERE id = 1)
 GROUP BY tenant_id, subject_id;

INSERT INTO commander_device_call_history_hourly (tenant_id, subject_id, hour_key, calls_count)
SELECT tenant_id, subject_id, substr(created_at_utc, 1, 13), COUNT(*)
  FROM commander_device_calls
 WHERE NOT EXISTS (SELECT 1 FROM commander_device_call_history_meta WHERE id = 1)
   AND created_at_utc >= strftime('%Y-%m-%dT%H:00:00.000Z', 'now', '-8 days')
 GROUP BY tenant_id, subject_id, substr(created_at_utc, 1, 13);

INSERT OR IGNORE INTO commander_device_call_history_meta (id, backfilled_at_utc)
VALUES (1, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));

CREATE TRIGGER IF NOT EXISTS trg_device_call_history_insert
AFTER INSERT ON commander_device_calls
BEGIN
  INSERT INTO commander_device_call_history_totals (tenant_id, subject_id, calls_total)
  VALUES (NEW.tenant_id, NEW.subject_id, 1)
  ON CONFLICT(tenant_id, subject_id) DO UPDATE SET
    calls_total = calls_total + 1;

  INSERT INTO commander_device_call_history_hourly (tenant_id, subject_id, hour_key, calls_count)
  VALUES (NEW.tenant_id, NEW.subject_id, substr(NEW.created_at_utc, 1, 13), 1)
  ON CONFLICT(tenant_id, subject_id, hour_key) DO UPDATE SET
    calls_count = calls_count + 1;
END;

CREATE INDEX IF NOT EXISTS idx_device_calls_terminal_retention
  ON commander_device_calls(state, created_at_utc, call_id)
  WHERE state IN ('COMPLETED', 'FAILED', 'CANCELLED', 'EXPIRED');
