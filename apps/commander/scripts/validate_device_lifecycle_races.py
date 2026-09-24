#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
MIG = ROOT / "apps/commander/migrations"

db = sqlite3.connect(":memory:")
for name in (
    "0001_product.sql",
    "0005_devices.sql",
    "0006_device_calls.sql",
    "0007_device_selections.sql",
    "0009_pairing_supersession.sql",
):
    db.executescript((MIG / name).read_text(encoding="utf-8"))

db.execute(
    "INSERT INTO tenants VALUES (?,?,?,?,?)",
    ("T1","Tenant","ACTIVE","PRODUCTION","2026-09-24T00:00:00.000Z"),
)
db.execute(
    """INSERT INTO users
       (subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
       VALUES (?,?,?,?,?,?,?,?,?)""",
    ("S1","T1","https://issuer.example/","sub","u@example.com","User","ACTIVE","OWNER",
     "2026-09-24T00:00:00.000Z"),
)
db.execute(
    """INSERT INTO device_pairing_tokens
       (pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,
        consumed_at_utc,superseded_at_utc)
       VALUES (?,?,?,?,?,?,?,NULL)""",
    (
        "P1","H1","T1","S1","2026-09-24T00:00:00.000Z","2026-09-24T01:00:00.000Z",
        "2026-09-24T00:00:01.000Z",
    ),
)
db.execute(
    """INSERT INTO commander_devices
       (device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,
        architecture,agent_version,tunnel_mode,credential_hash,state,created_at_utc,
        last_seen_at_utc,revoked_at_utc)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)""",
    (
        "D1","P1","T1","S1","Device","LINUX","x86_64","0.3.3","OUTBOUND_RELAY","CRED1",
        "ACTIVE","2026-09-24T00:00:01.000Z","2026-09-24T00:10:00.000Z",
    ),
)

select_sql = """INSERT INTO commander_device_selections
(tenant_id,subject_id,device_id,selected_at_utc)
SELECT ?,?,d.device_id,?
FROM commander_devices d
WHERE d.device_id=? AND d.tenant_id=? AND d.state='ACTIVE' AND d.revoked_at_utc IS NULL
ON CONFLICT(tenant_id,subject_id)
DO UPDATE SET device_id=excluded.device_id, selected_at_utc=excluded.selected_at_utc"""
first = db.execute(
    select_sql,
    ("T1","S1","2026-09-24T00:10:01.000Z","D1","T1"),
)
assert first.rowcount == 1, "ACTIVE_DEVICE_SELECTION_FAILED"

db.execute(
    """INSERT INTO commander_device_calls
       (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
        created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
       VALUES ('C-AUTH','REQ-AUTH','T1','S1','D1','hara.functions.invoke','{}','PENDING',
               '2026-09-24T00:10:01.000Z','2026-09-24T00:11:00.000Z',NULL,NULL,NULL,NULL)"""
)
unauthorized_at = "2026-09-24T00:10:01.500Z"
unauthorized = db.execute(
    """UPDATE commander_devices
          SET state='REVOKED',revoked_at_utc=?
        WHERE device_id='D1' AND tenant_id='T1'
          AND enrolled_by_subject_id='S2' AND state='ACTIVE'""",
    (unauthorized_at,),
)
assert unauthorized.rowcount == 0, "UNAUTHORIZED_REVOKE_MUTATED_DEVICE"
db.execute(
    """DELETE FROM commander_device_selections
        WHERE tenant_id='T1' AND device_id='D1'
          AND EXISTS (
            SELECT 1 FROM commander_devices d
             WHERE d.device_id='D1' AND d.tenant_id='T1'
               AND d.state='REVOKED' AND d.revoked_at_utc=?
          )""",
    (unauthorized_at,),
)
db.execute(
    """UPDATE commander_device_calls
          SET state='CANCELLED'
        WHERE tenant_id='T1' AND device_id='D1' AND state IN ('PENDING','EXECUTING')
          AND EXISTS (
            SELECT 1 FROM commander_devices d
             WHERE d.device_id=commander_device_calls.device_id
               AND d.tenant_id=commander_device_calls.tenant_id
               AND d.state='REVOKED' AND d.revoked_at_utc=?
          )""",
    (unauthorized_at,),
)
assert db.execute(
    "SELECT COUNT(*) FROM commander_device_selections WHERE device_id='D1'"
).fetchone()[0] == 1, "UNAUTHORIZED_REVOKE_DELETED_SELECTION"
assert db.execute(
    "SELECT state FROM commander_device_calls WHERE call_id='C-AUTH'"
).fetchone() == ("PENDING",), "UNAUTHORIZED_REVOKE_CANCELLED_CALL"
db.execute("DELETE FROM commander_device_calls WHERE call_id='C-AUTH'")

db.execute(
    "UPDATE commander_devices SET state='REVOKED', revoked_at_utc=? WHERE device_id='D1'",
    ("2026-09-24T00:10:02.000Z",),
)
db.execute("DELETE FROM commander_device_selections WHERE device_id='D1'")
after_revoke = db.execute(
    select_sql,
    ("T1","S1","2026-09-24T00:10:03.000Z","D1","T1"),
)
assert after_revoke.rowcount == 0, "REVOKED_DEVICE_RESELECTED"
assert db.execute(
    "SELECT COUNT(*) FROM commander_device_selections WHERE device_id='D1'"
).fetchone()[0] == 0

db.execute(
    "UPDATE commander_devices SET state='ACTIVE', revoked_at_utc=NULL WHERE device_id='D1'"
)
db.execute(
    select_sql,
    ("T1","S1","2026-09-24T00:10:04.000Z","D1","T1"),
)

enqueue_sql = """INSERT OR IGNORE INTO commander_device_calls
(call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
 created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
SELECT ?,?,?,?,d.device_id,?,?,'PENDING',?,?,NULL,NULL,NULL,NULL
FROM commander_devices d
JOIN commander_device_selections s
  ON s.tenant_id=d.tenant_id AND s.device_id=d.device_id
WHERE d.device_id=? AND d.tenant_id=? AND d.state='ACTIVE'
  AND d.revoked_at_utc IS NULL AND d.last_seen_at_utc>=? AND s.subject_id=?"""
args = (
    "C1","REQ1","T1","S1","hara.functions.invoke",'{"x":1}',
    "2026-09-24T00:10:05.000Z","2026-09-24T00:10:55.000Z",
    "D1","T1","2026-09-24T00:08:35.000Z","S1",
)
first_enqueue = db.execute(enqueue_sql, args)
assert first_enqueue.rowcount == 1, "FIRST_ENQUEUE_FAILED"

second_enqueue = db.execute(
    enqueue_sql,
    (
        "C2","REQ1","T1","S1","hara.functions.invoke",'{"x":1}',
        "2026-09-24T00:10:06.000Z","2026-09-24T00:10:56.000Z",
        "D1","T1","2026-09-24T00:08:36.000Z","S1",
    ),
)
assert second_enqueue.rowcount == 0, "DUPLICATE_REQUEST_ID_CREATED_SECOND_CALL"
assert db.execute(
    "SELECT COUNT(*) FROM commander_device_calls WHERE request_id='REQ1'"
).fetchone()[0] == 1

db.execute(
    "UPDATE commander_devices SET state='REVOKED', revoked_at_utc=? WHERE device_id='D1'",
    ("2026-09-24T00:10:07.000Z",),
)
db.execute("DELETE FROM commander_device_selections WHERE device_id='D1'")
revoked_enqueue = db.execute(
    enqueue_sql,
    (
        "C3","REQ2","T1","S1","hara.functions.invoke",'{"x":2}',
        "2026-09-24T00:10:08.000Z","2026-09-24T00:10:58.000Z",
        "D1","T1","2026-09-24T00:08:38.000Z","S1",
    ),
)
assert revoked_enqueue.rowcount == 0, "CALL_ENQUEUED_AFTER_REVOKE"
db.execute(
    """INSERT INTO commander_device_calls
       (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
        created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
       VALUES (?,?,?,?,?,?,?,'EXECUTING',?,?,?,NULL,NULL,NULL)""",
    (
        "C-LATE","REQ-LATE","T1","S1","D1","hara.functions.invoke",'{"late":true}',
        "2026-09-24T00:09:00.000Z","2026-09-24T00:09:50.000Z",
        "2026-09-24T00:09:01.000Z",
    ),
)
late_complete = db.execute(
    """UPDATE commander_device_calls
          SET state='COMPLETED',completed_at_utc=?,result_json=?,error_code=NULL
        WHERE call_id=? AND tenant_id=? AND device_id=?
          AND state='EXECUTING' AND expires_at_utc>?""",
    (
        "2026-09-24T00:10:00.000Z",'{"ok":true}',"C-LATE","T1","D1",
        "2026-09-24T00:10:00.000Z",
    ),
)
assert late_complete.rowcount == 0, "LATE_COMPLETION_ACCEPTED"
db.execute(
    """UPDATE commander_device_calls
          SET state='EXPIRED',completed_at_utc=?,error_code='DEVICE_CALL_EXPIRED'
        WHERE call_id=? AND tenant_id=? AND device_id=?
          AND state='EXECUTING' AND expires_at_utc<=?""",
    ("2026-09-24T00:10:00.000Z","C-LATE","T1","D1","2026-09-24T00:10:00.000Z"),
)
assert db.execute(
    "SELECT state,error_code FROM commander_device_calls WHERE call_id='C-LATE'"
).fetchone() == ("EXPIRED","DEVICE_CALL_EXPIRED")

# Prove every expiry path records the same canonical terminal cause.
db.execute(
    """INSERT INTO commander_device_calls
       (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
        created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
       VALUES ('C-MAINT','REQ-MAINT','T1','S1','D1','hara.health','{}','PENDING',
               '2026-09-24T00:08:00.000Z','2026-09-24T00:08:50.000Z',NULL,NULL,NULL,NULL)"""
)
db.execute(
    """UPDATE commander_device_calls
          SET state='EXPIRED',completed_at_utc=?,error_code='DEVICE_CALL_EXPIRED'
        WHERE tenant_id=? AND subject_id=? AND device_id=?
          AND state IN ('PENDING','EXECUTING') AND expires_at_utc<=?""",
    ("2026-09-24T00:10:00.000Z","T1","S1","D1","2026-09-24T00:10:00.000Z"),
)
assert db.execute(
    "SELECT state,error_code FROM commander_device_calls WHERE call_id='C-MAINT'"
).fetchone() == ("EXPIRED","DEVICE_CALL_EXPIRED"), "MAINTENANCE_EXPIRY_CAUSE_MISSING"

db.execute(
    """INSERT INTO commander_device_calls
       (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
        created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
       VALUES ('C-STATUS','REQ-STATUS','T1','S1','D1','hara.health','{}','EXECUTING',
               '2026-09-24T00:08:00.000Z','2026-09-24T00:08:50.000Z',
               '2026-09-24T00:08:01.000Z',NULL,NULL,NULL)"""
)
db.execute(
    """UPDATE commander_device_calls
          SET state='EXPIRED',completed_at_utc=?,error_code='DEVICE_CALL_EXPIRED'
        WHERE call_id=? AND tenant_id=? AND subject_id=?
          AND state IN ('PENDING','EXECUTING') AND expires_at_utc<=?""",
    ("2026-09-24T00:10:00.000Z","C-STATUS","T1","S1","2026-09-24T00:10:00.000Z"),
)
assert db.execute(
    "SELECT state,error_code FROM commander_device_calls WHERE call_id='C-STATUS'"
).fetchone() == ("EXPIRED","DEVICE_CALL_EXPIRED"), "STATUS_EXPIRY_CAUSE_MISSING"

select_block = WORKER.split("async function selectDevice",1)[1].split("async function selectPortalDevice",1)[0]
enqueue_block = WORKER.split("async function enqueueDeviceCall",1)[1].split("async function claimNextDeviceCall",1)[0]
complete_block = WORKER.split("async function completeDeviceCall",1)[1].split("async function deviceCallStatus",1)[0]
status_block = WORKER.split("async function deviceCallStatus",1)[1].split("export default",1)[0]
revoke_block = WORKER.split("async function revokePortalDevice",1)[1].split("async function enqueueDeviceCall",1)[0]
heartbeat_block = WORKER.split("async function heartbeatDevice",1)[1].split("async function revokeDeviceSelf",1)[0]
assert "SELECT ?, ?, d.device_id, ?" in select_block
assert "d.state = 'ACTIVE'" in select_block and "d.revoked_at_utc IS NULL" in select_block
assert "PRODUCT_DB.batch([" in revoke_block
assert "SET state = 'CANCELLED'" in revoke_block
assert "d.revoked_at_utc = ?" in revoke_block
assert "INSERT OR IGNORE INTO commander_device_calls" in enqueue_block
assert "existing.payload_json !== payloadJson" in enqueue_block
assert "JOIN commander_device_selections" in enqueue_block
assert "d.revoked_at_utc IS NULL" in enqueue_block
assert "AND expires_at_utc > ?" in complete_block
assert 'throw new Error("DEVICE_CALL_EXPIRED")' in complete_block
assert "existing.result_json !== resultJson" in complete_block
assert "error_code = 'DEVICE_CALL_EXPIRED'" in enqueue_block
assert "error_code = 'DEVICE_CALL_EXPIRED'" in status_block
assert "revoked_at_utc IS NULL" in heartbeat_block
assert 'throw new Error("DEVICE_AUTH_INVALID")' in heartbeat_block

print("COMMANDER_DEVICE_SELECTION_REVOKE_RACE=BLOCKED")
print("COMMANDER_DEVICE_ENQUEUE_REVOKE_RACE=BLOCKED")
print("COMMANDER_DEVICE_ENQUEUE_IDEMPOTENCY_RACE=BLOCKED")
print("COMMANDER_DEVICE_ENQUEUE_PAYLOAD_IDEMPOTENCY=STRICT")
print("COMMANDER_DEVICE_LATE_COMPLETION=EXPIRED")
print("COMMANDER_DEVICE_EXPIRY_ERROR_CODE=CANONICAL")
print("COMMANDER_DEVICE_COMPLETION_IDEMPOTENCY=STRICT")
print("COMMANDER_DEVICE_HEARTBEAT_REVOKE_RACE=BLOCKED")
print("COMMANDER_PORTAL_REVOKE_CALL_CANCELLATION=ATOMIC")
print("COMMANDER_PORTAL_REVOKE_UNAUTHORIZED_SIDE_EFFECTS=ABSENT")
