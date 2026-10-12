#!/usr/bin/env python3
"""Offline concurrent stress for EXACT Worker SQLite enqueue/claim SQL.

Runs only a temporary local SQLite DB with the current real migrations, including additive approval profile0035.
No HTTP, production D1, device tokens, GPU, or customer files are accessed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
MIGRATIONS = ROOT / "apps/commander/migrations"
THREADS = 12
ATTEMPTS = 256
QUEUE_LIMIT = 16


def sql_from_source(pattern: str) -> str:
    match = re.search(pattern, WORKER, re.S)
    assert match, "SOURCE_SQL_NOT_FOUND"
    assert "${" not in match.group(1), "SOURCE_SQL_DYNAMIC_TEMPLATE_NOT_ALLOWED"
    return match.group(1)


ENQUEUE_SQL = sql_from_source(
    r"const inserted = await env\.PRODUCT_DB\.prepare\(\s*`(INSERT OR IGNORE INTO commander_device_calls.*?)`\s*\)\.bind\("
)
CLAIM_SQL = sql_from_source(
    r"async function claimNextDeviceCall.*?const result = await env\.PRODUCT_DB\.prepare\(\s*`(UPDATE commander_device_calls.*?)`\s*\)\.bind\("
)
def source_bindings(pattern: str) -> list[str]:
    match = re.search(pattern, WORKER, re.S)
    assert match, "SOURCE_BINDINGS_NOT_FOUND"
    return [x.strip() for x in match.group(1).split(",") if x.strip()]


ENQUEUE_BINDINGS = source_bindings(r"const inserted = await env\.PRODUCT_DB\.prepare\(.*?\)\.bind\((.*?)\)\.run\(\)")
CLAIM_BINDINGS = source_bindings(r"async function claimNextDeviceCall.*?const result = await env\.PRODUCT_DB\.prepare\(.*?\)\.bind\((.*?)\)\.all\(\)")
EXPECTED_ENQUEUE_BINDINGS = [
    "callId", "requestId", "context.tenant_id", "context.subject_id", "toolId", "payloadJson",
    "createdAt", "expiresAt", "usageMode", "usageUnits", "usagePeriodKey",
    "usageMode", "usagePeriodKey", "createdAt", "usageUnits",
    "approvalProfile.approval_timeout_seconds", "approvalProfile.execution_budget_ms",
    "deviceId", "context.tenant_id", "eventV2Cutoff", "onlineCutoff",
    "createdAt", "DEVICE_CALL_ACTIVE_QUEUE_LIMIT",
    "approvalProfile.approval_timeout_seconds", "createdAt",
    "usageMode", "usagePeriodKey", "createdAt", "usageUnits",
]
assert ENQUEUE_BINDINGS == EXPECTED_ENQUEUE_BINDINGS, "ENQUEUE_BIND_ORDER_CHANGED"
assert CLAIM_BINDINGS == ["now", "now", "device.device_id", "now", "device.agent_version"], "CLAIM_BIND_ORDER_CHANGED"
assert ENQUEUE_SQL.count("?") == len(ENQUEUE_BINDINGS)
assert CLAIM_SQL.count("?") == len(CLAIM_BINDINGS)
assert "DEVICE_CALL_ACTIVE_QUEUE_LIMIT" in WORKER and "DEVICE_CALL_ACTIVE_QUEUE_LIMIT = 16" in WORKER


def stamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


CLOCK = datetime.now(timezone.utc).replace(microsecond=0)
CREATED = stamp(CLOCK)
EXPIRES = stamp(CLOCK + timedelta(seconds=50))
CUTOFF_7H = stamp(CLOCK - timedelta(hours=7))
CUTOFF_ONLINE = stamp(CLOCK - timedelta(seconds=90))


def connection(path: Path):
    db = sqlite3.connect(str(path), timeout=10)
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def seed(path: Path) -> None:
    db = connection(path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    for sqlfile in sorted(MIGRATIONS.glob("*.sql")):
        db.executescript(sqlfile.read_text(encoding="utf-8"))
    migration_names = {file.name for file in MIGRATIONS.glob("*.sql")}
    assert len(migration_names) >= 32
    assert "0031_free_15000_20261010.sql" in migration_names
    assert "0032_free_10000_revert_20261010.sql" in migration_names
    assert "0035_approval_async_call_metadata.sql" in migration_names
    columns = {row[1]: row for row in db.execute("PRAGMA table_info(commander_device_calls)")}
    assert columns["approval_timeout_seconds"][4] == "0"
    assert columns["execution_budget_ms"][4] == "0"
    assert columns["call_result_metadata_json"][3] == 0
    for tenant, user, device in (("T1", "S1", "D1"), ("T2", "S2", "D2")):
        db.execute(
            "INSERT INTO tenants (tenant_id,display_name,state,environment,created_at_utc) VALUES (?,?,?,?,?)",
            (tenant, tenant, "ACTIVE", "PRODUCTION", CREATED),
        )
        db.execute(
            "INSERT INTO users (subject_id,tenant_id,oidc_issuer,oidc_subject,state,role,created_at_utc) VALUES (?,?,?,?,?,?,?)",
            (user, tenant, "https://issuer.example.invalid/", user, "ACTIVE", "OWNER", CREATED),
        )
        db.execute(
            """INSERT INTO device_pairing_tokens
            (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,
             expires_at_utc,consumed_at_utc,superseded_at_utc)
             VALUES (?,?,?,?,?,?,?,NULL)""",
            ("PAIR-"+device, "HASH-"+device, tenant, user, CREATED, EXPIRES, CREATED),
        )
        db.execute(
            """INSERT INTO commander_devices
            (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,
             architecture,agent_version,tunnel_mode,credential_hash,state,
             created_at_utc,last_seen_at_utc,revoked_at_utc)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
            (device, "PAIR-"+device, tenant, user, device, "LINUX", "x86_64",
             "0.3.44", "EVENT_V2", "CRED-"+device, "ACTIVE", CREATED, CREATED),
        )
    db.commit()
    db.close()


def enqueue(dbfile: Path, i: int, *, tenant="T1", user="S1", device="D1", request_id=None, approval=0, execution=0, tool="hara.ping") -> int:
    db = connection(dbfile)
    try:
        request = request_id or ("REQ-" + str(i))
        params = (
            "CALL-" + tenant + "-" + str(i), request, tenant, user, tool, "{}",
            CREATED, EXPIRES, "UNMETERED", 0, None,
            "UNMETERED", None, CREATED, 0,
            approval, execution,
            device, tenant, CUTOFF_7H, CUTOFF_ONLINE,
            CREATED, QUEUE_LIMIT,
            approval, CREATED,
            "UNMETERED", None, CREATED, 0,
        )
        cursor = db.execute(ENQUEUE_SQL, params)
        db.commit()
        return cursor.rowcount
    finally:
        db.close()


def count(dbfile: Path, where: str) -> int:
    with connection(dbfile) as db:
        return db.execute("SELECT count(*) FROM commander_device_calls WHERE " + where).fetchone()[0]


def claim(dbfile: Path, i: int, when: str, version="0.3.44") -> str | None:
    db = connection(dbfile)
    try:
        row = db.execute(CLAIM_SQL, (when, when, "D1", when, version)).fetchone()
        db.commit()
        return row[0] if row else None
    finally:
        db.close()


def group_tasks(fn, items):
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=THREADS) as executor:
        output = list(executor.map(fn, items))
    return output, round(time.monotonic() - start, 3)


def main() -> None:
    global ATTEMPTS, THREADS
    parser = argparse.ArgumentParser(description="Isolated SQLite stress, not Cloudflare traffic")
    parser.add_argument("--attempts", type=int, default=ATTEMPTS)
    parser.add_argument("--threads", type=int, default=THREADS)
    opts = parser.parse_args()
    if not 64 <= opts.attempts <= 1000 or not 2 <= opts.threads <= 32:
        raise SystemExit("QUEUE_OFFLINE_LOAD_BOUND_DENIED")
    ATTEMPTS, THREADS = opts.attempts, opts.threads
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="hara-commander-queue-offline-") as folder:
        file = Path(folder) / "queue.sqlite3"
        seed(file)
        attempts, elapsed = group_tasks(lambda i: enqueue(file, i), range(ATTEMPTS))
        assert sum(attempts) == QUEUE_LIMIT, "ENQUEUE_ATOMIC_LIMIT_OVERFLOW"
        assert count(file, "device_id='D1'") == QUEUE_LIMIT
        assert count(file, "state='PENDING'") == QUEUE_LIMIT
        print(f"QUEUE_OFFLINE_CONCURRENT_ENQUEUE=PASS attempts={ATTEMPTS} accepted={sum(attempts)} limit={QUEUE_LIMIT} elapsed_seconds={elapsed}")

        # Same request_id must never create multiple executions.
        with connection(file) as db:
            db.execute("DELETE FROM commander_device_calls")
            db.commit()
        same, elapsed = group_tasks(lambda i: enqueue(file, i + 1000, request_id="REQ-SAME"), range(ATTEMPTS))
        assert sum(same) == 1, "IDEMPOTENT_REQUEST_REPLAYED_MULTIPLE_TIMES"
        assert count(file, "request_id='REQ-SAME'") == 1
        print(f"QUEUE_OFFLINE_IDEMPOTENCY_RACE=PASS attempts={ATTEMPTS} accepted={sum(same)} elapsed_seconds={elapsed}")

        with connection(file) as db:
            db.execute("DELETE FROM commander_device_calls")
            db.commit()
        cross, elapsed = group_tasks(
            lambda i: enqueue(file, i + 2000, tenant="T2", user="S2", device="D1"),
            range(ATTEMPTS),
        )
        assert not any(cross), "CROSS_TENANT_ENQUEUE_ALLOWED"
        assert count(file, "1=1") == 0
        print(f"QUEUE_OFFLINE_CROSS_TENANT_DENIAL=PASS attempts={ATTEMPTS} elapsed_seconds={elapsed}")

        # Refill 16, race 256 claim attempts, ensure only one claim per call.
        filled, _ = group_tasks(lambda i: enqueue(file, i + 3000), range(ATTEMPTS))
        assert sum(filled) == 16
        claims, elapsed = group_tasks(
            lambda i: claim(file, i, CREATED), range(ATTEMPTS)
        )
        ids = [x for x in claims if x]
        assert len(ids) == QUEUE_LIMIT and len(set(ids)) == QUEUE_LIMIT, "CALL_CLAIMED_DUPLICATE"
        assert count(file, "state='EXECUTING'") == QUEUE_LIMIT
        with connection(file) as db:
            assert db.execute("SELECT count(*) FROM commander_device_calls WHERE approval_timeout_seconds=0 AND execution_budget_ms=0 AND expires_at_utc=? AND call_result_metadata_json IS NULL", (EXPIRES,)).fetchone()[0] == QUEUE_LIMIT, "LEGACY_PROFILE_OR_TTL_CHANGED"
        print(f"QUEUE_OFFLINE_CLAIM_EXACTLY_ONCE=PASS attempts={ATTEMPTS} claimed={len(ids)} elapsed_seconds={elapsed}")

        # After expiry the existing queue cannot be newly claimed.
        with connection(file) as db:
            db.execute("UPDATE commander_device_calls SET state='PENDING'")
            db.commit()
        future = stamp(CLOCK + timedelta(seconds=60))
        expired, _ = group_tasks(lambda i: claim(file, i, future), range(THREADS))
        assert all(x is None for x in expired), "EXPIRED_CALL_CLAIMED"
        print("QUEUE_OFFLINE_EXPIRED_CALL_NOT_RECLAIMED=PASS")

        # Revocation must be part of the admission SQL, not merely a prior read.
        with connection(file) as db:
            db.execute("DELETE FROM commander_device_calls")
            db.execute("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id='D1'", (CREATED,))
            db.commit()
        after_revoke, _ = group_tasks(lambda i: enqueue(file, i + 4000), range(THREADS))
        assert sum(after_revoke) == 0, "REVOKED_DEVICE_ENQUEUE_ALLOWED"
        print("QUEUE_OFFLINE_REVOKED_DEVICE_ENQUEUE=DENIED")

        with connection(file) as db:
            db.execute("UPDATE commander_devices SET state='ACTIVE',revoked_at_utc=NULL,platform='WINDOWS',agent_version='0.3.49',approval_mode='ASK_EVERY_ACTION' WHERE device_id='D1'")
            db.commit()
        approval, elapsed = group_tasks(lambda i: enqueue(file, i+5000, approval=900, execution=10000, tool="hara.process.run"), range(ATTEMPTS))
        assert sum(approval) == 1, "APPROVAL_MUTATING_ADMISSION_NOT_ATOMIC"
        with connection(file) as db:
            profile = db.execute("SELECT call_id,approval_timeout_seconds,execution_budget_ms,typeof(approval_timeout_seconds),typeof(execution_budget_ms),expires_at_utc,call_result_metadata_json FROM commander_device_calls").fetchone()
            assert profile[1:] == (900,10000,"integer","integer",EXPIRES,None), "APPROVAL_SNAPSHOT_BIND_OR_TYPE_WRONG"
            for assignment in ("approval_timeout_seconds=901", "execution_budget_ms=10001"):
                try:
                    db.execute("UPDATE commander_device_calls SET "+assignment)
                except sqlite3.IntegrityError:
                    pass
                else:
                    raise AssertionError("APPROVAL_SCHEMA_CONSTRAINT_MISSING")
        assert enqueue(file, 6000) == 1, "APPROVAL_BLOCKED_READ_ONLY_CALL"
        claim_at = stamp(CLOCK + timedelta(seconds=30))
        raced, elapsed = group_tasks(lambda i: claim(file,i,claim_at,"0.3.49"),range(ATTEMPTS))
        claimed = [x for x in raced if x]
        assert len(claimed) == len(set(claimed)) == 2 and claimed.count(profile[0]) == 1, "APPROVAL_CLAIM_REPLAYED"
        expected = stamp(CLOCK + timedelta(seconds=30+900+10+60))
        with connection(file) as db:
            assert db.execute("SELECT claimed_at_utc,expires_at_utc FROM commander_device_calls WHERE call_id=?",(profile[0],)).fetchone() == (claim_at,expected), "APPROVAL_CLAIM_DEADLINE_INCOHERENT"
        assert all(x is None for x in group_tasks(lambda i: claim(file,i,stamp(CLOCK+timedelta(seconds=31)),"0.3.49"),range(THREADS))[0]), "APPROVAL_CLAIM_RETRY_RESET"
        print(f"QUEUE_OFFLINE_APPROVAL_PROFILE_CONCURRENCY=PASS attempts={ATTEMPTS} admitted=1 reads_coexist=1 claimed_once=1 deadline_seconds=970")

        with connection(file) as db:
            db.execute("DELETE FROM commander_device_calls")
            db.commit()
        assert enqueue(file,7000,approval=900,execution=3000,tool="hara.process.start") == 1
        for assignment in ("approval_mode='SESSION_TRUSTED'", "approval_mode='ASK_EVERY_ACTION',agent_version='0.3.48'", "agent_version='0.3.49',state='REVOKED',revoked_at_utc='revoked'"):
            with connection(file) as db:
                db.execute("UPDATE commander_devices SET "+assignment+" WHERE device_id='D1'")
                db.commit()
            assert claim(file,0,CREATED,"0.3.49") is None, "APPROVAL_INCOMPATIBLE_SNAPSHOT_CLAIMED"
        print("QUEUE_OFFLINE_APPROVAL_ATOMIC_POLICY_VERSION_REVOCATION=DENIED")
    print("QUEUE_OFFLINE_TOTAL_SECONDS="+str(round(time.monotonic()-start,3)))
    print("QUEUE_OFFLINE_DB_TARGET=TEMPORARY_ISOLATED")


if __name__ == "__main__":
    main()
