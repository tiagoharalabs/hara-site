PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUSPENDED','CLOSED')),
  environment TEXT NOT NULL CHECK (environment IN ('DEV','REVIEW','PRODUCTION')),
  created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  subject_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  oidc_issuer TEXT NOT NULL,
  oidc_subject TEXT NOT NULL,
  email TEXT,
  display_name TEXT,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUSPENDED','REVOKED')),
  role TEXT NOT NULL CHECK (role IN ('OWNER','ADMIN','MEMBER','REVIEWER')),
  created_at_utc TEXT NOT NULL,
  UNIQUE (oidc_issuer, oidc_subject)
);

CREATE TABLE IF NOT EXISTS plans (
  plan_code TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  meter_id TEXT NOT NULL,
  period_kind TEXT NOT NULL CHECK (period_kind IN ('CALENDAR_MONTH','LIFETIME','NONE')),
  unit_limit INTEGER,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','INACTIVE')),
  CHECK (
    (period_kind = 'NONE' AND unit_limit IS NULL)
    OR
    (period_kind <> 'NONE' AND unit_limit IS NOT NULL AND unit_limit > 0)
  )
);

CREATE TABLE IF NOT EXISTS entitlements (
  entitlement_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  subject_id TEXT REFERENCES users(subject_id),
  plan_code TEXT NOT NULL REFERENCES plans(plan_code),
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','SUSPENDED','EXPIRED','REVOKED')),
  valid_from_utc TEXT NOT NULL,
  valid_until_utc TEXT
);

CREATE TABLE IF NOT EXISTS billing_connections (
  billing_connection_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
  provider TEXT NOT NULL,
  external_customer_id TEXT,
  external_subscription_id TEXT,
  state TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_entitlements_tenant ON entitlements(tenant_id);
CREATE INDEX IF NOT EXISTS idx_billing_tenant ON billing_connections(tenant_id);
