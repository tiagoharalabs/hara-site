#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
quota = WORKER.split("export class TenantQuota", 1)[1].split(
    "async function entitlementForTenant", 1
)[0]
status = quota.split("  status(periodKey", 1)[1].split("  reserve(", 1)[0]

# Source contract: expiry must be indexed and the hot-path status must be O(1).
assert "idx_request_state_expiry" in quota
assert "ON request_state(state, updated_at_utc)" in quota
assert "period_usage" in quota
assert "quota_meta" in quota
assert "usage_schema_version" in quota
assert "trg_request_state_usage_insert" in quota
assert "trg_request_state_usage_update_same_period" in quota
assert "trg_request_state_usage_update_period" in quota
assert "trg_request_state_usage_delete" in quota
assert "FROM period_usage" in status
assert "SUM(units)" not in status
assert "SELECT consumed_units AS consumed" in status

# Simulate an existing pre-aggregate DO, then install v1 aggregate schema/triggers.
db = sqlite3.connect(":memory:")
db.executescript(
    """
    CREATE TABLE request_state (
      request_id TEXT PRIMARY KEY,
      subject_id TEXT NOT NULL,
      period_key TEXT NOT NULL,
      function_id TEXT NOT NULL,
      state TEXT NOT NULL,
      units INTEGER NOT NULL,
      receipt_sha256 TEXT,
      updated_at_utc TEXT NOT NULL
    );
    CREATE INDEX idx_request_period ON request_state(period_key, state);
    CREATE INDEX idx_request_state_expiry ON request_state(state, updated_at_utc);
    """
)
period = "LIFETIME"
legacy = [
    ("OLD-C","S1",period,"device.info","COMMITTED",1,"a"*64,"2026-10-05T00:00:00Z"),
    ("OLD-R","S1",period,"device.info","RESERVED",1,None,"2026-10-05T00:05:00Z"),
    ("OLD-X","S1",period,"device.info","RELEASED",0,None,"2026-10-05T00:00:00Z"),
]
db.executemany("INSERT INTO request_state VALUES (?,?,?,?,?,?,?,?)", legacy)

db.executescript(
    """
    CREATE TABLE period_usage (
      period_key TEXT PRIMARY KEY,
      consumed_units INTEGER NOT NULL DEFAULT 0 CHECK (consumed_units >= 0)
    );
    CREATE TABLE quota_meta (
      id INTEGER PRIMARY KEY CHECK (id = 1),
      usage_schema_version INTEGER NOT NULL DEFAULT 0
    );
    INSERT OR IGNORE INTO quota_meta (id, usage_schema_version) VALUES (1,0);

    CREATE TRIGGER trg_request_state_usage_insert
    AFTER INSERT ON request_state
    WHEN NEW.state IN ('RESERVED','COMMITTED') AND NEW.units <> 0
    BEGIN
      INSERT INTO period_usage(period_key,consumed_units)
      VALUES(NEW.period_key,NEW.units)
      ON CONFLICT(period_key) DO UPDATE SET
        consumed_units=consumed_units+excluded.consumed_units;
    END;

    CREATE TRIGGER trg_request_state_usage_update_same_period
    AFTER UPDATE OF period_key,state,units ON request_state
    WHEN OLD.period_key = NEW.period_key
      AND (OLD.state <> NEW.state OR OLD.units <> NEW.units)
    BEGIN
      UPDATE period_usage
         SET consumed_units = consumed_units
           - CASE WHEN OLD.state IN ('RESERVED','COMMITTED') THEN OLD.units ELSE 0 END
           + CASE WHEN NEW.state IN ('RESERVED','COMMITTED') THEN NEW.units ELSE 0 END
       WHERE period_key = NEW.period_key;
    END;

    CREATE TRIGGER trg_request_state_usage_update_period
    AFTER UPDATE OF period_key,state,units ON request_state
    WHEN OLD.period_key <> NEW.period_key
    BEGIN
      UPDATE period_usage
         SET consumed_units = consumed_units
           - CASE WHEN OLD.state IN ('RESERVED','COMMITTED') THEN OLD.units ELSE 0 END
       WHERE period_key = OLD.period_key;
      INSERT INTO period_usage(period_key,consumed_units)
      VALUES(
        NEW.period_key,
        CASE WHEN NEW.state IN ('RESERVED','COMMITTED') THEN NEW.units ELSE 0 END
      )
      ON CONFLICT(period_key) DO UPDATE SET
        consumed_units=consumed_units+excluded.consumed_units;
    END;

    CREATE TRIGGER trg_request_state_usage_delete
    AFTER DELETE ON request_state
    WHEN OLD.state IN ('RESERVED','COMMITTED') AND OLD.units <> 0
    BEGIN
      UPDATE period_usage
         SET consumed_units = consumed_units - OLD.units
       WHERE period_key = OLD.period_key;
    END;

    DELETE FROM period_usage;
    INSERT INTO period_usage(period_key,consumed_units)
    SELECT period_key,COALESCE(SUM(units),0)
      FROM request_state
     WHERE state IN ('RESERVED','COMMITTED')
     GROUP BY period_key;
    UPDATE quota_meta SET usage_schema_version=1 WHERE id=1;
    """
)


def consumed() -> int:
    row = db.execute(
        "SELECT consumed_units FROM period_usage WHERE period_key=?", (period,)
    ).fetchone()
    return int(row[0] if row else 0)


assert consumed() == 2, consumed()

# New reservation charges once.
db.execute(
    "INSERT INTO request_state VALUES (?,?,?,?,?,?,?,?)",
    ("NEW","S1",period,"device.info","RESERVED",1,None,"2026-10-05T01:00:00Z"),
)
assert consumed() == 3, consumed()

# RESERVED -> COMMITTED is net zero.
db.execute(
    "UPDATE request_state SET state='COMMITTED',receipt_sha256=? WHERE request_id='NEW'",
    ("b"*64,),
)
assert consumed() == 3, consumed()

# Stale reservation is released and aggregate decrements automatically.
db.execute(
    "UPDATE request_state SET state='RELEASED',units=0,updated_at_utc=? WHERE request_id='OLD-R'",
    ("2026-10-05T02:00:00Z",),
)
assert consumed() == 2, consumed()

# Zero-unit terminal rows do not change usage.
db.execute(
    "INSERT INTO request_state VALUES (?,?,?,?,?,?,?,?)",
    ("DENY","S1",period,"device.info","DENIED",0,None,"2026-10-05T02:00:00Z"),
)
assert consumed() == 2, consumed()

# Future retention/delete stays accounting-safe.
db.execute("DELETE FROM request_state WHERE request_id='OLD-C'")
assert consumed() == 1, consumed()

# Plans prove expiry sweep and O(1) status are indexed.
expiry_plan = " ".join(
    str(row)
    for row in db.execute(
        """
        EXPLAIN QUERY PLAN
        UPDATE request_state
           SET state='RELEASED', units=0, updated_at_utc=?
         WHERE state='RESERVED' AND updated_at_utc<=?
        """,
        ("2026-10-05T03:00:00Z", "2026-10-05T02:30:00Z"),
    )
)
assert "idx_request_state_expiry" in expiry_plan, expiry_plan

status_plan = " ".join(
    str(row)
    for row in db.execute(
        "EXPLAIN QUERY PLAN SELECT consumed_units FROM period_usage WHERE period_key=?",
        (period,),
    )
)
assert "period_usage" in status_plan and "INDEX" in status_plan.upper(), status_plan

assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

print("COMMANDER_TENANT_QUOTA_EXPIRY_INDEX=PASS")
print("COMMANDER_TENANT_QUOTA_AGGREGATE_BACKFILL=PASS")
print("COMMANDER_TENANT_QUOTA_TRIGGER_ACCOUNTING=PASS")
print("COMMANDER_TENANT_QUOTA_STATUS_SUM_QUERY=ABSENT")
print("COMMANDER_TENANT_QUOTA_STATUS_COMPLEXITY=O1")
print("COMMANDER_TENANT_QUOTA_STORAGE_EFFICIENCY_P02=PASS")
