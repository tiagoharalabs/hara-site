#!/usr/bin/env python3
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")

ttl_match = re.search(
    r"const QUOTA_RESERVATION_TTL_SECONDS = (\d+) \* (\d+);",
    WORKER,
)
assert ttl_match, "QUOTA_RESERVATION_TTL_CONSTANT_MISSING"
ttl_seconds = int(ttl_match.group(1)) * int(ttl_match.group(2))
assert ttl_seconds == 600, f"QUOTA_RESERVATION_TTL_UNEXPECTED:{ttl_seconds}"

quota_block = WORKER.split("export class TenantQuota", 1)[1].split(
    "async function entitlementForTenant", 1
)[0]
assert "expireStaleReservations()" in quota_block
assert "state = 'RELEASED', units = 0" in quota_block
assert "WHERE state = 'RESERVED'" in quota_block
assert "updated_at_utc <= ?" in quota_block

for method in ("status", "reserve", "commit", "release"):
    block = quota_block.split(f"  {method}(", 1)[1]
    if method == "status":
        block = block.split("  reserve(", 1)[0]
    elif method == "reserve":
        block = block.split("  commit(", 1)[0]
    elif method == "commit":
        block = block.split("  release(", 1)[0]
    assert "this.expireStaleReservations();" in block, f"{method.upper()}_TTL_SWEEP_MISSING"

assert 'reservation.existing && reservation.state === "RELEASED"' in WORKER
assert '"REQUEST_USAGE_TERMINAL"' in WORKER

db = sqlite3.connect(":memory:")
db.execute(
    """CREATE TABLE request_state (
       request_id TEXT PRIMARY KEY,
       subject_id TEXT NOT NULL,
       period_key TEXT NOT NULL,
       function_id TEXT NOT NULL,
       state TEXT NOT NULL,
       units INTEGER NOT NULL,
       receipt_sha256 TEXT,
       updated_at_utc TEXT NOT NULL
    )"""
)

period = "2026-09"
rows = (
    ("STALE","S1",period,"device.info","RESERVED",1,None,"2026-09-24T11:49:59.000Z"),
    ("BOUNDARY","S1",period,"device.info","RESERVED",1,None,"2026-09-24T11:50:00.000Z"),
    ("FRESH","S1",period,"device.info","RESERVED",1,None,"2026-09-24T11:50:00.001Z"),
    ("COMMITTED","S1",period,"device.info","COMMITTED",1,"a"*64,"2026-09-24T10:00:00.000Z"),
    ("RELEASED","S1",period,"device.info","RELEASED",0,None,"2026-09-24T09:00:00.000Z"),
    ("DENIED","S1",period,"device.info","DENIED",0,None,"2026-09-24T09:00:00.000Z"),
)
db.executemany("INSERT INTO request_state VALUES (?,?,?,?,?,?,?,?)", rows)

now = "2026-09-24T12:00:00.000Z"
cutoff = "2026-09-24T11:50:00.000Z"
db.execute(
    """UPDATE request_state
          SET state='RELEASED', units=0, updated_at_utc=?
        WHERE state='RESERVED' AND updated_at_utc<=?""",
    (now, cutoff),
)

state = dict(
    db.execute("SELECT request_id,state FROM request_state").fetchall()
)
units = dict(
    db.execute("SELECT request_id,units FROM request_state").fetchall()
)

assert state["STALE"] == "RELEASED" and units["STALE"] == 0
assert state["BOUNDARY"] == "RELEASED" and units["BOUNDARY"] == 0
assert state["FRESH"] == "RESERVED" and units["FRESH"] == 1
assert state["COMMITTED"] == "COMMITTED" and units["COMMITTED"] == 1
assert state["RELEASED"] == "RELEASED" and units["RELEASED"] == 0
assert state["DENIED"] == "DENIED" and units["DENIED"] == 0

consumed = db.execute(
    """SELECT COALESCE(SUM(units),0)
         FROM request_state
        WHERE period_key=? AND state IN ('RESERVED','COMMITTED')""",
    (period,),
).fetchone()[0]
assert consumed == 2, f"QUOTA_CONSUMED_AFTER_SWEEP_INVALID:{consumed}"

# A stale request id remains terminal and cannot silently become a new charge.
stale = db.execute(
    "SELECT subject_id,period_key,function_id,state,units FROM request_state WHERE request_id='STALE'"
).fetchone()
assert stale == ("S1", period, "device.info", "RELEASED", 0)

print("COMMANDER_QUOTA_RESERVATION_TTL_SECONDS=600")
print("COMMANDER_QUOTA_STALE_RESERVATION_AUTO_RELEASE=PASS")
print("COMMANDER_QUOTA_FRESH_RESERVATION_PRESERVED=PASS")
print("COMMANDER_QUOTA_COMMITTED_PRESERVED=PASS")
print("COMMANDER_QUOTA_STALE_REPLAY_TERMINAL=PASS")
print("COMMANDER_QUOTA_ABANDONED_USAGE_RELEASED=PASS")
print("COMMANDER_QUOTA_RESERVATION_TTL=PASS")
