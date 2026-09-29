PRAGMA foreign_keys = ON;

ALTER TABLE billing_connections ADD COLUMN plan_code TEXT REFERENCES plans(plan_code);
ALTER TABLE billing_connections ADD COLUMN subscription_status TEXT;
ALTER TABLE billing_connections ADD COLUMN current_period_end_utc TEXT;
ALTER TABLE billing_connections ADD COLUMN cancel_at_period_end INTEGER NOT NULL DEFAULT 0
  CHECK (cancel_at_period_end IN (0,1));

CREATE INDEX IF NOT EXISTS idx_billing_provider_customer
  ON billing_connections(provider, external_customer_id);

CREATE INDEX IF NOT EXISTS idx_billing_provider_subscription
  ON billing_connections(provider, external_subscription_id);

CREATE TABLE IF NOT EXISTS billing_webhook_events (
  event_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  event_type TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('RECEIVED','PROCESSING','PROCESSED','IGNORED','FAILED')),
  received_at_utc TEXT NOT NULL,
  processed_at_utc TEXT,
  result_code TEXT
);

CREATE INDEX IF NOT EXISTS idx_billing_webhook_received
  ON billing_webhook_events(provider, received_at_utc);
