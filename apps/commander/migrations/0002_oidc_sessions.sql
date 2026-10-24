PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS oidc_transactions (
  state_hash TEXT PRIMARY KEY,
  browser_binding_hash TEXT NOT NULL,
  code_verifier TEXT NOT NULL,
  nonce TEXT NOT NULL,
  return_to TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  consumed_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_oidc_transactions_expiry
  ON oidc_transactions(expires_at_utc);

CREATE TABLE IF NOT EXISTS portal_sessions (
  session_hash TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES users(subject_id),
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_portal_sessions_subject
  ON portal_sessions(subject_id);

CREATE INDEX IF NOT EXISTS idx_portal_sessions_expiry
  ON portal_sessions(expires_at_utc);

CREATE TABLE IF NOT EXISTS identity_invites (
  invite_id TEXT PRIMARY KEY,
  normalized_email TEXT NOT NULL UNIQUE,
  target_subject_id TEXT NOT NULL REFERENCES users(subject_id),
  state TEXT NOT NULL CHECK (state IN ('ACTIVE','CLAIMED','REVOKED','EXPIRED')),
  created_at_utc TEXT NOT NULL,
  expires_at_utc TEXT,
  claimed_at_utc TEXT,
  claimed_issuer TEXT,
  claimed_subject TEXT
);

CREATE INDEX IF NOT EXISTS idx_identity_invites_state
  ON identity_invites(state);
