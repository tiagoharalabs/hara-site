ALTER TABLE commander_slo_incidents ADD COLUMN acknowledged_at_utc TEXT;
ALTER TABLE commander_slo_incidents ADD COLUMN acknowledged_by_subject_id TEXT;
ALTER TABLE commander_slo_incidents ADD COLUMN escalation_level INTEGER NOT NULL DEFAULT 0;
ALTER TABLE commander_slo_incidents ADD COLUMN escalated_at_utc TEXT;

CREATE INDEX idx_commander_slo_incidents_open_escalation
  ON commander_slo_incidents(state,escalation_level,opened_at_utc);
