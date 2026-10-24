PRAGMA foreign_keys = ON;

-- Local-first operational history:
-- detailed events remain on the customer device; cloud stores only a bounded,
-- privacy-safe aggregate snapshot delivered by the existing device heartbeat.
ALTER TABLE commander_devices
  ADD COLUMN activity_summary_json TEXT;

ALTER TABLE commander_devices
  ADD COLUMN activity_summary_at_utc TEXT;
