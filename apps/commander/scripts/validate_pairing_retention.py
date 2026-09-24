#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "apps/commander/migrations"
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
READBACK = (ROOT / "apps/commander/scripts/commander_prod_readback.py").read_text(encoding="utf-8")

db = sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys = ON")
for name in ("0001_product.sql", "0005_devices.sql", "0009_pairing_supersession.sql"):
    db.executescript((MIG / name).read_text(encoding="utf-8"))

db.execute(
    "INSERT INTO tenants VALUES (?,?,?,?,?)",
    ("T1", "Tenant", "ACTIVE", "PRODUCTION", "2026-01-01T00:00:00.000Z"),
)
for index in range(1, 6):
    db.execute(
        """INSERT INTO users
        (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            f"S{index}", "T1", "https://issuer.example/", f"subject-{index}",
            f"u{index}@example.com", f"User {index}", "ACTIVE", "OWNER",
            "2026-01-01T00:00:00.000Z",
        ),
    )

insert_pair = """INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,
 consumed_at_utc,superseded_at_utc)
VALUES (?,?,?,?,?,?,?,?)"""

for index in range(105):
    db.execute(
        insert_pair,
        (
            f"OLD-SUP-{index:03d}", f"H-OLD-SUP-{index:03d}", "T1", "S1",
            "2026-07-01T00:00:00.000Z", "2026-07-01T00:10:00.000Z",
            None, "2026-07-01T00:05:00.000Z",
        ),
    )

db.execute(
    insert_pair,
    (
        "RECENT-SUP", "H-RECENT-SUP", "T1", "S1",
        "2026-09-20T00:00:00.000Z", "2026-09-20T00:10:00.000Z",
        None, "2026-09-20T00:05:00.000Z",
    ),
)
db.execute(
    insert_pair,
    (
        "OLD-EXPIRED", "H-OLD-EXPIRED", "T1", "S2",
        "2026-07-01T00:00:00.000Z", "2026-07-01T00:10:00.000Z",
        None, None,
    ),
)
db.execute(
    insert_pair,
    (
        "RECENT-EXPIRED", "H-RECENT-EXPIRED", "T1", "S3",
        "2026-09-23T00:00:00.000Z", "2026-09-23T00:10:00.000Z",
        None, None,
    ),
)
db.execute(
    insert_pair,
    (
        "CURRENT-VALID", "H-CURRENT-VALID", "T1", "S4",
        "2026-09-24T00:00:00.000Z", "2026-09-24T00:10:00.000Z",
        None, None,
    ),
)
db.execute(
    insert_pair,
    (
        "CONSUMED", "H-CONSUMED", "T1", "S5",
        "2026-07-01T00:00:00.000Z", "2026-07-01T00:10:00.000Z",
        "2026-07-01T00:03:00.000Z", None,
    ),
)
db.execute(
    """INSERT INTO commander_devices
    (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,
     architecture,agent_version,tunnel_mode,credential_hash,state,created_at_utc,
     last_seen_at_utc,revoked_at_utc)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
    (
        "D1", "CONSUMED", "T1", "S5", "Device", "LINUX", "x86_64", "0.3.5",
        "OUTBOUND_RELAY", "CRED", "ACTIVE", "2026-07-01T00:03:00.000Z",
        "2026-07-01T00:03:00.000Z",
    ),
)

cutoff = "2026-08-25T00:00:00.000Z"
eligible_before = db.execute(
    """SELECT COUNT(*) FROM device_pairing_tokens p
       WHERE p.consumed_at_utc IS NULL
         AND NOT EXISTS (
           SELECT 1 FROM commander_devices d WHERE d.pairing_id=p.pairing_id
         )
         AND (
           (p.superseded_at_utc IS NOT NULL AND p.superseded_at_utc <= ?)
           OR (p.superseded_at_utc IS NULL AND p.expires_at_utc <= ?)
         )""",
    (cutoff, cutoff),
).fetchone()[0]
assert eligible_before == 106, f"ELIGIBLE_BEFORE_INVALID:{eligible_before}"

db.execute(
    """DELETE FROM device_pairing_tokens
       WHERE pairing_id IN (
         SELECT p.pairing_id
           FROM device_pairing_tokens p
          WHERE p.consumed_at_utc IS NULL
            AND NOT EXISTS (
              SELECT 1 FROM commander_devices d WHERE d.pairing_id=p.pairing_id
            )
            AND (
              (p.superseded_at_utc IS NOT NULL AND p.superseded_at_utc <= ?)
              OR (p.superseded_at_utc IS NULL AND p.expires_at_utc <= ?)
            )
          ORDER BY COALESCE(p.superseded_at_utc,p.expires_at_utc) ASC
          LIMIT ?
       )""",
    (cutoff, cutoff, 100),
)

eligible_after = db.execute(
    """SELECT COUNT(*) FROM device_pairing_tokens p
       WHERE p.consumed_at_utc IS NULL
         AND NOT EXISTS (
           SELECT 1 FROM commander_devices d WHERE d.pairing_id=p.pairing_id
         )
         AND (
           (p.superseded_at_utc IS NOT NULL AND p.superseded_at_utc <= ?)
           OR (p.superseded_at_utc IS NULL AND p.expires_at_utc <= ?)
         )""",
    (cutoff, cutoff),
).fetchone()[0]
assert eligible_after == 6, f"RETENTION_BATCH_NOT_BOUNDED:{eligible_after}"

for pairing_id in ("RECENT-SUP", "RECENT-EXPIRED", "CURRENT-VALID", "CONSUMED"):
    row = db.execute(
        "SELECT pairing_id FROM device_pairing_tokens WHERE pairing_id=?",
        (pairing_id,),
    ).fetchone()
    assert row == (pairing_id,), f"PAIRING_SHOULD_BE_PRESERVED:{pairing_id}"

device_pair = db.execute(
    "SELECT pairing_id FROM commander_devices WHERE device_id='D1'"
).fetchone()
assert device_pair == ("CONSUMED",), "DEVICE_PROVENANCE_BROKEN"
db.execute("PRAGMA foreign_key_check")
assert db.execute("PRAGMA foreign_key_check").fetchall() == [], "FOREIGN_KEY_DEFECT"

block = WORKER.split("async function cleanupTerminalPairingTokens", 1)[1].split(
    "async function createDevicePairing", 1
)[0]
create = WORKER.split("async function createDevicePairing", 1)[1].split(
    "async function listDevices", 1
)[0]

assert "PAIRING_RETENTION_SECONDS = 30 * 24 * 60 * 60" in WORKER
assert "PAIRING_RETENTION_BATCH = 100" in WORKER
assert "PAIRING_RETENTION_DAYS = 30" in READBACK
assert "retention_eligible_pairing_tokens" in READBACK
assert "COMMANDER_PROD_PAIRING_RETENTION_ELIGIBLE=" in READBACK
assert "p.consumed_at_utc IS NULL" in block
assert "NOT EXISTS" in block and "commander_devices d" in block
assert "p.superseded_at_utc" in block and "p.expires_at_utc" in block
assert "LIMIT ?" in block
assert "cleanupTerminalPairingTokens(env).catch(() => null)" in create

print("COMMANDER_PAIRING_RETENTION_30D=PASS")
print("COMMANDER_PAIRING_RETENTION_BATCH_100=PASS")
print("COMMANDER_PAIRING_RETENTION_RECENT_TERMINAL_PRESERVED=PASS")
print("COMMANDER_PAIRING_RETENTION_CURRENT_VALID_PRESERVED=PASS")
print("COMMANDER_PAIRING_RETENTION_CONSUMED_PROVENANCE_PRESERVED=PASS")
print("COMMANDER_PAIRING_RETENTION_FOREIGN_KEYS=PASS")
print("COMMANDER_PAIRING_RETENTION_BEST_EFFORT=PASS")
