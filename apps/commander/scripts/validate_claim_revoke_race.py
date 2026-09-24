#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[3]
MIG = ROOT / "apps/commander/migrations"
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")

db = sqlite3.connect(":memory:")
for name in ("0001_product.sql","0005_devices.sql","0006_device_calls.sql"):
    db.executescript((MIG / name).read_text(encoding="utf-8"))

db.execute("INSERT INTO tenants VALUES (?,?,?,?,?)",
           ("T1","Tenant","ACTIVE","PRODUCTION","2026-09-24T00:00:00.000Z"))
db.execute("""INSERT INTO users
(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES (?,?,?,?,?,?,?,?,?)""",
           ("S1","T1","https://issuer.example/","sub","u@example.com","User","ACTIVE","OWNER",
            "2026-09-24T00:00:00.000Z"))
db.execute("""INSERT INTO device_pairing_tokens
(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc)
VALUES ('P1','H1','T1','S1','2026-09-24T00:00:00.000Z','2026-09-25T00:00:00.000Z',
        '2026-09-24T00:01:00.000Z')""")
db.execute("""INSERT INTO commander_devices
(device_id,pairing_id,tenant_id,enrolled_by_subject_id,device_name,platform,architecture,
 agent_version,tunnel_mode,credential_hash,state,created_at_utc,last_seen_at_utc,revoked_at_utc)
VALUES ('D1','P1','T1','S1','Device','LINUX','x86_64','0.3.3','OUTBOUND_RELAY',
        'CRED','ACTIVE','2026-09-24T00:01:00.000Z','2026-09-24T00:10:00.000Z',NULL)""")
def add_call(call_id, request_id, state="PENDING"):
    db.execute("""INSERT INTO commander_device_calls
    (call_id,request_id,tenant_id,subject_id,device_id,tool_id,payload_json,state,
     created_at_utc,expires_at_utc,claimed_at_utc,completed_at_utc,result_json,error_code)
    VALUES (?,?,?,?,?,?,?,?,'2026-09-24T00:10:00.000Z','2026-09-24T00:20:00.000Z',
            NULL,NULL,NULL,NULL)""",
               (call_id,request_id,"T1","S1","D1","hara.health","{}",state))

claim_sql = """UPDATE commander_device_calls
SET state='EXECUTING', claimed_at_utc=?
WHERE call_id=(
  SELECT c.call_id
  FROM commander_device_calls c
  JOIN commander_devices d
    ON d.device_id=c.device_id
   AND d.tenant_id=c.tenant_id
  WHERE c.device_id=?
    AND c.state='PENDING'
    AND c.expires_at_utc>?
    AND d.state='ACTIVE'
    AND d.revoked_at_utc IS NULL
  ORDER BY c.created_at_utc
  LIMIT 1
)
RETURNING call_id,state"""

add_call("C1","R1")
row = db.execute(claim_sql,("2026-09-24T00:11:00.000Z","D1","2026-09-24T00:11:00.000Z")).fetchone()
assert row == ("C1","EXECUTING"), f"ACTIVE_DEVICE_CLAIM_FAILED:{row}"
add_call("C2","R2")
db.execute("""UPDATE commander_devices
SET state='REVOKED', revoked_at_utc='2026-09-24T00:12:00.000Z'
WHERE device_id='D1'""")

row = db.execute(claim_sql,("2026-09-24T00:12:01.000Z","D1","2026-09-24T00:12:01.000Z")).fetchone()
assert row is None, f"REVOKED_DEVICE_CLAIMED:{row}"
state = db.execute("SELECT state FROM commander_device_calls WHERE call_id='C2'").fetchone()[0]
assert state == "PENDING", f"REVOKED_DEVICE_CALL_MUTATED:{state}"

claim = WORKER.split("async function claimNextDeviceCall",1)[1].split(
    "async function completeDeviceCall",1
)[0]
assert "JOIN commander_devices d" in claim, "CLAIM_DEVICE_REVALIDATION_JOIN_MISSING"
assert "d.state = 'ACTIVE'" in claim, "CLAIM_ACTIVE_GUARD_MISSING"
assert "d.revoked_at_utc IS NULL" in claim, "CLAIM_REVOKE_GUARD_MISSING"

print("COMMANDER_ACTIVE_DEVICE_CLAIM=PASS")
print("COMMANDER_REVOKED_DEVICE_CLAIM=DENIED")
print("COMMANDER_CLAIM_REVOKE_TOCTOU=BLOCKED")
