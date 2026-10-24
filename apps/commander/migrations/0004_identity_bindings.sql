PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS identity_bindings (
  identity_binding_id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES users(subject_id) ON DELETE CASCADE,
  provider_code TEXT NOT NULL,
  issuer TEXT NOT NULL,
  external_subject TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','REVOKED')),
  created_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT,
  UNIQUE (issuer, external_subject)
);

CREATE INDEX IF NOT EXISTS idx_identity_bindings_subject
  ON identity_bindings(subject_id);

CREATE INDEX IF NOT EXISTS idx_identity_bindings_provider
  ON identity_bindings(provider_code, state);

INSERT OR IGNORE INTO identity_bindings (
  identity_binding_id,
  subject_id,
  provider_code,
  issuer,
  external_subject,
  state,
  created_at_utc,
  revoked_at_utc
)
SELECT
  'PRIMARY:' || subject_id,
  subject_id,
  'PRIMARY_OIDC',
  oidc_issuer,
  oidc_subject,
  'ACTIVE',
  created_at_utc,
  NULL
FROM users;
