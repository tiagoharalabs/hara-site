#!/usr/bin/env python3
"""Offline concurrent stress for EXACT Worker SQLite enqueue/claim SQL.

Runs only a temporary local SQLite DB with the current 30 real migrations.
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
assert ENQUEUE_SQL.count("?") == 25
assert CLAIM_SQL.count("?") == 3
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
    assert len(list(MIGRATIONS.glob("*.sql"))) == 30
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


def enqueue(dbfile: Path, i: int, *, tenant="T1", user="S1", device="D1", request_id=None) -> int:
    db = connection(dbfile)
    try:
        request = request_id or ("REQ-" + str(i))
        params = (
            "CALL-" + tenant + "-" + str(i), request, tenant, user, "hara.ping", "{}",
            CREATED, EXPIRES, "UNMETERED", 0, None,
            "UNMETERED", None, CREATED, 0,
            device, tenant, CUTOFF_7H, CUTOFF_ONLINE,
            CREATED, QUEUE_LIMIT,
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


def claim(dbfile: Path, i: int, when: str) -> str | None:
    db = connection(dbfile)
    try:
        row = db.execute(CLAIM_SQL, (when, "D1", when)).fetchone()
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
    print("QUEUE_OFFLINE_TOTAL_SECONDS="+str(round(time.monotonic()-start,3)))
    print("QUEUE_OFFLINE_DB_TARGET=TEMPORARY_ISOLATED")


if __name__ == "__main__":
    main()
