#!/usr/bin/env python3
"""Adversarial two-tenant isolation proof for H.A.R.A Commander.

This validator is intentionally source/model level and does not attack PROD.
It applies the product migrations to an isolated SQLite DB, creates Tenant A/B,
then executes the same tenant-bound SQL shapes used by the Worker for the
cross-tenant operations tracked by security issue #189.
"""

from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
MIG = ROOT / "apps/commander/migrations"

db = sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys = ON")
for name in (
    "0001_product.sql",
    "0005_devices.sql",
    "0006_device_calls.sql",
    "0007_device_selections.sql",
    "0009_pairing_supersession.sql",
):
    db.executescript((MIG / name).read_text(encoding="utf-8"))

NOW = "2026-09-26T02:50:00.000Z"
FUTURE = "2026-09-26T03:50:00.000Z"

for tenant, label in (("TA", "Tenant A"), ("TB", "Tenant B")):
    db.execute(
        "INSERT INTO tenants VALUES (?,?,?,?,?)",
        (tenant, label, "ACTIVE", "PRODUCTION", NOW),
    )

for subject, tenant, email in (
    ("SA", "TA", "a@example.test"),
    ("SB", "TB", "b@example.test"),
):
    db.execute(
        """INSERT INTO users
           (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            subject,
            tenant,
            "https://issuer.example/",
            f"oidc-{subject}",
            email,
            subject,
            "ACTIVE",
            "OWNER",
            NOW,
        ),
    )

for pairing, token_hash, tenant, subject in (
    ("PA", "HA", "TA", "SA"),
    ("PB", "HB", "TB", "SB"),
):
    db.execute(
        """INSERT INTO device_pairing_tokens
           (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,
            consumed_at_utc,superseded_at_utc)
           VALUES (?,?,?,?,?,?,?,NULL)""",
        (pairing, token_hash, tenant, subject, NOW, FUTURE, NOW),
    )

for device, pairing, tenant, subject, credential in (
    ("DA", "PA", "TA", "SA", "CREDA"),
    ("DB", "PB", "TB", "SB", "CREDB"),
):
    db.execute(
        """INSERT INTO commander_devices
           (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,
            architecture,agent_version,tunnel_mode,credential_hash,state,created_at_utc,
            last_seen_at_utc,revoked_at_utc)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
        (
            device,
            pairing,
            tenant,
            subject,
            f"Device {tenant}",
            "LINUX",
            "x86_64",
            "0.3.7",
            "OUTBOUND_RELAY",
            credential,
            "ACTIVE",
            NOW,
            NOW,
        ),
    )

# Each tenant owns exactly one valid selection.
for tenant, subject, device in (("TA", "SA", "DA"), ("TB", "SB", "DB")):
    db.execute(
        """INSERT INTO commander_device_selections
           (tenant_id,subject_id,device_id,selected_at_utc)
           VALUES (?,?,?,?)""",
        (tenant, subject, device, NOW),
    )

# B owns one completed call containing receipt-like result material.
db.execute(
    """INSERT INTO commander_device_calls
       (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
        created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
       VALUES (?,?,?,?,?,?,?,'COMPLETED',?,?,?,?,?,NULL)""",
    (
        "CALL-B",
        "REQ-B",
        "TB",
        "SB",
        "DB",
        "hara.receipts.get",
        "{}",
        NOW,
        FUTURE,
        NOW,
        NOW,
        '{"receipt":{"sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}}',
    ),
)

# 1) Enumeration: A's list query must not return B.
rows = db.execute(
    """SELECT d.device_id
         FROM commander_devices d
         LEFT JOIN commander_device_selections s
           ON s.tenant_id = d.tenant_id
          AND s.subject_id = ?
        WHERE d.tenant_id = ?""",
    ("SA", "TA"),
).fetchall()
assert rows == [("DA",)], f"CROSS_TENANT_ENUMERATION_LEAK:{rows!r}"

# 2) Selection: A attempts to select B device using Worker's tenant-bound shape.
selection = db.execute(
    """INSERT INTO commander_device_selections
       (tenant_id,subject_id,device_id,selected_at_utc)
       SELECT ?,?,d.device_id,?
         FROM commander_devices d
        WHERE d.device_id=?
          AND d.tenant_id=?
          AND d.state='ACTIVE'
          AND d.revoked_at_utc IS NULL
       ON CONFLICT(tenant_id,subject_id)
       DO UPDATE SET device_id=excluded.device_id, selected_at_utc=excluded.selected_at_utc""",
    ("TA", "SA", NOW, "DB", "TA"),
)
assert selection.rowcount == 0, "CROSS_TENANT_DEVICE_SELECTED"
assert db.execute(
    "SELECT device_id FROM commander_device_selections WHERE tenant_id='TA' AND subject_id='SA'"
).fetchone() == ("DA",), "TENANT_A_SELECTION_CHANGED"

# 3) Revoke: privileged A owner still cannot revoke B because tenant is mandatory.
revoked = db.execute(
    """UPDATE commander_devices
          SET state='REVOKED',revoked_at_utc=?
        WHERE device_id=? AND tenant_id=? AND state='ACTIVE'""",
    (NOW, "DB", "TA"),
)
assert revoked.rowcount == 0, "CROSS_TENANT_DEVICE_REVOKED"
assert db.execute(
    "SELECT state,revoked_at_utc FROM commander_devices WHERE device_id='DB'"
).fetchone() == ("ACTIVE", None), "TENANT_B_DEVICE_MUTATED"

# 4) Enqueue: A explicitly requests B device; Worker shape requires tenant + subject selection match.
enqueued = db.execute(
    """INSERT OR IGNORE INTO commander_device_calls
       (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
        created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
       SELECT ?,?,?,?,d.device_id,?,?,'PENDING',?,?,NULL,NULL,NULL,NULL
         FROM commander_devices d
         JOIN commander_device_selections s
           ON s.tenant_id=d.tenant_id
          AND s.device_id=d.device_id
        WHERE d.device_id=?
          AND d.tenant_id=?
          AND d.state='ACTIVE'
          AND d.revoked_at_utc IS NULL
          AND s.subject_id=?""",
    (
        "CALL-A-X",
        "REQ-A-X",
        "TA",
        "SA",
        "hara.health",
        "{}",
        NOW,
        FUTURE,
        "DB",
        "TA",
        "SA",
    ),
)
assert enqueued.rowcount == 0, "CROSS_TENANT_CALL_ENQUEUED"
assert db.execute(
    "SELECT COUNT(*) FROM commander_device_calls WHERE call_id='CALL-A-X'"
).fetchone()[0] == 0

# 5) Receipt/call read: A cannot read B's completed call/result.
receipt = db.execute(
    """SELECT result_json
         FROM commander_device_calls
        WHERE call_id=? AND tenant_id=? AND subject_id=?
        LIMIT 1""",
    ("CALL-B", "TA", "SA"),
).fetchone()
assert receipt is None, "CROSS_TENANT_RECEIPT_READABLE"
assert db.execute(
    """SELECT result_json
         FROM commander_device_calls
        WHERE call_id=? AND tenant_id=? AND subject_id=?
        LIMIT 1""",
    ("CALL-B", "TB", "SB"),
).fetchone() is not None, "TENANT_B_RECEIPT_FIXTURE_INVALID"

# 6) Quota isolation: internal MCP reserve/commit/release derive the Durable Object
# namespace only from the resolved identity tenant, never from a caller-supplied tenant_id.
authorize_block = WORKER.split(
    'if (url.pathname === "/api/internal/mcp/authorize"', 1
)[1].split(
    'if (url.pathname === "/api/internal/mcp/commit"', 1
)[0]
commit_block = WORKER.split(
    'if (url.pathname === "/api/internal/mcp/commit"', 1
)[1].split(
    'if (url.pathname === "/api/internal/mcp/release"', 1
)[0]
release_block = WORKER.split(
    'if (url.pathname === "/api/internal/mcp/release"', 1
)[1].split(
    'if (url.pathname.startsWith("/api/dev/"))', 1
)[0]

assert ".getByName(context.tenant_id)" in authorize_block, "QUOTA_AUTHORIZE_TENANT_NAMESPACE_MISSING"
assert ".getByName(identity.tenant_id)" in commit_block, "QUOTA_COMMIT_TENANT_NAMESPACE_MISSING"
assert ".getByName(identity.tenant_id)" in release_block, "QUOTA_RELEASE_TENANT_NAMESPACE_MISSING"
for block, label in (
    (authorize_block, "AUTHORIZE"),
    (commit_block, "COMMIT"),
    (release_block, "RELEASE"),
):
    assert "body.tenant_id" not in block, f"QUOTA_{label}_CALLER_TENANT_OVERRIDE_PRESENT"

# Source guards: these are the exact Worker functions that must stay tenant-bound.
list_block = WORKER.split("async function listDevices", 1)[1].split("async function enrollDevice", 1)[0]
select_block = WORKER.split("async function selectDevice", 1)[1].split("async function selectPortalDevice", 1)[0]
revoke_block = WORKER.split("async function revokePortalDevice", 1)[1].split("async function enqueueDeviceCall", 1)[0]
enqueue_block = WORKER.split("async function enqueueDeviceCall", 1)[1].split("async function claimNextDeviceCall", 1)[0]
status_block = WORKER.split("async function deviceCallStatus", 1)[1].split("export default", 1)[0]

assert "WHERE d.tenant_id = ?" in list_block
assert "AND d.tenant_id = ?" in select_block
assert "device_id = ? AND tenant_id = ?" in revoke_block
assert "AND d.tenant_id = ?" in enqueue_block
assert "WHERE call_id = ? AND tenant_id = ? AND subject_id = ?" in status_block

print("CROSS_TENANT_DEVICE_ENUMERATION=BLOCKED")
print("CROSS_TENANT_DEVICE_SELECTION=BLOCKED")
print("CROSS_TENANT_DEVICE_REVOKE=BLOCKED")
print("CROSS_TENANT_DEVICE_ENQUEUE=BLOCKED")
print("CROSS_TENANT_RECEIPT_READ=BLOCKED")
print("CROSS_TENANT_QUOTA_ACCESS=BLOCKED")
print("CALLER_SUPPLIED_TENANT_OVERRIDE=ABSENT")
print("MULTITENANT_ISOLATION_SOURCE_MODEL=PASS")
print("MULTITENANT_ISOLATION_LIVE_DEV=PENDING")
