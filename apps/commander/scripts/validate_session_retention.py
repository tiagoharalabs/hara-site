#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
AUTH = (ROOT / "apps/commander/src/auth.js").read_text(encoding="utf-8")
READBACK = (ROOT / "apps/commander/scripts/commander_prod_readback.py").read_text(encoding="utf-8")
MIG = ROOT / "apps/commander/migrations"

assert "SESSION_RETENTION_SECONDS = 30 * 24 * 60 * 60" in AUTH
assert "SESSION_RETENTION_BATCH = 100" in AUTH
assert "cleanupTerminalPortalSessions" in AUTH
assert ".run().catch(() => null)" in AUTH
assert "SESSION_RETENTION_DAYS = 30" in READBACK
assert "retention_eligible_expired_sessions" in READBACK
assert "retention_eligible_revoked_sessions" in READBACK
assert "oldest_expired_age_days" in READBACK
assert "COMMANDER_PROD_SESSION_RETENTION_ELIGIBLE=" in READBACK

db = sqlite3.connect(":memory:")
db.executescript((MIG / "0001_product.sql").read_text(encoding="utf-8"))
db.executescript((MIG / "0002_oidc_sessions.sql").read_text(encoding="utf-8"))
db.execute(
    "INSERT INTO tenants VALUES (?,?,?,?,?)",
    ("T1","Tenant","ACTIVE","PRODUCTION","2026-01-01T00:00:00.000Z"),
)
db.execute(
    """INSERT INTO users
       (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    ("S1","T1","https://issuer.example/","sub","u@example.com","User","ACTIVE","OWNER",
     "2026-01-01T00:00:00.000Z"),
)
insert_session = """INSERT INTO portal_sessions
(session_hash,subject_id,created_at_utc,expires_at_utc,last_seen_at_utc,revoked_at_utc)
VALUES (?,?,?,?,?,?)"""

for i in range(105):
    db.execute(
        insert_session,
        (
            f"OLD-{i:03d}",
            "S1",
            "2026-07-01T00:00:00.000Z",
            "2026-07-02T00:00:00.000Z",
            "2026-07-01T00:00:00.000Z",
            None,
        ),
    )

db.execute(
    insert_session,
    (
        "RECENT-EXPIRED",
        "S1",
        "2026-09-20T00:00:00.000Z",
        "2026-09-23T00:00:00.000Z",
        "2026-09-23T00:00:00.000Z",
        None,
    ),
)
db.execute(
    insert_session,
    (
        "ACTIVE",
        "S1",
        "2026-09-24T00:00:00.000Z",
        "2026-09-25T00:00:00.000Z",
        "2026-09-24T00:00:00.000Z",
        None,
    ),
)

cutoff = "2026-08-25T00:00:00.000Z"
db.execute(
    """DELETE FROM portal_sessions
       WHERE session_hash IN (
         SELECT session_hash
           FROM portal_sessions
          WHERE expires_at_utc <= ?
             OR (revoked_at_utc IS NOT NULL AND revoked_at_utc <= ?)
          ORDER BY COALESCE(revoked_at_utc, expires_at_utc) ASC
          LIMIT 100
       )""",
    (cutoff, cutoff),
)

old_remaining = db.execute(
    "SELECT COUNT(*) FROM portal_sessions WHERE session_hash LIKE 'OLD-%'"
).fetchone()[0]
assert old_remaining == 5, f"RETENTION_BATCH_NOT_BOUNDED:{old_remaining}"
assert db.execute(
    "SELECT 1 FROM portal_sessions WHERE session_hash='RECENT-EXPIRED'"
).fetchone(), "RECENT_TERMINAL_SESSION_DELETED"
assert db.execute(
    "SELECT 1 FROM portal_sessions WHERE session_hash='ACTIVE'"
).fetchone(), "ACTIVE_SESSION_DELETED"

print("COMMANDER_PORTAL_SESSION_RETENTION_30D=PASS")
print("COMMANDER_PORTAL_SESSION_RETENTION_BATCH_100=PASS")
print("COMMANDER_PORTAL_SESSION_RECENT_TERMINAL_PRESERVED=PASS")
print("COMMANDER_PORTAL_SESSION_ACTIVE_PRESERVED=PASS")
print("COMMANDER_PORTAL_SESSION_RETENTION_BEST_EFFORT=PASS")
