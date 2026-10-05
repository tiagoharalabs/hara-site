CREATE TABLE IF NOT EXISTS commander_beta_access_requests (
  request_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  plan_code TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'REQUESTED'
    CHECK (state IN ('REQUESTED','CONTACTED','APPROVED','DECLINED','CANCELLED')),
  requested_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  UNIQUE (tenant_id, subject_id, plan_code)
);

CREATE INDEX IF NOT EXISTS idx_beta_access_requests_state_updated
  ON commander_beta_access_requests(state, updated_at_utc DESC);
