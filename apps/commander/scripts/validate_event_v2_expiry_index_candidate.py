#!/usr/bin/env python3
"""Offline proof for the non-executable Event V2 expiry-index candidate."""

from __future__ import annotations

import runpy
import sqlite3
from pathlib import Path

COMMANDER = Path(__file__).resolve().parent.parent
CANDIDATE = COMMANDER / "candidate" / "0012_event_v2_drop_redundant_expiry_index.sql"
MIGRATION_0011 = COMMANDER / "migrations" / "0011_event_v2_transport.sql"
SCHEMA_VALIDATOR = COMMANDER / "scripts" / "validate_event_v2_schema_0011.py"
WORKER = COMMANDER / "src" / "worker.js"
MIGRATIONS = COMMANDER / "migrations"


def plan(db: sqlite3.Connection, sql: str, args: tuple) -> tuple[str, ...]:
    return tuple(
        str(row[3])
        for row in db.execute("EXPLAIN QUERY PLAN " + sql, args).fetchall()
    )


QUERIES = {
    "self_revoke": (
        """UPDATE commander_device_calls
              SET state='CANCELLED', completed_at_utc=?, error_code='DEVICE_REVOKED'
            WHERE tenant_id=? AND device_id=?
              AND state IN ('PENDING','EXECUTING')""",
        ("2026-09-26T00:00:00Z", "T1", "D1"),
    ),
    "cleanup": (
        """UPDATE commander_device_calls INDEXED BY idx_device_calls_poll
              SET state='EXPIRED', completed_at_utc=?, error_code='DEVICE_CALL_EXPIRED'
            WHERE tenant_id=? AND subject_id=? AND device_id=?
              AND state IN ('PENDING','EXECUTING')
              AND expires_at_utc<=?""",
        (
            "2026-09-26T00:00:00Z",
            "T1",
            "S1",
            "D1",
            "2026-09-26T00:00:00Z",
        ),
    ),
    "active_count": (
        """SELECT COUNT(*)
             FROM commander_device_calls INDEXED BY idx_device_calls_poll
            WHERE device_id=? AND tenant_id=?
              AND state IN ('PENDING','EXECUTING')
              AND expires_at_utc>?""",
        ("D1", "T1", "2026-09-26T00:00:00Z"),
    ),
    "claim": (
        """SELECT c.call_id
             FROM commander_device_calls AS c INDEXED BY idx_device_calls_poll
            WHERE c.device_id=?
              AND c.state='PENDING'
              AND c.expires_at_utc>?
            ORDER BY c.created_at_utc
            LIMIT 1""",
        ("D1", "2026-09-26T00:00:00Z"),
    ),
    "complete": (
        """UPDATE commander_device_calls
              SET state=?, completed_at_utc=?, result_json=?, error_code=?
            WHERE call_id=? AND tenant_id=? AND device_id=?
              AND state='EXECUTING' AND expires_at_utc>?""",
        (
            "COMPLETED",
            "2026-09-26T00:00:00Z",
            "{}",
            None,
            "C1",
            "T1",
            "D1",
            "2026-09-25T00:00:00Z",
        ),
    ),
    "status": (
        """SELECT call_id, state
             FROM commander_device_calls
            WHERE call_id=? AND tenant_id=? AND subject_id=?
            LIMIT 1""",
        ("C1", "T1", "S1"),
    ),
}


def explicit_indexes(db: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in db.execute(
            """
            SELECT name
              FROM sqlite_master
             WHERE type='index'
               AND name NOT LIKE 'sqlite_autoindex_%'
            """
        )
    }


def main() -> int:
    candidate_sql = CANDIDATE.read_text(encoding="utf-8")
    migration_sql = MIGRATION_0011.read_text(encoding="utf-8")
    worker = WORKER.read_text(encoding="utf-8")

    assert "DROP INDEX IF EXISTS idx_device_calls_expiry;" in candidate_sql
    assert "DEV_APPLY=DENY" in candidate_sql
    assert "PROD_APPLY=DENY" in candidate_sql
    assert not (MIGRATIONS / "0012_event_v2_drop_redundant_expiry_index.sql").exists()

    assert "idx_device_calls_expiry" not in worker
    assert worker.count("INDEXED BY idx_device_calls_poll") >= 4

    schema_module = runpy.run_path(str(SCHEMA_VALIDATOR))
    base_schema = schema_module["BASE_SCHEMA"]

    db = sqlite3.connect(":memory:")
    db.executescript(base_schema)
    db.executescript(migration_sql)

    before_indexes = explicit_indexes(db)
    assert "idx_device_calls_poll" in before_indexes
    assert "idx_device_calls_tenant" in before_indexes
    assert "idx_device_calls_expiry" in before_indexes

    before_plans = {
        name: plan(db, sql, args)
        for name, (sql, args) in QUERIES.items()
    }

    db.executescript(candidate_sql)

    after_indexes = explicit_indexes(db)
    assert "idx_device_calls_poll" in after_indexes
    assert "idx_device_calls_tenant" in after_indexes
    assert "idx_device_calls_expiry" not in after_indexes

    after_plans = {
        name: plan(db, sql, args)
        for name, (sql, args) in QUERIES.items()
    }

    assert after_plans == before_plans

    joined = {
        name: " | ".join(rows)
        for name, rows in after_plans.items()
    }
    assert "idx_device_calls_tenant" in joined["self_revoke"]
    assert "idx_device_calls_poll" in joined["cleanup"]
    assert "idx_device_calls_poll" in joined["active_count"]
    assert "idx_device_calls_poll" in joined["claim"]
    assert "sqlite_autoindex_commander_device_calls_1" in joined["complete"]
    assert "sqlite_autoindex_commander_device_calls_1" in joined["status"]

    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []

    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE=PASS")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_SOURCE_ONLY=TRUE")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_DEV_APPLY=DENY")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_PROD_APPLY=DENY")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_PLAN_DELTA=NONE")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_POLL_INDEX=PRESERVED")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_TENANT_INDEX=PRESERVED")
    print("COMMANDER_EVENT_V2_EXPIRY_INDEX_CANDIDATE_LIVE_D1_SAVINGS=MEASURE_REQUIRED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
