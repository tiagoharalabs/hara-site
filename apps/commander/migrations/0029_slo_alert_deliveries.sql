PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS commander_slo_alert_deliveries (
  delivery_id TEXT PRIMARY KEY,
  delivery_key TEXT NOT NULL UNIQUE,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  incident_id TEXT NOT NULL REFERENCES commander_slo_incidents(incident_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL CHECK (event_type IN ('OPENED','ESCALATED','RESOLVED')),
  escalation_level INTEGER NOT NULL DEFAULT 0 CHECK (escalation_level BETWEEN 0 AND 3),
  payload_json TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PENDING','RETRY','DELIVERED')),
  attempt_count INTEGER NOT NULL DEFAULT 0,
  next_attempt_at_utc TEXT NOT NULL,
  last_attempt_at_utc TEXT,
  delivered_at_utc TEXT,
  last_error_code TEXT,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_commander_slo_alert_delivery_pending
  ON commander_slo_alert_deliveries(state, next_attempt_at_utc, created_at_utc);

CREATE INDEX IF NOT EXISTS idx_commander_slo_alert_delivery_incident
  ON commander_slo_alert_deliveries(incident_id, created_at_utc);
