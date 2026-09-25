PRAGMA foreign_keys = ON;

CREATE INDEX IF NOT EXISTS idx_portal_sessions_revoked
  ON portal_sessions(revoked_at_utc);
