CREATE TABLE commander_slo_state (
  tenant_id TEXT PRIMARY KEY,
  profile TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('PASS','DEGRADED','INSUFFICIENT_DATA')),
  breach_streak INTEGER NOT NULL DEFAULT 0,
  recovery_streak INTEGER NOT NULL DEFAULT 0,
  current_incident_id TEXT,
  last_evaluated_at_utc TEXT NOT NULL,
  last_snapshot_at_utc TEXT,
  summary_json TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE TABLE commander_slo_incidents (
  incident_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  profile TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('OPEN','RESOLVED')),
  opened_at_utc TEXT NOT NULL,
  resolved_at_utc TEXT,
  first_breach_at_utc TEXT NOT NULL,
  last_breach_at_utc TEXT,
  last_seen_at_utc TEXT NOT NULL,
  summary_json TEXT NOT NULL,
  resolution_json TEXT,
  updated_at_utc TEXT NOT NULL,
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE
);

CREATE INDEX idx_commander_slo_incidents_tenant_state
  ON commander_slo_incidents(tenant_id,state,opened_at_utc DESC);

CREATE INDEX idx_commander_slo_incidents_resolved
  ON commander_slo_incidents(state,resolved_at_utc);
