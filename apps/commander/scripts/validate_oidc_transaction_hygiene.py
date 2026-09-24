#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "apps/commander/migrations"
AUTH = (ROOT / "apps/commander/src/auth.js").read_text(encoding="utf-8")
READBACK = (ROOT / "apps/commander/scripts/commander_prod_readback.py").read_text(encoding="utf-8")

db = sqlite3.connect(":memory:")
db.executescript((MIG / "0001_product.sql").read_text(encoding="utf-8"))
db.executescript((MIG / "0002_oidc_sessions.sql").read_text(encoding="utf-8"))

insert_tx = """INSERT INTO oidc_transactions
(state_hash,browser_binding_hash,code_verifier,nonce,return_to,created_at_utc,expires_at_utc,consumed_at_utc)
VALUES (?,?,?,?,?,?,?,?)"""

for index in range(105):
    db.execute(
        insert_tx,
        (
            f"EXPIRED-{index:03d}", f"B-{index:03d}", f"V-{index:03d}",
            f"N-{index:03d}", "/", "2026-09-24T00:00:00.000Z",
            "2026-09-24T00:10:00.000Z", None,
        ),
    )

db.execute(
    insert_tx,
    (
        "ACTIVE-UNCONSUMED", "B-ACTIVE-U", "V-ACTIVE-U", "N-ACTIVE-U", "/",
        "2026-09-24T00:10:00.000Z", "2026-09-24T00:30:00.000Z", None,
    ),
)
db.execute(
    insert_tx,
    (
        "ACTIVE-CONSUMED", "B-ACTIVE-C", "V-ACTIVE-C", "N-ACTIVE-C", "/",
        "2026-09-24T00:10:00.000Z", "2026-09-24T00:30:00.000Z",
        "2026-09-24T00:15:00.000Z",
    ),
)

now = "2026-09-24T00:20:00.000Z"
expired_before = db.execute(
    "SELECT COUNT(*) FROM oidc_transactions WHERE expires_at_utc <= ?",
    (now,),
).fetchone()[0]
assert expired_before == 105, f"EXPIRED_BEFORE_INVALID:{expired_before}"

db.execute(
    """DELETE FROM oidc_transactions
       WHERE state_hash IN (
         SELECT state_hash
           FROM oidc_transactions
          WHERE expires_at_utc <= ?
          ORDER BY expires_at_utc ASC
          LIMIT ?
       )""",
    (now, 100),
)

expired_after = db.execute(
    "SELECT COUNT(*) FROM oidc_transactions WHERE expires_at_utc <= ?",
    (now,),
).fetchone()[0]
assert expired_after == 5, f"OIDC_CLEANUP_NOT_BOUNDED:{expired_after}"

for state_hash, consumed in (
    ("ACTIVE-UNCONSUMED", None),
    ("ACTIVE-CONSUMED", "2026-09-24T00:15:00.000Z"),
):
    row = db.execute(
        "SELECT consumed_at_utc FROM oidc_transactions WHERE state_hash=?",
        (state_hash,),
    ).fetchone()
    assert row == (consumed,), f"ACTIVE_TRANSACTION_MUTATED:{state_hash}:{row}"

block = AUTH.split("async function cleanupExpiredOidcTransactions", 1)[1].split(
    "async function cleanupTerminalPortalSessions", 1
)[0]
begin = AUTH.split("export async function beginLogin", 1)[1].split(
    "async function ensurePrimaryIdentityBinding", 1
)[0]

assert "TX_SECONDS = 10 * 60" in AUTH
assert "TX_RETENTION_BATCH = 100" in AUTH
assert "WHERE expires_at_utc <= ?" in block
assert "ORDER BY expires_at_utc ASC" in block
assert "LIMIT ?" in block
assert ".run().catch(() => null)" in block
assert "await cleanupExpiredOidcTransactions(env)" in begin
assert "DELETE FROM oidc_transactions WHERE expires_at_utc <= ?" not in AUTH
assert "OIDC_TRANSACTION_WINDOW_MINUTES = 10" in READBACK
assert "expired_oidc_transactions" in READBACK
assert "COMMANDER_PROD_OIDC_TX_EXPIRED=" in READBACK

print("COMMANDER_OIDC_TX_WINDOW_10M=PASS")
print("COMMANDER_OIDC_TX_CLEANUP_BATCH_100=PASS")
print("COMMANDER_OIDC_TX_ACTIVE_UNCONSUMED_PRESERVED=PASS")
print("COMMANDER_OIDC_TX_ACTIVE_CONSUMED_REPLAY_WINDOW_PRESERVED=PASS")
print("COMMANDER_OIDC_TX_CLEANUP_BEST_EFFORT=PASS")
print("COMMANDER_OIDC_TX_READBACK_SANITIZED=PASS")
