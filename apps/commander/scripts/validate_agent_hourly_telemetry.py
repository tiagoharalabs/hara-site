#!/usr/bin/env python3
"""Offline contract regression for Commander Agent -> existing Cloudflare metering endpoint."""
import json
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
AGENT=APP/"public/agent/linux.py"
WORKER=(APP/"src/worker.js").read_text(encoding="utf-8")
SOURCE=AGENT.read_text(encoding="utf-8")

def need(condition,name):
    if not condition:
        raise AssertionError("AGENT_TELEMETRY_"+name+"=FAIL")
    print("AGENT_TELEMETRY_"+name+"=PASS")

need("AGENT_TELEMETRY_INTERVAL_SECONDS = 60 * 60" in SOURCE,"HOURLY_SCHEDULE")
need('url.pathname === "/api/device/metering-sync"' in WORKER,"EXISTING_ENDPOINT")
need("deviceAgentLifecycleTelemetry(env, request, body)" in WORKER,"CLOUDFLARE_DISPATCH")
need("LOCAL_AGENT_HEARTBEAT_EARLY" in WORKER,"SERVER_HOURLY_GUARD")
need("customer_content_persisted:false" in WORKER,"CLOUD_PRIVACY")

with sqlite3.connect(":memory:") as db:
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("CREATE TABLE commander_devices(device_id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL)")
    db.executescript((APP/"migrations/0029_local_tunnel_authorization.sql").read_text())
    db.executescript((APP/"migrations/0030_agent_lifecycle_telemetry.sql").read_text())
    db.execute("INSERT INTO commander_devices(device_id,tenant_id) VALUES('d1','t1')")
    def insert_event(event_id,event_type):
        db.execute(
            "INSERT INTO commander_device_agent_telemetry "
            "(event_id,device_id,tenant_id,subject_id,session_id,event_type,event_at_utc,received_at_utc,transport_mode) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (event_id,"d1","t1","s1","sess1",event_type,"2026-10-08T20:00:00Z","2026-10-08T20:00:00Z","LOCAL_TUNNEL"),
        )
    insert_event("e1","AGENT_START")
    insert_event("e2","AGENT_HEARTBEAT")
    insert_event("e3","AGENT_STOP")
    need(db.execute("SELECT count(*) FROM commander_device_agent_telemetry").fetchone()[0]==3,"MIGRATION_EVENTS")
    try:
        insert_event("e4","AGENT_START")
        raise AssertionError("Duplicate START accepted")
    except sqlite3.IntegrityError:
        need(True,"UNIQUE_START_STOP")
    try:
        insert_event("e5","RAW_COMMAND")
        raise AssertionError("Unexpected event accepted")
    except sqlite3.IntegrityError:
        need(True,"MIGRATION_EVENT_ALLOWLIST")

ns={"__name__":"hara_agent_telemetry_test","__file__":str(AGENT)}
exec(compile(SOURCE,str(AGENT),"exec"),ns)
with tempfile.TemporaryDirectory(prefix="hara-telemetry-unit-") as td:
    root=Path(td)
    config_dir=root/"config"; config_dir.mkdir()
    data_dir=root/"data"; data_dir.mkdir()
    cfg=config_dir/"device.env"
    cfg.write_text(
        "HARA_COMMANDER_URL=https://example.invalid\n"
        "HARA_DEVICE_ID=HARA-DEVICE-TEST\n"
        "HARA_DEVICE_TOKEN=FAKE_DEVICE_TOKEN\n"
        "HARA_DEVICE_ARCH=x86_64\n"
        "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n"
        "HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL\n"
    )
    os.chmod(cfg,0o600)
    ns["CONFIG_FILE"]=cfg
    ns["DATA_DIR"]=data_dir
    ns["RECEIPT_DIR"]=data_dir/"receipts"
    ns["STATUS_FILE"]=data_dir/"runtime-status.json"
    ns["SESSION_FILE"]=data_dir/"operator-session.json"
    ns["CONSOLE_EVENTS_FILE"]=data_dir/"console-events.jsonl"
    ns["OPERATIONS_DB_FILE"]=data_dir/"operations.sqlite3"
    ns["APPROVAL_DIR"]=data_dir/"approvals"
    ns["PREIMAGE_DIR"]=data_dir/"preimages"
    config=ns["load_config"]()
    session="HARA-AGENT-SESSION-"+"a"*32
    start=ns["time"].monotonic()

    def offline(*args,**kwargs):
        raise RuntimeError("OFFLINE_TEST")
    ns["post_json"]=offline
    ns["agent_telemetry_emit"](config,"AGENT_START",session,start)
    with ns["_ops_connect"]() as conn:
        pending=conn.execute("SELECT COUNT(*) FROM agent_telemetry_outbox").fetchone()[0]
    need(pending==1,"OFFLINE_DURABLE_OUTBOX")

    calls=[]
    def received(url,token,payload,timeout=25):
        need(url.endswith("/api/device/metering-sync") and token=="FAKE_DEVICE_TOKEN","SAME_AUTHENTICATED_ROUTE")
        need(payload["metadata_only"] is True and payload["customer_content_included"] is False,"NO_CUSTOMER_CONTENT")
        need(set(payload)=={
            "schema","event_id","event_type","session_id","event_at_utc",
            "session_duration_seconds","agent_version","transport_mode",
            "usage_report","metadata_only","customer_content_included",
        },"MINIMAL_SCHEMA")
        calls.append(dict(payload))
        return {"ok":True,"accepted":True,"event_type":payload["event_type"]}
    ns["post_json"]=received
    need(ns["agent_telemetry_flush"](config)["pending"]==0,"REPLAY_AFTER_OUTAGE")
    need(len(calls)==1 and calls[0]["event_type"]=="AGENT_START","START_ON_RECOVERY")

    class FakeEvent:
        def __init__(self):
            self.calls=0
        def set(self):
            self.calls=999
        def wait(self,_timeout):
            self.calls+=1
            return self.calls>=2
    threading_mod=ns["threading"]
    signal_mod=ns["signal"]
    original_event=threading_mod.Event
    original_signal=signal_mod.signal
    old_interval=ns["AGENT_TELEMETRY_INTERVAL_SECONDS"]
    try:
        threading_mod.Event=FakeEvent
        signal_mod.signal=lambda *args:None
        ns["AGENT_TELEMETRY_INTERVAL_SECONDS"]=0
        before=len(calls)
        ns["run_local_tunnel_agent_telemetry"](config)
        events=[x["event_type"] for x in calls[before:]]
        need(events==["AGENT_START","AGENT_HEARTBEAT","AGENT_STOP"],"SERVICE_START_HEARTBEAT_STOP")
    finally:
        threading_mod.Event=original_event
        signal_mod.signal=original_signal
        ns["AGENT_TELEMETRY_INTERVAL_SECONDS"]=old_interval

print("COMMANDER_AGENT_HOURLY_TELEMETRY=PASS")
