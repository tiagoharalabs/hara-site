#!/usr/bin/env python3
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps"/"commander"
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")

def need(ok, code):
    if not ok:
        raise AssertionError("COMMANDER_PORTAL_ACTIVITY_"+code+"=FAIL")
    print("COMMANDER_PORTAL_ACTIVITY_"+code+"=PASS")

need("async function portalActivity" in WORKER,"FUNCTION_PRESENT")
block=WORKER.split("async function portalActivity",1)[1].split("async function executeCustomerMcpTool",1)[0]
need('["OWNER","ADMIN"]' in block,"PRIVILEGED_SCOPE")
need('clauses=["c.tenant_id = ?"]' in block and 'clauses.push("c.subject_id = ?")' in block,"SUBJECT_SCOPE")
need("payload_json" not in block and "result_json" not in block,"CONTENT_NOT_SELECTED")
need("payload_values_exposed:false" in block and "result_values_exposed:false" in block and "request_id_exposed:false" in block,"PRIVACY_MARKERS")
need('url.pathname === "/api/portal/activity"' in WORKER,"ROUTE_PRESENT")
route=WORKER.split('url.pathname === "/api/portal/activity"',1)[1].split('url.pathname === "/api/portal/billing"',1)[0]
need("resolvePortalSession" in route and "AUTH_REQUIRED" in route,"AUTH_GUARD")

db=sqlite3.connect(":memory:")
db.execute("PRAGMA foreign_keys=OFF")
db.executescript("""
CREATE TABLE commander_devices(
 device_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL,enrolled_by_subject_id TEXT NOT NULL,
 device_name TEXT NOT NULL,platform TEXT NOT NULL,architecture TEXT NOT NULL,
 agent_version TEXT NOT NULL,tunnel_mode TEXT NOT NULL,state TEXT NOT NULL,
 created_at_utc TEXT NOT NULL,last_seen_at_utc TEXT,revoked_at_utc TEXT,approval_mode TEXT NOT NULL
);
CREATE TABLE commander_device_calls(
 call_id TEXT PRIMARY KEY,request_id TEXT NOT NULL UNIQUE,tenant_id TEXT NOT NULL,
 subject_id TEXT NOT NULL,device_id TEXT NOT NULL,tool_id TEXT NOT NULL,
 payload_json TEXT NOT NULL,state TEXT NOT NULL,created_at_utc TEXT NOT NULL,
 expires_at_utc TEXT NOT NULL,claimed_at_utc TEXT,completed_at_utc TEXT,
 result_json TEXT,error_code TEXT
);
""")
devices=[
 ("D1","T1","U1","nucleo-a","LINUX","x86_64","0.3.26","OUTBOUND_RELAY","ACTIVE","2026-10-04T00:00:00Z","2026-10-04T01:00:00Z",None,"SESSION_TRUSTED"),
 ("D2","T2","U3","other","LINUX","x86_64","0.3.26","OUTBOUND_RELAY","ACTIVE","2026-10-04T00:00:00Z","2026-10-04T01:00:00Z",None,"SESSION_TRUSTED"),
]
db.executemany("INSERT INTO commander_devices VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",devices)
calls=[
 ("C1","HARA-CUSTOMER-MCP-1","T1","U1","D1","hara.health","<redacted:1>","COMPLETED","2026-10-04T00:00:00Z","2026-10-04T00:01:00Z","2026-10-04T00:00:00.500Z","2026-10-04T00:00:01Z","<redacted:r1>",None),
 ("C2","HARA-CUSTOMER-MCP-2","T1","U2","D1","hara.files.read","<redacted:2>","FAILED","2026-10-04T00:02:00Z","2026-10-04T00:03:00Z","2026-10-04T00:02:00.500Z","2026-10-04T00:02:01Z","<redacted:r2>","TEST_FAILURE"),
 ("C3","HARA-CUSTOMER-MCP-3","T2","U3","D2","hara.health","<redacted:3>","COMPLETED","2026-10-04T00:04:00Z","2026-10-04T00:05:00Z","2026-10-04T00:04:00.500Z","2026-10-04T00:04:01Z","<redacted:r3>",None),
]
db.executemany("INSERT INTO commander_device_calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",calls)

owner=db.execute("SELECT COUNT(*) FROM commander_device_calls c WHERE c.tenant_id=?",( "T1",)).fetchone()[0]
member=db.execute("SELECT COUNT(*) FROM commander_device_calls c WHERE c.tenant_id=? AND c.subject_id=?",( "T1","U1")).fetchone()[0]
cross=db.execute("SELECT COUNT(*) FROM commander_device_calls c WHERE c.tenant_id=?",( "T2",)).fetchone()[0]
need(owner==2,"OWNER_TENANT_SCOPE")
need(member==1,"MEMBER_SUBJECT_SCOPE")
need(cross==1 and owner+cross==3,"CROSS_TENANT_ISOLATION")

row=db.execute("""
SELECT COUNT(*) total,
 SUM(CASE WHEN state='COMPLETED' THEN 1 ELSE 0 END) completed,
 SUM(CASE WHEN state='FAILED' THEN 1 ELSE 0 END) failed
FROM commander_device_calls c WHERE c.tenant_id=?
""",("T1",)).fetchone()
need(row==(2,1,1),"SUMMARY_COUNTS")

print("COMMANDER_PORTAL_ACTIVITY_CONTRACT=PASS")
