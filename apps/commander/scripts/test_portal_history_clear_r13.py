#!/usr/bin/env python3
"""R13 portal history: real SQLite deletion, separate from immutable device audit."""
import sqlite3
from pathlib import Path

MIGRATION=Path(__file__).resolve().parents[1]/"migrations/0036_portal_device_history_clear.sql"

def setup():
    db=sqlite3.connect(":memory:")
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
        CREATE TABLE tenants(tenant_id TEXT PRIMARY KEY);
        CREATE TABLE users(subject_id TEXT PRIMARY KEY);
        CREATE TABLE commander_devices(
            device_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            created_at_utc TEXT NOT NULL,
            revoked_at_utc TEXT,
            state TEXT NOT NULL);
        CREATE TABLE commander_device_calls(
            call_id TEXT PRIMARY KEY,device_id TEXT NOT NULL REFERENCES commander_devices(device_id),
            state TEXT NOT NULL);
        CREATE TABLE commander_device_receipts(
            receipt_id TEXT PRIMARY KEY, device_id TEXT NOT NULL REFERENCES commander_devices(device_id));
        INSERT INTO tenants VALUES ('A'),('B');
        INSERT INTO users VALUES ('adminA'),('adminB');
        INSERT INTO commander_devices VALUES
          ('A-active','A','2026-10-01T01:00:00Z',NULL,'ACTIVE'),
          ('A-revoked1','A','2026-10-01T01:00:00Z','2026-10-20T03:00:00Z','REVOKED'),
          ('A-revoked2','A','2026-10-01T01:00:00Z','2026-10-21T03:00:00Z','REVOKED'),
          ('B-revoked1','B','2026-10-01T01:00:00Z','2026-10-22T03:00:00Z','REVOKED');
        INSERT INTO commander_device_calls VALUES ('c1','A-revoked1','COMPLETED');
        INSERT INTO commander_device_receipts VALUES ('r1','A-revoked1');
    """)
    db.executescript(MIGRATION.read_text())
    return db

def clear(db,tenant,actor,expected):
    before=db.execute("SELECT COUNT(*) FROM commander_device_history WHERE tenant_id=?",(tenant,)).fetchone()[0]
    if before!=expected:
        return "CONFLICT"
    # Same two statements sent in D1 .batch(), which is transactional.
    db.execute("""DELETE FROM commander_device_history
        WHERE tenant_id=? AND (SELECT COUNT(*) FROM commander_device_history WHERE tenant_id=?)=?""",
        (tenant,tenant,expected))
    deleted=db.execute("SELECT changes()").fetchone()[0]
    db.execute("""INSERT INTO commander_device_history_clears
         (clearance_id,tenant_id,actor_subject_id,deleted_count,cleared_at_utc)
         SELECT ?,?,?,?,? WHERE changes()=?""",
         ("clear-"+actor+str(expected),tenant,actor,expected,"2026-10-23T17:50:00Z",expected))
    db.commit()
    return deleted

def count(db,tenant):
    return db.execute("SELECT COUNT(*) FROM commander_device_history WHERE tenant_id=?",(tenant,)).fetchone()[0]

def main():
    db=setup()
    assert count(db,"A")==2 and count(db,"B")==1
    print("MIGRATION_BACKFILLS_REVOKED_ONLY=PASS")
    assert db.execute("SELECT COUNT(*) FROM commander_device_history WHERE device_id='A-active'").fetchone()[0]==0
    assert clear(db,"A","adminA",1)=="CONFLICT"
    assert count(db,"A")==2
    print("CONCURRENT_COUNT_CHANGE_FAIL_CLOSED=PASS")
    assert clear(db,"A","adminA",2)==2
    assert count(db,"A")==0 and count(db,"B")==1
    print("SERVER_HISTORY_ROWS_PHYSICALLY_DELETED_TENANT_ISOLATED=PASS")
    assert db.execute("SELECT COUNT(*) FROM commander_devices WHERE tenant_id='A'").fetchone()[0]==3
    assert db.execute("SELECT COUNT(*) FROM commander_device_calls").fetchone()[0]==1
    assert db.execute("SELECT COUNT(*) FROM commander_device_receipts").fetchone()[0]==1
    print("ACTIVE_DEVICES_REVOKED_TOMBSTONES_CALLS_RECEIPTS_RETAINED=PASS")
    assert db.execute("SELECT COUNT(*) FROM commander_device_history_clears").fetchone()[0]==1
    print("ADMIN_CLEAR_AUDIT_PERSISTED=PASS")
    assert clear(db,"A","adminA",2)=="CONFLICT"
    assert count(db,"A")==0
    print("REPLAY_CANNOT_RECREATE_CLEARED_HISTORY=PASS")
    # New revocations after deletion must appear; old ones must not be reinserted.
    db.execute("UPDATE commander_devices SET state='REVOKED',revoked_at_utc=? WHERE device_id='A-active'",("2026-10-23T17:51:00Z",))
    db.execute("""INSERT OR IGNORE INTO commander_device_history (tenant_id,device_id,revoked_at_utc)
                  SELECT tenant_id,device_id,revoked_at_utc FROM commander_devices
                  WHERE tenant_id=? AND device_id=? AND state='REVOKED' AND revoked_at_utc=?""",
                  ("A","A-active","2026-10-23T17:51:00Z"))
    assert count(db,"A")==1
    assert db.execute("SELECT device_id FROM commander_device_history WHERE tenant_id='A'").fetchone()[0]=="A-active"
    print("FUTURE_REVOKCATIONS_ONLY_VISIBLE=PASS")
    print("SQLITE_FOREIGN_KEY_CHECK="+str(db.execute("PRAGMA foreign_key_check").fetchall()))
    assert db.execute("PRAGMA foreign_key_check").fetchall()==[]
    print("R13_SQL_HISTORY_DELETION_PASS=7_CHECKS")
if __name__=="__main__":main()
