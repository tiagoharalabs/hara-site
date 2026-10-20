PRAGMA foreign_keys = ON;

-- A retry may reclaim a crashed webhook worker, while its old owner cannot
-- mark the newer attempt complete. Existing completed event IDs remain final.
ALTER TABLE billing_webhook_events ADD COLUMN claim_token TEXT;
ALTER TABLE billing_webhook_events ADD COLUMN claim_expires_at_utc TEXT;
CREATE INDEX IF NOT EXISTS idx_billing_webhook_stale_claims
  ON billing_webhook_events(state, claim_expires_at_utc)
  WHERE state = 'PROCESSING';

CREATE TABLE IF NOT EXISTS billing_projection_claims (
  tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id),
  claim_token TEXT NOT NULL,
  claim_expires_at_utc TEXT NOT NULL
);

-- One checkout attempt per tenant. The attempt ID is also the Stripe
-- idempotency key; it changes only after the previous session expires.
CREATE TABLE IF NOT EXISTS billing_checkout_attempts (
  tenant_id TEXT PRIMARY KEY REFERENCES tenants(tenant_id),
  attempt_id TEXT NOT NULL UNIQUE,
  plan_code TEXT NOT NULL REFERENCES plans(plan_code),
  request_sha256 TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('CREATING','UNCERTAIN','READY')),
  claim_token TEXT,
  checkout_session_id TEXT,
  checkout_url TEXT,
  expires_at_utc TEXT,
  claim_expires_at_utc TEXT,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_billing_checkout_expiry
  ON billing_checkout_attempts(state, expires_at_utc);
