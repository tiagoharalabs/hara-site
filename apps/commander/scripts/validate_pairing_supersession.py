#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "apps/commander/migrations"
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")

db = sqlite3.connect(":memory:")
db.executescript((MIGRATIONS / "0001_product.sql").read_text(encoding="utf-8"))
db.executescript((MIGRATIONS / "0005_devices.sql").read_text(encoding="utf-8"))
db.execute(
    "INSERT INTO tenants VALUES (?,?,?,?,?)",
    ("T1", "Tenant", "ACTIVE", "PRODUCTION", "2026-09-24T00:00:00.000Z"),
)
db.execute(
    """INSERT INTO users
       (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    ("S1","T1","https://issuer.example/","subject","a@example.com","User","ACTIVE","OWNER",
     "2026-09-24T00:00:00.000Z"),
)

pair_sql = """INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc)
VALUES (?,?,?,?,?,?,NULL)"""
for pairing_id, token_hash, created_at in (
    ("P1","H1","2026-09-24T00:01:00.000Z"),
    ("P2","H2","2026-09-24T00:02:00.000Z"),
    ("P3","H3","2026-09-24T00:03:00.000Z"),
):
    db.execute(
        pair_sql,
        (pairing_id,token_hash,"T1","S1",created_at,"2026-09-24T01:00:00.000Z"),
    )

db.executescript((MIGRATIONS / "0009_pairing_supersession.sql").read_text(encoding="utf-8"))

rows = db.execute(
    """SELECT pairing_id,superseded_at_utc
         FROM device_pairing_tokens
        WHERE tenant_id='T1' AND subject_id='S1'
        ORDER BY created_at_utc"""
).fetchall()
current = [row[0] for row in rows if row[1] is None]
assert current == ["P3"], f"HISTORICAL_NORMALIZATION_FAILED:{rows}"

try:
    db.execute(
        """INSERT INTO device_pairing_tokens
           (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,
            consumed_at_utc,superseded_at_utc)
           VALUES ('P4-BAD','H4-BAD','T1','S1','2026-09-24T00:04:00.000Z',
                   '2026-09-24T01:00:00.000Z',NULL,NULL)"""
    )
    raise AssertionError("PAIRING_CURRENT_UNIQUENESS_NOT_ENFORCED")
except sqlite3.IntegrityError:
    pass
with db:
    db.execute(
        """UPDATE device_pairing_tokens
              SET superseded_at_utc='2026-09-24T00:04:00.000Z'
            WHERE tenant_id='T1' AND subject_id='S1'
              AND consumed_at_utc IS NULL AND superseded_at_utc IS NULL"""
    )
    db.execute(
        """INSERT INTO device_pairing_tokens
           (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,
            consumed_at_utc,superseded_at_utc)
           VALUES ('P4','H4','T1','S1','2026-09-24T00:04:00.000Z',
                   '2026-09-24T01:00:00.000Z',NULL,NULL)"""
    )

eligible = lambda token_hash: db.execute(
    """SELECT pairing_id FROM device_pairing_tokens
       WHERE token_hash=? AND consumed_at_utc IS NULL
         AND superseded_at_utc IS NULL AND expires_at_utc > ?""",
    (token_hash, "2026-09-24T00:05:00.000Z"),
).fetchone()

assert eligible("H3") is None, "SUPERSEDED_TOKEN_REPLAY_ALLOWED"
assert eligible("H4") == ("P4",), "LATEST_TOKEN_NOT_ELIGIBLE"

create = WORKER.split("async function createDevicePairing", 1)[1].split("async function listDevices", 1)[0]
enroll = WORKER.split("async function enrollDevice", 1)[1].split("async function resolveDeviceCredential", 1)[0]
assert "PRODUCT_DB.batch([supersede, insert])" in create, "PAIRING_SUPERSESSION_NOT_ATOMIC"
assert "superseded_at_utc = ?" in create, "PAIRING_SUPERSESSION_UPDATE_MISSING"
assert create.count("consumed_at_utc IS NULL") >= 1
assert create.count("superseded_at_utc IS NULL") >= 1
assert enroll.count("superseded_at_utc IS NULL") >= 2, "ENROLL_SUPERSESSION_GUARD_MISSING"

print("COMMANDER_PAIRING_HISTORICAL_NORMALIZATION=PASS")
print("COMMANDER_PAIRING_SINGLE_CURRENT_TOKEN=PASS")
print("COMMANDER_PAIRING_SUPERSEDED_REPLAY=DENIED")
print("COMMANDER_PAIRING_SUPERSESSION_ATOMIC=PASS")
