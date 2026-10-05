#!/usr/bin/env python3
from __future__ import annotations

import runpy
import sqlite3
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")
AGENT=APP/"public/agent/linux.py"
MIG=(APP/"migrations/0023_device_local_budget_blocks.sql").read_text(encoding="utf-8")
PREPROD=APP/"scripts/validate_preprod_readiness.py"

def need(ok, code):
    if not ok:
        raise SystemExit("COMMANDER_LOCAL_BUDGET_"+code+"=FAIL")
    print("COMMANDER_LOCAL_BUDGET_"+code+"=PASS")

# Source / architecture contract.
need("commander_device_budget_blocks" in MIG, "CLOUD_TABLE")
need("usage_mode TEXT NOT NULL DEFAULT 'CLOUD_QUOTA'" in MIG, "CALL_USAGE_MODE_COLUMN")
need("usage_units INTEGER NOT NULL DEFAULT 0" in MIG, "CALL_USAGE_UNITS_COLUMN")
need("usage_period_key TEXT" in MIG, "CALL_USAGE_PERIOD_COLUMN")
need("idx_device_budget_tenant_period_sequence" in MIG, "TENANT_SEQUENCE_RACE_GUARD")
need("idx_device_budget_one_active" in MIG and "WHERE state = 'ACTIVE'" in MIG, "ONE_ACTIVE_PER_DEVICE")
need("LOCAL_BUDGET_BLOCK_UNITS = 100" in WORKER, "BLOCK_SIZE_100")
need("LOCAL_BUDGET_MIN_LINUX_PATCH = 35" in WORKER, "AGENT_035_GATE")
need('return "LOCAL_BUDGET"' in WORKER, "USAGE_MODE_SELECTOR")
need('url.pathname === "/api/device/product-lease"' in WORKER, "PRODUCT_LEASE_ROUTE")
need("LOCAL_BUDGET_ALLOCATION_CONFLICT" in WORKER, "ALLOCATION_CONFLICT_FAIL_CLOSED")
need("effectiveCloudQuotaLimit" in WORKER and "configured - localAllocated" in WORKER, "MIXED_MODE_SHARED_LIMIT")
need(".status(periodKey, limit)" in WORKER and "legacyConsumed" in WORKER and "limit - legacyConsumed - allocated" in WORKER, "LEGACY_USAGE_BASELINE")
need("EVENTUAL_LOCAL_BUDGET" in WORKER and "local_budget_allocated_units" in WORKER and "local_budget_reported_units" in WORKER, "USAGE_PROJECTION")
need("LOCAL_BUDGET_REPORT_NON_MONOTONIC" in WORKER, "REPORT_MONOTONIC")
need("lease_token_hash" in WORKER and "secretMatches" in WORKER, "LEASE_TOKEN_HASH_VERIFY")
need('usageMode === "LOCAL_BUDGET"' in WORKER, "CUSTOMER_MCP_LOCAL_MODE")
need('usageMode === "CLOUD_QUOTA"' in WORKER, "CLOUD_FALLBACK")
need('context.period_kind === "NONE"' in WORKER and 'state: "UNMETERED"' in WORKER, "UNMETERED_BYPASS")
need("cloud_quota_transaction: false" in WORKER, "NO_DO_TRANSACTION_MARKER")
need(all(x in WORKER for x in ("usage_mode","usage_units","usage_period_key")) and "usage: {" in WORKER, "CALL_CARRIES_USAGE_METADATA")

agent_src=AGENT.read_text(encoding="utf-8")
need('AGENT_VERSION = "0.3.35"' in agent_src, "AGENT_VERSION")
need("CREATE TABLE IF NOT EXISTS product_lease" in agent_src, "LOCAL_LEASE_TABLE")
need("CREATE TABLE IF NOT EXISTS local_budget_blocks" in agent_src, "LOCAL_BLOCK_TABLE")
need("CREATE TABLE IF NOT EXISTS local_budget_debits" in agent_src, "LOCAL_DEBIT_TABLE")
need("def refresh_product_lease" in agent_src, "LEASE_REFRESH")
need("def local_budget_reserve" in agent_src, "LOCAL_RESERVE")
need("def local_budget_commit" in agent_src, "LOCAL_COMMIT")
need("def local_budget_release" in agent_src, "LOCAL_RELEASE")
need("PRODUCT_LEASE_REFRESH_SECONDS = 4 * 60 * 60" in agent_src, "LEASE_REFRESH_INTERVAL")
need("LOCAL_BUDGET_REQUEST_ALREADY_COMMITTED" in agent_src, "LOCAL_REPLAY_GUARD")

# Migration replay / schema semantics.
db=sqlite3.connect(":memory:")
for path in sorted((APP/"migrations").glob("*.sql")):
    try:
        db.executescript(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"COMMANDER_LOCAL_BUDGET_MIGRATION_REPLAY=FAIL:{path.name}:{exc}")
need(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok", "MIGRATION_INTEGRITY")
cols={row[1] for row in db.execute("PRAGMA table_info(commander_device_calls)")}
need({"usage_mode","usage_units","usage_period_key"}.issubset(cols), "MIGRATION_CALL_COLUMNS")
budget_cols={row[1] for row in db.execute("PRAGMA table_info(commander_device_budget_blocks)")}
need({
    "budget_id","tenant_id","device_id","period_key","allocation_sequence",
    "units_allocated","units_reported","lease_token_hash","state",
}.issubset(budget_cols), "MIGRATION_BUDGET_COLUMNS")

# Exercise race guards with minimal fixture.
now="2026-10-05T00:00:00Z"
db.execute("INSERT INTO tenants VALUES (?,?,?,?,?)",("T","Tenant","ACTIVE","DEV",now))
db.execute("INSERT INTO users VALUES (?,?,?,?,?,?,?,?,?,?)",(
    "S","T","https://issuer","sub","u@example.com","U","ACTIVE","OWNER",now,None
)) if False else None
# Use existing table shapes without relying on user fixture for FK chain by turning
# FK enforcement off only for index-race semantics below.
db.commit()
db.execute("PRAGMA foreign_keys=OFF")
base=("B1","T","D1","E1","TRIAL","HARA_COMMANDER_GOVERNED_INVOKE","2026-10",1,100,0,"h1","ACTIVE",now,"2026-11-01T00:00:00Z",None)
db.execute("""INSERT INTO commander_device_budget_blocks
 (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,period_key,
  allocation_sequence,units_allocated,units_reported,lease_token_hash,state,
  issued_at_utc,expires_at_utc,last_reported_at_utc)
 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",base)

try:
    db.execute("""INSERT INTO commander_device_budget_blocks
     (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,period_key,
      allocation_sequence,units_allocated,units_reported,lease_token_hash,state,
      issued_at_utc,expires_at_utc,last_reported_at_utc)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
     ("B2","T","D2","E1","TRIAL","HARA_COMMANDER_GOVERNED_INVOKE","2026-10",1,100,0,"h2","ACTIVE",now,"2026-11-01T00:00:00Z",None))
except sqlite3.IntegrityError:
    pass
else:
    raise SystemExit("COMMANDER_LOCAL_BUDGET_SEQUENCE_RACE_RUNTIME=FAIL")
print("COMMANDER_LOCAL_BUDGET_SEQUENCE_RACE_RUNTIME=PASS")

try:
    db.execute("""INSERT INTO commander_device_budget_blocks
     (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,period_key,
      allocation_sequence,units_allocated,units_reported,lease_token_hash,state,
      issued_at_utc,expires_at_utc,last_reported_at_utc)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
     ("B3","T","D1","E1","TRIAL","HARA_COMMANDER_GOVERNED_INVOKE","2026-10",2,100,0,"h3","ACTIVE",now,"2026-11-01T00:00:00Z",None))
except sqlite3.IntegrityError:
    pass
else:
    raise SystemExit("COMMANDER_LOCAL_BUDGET_ONE_ACTIVE_RUNTIME=FAIL")
print("COMMANDER_LOCAL_BUDGET_ONE_ACTIVE_RUNTIME=PASS")

# Dynamic local Agent block consumption with fake authenticated cloud responses.
ns=runpy.run_path(str(AGENT))
with tempfile.TemporaryDirectory(prefix="hara-local-budget-") as td:
    root=Path(td)
    agent_globals=ns["refresh_product_lease"].__globals__
    agent_globals["DATA_DIR"]=root
    agent_globals["OPERATIONS_DB_FILE"]=root/"operations.sqlite3"
    agent_globals["CONSOLE_EVENTS_FILE"]=root/"console-events.jsonl"
    agent_globals["RECEIPT_DIR"]=root/"receipts"

    config={
        "HARA_COMMANDER_URL":"https://commander.invalid",
        "HARA_DEVICE_ID":"DEVICE-LOCAL",
        "HARA_DEVICE_TOKEN":"token-local",
    }
    cloud_calls=[]
    def response(block_id,token,units):
        return {
            "schema":"hara.commander-device-product-lease-response.v1",
            "ok":True,
            "product_lease":{
                "schema":"hara.commander-device-product-lease.v1",
                "lease_id":"LEASE-"+block_id,
                "authority":"HARA_COMMANDER_CLOUD",
                "device_id":"DEVICE-LOCAL",
                "tenant_id":"TENANT-LOCAL",
                "entitlement_id":"ENT-LOCAL",
                "plan_code":"TRIAL",
                "plan_name":"Free",
                "grants":["COMMANDER_READ_ONLY_INVOKE"],
                "meter_id":"HARA_COMMANDER_GOVERNED_INVOKE",
                "period_kind":"CALENDAR_MONTH",
                "unit_limit":10000,
                "usage_mode":"LOCAL_BUDGET",
                "issued_at_utc":"2026-10-05T00:00:00Z",
                "valid_until_utc":"2026-10-05T06:00:00Z",
            },
            "budget":{
                "exhausted":False,
                "block":{
                    "schema":"hara.commander-local-budget-block.v1",
                    "budget_id":block_id,
                    "device_id":"DEVICE-LOCAL",
                    "tenant_id":"TENANT-LOCAL",
                    "entitlement_id":"ENT-LOCAL",
                    "plan_code":"TRIAL",
                    "meter_id":"HARA_COMMANDER_GOVERNED_INVOKE",
                    "period_key":"2026-10",
                    "allocation_sequence":1 if block_id=="B1" else 2,
                    "allocated_units":units,
                    "committed_units":0,
                    "lease_token":token,
                    "issued_at_utc":"2026-10-05T00:00:00Z",
                    "expires_at_utc":"2026-11-01T00:00:00Z",
                    "cloud_authoritative":True,
                },
            },
        }

    def fake_post(url,token,payload,timeout=25):
        assert url.endswith("/api/device/product-lease")
        assert token=="token-local"
        cloud_calls.append(payload)
        if len(cloud_calls)==1:
            assert payload=={}
            return response("B1","tok1",3)
        report=payload.get("budget_report") or {}
        assert report.get("budget_id")=="B1"
        assert report.get("lease_token")=="tok1"
        assert report.get("committed_units")==3
        return response("B2","tok2",2)

    agent_globals["post_json"]=fake_post
    lease=ns["refresh_product_lease"](config)
    need(lease["product_lease"]["usage_mode"]=="LOCAL_BUDGET", "DYNAMIC_LEASE")

    for rid in ("r1","r2","r3"):
        reservation=ns["local_budget_reserve"](config,{
            "request_id":rid,
            "usage":{"mode":"LOCAL_BUDGET","units":1,"period_key":"2026-10"},
        })
        need(reservation["state"]=="RESERVED", "DYNAMIC_RESERVE_"+rid.upper())
        committed=ns["local_budget_commit"](rid)
        need(committed["state"]=="COMMITTED", "DYNAMIC_COMMIT_"+rid.upper())

    try:
        ns["local_budget_reserve"](config,{
            "request_id":"r1",
            "usage":{"mode":"LOCAL_BUDGET","units":1,"period_key":"2026-10"},
        })
    except ValueError as exc:
        need(str(exc)=="LOCAL_BUDGET_REQUEST_ALREADY_COMMITTED", "DYNAMIC_REPLAY_DENIED")
    else:
        raise SystemExit("COMMANDER_LOCAL_BUDGET_DYNAMIC_REPLAY_DENIED=FAIL")

    # B1 is exhausted, so r4 causes exactly one cloud refresh and lands on B2.
    r4=ns["local_budget_reserve"](config,{
        "request_id":"r4",
        "usage":{"mode":"LOCAL_BUDGET","units":1,"period_key":"2026-10"},
    })
    need(r4["budget_id"]=="B2", "DYNAMIC_BLOCK_ROLLOVER")
    need(len(cloud_calls)==2, "DYNAMIC_ONE_REFRESH_PER_BLOCK")
    rel=ns["local_budget_release"]("r4")
    need(rel["state"]=="RELEASED", "DYNAMIC_RELEASE")

    try:
        ns["local_budget_reserve"](config,{
            "request_id":"r4",
            "usage":{"mode":"LOCAL_BUDGET","units":1,"period_key":"2026-10"},
        })
    except ValueError as exc:
        need(str(exc)=="LOCAL_BUDGET_REQUEST_TERMINAL", "DYNAMIC_RELEASE_TERMINAL")
    else:
        raise SystemExit("COMMANDER_LOCAL_BUDGET_DYNAMIC_RELEASE_TERMINAL=FAIL")

    with sqlite3.connect(agent_globals["OPERATIONS_DB_FILE"]) as local:
        local.row_factory=sqlite3.Row
        lease_row=local.execute("SELECT lease_json FROM product_lease WHERE singleton=1").fetchone()
        blocks=local.execute("SELECT budget_id,state FROM local_budget_blocks ORDER BY budget_id").fetchall()
        debits=local.execute("SELECT request_id,state FROM local_budget_debits ORDER BY request_id").fetchall()
        cols={r[1] for r in local.execute("PRAGMA table_info(activity_events)")}
    need(lease_row is not None, "DYNAMIC_LEASE_PERSISTED")
    need([(r["budget_id"],r["state"]) for r in blocks]==[("B1","EXHAUSTED"),("B2","ACTIVE")], "DYNAMIC_BLOCK_STATES")
    need(dict((r["request_id"],r["state"]) for r in debits)=={
        "r1":"COMMITTED","r2":"COMMITTED","r3":"COMMITTED","r4":"RELEASED"
    }, "DYNAMIC_DEBIT_STATES")
    need("payload_json" not in cols and "result_json" not in cols, "DYNAMIC_RAW_CONTENT_ABSENT")

print("COMMANDER_LOCAL_BUDGET_BLOCKS=PASS")
