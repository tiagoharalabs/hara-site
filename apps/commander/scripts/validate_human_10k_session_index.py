#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"
AUTH = (ROOT / "src" / "auth.js").read_text()

db = sqlite3.connect(":memory:")
db.executescript((MIG / "0001_product.sql").read_text())
db.executescript((MIG / "0002_oidc_sessions.sql").read_text())
db.executescript((MIG / "0010_session_scale.sql").read_text())

tenants = [
    (f"T-{i:05d}", f"Tenant {i}", "ACTIVE", "PRODUCTION", "2026-09-25T00:00:00.000Z")
    for i in range(10_000)
]
users = [
    (
        f"S-{i:05d}", f"T-{i:05d}", "https://auth.haralabs.com.br/",
        f"sub-{i:05d}", f"u{i}@example.invalid", f"User {i}",
        "ACTIVE", "OWNER", "2026-09-25T00:00:00.000Z",
    )
    for i in range(10_000)
]
sessions = [
    (
        f"HASH-{i:05d}", f"S-{i:05d}", "2026-09-25T00:00:00.000Z",
        "2026-09-25T08:00:00.000Z", "2026-09-25T00:00:00.000Z", None,
    )
    for i in range(10_000)
]

db.executemany("INSERT INTO tenants VALUES (?,?,?,?,?)", tenants)
db.executemany(
    """INSERT INTO users
       (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    users,
)
db.executemany(
    """INSERT INTO portal_sessions
       (session_hash,subject_id,created_at_utc,expires_at_utc,last_seen_at_utc,revoked_at_utc)
       VALUES (?,?,?,?,?,?)""",
    sessions,
)

sql = """
SELECT
  s.session_hash,
  s.subject_id,
  s.expires_at_utc,
  s.last_seen_at_utc,
  s.revoked_at_utc,
  u.tenant_id,
  u.oidc_issuer,
  u.oidc_subject,
  u.email,
  u.display_name,
  u.state AS user_state,
  u.role,
  t.display_name AS tenant_name,
  t.state AS tenant_state
FROM portal_sessions s
JOIN users u ON u.subject_id = s.subject_id
JOIN tenants t ON t.tenant_id = u.tenant_id
WHERE s.session_hash = ?
LIMIT 1
"""

plan_rows = db.execute("EXPLAIN QUERY PLAN " + sql, ("HASH-09999",)).fetchall()
plan = "\n".join(str(row) for row in plan_rows).lower()

assert "portal_sessions" in AUTH
assert "where s.session_hash = ?" in AUTH.lower()
assert "portal_sessions" in plan
assert "session_hash" in plan or "sqlite_autoindex_portal_sessions_1" in plan
assert "users" in plan
assert "tenants" in plan

row = db.execute(sql, ("HASH-09999",)).fetchone()
assert row is not None
assert row[1] == "S-09999"
assert row[5] == "T-09999"
assert db.execute("SELECT COUNT(*) FROM portal_sessions").fetchone()[0] == 10_000

revoked_index = db.execute(
    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_portal_sessions_revoked'"
).fetchone()
assert revoked_index == ("idx_portal_sessions_revoked",)

print("COMMANDER_HUMAN_10K_SESSION_LOOKUP_INDEXED=PASS")
print("COMMANDER_HUMAN_10K_SESSION_DATASET=10000")
print("COMMANDER_HUMAN_SESSION_RETENTION_REVOKED_INDEX=PASS")
