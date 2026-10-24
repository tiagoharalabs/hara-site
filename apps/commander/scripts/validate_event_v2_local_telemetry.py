#!/usr/bin/env python3
"""Offline real-module checks: persistent local metrics and idle WebSocket flow."""
from __future__ import annotations
import importlib.util
import json
import os
import socket
import sqlite3
import stat
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
def load(relative,name):
    path=ROOT/relative
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

telemetry=load("apps/commander/experimental/event_v2_telemetry.py","test_hara_event_telemetry")
transport=load("apps/commander/experimental/event_v2_websocket.py","test_hara_event_websocket")
loop=load("apps/commander/experimental/event_v2_agent_loop.py","test_hara_event_loop")
count=0
def ok(cond,message):
    global count
    assert cond,message
    count+=1

with tempfile.TemporaryDirectory() as root:
    path=Path(root)/"event-v2.sqlite3"
    ticks=[0.]
    clock=lambda: ticks[0]
    store=telemetry.LocalTelemetry(path,monotonic=clock)
    ok(stat.S_IMODE(path.stat().st_mode)==0o600,"PRIVATE_FILE_MODE")
    ok(store.snapshot()["window_days"]==7,"EXPECTED_WINDOW")
    store.add("durable_calls",3)
    store.add("transient_calls")
    ticks[0]=301.
    store.add("connections")
    ok(store.snapshot()["durable_calls"]==3,"DURABLE_COUNTER")
    ok(store.snapshot()["transient_calls"]==1,"TRANSIENT_COUNTER")
    ok(store.snapshot()["connections"]==1,"TIMED_BATCH_COUNTER")
    ok(store.snapshot()==store.snapshot(),"SNAPSHOT_NOT_DOUBLE_COUNTED")
    store.close()
    recovered=telemetry.LocalTelemetry(path)
    ok(recovered.snapshot()["durable_calls"]==3,"SURVIVES_RESTART")
    for metric in ("tool_id","command","args","content","path","token"):
        ok(metric not in recovered.snapshot(),"PRIVATE_FIELD:"+metric)
    with sqlite3.connect(path) as db:
        columns=[x[1] for x in db.execute("PRAGMA table_info(event_v2_telemetry_daily)")]
    ok(set(columns)=={"day_utc",*telemetry.METRICS},"SCHEMA_EXACT")
    older=(datetime.now(timezone.utc)-timedelta(days=10)).date().isoformat()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO event_v2_telemetry_daily (day_utc,connections) VALUES (?,?)",
                   (older,123))
    recovered.add("reconnects")
    recovered.flush()
    with sqlite3.connect(path) as db:
        stale=db.execute("SELECT COUNT(*) FROM event_v2_telemetry_daily WHERE day_utc=?",(older,)).fetchone()[0]
    ok(stale==0,"BOUNDED_RETENTION")
    for bad in ["commands","output","customer_content","path"]:
        try: recovered.add(bad)
        except ValueError: pass
        else: raise AssertionError("UNRESTRICTED_METRIC")
        count+=1
    for bad in [True,-1,86401,3.5]:
        try: recovered.add("connections",bad)
        except ValueError: pass
        else: raise AssertionError("INVALID_AMOUNT")
        count+=1
    unsafe=Path(root)/"link.sqlite3"
    unsafe.symlink_to(path)
    try: telemetry.LocalTelemetry(unsafe)
    except ValueError: pass
    else: raise AssertionError("SYMLINK_FOLLOWED")
    count+=1
    exposed=Path(root)/"exposed.sqlite3"
    exposed.write_bytes(b"")
    exposed.chmod(0o644)
    try: telemetry.LocalTelemetry(exposed)
    except ValueError: pass
    else: raise AssertionError("OPEN_PERMISSIONS")
    count+=1

    class Socket:
        def __init__(self): self.sent=[]
        def sendall(self,chunk): self.sent.append(chunk)
    wire=Socket()
    transport.send_liveness(wire)
    ok(len(wire.sent)==1,"OLD_LIVENESS_SENT")
    def unpack(frame):
        length=frame[1]&0x7f
        offset=2
        if length==126:
            length=int.from_bytes(frame[2:4],"big");offset=4
        mask=frame[offset:offset+4]
        body=bytes(b^mask[i%4] for i,b in enumerate(frame[offset+4:offset+4+length]))
        return json.loads(body)
    old_event=unpack(wire.sent[-1])
    ok(set(old_event)=={"schema","type"},"LEGACY_FRAME_COMPATIBLE")
    report=recovered.snapshot()
    transport.send_liveness(wire,report)
    new_event=unpack(wire.sent[-1])
    ok(set(new_event)=={"schema","type","metrics"},"OPTIONAL_TELEMETRY_PIGGYBACK")
    ok(new_event["metrics"]==report,"TELEMETRY_EXACT")
    for mutation in [
        {**report,"tool_id":"secret"},
        {**report,"connections":True},
        {**report,"connected_seconds":-1},
        {**report,"window_days":14},
        {**report,"durable_calls":10**14},
    ]:
        previous=len(wire.sent)
        try: transport.send_liveness(wire,mutation)
        except transport.EventV2Error: pass
        else: raise AssertionError("INVALID_TELEMETRY_ACCEPTED")
        ok(len(wire.sent)==previous,"INVALID_FRAME_NOT_SENT")
    transport.send_liveness(wire,report)
    ok(not any(word in str(wire.sent[-1]) for word in ("secret","command_text","private")),
       "NO_CUSTOMER_CONTENT_ON_WIRE")

    class FakeTransport:
        DURABLE_LIVENESS_SECONDS=21600
        def __init__(self): self.sent=[];self.closed=0
        def open_event_socket(self, *_args):return object()
        def recv_event_or_keepalive(self,_sock):return None
        def send_liveness(self,_sock,metrics=None):self.sent.append(metrics)
        def close_socket(self,_sock):self.closed+=1
    class FakeAgent:
        def __init__(self,db):self.status=[];self.polls=0;self.db=db
        def open_telemetry(self):return telemetry.LocalTelemetry(self.db,monotonic=clock)
        def utcnow(self):return "2026-10-11T00:00:00Z"
        def try_write_event_v2_status(self,**kwargs):self.status.append(kwargs);return True
        def post_json(self,*args):self.polls+=1;return None
    ft=FakeTransport(); fa=FakeAgent(Path(root)/"agent.sqlite3")
    counter=[0]
    def advance():
        counter[0]+=23000
        return counter[0]
    result=loop.run_connected_session(
        ft,fa,{"HARA_COMMANDER_URL":"https://fixture.invalid",
               "HARA_DEVICE_TOKEN":"synthetic","HARA_DEVICE_ID":"D-SAMPLE"},
        max_steps=1,monotonic=advance)
    ok(len(ft.sent)==1,"ONCE_PER_SIX_HOUR_CHECKPOINT")
    ok(ft.sent[0]["connections"]==1,"LIVE_SUMMARY_CONNECTIONS")
    ok(ft.sent[0]["liveness_attempts"]==1,"LIVE_SUMMARY_CHECKPOINT")
    ok(fa.polls==1,"RECONCILE_ONLY_NO_IDLE_POLLING")
    ok(result["steps"]==1,"BOUNDED_IDLE_SESSION")
    ok(ft.closed==1 and fa.status[-1]["connected"] is False,"CLEAN_DISCONNECT")
    persisted=telemetry.LocalTelemetry(fa.db).snapshot()
    ok(persisted["disconnects"]==1,"DISCONNECT_PERSISTED")
    ok(persisted["connected_seconds"]>0,"DURATION_PERSISTED")
    ok(persisted["transport_pings"]==1,"CONTROL_PING_NOT_HTTP")
    ok(persisted["liveness_attempts"]==1,"SINGLE_REPORT_ONLY")

# The signed fleet launches the full-tool adapter, not the restricted adapter.
full_agent=load("apps/commander/candidate/event_v2_full_agent.py","test_hara_full_agent_telemetry")
ok(hasattr(full_agent,"open_telemetry"),"FULL_SIGNED_AGENT_TELEMETRY_ADAPTER")
with tempfile.TemporaryDirectory() as root:
    old=full_agent.BASELINE.DATA_DIR
    try:
        full_agent.BASELINE.DATA_DIR=Path(root)
        probe=full_agent.open_telemetry()
        probe.add("connections")
        probe.close()
        ok(probe.snapshot()["connections"]==1,"FULL_ADAPTER_SQLITE_PERSISTED")
        ok(stat.S_IMODE(probe.path.stat().st_mode)==0o600,"FULL_ADAPTER_PRIVATE_MODE")
    finally:
        full_agent.BASELINE.DATA_DIR=old

print(json.dumps({"schema":"hara.commander-event-v2-telemetry-validation.v1",
                  "state":"PASS","checked":count,"passed":count,
                  "cloud_calls":0,"content_persisted":False,
                  "local_retention_days":7,"liveness_seconds":21600,
                  "independent_http_uploads":0},sort_keys=True))
