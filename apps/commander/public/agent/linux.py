#!/usr/bin/env python3
import base64
import hashlib
import hmac
import json
import getpass
import subprocess
import fnmatch
import difflib
import shutil
import os
import platform
import pty
import re
import select
import shlex
import signal
import sqlite3
import sys
import threading
import uuid
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AGENT_VERSION = "0.3.43"
CONFIG_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "hara-commander/device.env"
DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", str(Path.home()/".local/share"))) / "hara-commander"
RECEIPT_DIR = DATA_DIR / "receipts"
STATUS_FILE = DATA_DIR / "runtime-status.json"
SESSION_FILE = DATA_DIR / "operator-session.json"
CONSOLE_EVENTS_FILE = DATA_DIR / "console-events.jsonl"
OPERATIONS_DB_FILE = DATA_DIR / "operations.sqlite3"
PRODUCT_LEASE_KID = "commander-lease-v1"
PRODUCT_LEASE_AUDIENCE = "hara-commander-agent"
PRODUCT_LEASE_RSA_N = "pq_Ql3poia63FAgi3MwPXFe9M9LNyJXPMKsjII0d6zgeu0RUcWwFvdBOnjCt6b2bVfElQF4ykvKLxEF6anfQT00nOmI1crDUpLcmx34cB1yZPkDcXiNqkN1g0rkhlkWJXNkGye6jYM7WLxS_Y_jx0Taky-5pGFHmY70Mh1XNv9hGhfXeN6mV83n8-v1oFJ9S0mMjbACwzIGjPs70wb8mZdGRZU_oT0mGlAOvG2oIToEwWZCQbTVVgap0XF2mEeY8IkNWiDh2wYCiTeAWTH5M2tJnkBZC0lx1HLC6jwnRowjIDTJvQhLUzs58ilbDwWPSPihehJ9WiImvnYu0M6xy-Q"
PRODUCT_LEASE_RSA_E = "AQAB"
LOCAL_PORTAL_HOST = "127.0.0.1"
LOCAL_PORTAL_PORT = max(1024, min(65535, int(os.environ.get("HARA_COMMANDER_LOCAL_PORT", "32145"))))
APPROVAL_DIR = DATA_DIR / "approvals"
PREIMAGE_DIR = DATA_DIR / "preimages"
SESSION_MAX_SECONDS = 12 * 60 * 60
PRODUCT_LEASE_REFRESH_SECONDS = 4 * 60 * 60
LOCAL_METERING_MIN_INTERVAL_SECONDS = 60 * 60
TRANSPORT_MODES = {"OUTBOUND_RELAY","LOCAL_TUNNEL"}
TUNNEL_PROFILE = "hara-commander"
TUNNEL_ENV_FILE = CONFIG_FILE.parent / "openai-tunnel.env"
TUNNEL_UNIT_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "systemd/user/hara-commander-openai-tunnel.service"
HEARTBEAT_SECONDS = 60
CALL_POLL_HOT_SECONDS = 2
CALL_POLL_IDLE_SECONDS = 10
CALL_POLL_HOT_WINDOW_SECONDS = 120
CALL_POLL_STARTUP_HOT_SECONDS = 30
RATE_LIMIT_BACKOFF_INITIAL_SECONDS = 30
RATE_LIMIT_BACKOFF_MAX_SECONDS = 300
SLO_PROFILE = "INTERNAL_BETA_V1"
SLO_MIN_SUCCESS_PERCENT = 99.0
SLO_P50_MAX_MS = 1000
SLO_P95_MAX_MS = 6000
SLO_P99_MAX_MS = 12000
SLO_MIN_LATENCY_SAMPLES = 20
SLO_LATENCY_SAMPLE_MAX = 5000
APPROVAL_MODES = {"ASK_EVERY_ACTION","SESSION_TRUSTED","PERSISTENT_TRUSTED"}
FUNCTION_ID = "device.info"
FUNCTION_IDS = (
    "device.info", "device.ping", "system.uptime", "system.resources", "workspace.inspect", "process.list",
    "filesystem.info", "filesystem.hash", "filesystem.diff", "filesystem.search", "filesystem.list", "filesystem.read", "filesystem.read_many",
)
DIRECT_TOOL_FUNCTIONS = {
    "hara.device.info":"device.info",
    "hara.ping":"device.ping",
    "hara.system.uptime":"system.uptime",
    "hara.system.resources":"system.resources",
    "hara.workspace.inspect":"workspace.inspect",
    "hara.processes.list":"process.list",
    "hara.files.info":"filesystem.info",
    "hara.files.hash":"filesystem.hash",
    "hara.files.diff":"filesystem.diff",
    "hara.files.search":"filesystem.search",
    "hara.files.list":"filesystem.list",
    "hara.files.read":"filesystem.read",
    "hara.files.read_many":"filesystem.read_many",
}

FILESYSTEM_MUTATION_TOOLS = {
    "hara.files.create_directory",
    "hara.files.write",
    "hara.files.edit",
    "hara.files.move",
    "hara.files.copy",
    "hara.files.delete",
    "hara.files.rollback",
}
PROCESS_TOOLS = {
    "hara.process.sessions",
    "hara.process.run",
    "hara.process.start",
    "hara.process.output",
    "hara.process.interact",
    "hara.process.kill",
}
PROCESS_MUTATION_TOOLS = {
    "hara.process.run",
    "hara.process.start",
    "hara.process.interact",
    "hara.process.kill",
}
PROCESS_SESSIONS = {}
MAX_PROCESS_LINES = 5000

def _is_process_tool(tool_id):
    return str(tool_id or "") in PROCESS_TOOLS

def _is_mutation_tool(tool_id):
    tool=str(tool_id or "")
    return tool in FILESYSTEM_MUTATION_TOOLS or tool in PROCESS_MUTATION_TOOLS

def _mutation_class(tool_id):
    tool=str(tool_id or "")
    if tool in PROCESS_MUTATION_TOOLS: return "PROCESS_EXECUTION_V1"
    if tool == "hara.files.rollback": return "FILESYSTEM_ROLLBACK_V1"
    if tool in FILESYSTEM_MUTATION_TOOLS: return "FILESYSTEM_MUTATION_V1"
    return "READ_ONLY_OR_NONE_V1"

class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "REDIRECT_DENIED", headers, fp)

NO_REDIRECT_OPENER = urllib.request.build_opener(NoRedirectHandler)

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def safe_error_code(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP_{int(exc.code)}"
    if isinstance(exc, urllib.error.URLError):
        return "NETWORK_ERROR"
    raw = str(exc or "").strip().upper()
    if raw and len(raw) <= 80 and all(c.isalnum() or c == "_" for c in raw):
        return raw
    name = type(exc).__name__.upper()
    if name and len(name) <= 80 and all(c.isalnum() or c == "_" for c in name):
        return name
    return "RUNTIME_ERROR"

def write_runtime_status(*, heartbeat_at=None, error_code=None, error_at=None, started_at=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = {}
    if STATUS_FILE.is_file():
        try:
            current = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    payload = {
        "schema":"hara.commander-agent-runtime-status.v1",
        "agent_version":AGENT_VERSION,
        "started_at_utc": started_at if started_at is not None else current.get("started_at_utc"),
        "last_successful_heartbeat_at_utc": heartbeat_at if heartbeat_at is not None else current.get("last_successful_heartbeat_at_utc"),
        "last_runtime_error_code":error_code,
        "last_runtime_error_at_utc":error_at,
        "updated_at_utc":utcnow(),
    }
    tmp = STATUS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload,sort_keys=True,separators=(",",":")),encoding="utf-8")
    os.chmod(tmp,0o600)
    tmp.replace(STATUS_FILE)
    os.chmod(STATUS_FILE,0o600)

def try_write_runtime_status(**kwargs):
    try:
        write_runtime_status(**kwargs)
        return True
    except Exception:
        return False

def _pid_alive(pid):
    try:
        pid = int(pid)
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _pid_start_marker(pid):
    try:
        raw = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        tail = raw[raw.rfind(")") + 2:].split()
        return tail[19] if len(tail) > 19 else None
    except Exception:
        return None

def read_operator_session():
    if not SESSION_FILE.is_file():
        return None
    try:
        session = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    if session.get("schema") != "hara.commander-operator-session.v1":
        return None
    started = session.get("started_at_epoch")
    if not isinstance(started, (int, float)):
        return None
    if time.time() - float(started) > SESSION_MAX_SECONDS:
        return None
    pid = session.get("owner_pid")
    if not _pid_alive(pid):
        return None
    marker = _pid_start_marker(pid)
    if not marker or marker != str(session.get("owner_start_marker") or ""):
        return None
    return session

def operator_session_active():
    return read_operator_session() is not None

def _ops_connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn=sqlite3.connect(str(OPERATIONS_DB_FILE),timeout=2.0)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS activity_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        at_utc TEXT NOT NULL,
        event TEXT NOT NULL,
        state TEXT,
        tool_id TEXT,
        function_id TEXT,
        request_id TEXT,
        error_code TEXT,
        receipt_sha256 TEXT,
        approval_id TEXT,
        action_summary TEXT,
        duration_ms INTEGER,
        transport_mode TEXT,
        local_only INTEGER NOT NULL DEFAULT 1
      );
      CREATE INDEX IF NOT EXISTS idx_activity_events_at
        ON activity_events(at_utc DESC);
      CREATE INDEX IF NOT EXISTS idx_activity_events_terminal
        ON activity_events(event, at_utc DESC);
      CREATE INDEX IF NOT EXISTS idx_activity_events_tool
        ON activity_events(tool_id, at_utc DESC);
      CREATE TABLE IF NOT EXISTS local_store_meta (
        meta_key TEXT PRIMARY KEY,
        meta_value TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS product_lease (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        lease_json TEXT NOT NULL,
        lease_token TEXT,
        valid_until_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS local_budget_blocks (
        budget_id TEXT PRIMARY KEY,
        tenant_id TEXT NOT NULL,
        device_id TEXT NOT NULL,
        entitlement_id TEXT NOT NULL,
        plan_code TEXT NOT NULL,
        meter_id TEXT NOT NULL,
        period_key TEXT NOT NULL,
        allocated_units INTEGER NOT NULL,
        lease_token TEXT NOT NULL,
        issued_at_utc TEXT NOT NULL,
        expires_at_utc TEXT NOT NULL,
        state TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_local_budget_period
        ON local_budget_blocks(period_key, state, issued_at_utc);
      CREATE TABLE IF NOT EXISTS local_budget_debits (
        request_id TEXT PRIMARY KEY,
        budget_id TEXT NOT NULL,
        units INTEGER NOT NULL,
        state TEXT NOT NULL,
        created_at_utc TEXT NOT NULL,
        updated_at_utc TEXT NOT NULL,
        FOREIGN KEY (budget_id) REFERENCES local_budget_blocks(budget_id)
      );
      CREATE INDEX IF NOT EXISTS idx_local_budget_debits_block
        ON local_budget_debits(budget_id, state);
    """)
    lease_columns={row["name"] for row in conn.execute("PRAGMA table_info(product_lease)")}
    if "lease_token" not in lease_columns:
        conn.execute("ALTER TABLE product_lease ADD COLUMN lease_token TEXT")
        conn.commit()
    try:
        os.chmod(OPERATIONS_DB_FILE,0o600)
        for suffix in ("-wal","-shm"):
            sidecar=Path(str(OPERATIONS_DB_FILE)+suffix)
            if sidecar.exists(): os.chmod(sidecar,0o600)
    except Exception:
        pass
    _ops_migrate_legacy_jsonl(conn)
    return conn

def _ops_migrate_legacy_jsonl(conn):
    marker=conn.execute(
        "SELECT meta_value FROM local_store_meta WHERE meta_key='console_events_jsonl_v1'"
    ).fetchone()
    if marker:
        return
    if CONSOLE_EVENTS_FILE.is_file():
        for raw in CONSOLE_EVENTS_FILE.read_text(encoding="utf-8",errors="replace").splitlines():
            try:
                event=json.loads(raw)
            except Exception:
                continue
            if event.get("schema")!="hara.commander-console-event.v1":
                continue
            conn.execute(
                """INSERT INTO activity_events
                   (at_utc,event,state,tool_id,function_id,request_id,error_code,
                    receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    str(event.get("at_utc") or utcnow()),
                    str(event.get("event") or "EVENT"),
                    event.get("state"),
                    event.get("tool_id") or event.get("tool"),
                    event.get("function_id"),
                    event.get("request_id"),
                    event.get("error_code"),
                    event.get("receipt_sha256"),
                    event.get("approval_id"),
                    event.get("action_summary"),
                    event.get("duration_ms"),
                    event.get("transport_mode") or "LEGACY_JSONL",
                ),
            )
    conn.execute(
        "INSERT OR REPLACE INTO local_store_meta(meta_key,meta_value) VALUES('console_events_jsonl_v1',?)",
        (utcnow(),),
    )
    conn.commit()

def _ops_insert_event(payload):
    try:
        with _ops_connect() as conn:
            conn.execute(
                """INSERT INTO activity_events
                   (at_utc,event,state,tool_id,function_id,request_id,error_code,
                    receipt_sha256,approval_id,action_summary,duration_ms,transport_mode,local_only)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    payload.get("at_utc"),payload.get("event"),payload.get("state"),
                    payload.get("tool_id"),payload.get("function_id"),payload.get("request_id"),
                    payload.get("error_code"),payload.get("receipt_sha256"),payload.get("approval_id"),
                    payload.get("action_summary"),payload.get("duration_ms"),payload.get("transport_mode"),
                ),
            )
    except Exception:
        # JSONL remains the compatibility/fail-safe sink.
        pass

def _activity_window(value):
    raw=str(value or "7d").strip().lower()
    hours={"24h":24,"7d":7*24,"30d":30*24}.get(raw,7*24)
    return raw if raw in {"24h","7d","30d"} else "7d", hours

def _nearest_rank_percentile(values,percent):
    if not values:
        return None
    ordered=sorted(int(v) for v in values)
    rank=max(1,(len(ordered)*int(percent)+99)//100)
    return ordered[min(len(ordered)-1,rank-1)]

SLO_POLICY_FAILURE_CODES={
    "HTTP_401","HTTP_403","HTTP_409","HTTP_429",
    "LOCAL_OPERATOR_APPROVAL_DENIED","APPROVAL_TIMEOUT",
}
SLO_CLIENT_FAILURE_CODES={
    "HTTP_400","HTTP_404","HTTP_405","HTTP_410","HTTP_422",
    "FILENOTFOUNDERROR","FILEEXISTSERROR","ISADIRECTORYERROR","NOTADIRECTORYERROR",
    "EDIT_MATCH_AMBIGUOUS","PROCESS_SESSION_EXITED","PROCESS_SESSION_NOT_FOUND",
}

def _slo_failure_class(error_code):
    code=str(error_code or "UNKNOWN").strip().upper()
    if code in SLO_POLICY_FAILURE_CODES:
        return "POLICY"
    if code in SLO_CLIENT_FAILURE_CODES:
        return "CLIENT_ACTION"
    return "SERVICE"

def _internal_slo(summary):
    sample=int(summary.get("latency_sample_size") or 0)
    terminal=int(summary.get("completed") or 0)+int(summary.get("service_failed") or 0)
    success=summary.get("availability_success_rate_percent")
    checks={
        "success_rate":None if success is None else float(success)>=SLO_MIN_SUCCESS_PERCENT,
        "p50":None if summary.get("latency_p50_ms") is None else float(summary["latency_p50_ms"])<=SLO_P50_MAX_MS,
        "p95":None if summary.get("latency_p95_ms") is None else float(summary["latency_p95_ms"])<=SLO_P95_MAX_MS,
        "p99":None if summary.get("latency_p99_ms") is None else float(summary["latency_p99_ms"])<=SLO_P99_MAX_MS,
    }
    evaluable=sample>=SLO_MIN_LATENCY_SAMPLES and terminal>=SLO_MIN_LATENCY_SAMPLES
    status="INSUFFICIENT_DATA" if not evaluable else ("PASS" if all(v is True for v in checks.values()) else "DEGRADED")
    return {
        "profile":SLO_PROFILE,
        "status":status,
        "evaluable":evaluable,
        "success_metric":"availability_success_rate_percent",
        "targets":{
            "min_success_rate_percent":SLO_MIN_SUCCESS_PERCENT,
            "p50_max_ms":SLO_P50_MAX_MS,
            "p95_max_ms":SLO_P95_MAX_MS,
            "p99_max_ms":SLO_P99_MAX_MS,
            "min_latency_samples":SLO_MIN_LATENCY_SAMPLES,
        },
        "checks":checks,
    }

def local_activity_snapshot(window="7d",limit=50,include_events=True):
    key,hours=_activity_window(window)
    since=datetime.fromtimestamp(time.time()-(hours*3600),timezone.utc).isoformat()
    limit=max(1,min(100,int(limit)))
    try:
        with _ops_connect() as conn:
            row=conn.execute(
                """SELECT
                     COUNT(*) AS total_calls,
                     SUM(CASE WHEN state='COMPLETED' THEN 1 ELSE 0 END) AS completed,
                     SUM(CASE WHEN state='FAILED' THEN 1 ELSE 0 END) AS failed,
                     SUM(CASE WHEN state='EXPECTED' THEN 1 ELSE 0 END) AS operational,
                     ROUND(AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END),1) AS avg_total_ms,
                     SUM(CASE WHEN state='COMPLETED' AND duration_ms < 3000 THEN 1 ELSE 0 END) AS under_3s,
                     SUM(CASE WHEN state='COMPLETED' AND duration_ms IS NOT NULL THEN 1 ELSE 0 END) AS duration_population
                   FROM activity_events
                  WHERE at_utc >= ?
                    AND event IN ('PASS','DENIED','OPERATIONAL')""",
                (since,),
            ).fetchone()
            tools=conn.execute(
                """SELECT COALESCE(tool_id,'unknown') AS tool_id,COUNT(*) AS calls
                     FROM activity_events
                    WHERE at_utc >= ? AND event IN ('PASS','DENIED','OPERATIONAL')
                    GROUP BY COALESCE(tool_id,'unknown')
                    ORDER BY calls DESC,tool_id
                    LIMIT 6""",
                (since,),
            ).fetchall()
            failure_rows=conn.execute(
                """SELECT COALESCE(error_code,'UNKNOWN') AS error_code,COUNT(*) AS calls
                     FROM activity_events
                    WHERE at_utc >= ? AND event='DENIED' AND state='FAILED'
                    GROUP BY COALESCE(error_code,'UNKNOWN')
                    ORDER BY calls DESC,error_code""",
                (since,),
            ).fetchall()
            errors=failure_rows[:6]
            transports=conn.execute(
                """SELECT DISTINCT COALESCE(transport_mode,'LOCAL_AGENT') AS transport_mode
                     FROM activity_events
                    WHERE at_utc >= ? AND event IN ('PASS','DENIED','OPERATIONAL')
                    ORDER BY transport_mode""",
                (since,),
            ).fetchall()
            duration_rows=conn.execute(
                """SELECT duration_ms
                     FROM activity_events
                    WHERE at_utc >= ?
                      AND state='COMPLETED'
                      AND duration_ms IS NOT NULL
                    ORDER BY event_id DESC
                    LIMIT ?""",
                (since,SLO_LATENCY_SAMPLE_MAX),
            ).fetchall()
            events=[]
            if include_events:
                events=conn.execute(
                    """SELECT at_utc,event,state,tool_id,function_id,error_code,receipt_sha256,
                              action_summary,duration_ms,transport_mode
                         FROM activity_events
                        WHERE at_utc >= ? AND event IN ('PASS','DENIED','OPERATIONAL')
                        ORDER BY event_id DESC
                        LIMIT ?""",
                    (since,limit),
                ).fetchall()
    except Exception:
        row=None; tools=[]; failure_rows=[]; errors=[]; transports=[]; duration_rows=[]; events=[]
    total=int((row["total_calls"] if row else 0) or 0)
    completed=int((row["completed"] if row else 0) or 0)
    failed=int((row["failed"] if row else 0) or 0)
    operational=int((row["operational"] if row else 0) or 0)
    failure_classes={"CLIENT_ACTION":0,"POLICY":0,"SERVICE":0}
    for item in failure_rows:
        klass=_slo_failure_class(item["error_code"])
        failure_classes[klass]+=int(item["calls"] or 0)
    client_failed=failure_classes["CLIENT_ACTION"]
    policy_failed=failure_classes["POLICY"]
    service_failed=failure_classes["SERVICE"]
    terminal=completed+failed
    availability_terminal=completed+service_failed
    under3=int((row["under_3s"] if row else 0) or 0)
    duration_population=int((row["duration_population"] if row else 0) or 0)
    durations=[int(x["duration_ms"]) for x in duration_rows if x["duration_ms"] is not None]
    latency_p50=_nearest_rank_percentile(durations,50)
    latency_p95=_nearest_rank_percentile(durations,95)
    latency_p99=_nearest_rank_percentile(durations,99)
    summary={
        "total_calls":total,
        "completed":completed,
        "failed":failed,"operational":operational,
        "client_failed":client_failed,
        "policy_failed":policy_failed,
        "service_failed":service_failed,
        "pending":0,
        "executing":0,
        "expired":0,
        "cancelled":0,
        "success_rate_percent":round((completed/terminal)*100,1) if terminal else None,
        "availability_success_rate_percent":round((completed/availability_terminal)*100,1) if availability_terminal else None,
        "under_3s_percent":round((under3/completed)*100,1) if completed else None,
        "avg_queue_ms":0.0 if total else None,
        "avg_execution_ms":float(row["avg_total_ms"]) if row and row["avg_total_ms"] is not None else None,
        "avg_total_ms":float(row["avg_total_ms"]) if row and row["avg_total_ms"] is not None else None,
        "latency_p50_ms":latency_p50,
        "latency_p95_ms":latency_p95,
        "latency_p99_ms":latency_p99,
        "latency_sample_size":len(durations),
        "latency_population_size":duration_population,
        "latency_sample_capped":duration_population>len(durations),
        "device_count":1 if total else 0,
        "transport_modes":[str(x["transport_mode"]) for x in transports],
    }
    return {
        "schema":"hara.commander-local-activity.v2",
        "source":"LOCAL_SQLITE",
        "window":{"key":key,"label":{"24h":"24 horas","7d":"7 dias","30d":"30 dias"}[key],"since_at_utc":since},
        "privacy":{
            "local_authoritative":True,
            "payload_values_exposed":False,
            "result_values_exposed":False,
            "cloud_history_persisted":False,
            "action_summary_local_only":True,
        },
        "summary":summary,
        "slo":_internal_slo(summary),
        "diagnostics":{
            "top_tools":[{"tool_id":str(x["tool_id"]),"calls":int(x["calls"])} for x in tools],
            "top_errors":[{"error_code":str(x["error_code"]),"calls":int(x["calls"])} for x in errors],
        },
        "events":[{
            "at_utc":x["at_utc"],"event":x["event"],"state":x["state"],
            "tool_id":x["tool_id"],"function_id":x["function_id"],
            "error_code":x["error_code"],"receipt_sha256":x["receipt_sha256"],
            "action_summary":x["action_summary"],"duration_ms":x["duration_ms"],
            "transport_mode":x["transport_mode"],"local_only":True,
        } for x in events],
    }

def local_activity_heartbeat_snapshot():
    return {
        "schema":"hara.commander-local-activity-snapshots.v1",
        "generated_at_utc":utcnow(),
        "windows":{
            key:local_activity_snapshot(key,limit=1,include_events=False)
            for key in ("24h","7d","30d")
        },
        "detail_location":"LOCAL_DEVICE",
        "customer_content_synced":False,
    }

def _budget_counts(conn,budget_id):
    row=conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN state='COMMITTED' THEN units ELSE 0 END),0) AS committed,
             COALESCE(SUM(CASE WHEN state='RESERVED' THEN units ELSE 0 END),0) AS reserved
           FROM local_budget_debits
          WHERE budget_id = ?""",
        (str(budget_id),),
    ).fetchone()
    return int(row["committed"] or 0), int(row["reserved"] or 0)

def _local_budget_report():
    try:
        with _ops_connect() as conn:
            row=conn.execute(
                """SELECT budget_id,lease_token,allocated_units,state,expires_at_utc
                     FROM local_budget_blocks
                    ORDER BY issued_at_utc DESC
                    LIMIT 1"""
            ).fetchone()
            if not row:
                return None
            committed,_reserved=_budget_counts(conn,row["budget_id"])
            return {
                "budget_id":str(row["budget_id"]),
                "lease_token":str(row["lease_token"]),
                "committed_units":committed,
            }
    except Exception:
        return None

def _b64url_decode(value):
    text=str(value or "")
    if not text or not re.fullmatch(r"[A-Za-z0-9_-]+",text):
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID")
    return base64.urlsafe_b64decode(text + ("="*((4-len(text)%4)%4)))

def _verify_rs256(signing_input,signature_b64):
    n=int.from_bytes(_b64url_decode(PRODUCT_LEASE_RSA_N),"big")
    e=int.from_bytes(_b64url_decode(PRODUCT_LEASE_RSA_E),"big")
    signature=_b64url_decode(signature_b64)
    size=(n.bit_length()+7)//8
    if len(signature)!=size:
        raise ValueError("PRODUCT_LEASE_SIGNATURE_INVALID")
    em=pow(int.from_bytes(signature,"big"),e,n).to_bytes(size,"big")
    digest=hashlib.sha256(signing_input.encode("ascii")).digest()
    digest_info=bytes.fromhex("3031300d060960864801650304020105000420")+digest
    pad_len=size-len(digest_info)-3
    if pad_len<8:
        raise ValueError("PRODUCT_LEASE_SIGNATURE_INVALID")
    expected=b"\x00\x01"+(b"\xff"*pad_len)+b"\x00"+digest_info
    if not hmac.compare_digest(em,expected):
        raise ValueError("PRODUCT_LEASE_SIGNATURE_INVALID")

def verify_product_lease_token(config,token):
    parts=str(token or "").split(".")
    if len(parts)!=3:
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID")
    try:
        header=json.loads(_b64url_decode(parts[0]).decode("utf-8"))
        claims=json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception as exc:
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID") from exc
    if (
        header.get("alg")!="RS256"
        or header.get("kid")!=PRODUCT_LEASE_KID
        or header.get("typ")!="JWT"
    ):
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID")
    _verify_rs256(parts[0]+"."+parts[1],parts[2])
    expected_issuer=_portal_origin(config.get("HARA_COMMANDER_URL"))
    if str(claims.get("iss") or "")!=str(expected_issuer or ""):
        raise ValueError("PRODUCT_LEASE_ISSUER_INVALID")
    if str(claims.get("aud") or "")!=PRODUCT_LEASE_AUDIENCE:
        raise ValueError("PRODUCT_LEASE_AUDIENCE_INVALID")
    lease=claims.get("lease") or {}
    if lease.get("schema")!="hara.commander-device-product-lease.v1":
        raise ValueError("PRODUCT_LEASE_INVALID")
    if str(claims.get("sub") or "")!=str(config.get("HARA_DEVICE_ID") or ""):
        raise ValueError("PRODUCT_LEASE_DEVICE_MISMATCH")
    if str(lease.get("device_id") or "")!=str(config.get("HARA_DEVICE_ID") or ""):
        raise ValueError("PRODUCT_LEASE_DEVICE_MISMATCH")
    if str(claims.get("jti") or "")!=str(lease.get("lease_id") or ""):
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID")
    now=int(time.time())
    try:
        issued=int(claims.get("iat"))
        expires=int(claims.get("exp"))
    except Exception as exc:
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID") from exc
    if issued>now+60 or expires<=now or expires-issued>PRODUCT_LEASE_REFRESH_SECONDS+3*60*60:
        raise ValueError("PRODUCT_LEASE_EXPIRED")
    lease_expiry=datetime.fromisoformat(str(lease.get("valid_until_utc")).replace("Z","+00:00")).timestamp()
    if abs(lease_expiry-expires)>2:
        raise ValueError("PRODUCT_LEASE_TOKEN_INVALID")
    return lease

def _active_verified_product_lease(conn,config):
    row=conn.execute(
        "SELECT lease_json,lease_token,valid_until_utc FROM product_lease WHERE singleton=1"
    ).fetchone()
    if not row or not row["lease_token"]:
        return None
    try:
        lease=verify_product_lease_token(config,str(row["lease_token"]))
        stored=json.loads(str(row["lease_json"]))
        expires=datetime.fromisoformat(str(row["valid_until_utc"]).replace("Z","+00:00")).timestamp()
    except Exception:
        return None
    if expires<=time.time():
        return None
    if json.dumps(lease,sort_keys=True,separators=(",",":"))!=json.dumps(stored,sort_keys=True,separators=(",",":")):
        return None
    return lease

def _store_product_lease_response(config,payload):
    if not isinstance(payload,dict) or payload.get("schema")!="hara.commander-device-product-lease-response.v1":
        raise ValueError("PRODUCT_LEASE_RESPONSE_INVALID")
    token=str(payload.get("product_lease_token") or "")
    signature=payload.get("product_lease_signature") or {}
    if signature.get("alg")!="RS256" or signature.get("kid")!=PRODUCT_LEASE_KID:
        raise ValueError("PRODUCT_LEASE_SIGNATURE_INVALID")
    verified=verify_product_lease_token(config,token)
    lease=payload.get("product_lease") or {}
    if json.dumps(verified,sort_keys=True,separators=(",",":"))!=json.dumps(lease,sort_keys=True,separators=(",",":")):
        raise ValueError("PRODUCT_LEASE_PAYLOAD_MISMATCH")
    if lease.get("schema")!="hara.commander-device-product-lease.v1":
        raise ValueError("PRODUCT_LEASE_INVALID")
    if str(lease.get("device_id") or "")!=str(config.get("HARA_DEVICE_ID") or ""):
        raise ValueError("PRODUCT_LEASE_DEVICE_MISMATCH")
    valid_until=str(lease.get("valid_until_utc") or "")
    if not valid_until:
        raise ValueError("PRODUCT_LEASE_INVALID")
    budget=payload.get("budget") or {}
    block=budget.get("block") if isinstance(budget,dict) else None
    with _ops_connect() as conn:
        conn.execute(
            """INSERT INTO product_lease(singleton,lease_json,lease_token,valid_until_utc,updated_at_utc)
               VALUES (1,?,?,?,?)
               ON CONFLICT(singleton) DO UPDATE SET
                 lease_json=excluded.lease_json,
                 lease_token=excluded.lease_token,
                 valid_until_utc=excluded.valid_until_utc,
                 updated_at_utc=excluded.updated_at_utc""",
            (
                json.dumps(lease,sort_keys=True,separators=(",",":")),
                token,
                valid_until,
                utcnow(),
            ),
        )
        if block:
            required={
                "budget_id","tenant_id","device_id","entitlement_id","plan_code","meter_id",
                "period_key","allocated_units","lease_token","issued_at_utc","expires_at_utc",
            }
            if not required.issubset(block):
                raise ValueError("LOCAL_BUDGET_BLOCK_INVALID")
            if str(block["device_id"])!=str(config.get("HARA_DEVICE_ID") or ""):
                raise ValueError("LOCAL_BUDGET_DEVICE_MISMATCH")
            for key in ("tenant_id","entitlement_id","plan_code","meter_id"):
                if str(block.get(key) or "")!=str(lease.get(key) or ""):
                    raise ValueError("LOCAL_BUDGET_LEASE_BINDING_INVALID")
            if str(lease.get("usage_mode") or "")!="LOCAL_BUDGET":
                raise ValueError("LOCAL_BUDGET_LEASE_BINDING_INVALID")
            units=int(block["allocated_units"])
            if units<1 or units>10000:
                raise ValueError("LOCAL_BUDGET_BLOCK_INVALID")
            conn.execute(
                """INSERT INTO local_budget_blocks
                   (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,period_key,
                    allocated_units,lease_token,issued_at_utc,expires_at_utc,state)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'ACTIVE')
                   ON CONFLICT(budget_id) DO UPDATE SET
                     lease_token=excluded.lease_token,
                     expires_at_utc=excluded.expires_at_utc""",
                (
                    str(block["budget_id"]),str(block["tenant_id"]),str(block["device_id"]),
                    str(block["entitlement_id"]),str(block["plan_code"]),str(block["meter_id"]),
                    str(block["period_key"]),units,str(block["lease_token"]),
                    str(block["issued_at_utc"]),str(block["expires_at_utc"]),
                ),
            )
        conn.commit()
    return lease

def _local_usage_baseline(conn,config):
    device_id=str(config.get("HARA_DEVICE_ID") or "")
    if not device_id:
        raise ValueError("DEVICE_CONFIG_INVALID")
    stored=conn.execute(
        "SELECT meta_value FROM local_store_meta WHERE meta_key='local_usage_device_id'"
    ).fetchone()
    baseline=conn.execute(
        "SELECT meta_value FROM local_store_meta WHERE meta_key='local_usage_baseline_event_id'"
    ).fetchone()
    stored_device=str(stored["meta_value"] if stored else "")
    if not stored_device:
        # First adoption of aggregate sync: include existing LOCAL_MCP history for
        # this enrolled device. Local MCP was zero-relay and therefore was not
        # represented in commander_device_calls.
        baseline_event_id=0
    elif stored_device != device_id:
        # Re-enrollment creates a new device identity while preserving the local
        # SQLite store. Do not reattribute historical calls to the new device.
        row=conn.execute("SELECT COALESCE(MAX(event_id),0) AS event_id FROM activity_events").fetchone()
        baseline_event_id=int((row["event_id"] if row else 0) or 0)
    else:
        try:
            baseline_event_id=int((baseline["meta_value"] if baseline else "0") or 0)
        except Exception:
            baseline_event_id=0
    if stored_device != device_id or not baseline:
        conn.execute(
            "INSERT INTO local_store_meta(meta_key,meta_value) VALUES('local_usage_device_id',?) "
            "ON CONFLICT(meta_key) DO UPDATE SET meta_value=excluded.meta_value",
            (device_id,),
        )
        conn.execute(
            "INSERT INTO local_store_meta(meta_key,meta_value) VALUES('local_usage_baseline_event_id',?) "
            "ON CONFLICT(meta_key) DO UPDATE SET meta_value=excluded.meta_value",
            (str(baseline_event_id),),
        )
        conn.commit()
    return baseline_event_id

def local_usage_report(config):
    with _ops_connect() as conn:
        baseline_event_id=_local_usage_baseline(conn,config)
        lifetime=conn.execute(
            """SELECT COUNT(*) AS units
                 FROM activity_events
                WHERE event_id > ?
                  AND tool_id IS NOT NULL
                  AND transport_mode='LOCAL_MCP'
                  AND event IN ('PASS','OPERATIONAL','DENIED')""",
            (baseline_event_id,),
        ).fetchone()
        rows=conn.execute(
            """SELECT substr(at_utc,1,10) AS day_key,COUNT(*) AS units
                 FROM activity_events
                WHERE event_id > ?
                  AND tool_id IS NOT NULL
                  AND transport_mode='LOCAL_MCP'
                  AND event IN ('PASS','OPERATIONAL','DENIED')
                  AND at_utc >= ?
                GROUP BY substr(at_utc,1,10)
                ORDER BY day_key""",
            (
                baseline_event_id,
                (datetime.now(timezone.utc)-timedelta(days=13)).date().isoformat(),
            ),
        ).fetchall()
    return {
        "schema":"hara.commander-local-usage-report.v1",
        "lifetime_units":int((lifetime["units"] if lifetime else 0) or 0),
        "daily":[{"day_key":str(row["day_key"]),"units":int(row["units"] or 0)} for row in rows],
        "metadata_only":True,
        "customer_content_included":False,
    }

def _local_meta_get(key):
    with _ops_connect() as conn:
        row=conn.execute(
            "SELECT meta_value FROM local_store_meta WHERE meta_key=?",
            (str(key),),
        ).fetchone()
    return None if not row else str(row["meta_value"])

def _local_meta_set(key,value):
    with _ops_connect() as conn:
        conn.execute(
            "INSERT INTO local_store_meta(meta_key,meta_value) VALUES(?,?) "
            "ON CONFLICT(meta_key) DO UPDATE SET meta_value=excluded.meta_value",
            (str(key),str(value)),
        )
        conn.commit()

def _iso_epoch(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z","+00:00")).timestamp()
    except Exception:
        return None

def local_metering_sync_due(now_epoch=None):
    now_epoch=time.time() if now_epoch is None else float(now_epoch)
    last=_iso_epoch(_local_meta_get("local_metering_last_sync_at_utc") or "")
    if last is None:
        return True
    return now_epoch-last >= LOCAL_METERING_MIN_INTERVAL_SECONDS

def local_metering_sync(config,event_type,session_id,session_started_at_utc,session_duration_seconds=None):
    event=str(event_type or "").strip().upper()
    if event not in {"MCP_START","MCP_STOP"}:
        raise ValueError("LOCAL_METERING_EVENT_INVALID")
    if event=="MCP_STOP" and (session_duration_seconds is None or int(session_duration_seconds)<LOCAL_METERING_MIN_INTERVAL_SECONDS):
        append_console_event(
            "METERING_SYNC_SKIPPED",
            state="SESSION_UNDER_MIN_INTERVAL",
            action_summary="event=MCP_STOP",
        )
        return {"attempted":False,"reason":"SESSION_UNDER_MIN_INTERVAL"}
    if transport_mode(config)!="LOCAL_TUNNEL":
        return {"attempted":False,"reason":"TRANSPORT_NOT_LOCAL_TUNNEL"}
    try:
        with _ops_connect() as conn:
            lease=_active_verified_product_lease(conn,config)
        if not lease or str(lease.get("transport_mode") or "")!="LOCAL_TUNNEL":
            return {"attempted":False,"reason":"LEASE_NOT_ACTIVE"}
    except Exception:
        return {"attempted":False,"reason":"LEASE_NOT_ACTIVE"}
    if not local_metering_sync_due():
        append_console_event(
            "METERING_SYNC_SKIPPED",
            state="THROTTLED_LOCAL",
            action_summary="event="+event,
        )
        return {"attempted":False,"reason":"MIN_INTERVAL"}

    payload={
        "schema":"hara.commander-local-metering-sync.v1",
        "event_type":event,
        "session_id":str(session_id),
        "session_started_at_utc":str(session_started_at_utc),
        "session_duration_seconds":None if session_duration_seconds is None else max(0,int(session_duration_seconds)),
        "agent_version":AGENT_VERSION,
        "transport_mode":"LOCAL_TUNNEL",
        "usage_report":local_usage_report(config),
        "metadata_only":True,
        "customer_content_included":False,
    }
    try:
        response=post_json(
            config["HARA_COMMANDER_URL"]+"/api/device/metering-sync",
            config["HARA_DEVICE_TOKEN"],
            payload,
            timeout=8,
        ) or {}
        accepted=response.get("accepted") is True
        if accepted:
            synced_at=str(response.get("event_at_utc") or response.get("server_time_utc") or utcnow())
            _local_meta_set("local_metering_last_sync_at_utc",synced_at)
            _local_meta_set("local_metering_last_event",event)
            append_console_event(
                "METERING_SYNC",
                state="SYNCED",
                action_summary="event="+event,
            )
            return {"attempted":True,"accepted":True,"event":event}
        if str(response.get("code") or "")=="LOCAL_METERING_THROTTLED":
            # Another local MCP process may have synchronized first. Respect the
            # server's one-hour window locally so retries do not create traffic.
            server_time=str(response.get("server_time_utc") or utcnow())
            _local_meta_set("local_metering_last_sync_at_utc",server_time)
            append_console_event(
                "METERING_SYNC_SKIPPED",
                state="THROTTLED_SERVER",
                action_summary="event="+event,
            )
            return {"attempted":True,"accepted":False,"reason":"SERVER_THROTTLED"}
        return {"attempted":True,"accepted":False,"reason":"NOT_ACCEPTED"}
    except Exception as exc:
        append_console_event(
            "METERING_SYNC_DEGRADED",
            state="DEGRADED",
            error_code=safe_error_code(exc),
            action_summary="event="+event,
        )
        return {"attempted":True,"accepted":False,"reason":"CONTROL_PLANE_UNAVAILABLE"}

def _local_metering_sync_background(config,event_type,session_id,session_started_at_utc):
    try:
        local_metering_sync(config,event_type,session_id,session_started_at_utc)
    except Exception as exc:
        append_console_event(
            "METERING_SYNC_DEGRADED",
            state="DEGRADED",
            error_code=safe_error_code(exc),
            action_summary="event="+str(event_type),
        )

def refresh_product_lease(config,authorization_code=None,requested_transport=None):
    report=_local_budget_report()
    body={"usage_report":local_usage_report(config)}
    if report:
        body["budget_report"]=report
    if authorization_code:
        body["authorization_code"]=str(authorization_code)
    if requested_transport:
        body["transport_mode"]=str(requested_transport)
    payload=post_json(
        config["HARA_COMMANDER_URL"]+"/api/device/product-lease",
        config["HARA_DEVICE_TOKEN"],
        body,
        timeout=20,
    )
    lease=_store_product_lease_response(config,payload)
    append_console_event(
        "PRODUCT_LEASE_REFRESH",
        state=str(lease.get("usage_mode") or "UNKNOWN"),
        action_summary="plan="+str(lease.get("plan_code") or ""),
    )
    return payload

def _local_budget_find_available(conn,period_key,units):
    rows=conn.execute(
        """SELECT budget_id,allocated_units,expires_at_utc
             FROM local_budget_blocks
            WHERE period_key = ?
              AND state = 'ACTIVE'
              AND expires_at_utc > ?
            ORDER BY issued_at_utc ASC""",
        (str(period_key),utcnow()),
    ).fetchall()
    for row in rows:
        committed,reserved=_budget_counts(conn,row["budget_id"])
        if int(row["allocated_units"])-committed-reserved >= units:
            return row
    return None

def local_budget_reserve(config,call):
    usage=(call or {}).get("usage") or {}
    if str(usage.get("mode") or "")!="LOCAL_BUDGET":
        return None
    units=int(usage.get("units") or 0)
    period_key=str(usage.get("period_key") or "")
    budget_id=str(usage.get("budget_id") or "")
    request_id=str((call or {}).get("request_id") or "")
    if units<1 or not period_key or not budget_id or not request_id:
        raise ValueError("LOCAL_BUDGET_USAGE_INVALID")

    missing_lease=False
    for attempt in range(2):
        missing_lease=False
        with _ops_connect() as conn:
            lease=_active_verified_product_lease(conn,config)
            if not lease or str(lease.get("usage_mode") or "")!="LOCAL_BUDGET":
                missing_lease=True
            else:
                existing=conn.execute(
                    "SELECT budget_id,units,state FROM local_budget_debits WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if existing:
                    if str(existing["budget_id"])!=budget_id or int(existing["units"])!=units:
                        raise ValueError("LOCAL_BUDGET_IDEMPOTENCY_CONFLICT")
                    state=str(existing["state"])
                    if state=="RESERVED":
                        return {
                            "request_id":request_id,
                            "budget_id":str(existing["budget_id"]),
                            "units":int(existing["units"]),
                            "state":state,
                            "existing":True,
                        }
                    if state=="COMMITTED":
                        raise ValueError("LOCAL_BUDGET_REQUEST_ALREADY_COMMITTED")
                    raise ValueError("LOCAL_BUDGET_REQUEST_TERMINAL")

                block=conn.execute(
                    """SELECT budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,
                              period_key,allocated_units,expires_at_utc
                         FROM local_budget_blocks
                        WHERE budget_id = ?
                          AND period_key = ?
                          AND state = 'ACTIVE'
                          AND expires_at_utc > ?
                        LIMIT 1""",
                    (budget_id,period_key,utcnow()),
                ).fetchone()
                if block:
                    for key in ("tenant_id","device_id","entitlement_id","plan_code","meter_id"):
                        expected=str(lease.get(key) or "")
                        observed=str(block[key] or "")
                        if observed!=expected:
                            raise ValueError("LOCAL_BUDGET_LEASE_BINDING_INVALID")
                    committed,reserved=_budget_counts(conn,block["budget_id"])
                    if int(block["allocated_units"])-committed-reserved < units:
                        block=None
                if block:
                    now=utcnow()
                    conn.execute(
                        """INSERT INTO local_budget_debits
                           (request_id,budget_id,units,state,created_at_utc,updated_at_utc)
                           VALUES (?,?,?,'RESERVED',?,?)""",
                        (request_id,str(block["budget_id"]),units,now,now),
                    )
                    conn.commit()
                    return {
                        "request_id":request_id,
                        "budget_id":str(block["budget_id"]),
                        "units":units,
                        "state":"RESERVED",
                        "existing":False,
                    }

        if attempt==0 and transport_mode(config)!="LOCAL_TUNNEL":
            refresh_product_lease(config)

    if missing_lease:
        raise ValueError("PRODUCT_LEASE_REQUIRED")
    raise ValueError("LOCAL_BUDGET_EXHAUSTED")

def local_budget_commit(request_id):
    with _ops_connect() as conn:
        row=conn.execute(
            "SELECT budget_id,units,state FROM local_budget_debits WHERE request_id = ?",
            (str(request_id),),
        ).fetchone()
        if not row:
            raise ValueError("LOCAL_BUDGET_DEBIT_NOT_FOUND")
        if str(row["state"])=="COMMITTED":
            return {"state":"COMMITTED","existing":True,"budget_id":str(row["budget_id"])}
        if str(row["state"])!="RESERVED":
            raise ValueError("LOCAL_BUDGET_DEBIT_NOT_ACTIVE")
        now=utcnow()
        conn.execute(
            "UPDATE local_budget_debits SET state='COMMITTED',updated_at_utc=? WHERE request_id=?",
            (now,str(request_id)),
        )
        committed,reserved=_budget_counts(conn,row["budget_id"])
        block=conn.execute(
            "SELECT allocated_units FROM local_budget_blocks WHERE budget_id=?",
            (str(row["budget_id"]),),
        ).fetchone()
        exhausted=bool(block and committed>=int(block["allocated_units"]) and reserved==0)
        if exhausted:
            conn.execute(
                "UPDATE local_budget_blocks SET state='EXHAUSTED' WHERE budget_id=?",
                (str(row["budget_id"]),),
            )
        conn.commit()
        return {
            "state":"COMMITTED","existing":False,"budget_id":str(row["budget_id"]),
            "committed_units":committed,
            "exhausted":exhausted,
        }

def local_budget_release(request_id):
    with _ops_connect() as conn:
        row=conn.execute(
            "SELECT budget_id,state FROM local_budget_debits WHERE request_id = ?",
            (str(request_id),),
        ).fetchone()
        if not row:
            return {"state":"ABSENT","existing":False}
        if str(row["state"])=="RELEASED":
            return {"state":"RELEASED","existing":True,"budget_id":str(row["budget_id"])}
        if str(row["state"])=="COMMITTED":
            return {"state":"COMMITTED","existing":True,"budget_id":str(row["budget_id"])}
        conn.execute(
            "UPDATE local_budget_debits SET state='RELEASED',updated_at_utc=? WHERE request_id=?",
            (utcnow(),str(request_id)),
        )
        conn.commit()
        return {"state":"RELEASED","existing":False,"budget_id":str(row["budget_id"])}

def _portal_origin(value):
    parsed=urllib.parse.urlparse(str(value or ""))
    if parsed.scheme not in {"http","https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"

class _LocalPortalHandler(BaseHTTPRequestHandler):
    protocol_version="HTTP/1.1"
    server_version="HARA-Commander-Local/1"

    def log_message(self, _format, *_args):
        return

    def _origin_allowed(self):
        origin=str(self.headers.get("Origin") or "")
        return not origin or origin in getattr(self.server,"allowed_origins",set())

    def _cors_headers(self):
        origin=str(self.headers.get("Origin") or "")
        if origin and origin in getattr(self.server,"allowed_origins",set()):
            self.send_header("Access-Control-Allow-Origin",origin)
            self.send_header("Vary","Origin")
        self.send_header("Access-Control-Allow-Methods","GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","content-type")
        self.send_header("Access-Control-Allow-Private-Network","true")
        self.send_header("Cache-Control","no-store")

    def _json(self,status,payload):
        raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Content-Length",str(len(raw)))
        self.end_headers()
        if raw:
            self.wfile.write(raw)

    def do_OPTIONS(self):
        if not self._origin_allowed():
            self._json(403,{"ok":False,"code":"LOCAL_ORIGIN_DENIED"})
            return
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length","0")
        self.end_headers()

    def do_GET(self):
        if not self._origin_allowed():
            self._json(403,{"ok":False,"code":"LOCAL_ORIGIN_DENIED"})
            return
        parsed=urllib.parse.urlparse(self.path)
        if parsed.path=="/v1/health":
            config=getattr(self.server,"hara_config",{})
            self._json(200,{
                "schema":"hara.commander-local-portal-health.v1",
                "ok":True,
                "computer":platform.node(),
                "device_id":config.get("HARA_DEVICE_ID"),
                "agent_version":AGENT_VERSION,
                "source":"LOCAL_AGENT",
            })
            return
        if parsed.path=="/v1/activity":
            query=urllib.parse.parse_qs(parsed.query,keep_blank_values=False)
            window=str((query.get("window") or ["7d"])[0])
            try:
                limit=int((query.get("limit") or ["50"])[0])
            except Exception:
                limit=50
            snap=local_activity_snapshot(window,limit=limit,include_events=True)
            config=getattr(self.server,"hara_config",{})
            snap.update({
                "scope":"LOCAL_DEVICE",
                "computer":platform.node(),
                "device_id":config.get("HARA_DEVICE_ID"),
                "agent_version":AGENT_VERSION,
                "detail_location":"LOCAL_DEVICE",
                "local_direct":True,
            })
            self._json(200,snap)
            return
        if parsed.path=="/v1/support":
            self._json(200,build_support_report())
            return
        self._json(404,{"ok":False,"code":"LOCAL_NOT_FOUND"})

def start_local_portal_server(config):
    origin=_portal_origin(config.get("HARA_COMMANDER_URL"))
    allowed={origin} if origin else set()
    try:
        server=ThreadingHTTPServer((LOCAL_PORTAL_HOST,LOCAL_PORTAL_PORT),_LocalPortalHandler)
        server.daemon_threads=True
        server.allowed_origins=allowed
        server.hara_config=dict(config)
        thread=threading.Thread(target=server.serve_forever,name="hara-local-portal",daemon=True)
        thread.start()
        append_console_event(
            "LOCAL_PORTAL_ONLINE",
            state="LOOPBACK_ONLY",
            action_summary=f"http://{LOCAL_PORTAL_HOST}:{LOCAL_PORTAL_PORT}",
        )
        return server
    except OSError as exc:
        append_console_event("LOCAL_PORTAL_UNAVAILABLE",state="DEGRADED",error_code=safe_error_code(exc))
        return None

def append_console_event(event, call=None, *, state=None, error_code=None, receipt_sha256=None, approval_id=None, action_summary=None, duration_ms=None):
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = {
        "schema":"hara.commander-console-event.v1",
        "at_utc":utcnow(),
        "event":str(event),
        "state":state,
        "tool_id":None,
        "function_id":None,
        "request_id":None,
        "error_code":error_code,
        "receipt_sha256":receipt_sha256,
        "approval_id":approval_id,
        "action_summary":action_summary,
        "duration_ms":None if duration_ms is None else max(0,int(duration_ms)),
        "transport_mode":str((call or {}).get("_transport") or "OUTBOUND_RELAY") if isinstance(call,dict) else "LOCAL_AGENT",
        "local_only":True,
        "payload_values_exposed":False,
        "secret_material_exposed":False,
    }
    if isinstance(call, dict):
        payload["tool_id"] = str(call.get("tool_id") or "") or None
        inner = call.get("payload") or {}
        payload["function_id"] = str(inner.get("function_id") or DIRECT_TOOL_FUNCTIONS.get(payload["tool_id"]) or "") or None
        payload["request_id"] = str(call.get("request_id") or "") or None
        if not payload.get("action_summary") and _is_mutation_tool(payload.get("tool_id")):
            payload["action_summary"] = _safe_action_summary(call)
    _ops_insert_event(payload)
    with CONSOLE_EVENTS_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    os.chmod(CONSOLE_EVENTS_FILE, 0o600)

def _format_console_event(payload):
    at = str(payload.get("at_utc") or "")
    stamp = at[11:19] if len(at) >= 19 else "--:--:--"
    event = str(payload.get("event") or "EVENT")
    tool = str(payload.get("tool_id") or "-")
    function_id = str(payload.get("function_id") or "-")
    request_id = str(payload.get("request_id") or "")
    state = str(payload.get("state") or "")
    error = str(payload.get("error_code") or "")
    receipt = str(payload.get("receipt_sha256") or "")
    approval_id = str(payload.get("approval_id") or "")
    action_summary = str(payload.get("action_summary") or "")
    command = tool if tool != "-" else function_id
    suffix = f" cliente=MCP comando={command} tool={tool}"
    if function_id != "-" and function_id != tool:
        suffix += " funcao=" + function_id
    if request_id:
        suffix += " request=" + request_id[:12] + ("..." if len(request_id) > 12 else "")
    if state:
        suffix += " state=" + state
    if error:
        suffix += " error=" + error
    if receipt:
        suffix += " receipt=" + receipt[:12] + "..."
    if action_summary:
        suffix += " acao=" + action_summary
    if approval_id:
        suffix += " approval=" + approval_id[:12] + "..."
    return f"[{stamp}] {event:<18}{suffix}"

def _redact_command_preview(value):
    text=str(value or "")
    text=re.sub(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*=\s*([^\s]+)",lambda m:m.group(1)+"=<redacted>",text)
    text=re.sub(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+",r"\1<redacted>",text)
    return text if len(text)<=240 else text[:237]+"..."

def _safe_action_summary(call):
    tool=str(call.get("tool_id") or "")
    p=call.get("payload") or {}
    if tool=="hara.files.create_directory": return f"mkdir path={p.get('path')}"
    if tool=="hara.files.write": return f"write mode={p.get('mode','rewrite')} path={p.get('path')} bytes={len(str(p.get('content') or '').encode('utf-8'))}"
    if tool=="hara.files.edit": return f"edit path={p.get('path')} old_bytes={len(str(p.get('old_text') or '').encode('utf-8'))} new_bytes={len(str(p.get('new_text') or '').encode('utf-8'))} all={bool(p.get('replace_all'))}"
    if tool=="hara.files.move": return f"move {p.get('source')} -> {p.get('destination')}"
    if tool=="hara.files.copy": return f"copy {p.get('source')} -> {p.get('destination')}"
    if tool=="hara.files.delete": return f"delete file path={p.get('path')} (preimage required)"
    if tool=="hara.files.rollback": return f"rollback preimage={p.get('preimage_id')}"
    if tool=="hara.process.run": return f"process.run cwd={p.get('cwd') or '~'} timeout_ms={p.get('timeout_ms',3000)} command={_redact_command_preview(p.get('command'))}"
    if tool=="hara.process.start": return f"process.start cwd={p.get('cwd') or '~'} command={_redact_command_preview(p.get('command'))}"
    if tool=="hara.process.interact": return f"process.interact session={p.get('session_id')} input={_redact_command_preview(p.get('input'))}"
    if tool=="hara.process.kill": return f"process.kill session={p.get('session_id')} force={bool(p.get('force'))}"
    return tool or "mutation"

def _approval_paths(approval_id):
    safe=re.sub(r"[^A-Za-z0-9_.-]","_",str(approval_id))[:180]
    return APPROVAL_DIR/(safe+".request.json"), APPROVAL_DIR/(safe+".response.json")

def request_local_approval(call, timeout_seconds=30):
    config=load_config()
    configured_mode=str(config.get("HARA_COMMANDER_APPROVAL_MODE") or "ASK_EVERY_ACTION").upper()
    approval_id=str(call.get("call_id") or call.get("request_id") or "")
    if not approval_id: raise ValueError("APPROVAL_ID_MISSING")
    summary=_safe_action_summary(call)
    if configured_mode=="PERSISTENT_TRUSTED":
        append_console_event("APPROVAL_GRANTED",call,state="APPROVED",approval_id=approval_id,action_summary=summary)
        return {"state":"APPROVED","approval_id":approval_id,"decided_at_utc":utcnow(),"mode":"PERSISTENT_TRUSTED","source":"DEVICE_ENROLLMENT_POLICY"}
    session=read_operator_session()
    if not session: raise ValueError("LOCAL_OPERATOR_SESSION_REQUIRED")
    if str(session.get("agent_version") or "") != AGENT_VERSION:
        raise ValueError("LOCAL_OPERATOR_SESSION_UPGRADE_REQUIRED")
    mode=str(session.get("approval_mode") or "ASK_EVERY_ACTION").upper()
    if mode not in APPROVAL_MODES: raise ValueError("LOCAL_OPERATOR_APPROVAL_MODE_INVALID")
    if mode=="SESSION_TRUSTED":
        append_console_event("APPROVAL_GRANTED",call,state="APPROVED",approval_id=approval_id,action_summary=summary)
        return {"state":"APPROVED","approval_id":approval_id,"decided_at_utc":utcnow(),"mode":"SESSION_TRUSTED","source":"LOCAL_OPERATOR_SESSION"}
    APPROVAL_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    req_path,res_path=_approval_paths(approval_id)
    res_path.unlink(missing_ok=True)
    request={"schema":"hara.commander-local-approval.v1","approval_id":approval_id,"tool_id":str(call.get("tool_id") or ""),"action_summary":summary,"requested_at_utc":utcnow(),"expires_at_epoch":int(time.time()+timeout_seconds)}
    tmp=req_path.with_suffix(".tmp"); tmp.write_text(json.dumps(request,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(tmp,0o600); tmp.replace(req_path); os.chmod(req_path,0o600)
    append_console_event("APPROVAL_REQUIRED",call,state="WAITING",approval_id=approval_id,action_summary=summary)
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        if not operator_session_active(): raise ValueError("LOCAL_OPERATOR_SESSION_REQUIRED")
        if res_path.is_file():
            try: response=json.loads(res_path.read_text(encoding="utf-8"))
            except Exception: response={}
            decision=str(response.get("decision") or "DENIED").upper()
            req_path.unlink(missing_ok=True); res_path.unlink(missing_ok=True)
            if decision!="APPROVED":
                append_console_event("APPROVAL_DENIED",call,state="DENIED",approval_id=approval_id,action_summary=summary)
                raise ValueError("LOCAL_OPERATOR_APPROVAL_DENIED")
            append_console_event("APPROVAL_GRANTED",call,state="APPROVED",approval_id=approval_id,action_summary=summary)
            return {"state":"APPROVED","approval_id":approval_id,"decided_at_utc":str(response.get("decided_at_utc") or utcnow()),"mode":"ASK_EVERY_ACTION","source":"PER_ACTION_PROMPT"}
        time.sleep(0.1)
    req_path.unlink(missing_ok=True); res_path.unlink(missing_ok=True)
    append_console_event("APPROVAL_TIMEOUT",call,state="DENIED",approval_id=approval_id,action_summary=summary)
    raise ValueError("LOCAL_OPERATOR_APPROVAL_TIMEOUT")

def _preimage_paths(preimage_id):
    value=str(preimage_id or "")
    if not re.fullmatch(r"HARA-PREIMAGE-[0-9a-f]{32}",value): raise ValueError("PREIMAGE_ID_INVALID")
    return PREIMAGE_DIR/(value+".json"), PREIMAGE_DIR/(value+".bin")

def _load_preimage(preimage_id):
    meta_path,data_path=_preimage_paths(preimage_id)
    if not meta_path.is_file() or not data_path.is_file(): raise ValueError("PREIMAGE_NOT_FOUND")
    try: meta=json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception: raise ValueError("PREIMAGE_METADATA_INVALID")
    if meta.get("schema")!="hara.commander-file-preimage.v1" or meta.get("preimage_id")!=preimage_id: raise ValueError("PREIMAGE_METADATA_INVALID")
    data=data_path.read_bytes()
    sha=hashlib.sha256(data).hexdigest()
    if sha!=str(meta.get("sha256") or "") or len(data)!=int(meta.get("bytes") or -1): raise ValueError("PREIMAGE_INTEGRITY_FAILED")
    return meta,data

def _store_preimage(path, call_id, source_tool=None):
    if not path.exists() or not path.is_file(): return None
    resolved=path.resolve(strict=True)
    data=resolved.read_bytes()
    if len(data)>2*1024*1024: raise ValueError("PREIMAGE_FILE_TOO_LARGE")
    sha=hashlib.sha256(data).hexdigest()
    st=resolved.stat()
    preimage_id="HARA-PREIMAGE-"+uuid.uuid4().hex
    PREIMAGE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    meta_path,data_path=_preimage_paths(preimage_id)
    data_tmp=data_path.with_suffix(".tmp")
    data_tmp.write_bytes(data); os.chmod(data_tmp,0o600); os.replace(data_tmp,data_path); os.chmod(data_path,0o600)
    meta={
        "schema":"hara.commander-file-preimage.v1",
        "preimage_id":preimage_id,
        "original_path":str(resolved),
        "sha256":sha,
        "bytes":len(data),
        "mode":int(st.st_mode & 0o777),
        "source_call_id":str(call_id or "")[:180],
        "source_tool":str(source_tool or "")[:120] or None,
        "created_at_utc":utcnow(),
    }
    meta_tmp=meta_path.with_suffix(".tmp")
    meta_tmp.write_text(json.dumps(meta,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(meta_tmp,0o600); os.replace(meta_tmp,meta_path); os.chmod(meta_path,0o600)
    return meta

def filesystem_preimages_list(limit=50,path_filter=None):
    PREIMAGE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    wanted=None
    if path_filter:
        wanted=str(Path(path_filter).expanduser().resolve(strict=False))
    items=[]
    for meta_path in PREIMAGE_DIR.glob("HARA-PREIMAGE-*.json"):
        try:
            meta=json.loads(meta_path.read_text(encoding="utf-8"))
            pid=str(meta.get("preimage_id") or "")
            _load_preimage(pid)
            if wanted and str(meta.get("original_path") or "")!=wanted: continue
            items.append({
                "preimage_id":pid,
                "original_path":meta.get("original_path"),
                "sha256":meta.get("sha256"),
                "bytes":meta.get("bytes"),
                "source_tool":meta.get("source_tool"),
                "created_at_utc":meta.get("created_at_utc"),
            })
        except Exception:
            continue
    items.sort(key=lambda x:str(x.get("created_at_utc") or ""),reverse=True)
    capped=items[:max(1,min(100,int(limit)))]
    return {"count":len(capped),"preimages":capped,"truncated":len(items)>len(capped)}

def filesystem_rollback(call,preimage_id):
    meta,data=_load_preimage(preimage_id)
    target=Path(str(meta["original_path"]))
    if target.exists() and not target.is_file(): raise ValueError("ROLLBACK_TARGET_NOT_FILE")
    if not target.parent.exists() or not target.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    current=_store_preimage(target,(call.get("call_id") or "rollback")+"-current","hara.files.rollback") if target.exists() else None
    tmp=target.with_name("."+target.name+".hara-rollback-"+str(os.getpid()))
    tmp.write_bytes(data); os.chmod(tmp,int(meta.get("mode") or 0o600)); os.replace(tmp,target); os.chmod(target,int(meta.get("mode") or 0o600))
    restored_sha=hashlib.sha256(target.read_bytes()).hexdigest()
    if restored_sha!=meta["sha256"]: raise ValueError("ROLLBACK_VERIFY_FAILED")
    return {
        "path":str(target),
        "restored_from_preimage_id":preimage_id,
        "restored_sha256":restored_sha,
        "bytes_restored":len(data),
        "rollback_preimage_id":current.get("preimage_id") if current else None,
        "rollback_preimage_sha256":current.get("sha256") if current else None,
    }

def _append_process_output(session,text):
    combined=session.get("partial","")+str(text)
    parts=combined.split("\n")
    session["partial"]=parts.pop() if parts else ""
    session["lines"].extend(parts)
    if len(session["lines"])>MAX_PROCESS_LINES:
        drop=len(session["lines"])-MAX_PROCESS_LINES
        session["lines"]=session["lines"][drop:]
        session["base_line"]+=drop
        session["cursor"]=max(session["cursor"],session["base_line"])
        session["truncated"]=True

def _process_update_state(session):
    if session.get("exit_code") is not None: return
    try:
        pid,status=os.waitpid(int(session["pid"]),os.WNOHANG)
    except ChildProcessError:
        pid=int(session["pid"]); status=0
    if pid:
        session["exit_code"]=os.waitstatus_to_exitcode(status) if hasattr(os,"waitstatus_to_exitcode") else 0
        if session.get("partial"):
            session["lines"].append(session["partial"]); session["partial"]=""
        try: os.close(int(session["fd"]))
        except OSError: pass
        session["fd"]=-1

def _drain_process(session,wait_ms=0):
    fd=int(session.get("fd",-1))
    if fd<0:
        _process_update_state(session); return
    deadline=time.monotonic()+max(0,min(3000,int(wait_ms)))/1000.0
    first=True
    while True:
        timeout=max(0.0,deadline-time.monotonic()) if wait_ms else 0.0
        try: ready,_,_=select.select([fd],[],[],timeout if first else 0.0)
        except (OSError,ValueError): ready=[]
        first=False
        if not ready: break
        try: data=os.read(fd,65536)
        except BlockingIOError: break
        except OSError: data=b""
        if not data: break
        _append_process_output(session,data.decode("utf-8",errors="replace"))
        if time.monotonic()>=deadline: break
    _process_update_state(session)

def _process_get(session_id):
    sid=str(session_id or "")
    session=PROCESS_SESSIONS.get(sid)
    if not session: raise ValueError("PROCESS_SESSION_NOT_FOUND")
    return session

def _process_output_payload(session,offset=None,length=200,wait_ms=0):
    _drain_process(session,wait_ms)
    base=int(session.get("base_line",0)); lines=session.get("lines",[])
    start=int(session.get("cursor",base)) if offset is None else int(offset)
    truncated_before=start<base
    if start<base: start=base
    rel=max(0,start-base); selected=lines[rel:rel+max(1,min(500,int(length)))]
    next_offset=start+len(selected)
    if offset is None: session["cursor"]=next_offset
    state="EXITED" if session.get("exit_code") is not None else "RUNNING"
    return {"session_id":session["session_id"],"pid":session["pid"],"state":state,"exit_code":session.get("exit_code"),"offset":start,"next_offset":next_offset,"base_line":base,"total_lines":base+len(lines),"text":"\n".join(selected),"partial":session.get("partial","")[:1000],"truncated_before":truncated_before,"buffer_truncated":bool(session.get("truncated"))}

def process_start(command,cwd=None,timeout_ms=1000):
    command=str(command or "")
    if not command or len(command)>4096 or "\x00" in command: raise ValueError("PROCESS_COMMAND_INVALID")
    work=Path(cwd).expanduser().resolve(strict=True) if cwd else Path.home()
    if not work.is_dir(): raise ValueError("PROCESS_CWD_INVALID")
    pid,fd=pty.fork()
    if pid==0:
        try:
            os.chdir(work)
            os.execv("/bin/bash",["/bin/bash","-lc",command])
        except Exception:
            os._exit(127)
    os.set_blocking(fd,False)
    sid="HARA-PROC-"+uuid.uuid4().hex
    session={"session_id":sid,"pid":pid,"fd":fd,"started_at_utc":utcnow(),"command_sha256":hashlib.sha256(command.encode()).hexdigest(),"cwd":str(work),"lines":[],"partial":"","base_line":0,"cursor":0,"truncated":False,"exit_code":None}
    PROCESS_SESSIONS[sid]=session
    output=_process_output_payload(session,offset=None,length=200,wait_ms=timeout_ms)
    return {**output,"cwd":str(work),"command_sha256":session["command_sha256"],"command_preview":_redact_command_preview(command)}

def process_run(command,cwd=None,timeout_ms=3000,max_lines=200):
    timeout_ms=max(100,min(10000,int(timeout_ms)))
    max_lines=max(1,min(500,int(max_lines)))
    started=process_start(command,cwd,0)
    sid=started["session_id"]
    session=_process_get(sid)
    deadline=time.monotonic()+timeout_ms/1000.0
    while session.get("exit_code") is None and time.monotonic()<deadline:
        remaining=max(1,int((deadline-time.monotonic())*1000))
        _drain_process(session,min(100,remaining))
    timed_out=session.get("exit_code") is None
    if timed_out:
        process_kill(sid,True)
        settle=time.monotonic()+0.5
        while session.get("exit_code") is None and time.monotonic()<settle:
            _drain_process(session,50)
    base=int(session.get("base_line",0))
    output=_process_output_payload(session,offset=base,length=max_lines,wait_ms=0)
    total=int(output.get("total_lines") or 0)
    next_offset=int(output.get("next_offset") or base)
    result={
        "run_id":sid,
        "pid":session["pid"],
        "state":"TIMED_OUT" if timed_out else "EXITED",
        "exit_code":session.get("exit_code"),
        "timed_out":timed_out,
        "cwd":session["cwd"],
        "command_sha256":session["command_sha256"],
        "command_preview":_redact_command_preview(command),
        "text":output.get("text",""),
        "partial":output.get("partial",""),
        "total_lines":total,
        "output_truncated":bool(output.get("buffer_truncated")) or next_offset<total,
        "session_retained":False,
    }
    PROCESS_SESSIONS.pop(sid,None)
    return result

def process_sessions():
    items=[]
    for sid,session in list(PROCESS_SESSIONS.items()):
        _drain_process(session,0)
        items.append({"session_id":sid,"pid":session["pid"],"state":"EXITED" if session.get("exit_code") is not None else "RUNNING","exit_code":session.get("exit_code"),"started_at_utc":session["started_at_utc"],"cwd":session["cwd"],"command_sha256":session["command_sha256"]})
    return {"count":len(items),"sessions":items}

def process_interact(session_id,input_text,timeout_ms=1000):
    session=_process_get(session_id); _process_update_state(session)
    if session.get("exit_code") is not None or int(session.get("fd",-1))<0: raise ValueError("PROCESS_SESSION_EXITED")
    text=str(input_text or "")
    if len(text)>4096 or "\x00" in text: raise ValueError("PROCESS_INPUT_INVALID")
    data=(text+"\n").encode("utf-8")
    os.write(int(session["fd"]),data)
    return _process_output_payload(session,offset=None,length=200,wait_ms=timeout_ms)

def process_kill(session_id,force=False):
    session=_process_get(session_id); _process_update_state(session)
    if session.get("exit_code") is not None:
        return {"session_id":session_id,"pid":session["pid"],"state":"EXITED","exit_code":session.get("exit_code"),"existing":True}
    sig=signal.SIGKILL if force else signal.SIGTERM
    try:
        try: os.killpg(int(session["pid"]),sig)
        except ProcessLookupError: pass
        except OSError: os.kill(int(session["pid"]),sig)
    except ProcessLookupError: pass
    deadline=time.monotonic()+0.5
    while time.monotonic()<deadline and session.get("exit_code") is None:
        _drain_process(session,50)
    return {"session_id":session_id,"pid":session["pid"],"state":"EXITED" if session.get("exit_code") is not None else "TERMINATING","exit_code":session.get("exit_code"),"signal":"SIGKILL" if force else "SIGTERM"}

def cleanup_process_sessions():
    killed=0
    for sid,session in list(PROCESS_SESSIONS.items()):
        _process_update_state(session)
        if session.get("exit_code") is None:
            try:
                try: os.killpg(int(session["pid"]),signal.SIGKILL)
                except OSError: os.kill(int(session["pid"]),signal.SIGKILL)
                killed+=1
            except ProcessLookupError: pass
            _drain_process(session,50)
    return killed

def filesystem_create_directory(path_value,parents=True):
    path=Path(path_value).expanduser()
    existed=path.exists()
    if existed and not path.is_dir(): raise ValueError("PATH_EXISTS_NOT_DIRECTORY")
    path.mkdir(parents=bool(parents),exist_ok=True)
    return {"path":str(path.resolve()),"created":not existed,"parents":bool(parents)}

def filesystem_write(call,path_value,content,mode="rewrite"):
    path=Path(path_value).expanduser()
    if path.exists() and not path.is_file(): raise ValueError("PATH_NOT_FILE")
    data=str(content)
    if len(data.encode("utf-8"))>65536: raise ValueError("WRITE_TOO_LARGE")
    preimage=_store_preimage(path,call.get("call_id") or "write","hara.files.write") if path.exists() else None
    if not path.parent.exists() or not path.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    if mode=="append":
        with path.open("a",encoding="utf-8") as fh: fh.write(data)
    elif mode=="rewrite":
        tmp=path.with_name("."+path.name+".hara-tmp-"+str(os.getpid()))
        tmp.write_text(data,encoding="utf-8"); os.replace(tmp,path)
    else: raise ValueError("WRITE_MODE_INVALID")
    return {"path":str(path.resolve()),"mode":mode,"bytes_written":len(data.encode("utf-8")),"preimage_id":preimage.get("preimage_id") if preimage else None,"preimage_sha256":preimage.get("sha256") if preimage else None}

def filesystem_edit(call,path_value,old_text,new_text,replace_all=False):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    if path.stat().st_size>2*1024*1024: raise ValueError("FILE_TOO_LARGE")
    text=path.read_text(encoding="utf-8",errors="strict")
    count=text.count(old_text)
    if count==0: raise ValueError("EDIT_MATCH_NOT_FOUND")
    if not replace_all and count!=1: raise ValueError("EDIT_MATCH_AMBIGUOUS")
    preimage=_store_preimage(path,call.get("call_id") or "edit","hara.files.edit")
    updated=text.replace(old_text,new_text) if replace_all else text.replace(old_text,new_text,1)
    tmp=path.with_name("."+path.name+".hara-tmp-"+str(os.getpid())); tmp.write_text(updated,encoding="utf-8"); os.replace(tmp,path)
    return {"path":str(path),"replacements":count if replace_all else 1,"preimage_id":preimage.get("preimage_id"),"preimage_sha256":preimage.get("sha256")}

def filesystem_move(source_value,destination_value):
    src=Path(source_value).expanduser().resolve(strict=True)
    dst=Path(destination_value).expanduser()
    if dst.exists(): raise ValueError("DESTINATION_EXISTS")
    if not dst.parent.exists() or not dst.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    moved=shutil.move(str(src),str(dst))
    return {"source":str(src),"destination":str(Path(moved).resolve()),"overwrote":False}

def filesystem_copy(source_value,destination_value):
    src=Path(source_value).expanduser().resolve(strict=True)
    if not src.is_file(): raise ValueError("SOURCE_NOT_FILE")
    if src.stat().st_size>2*1024*1024: raise ValueError("COPY_FILE_TOO_LARGE")
    dst=Path(destination_value).expanduser()
    if dst.exists(): raise ValueError("DESTINATION_EXISTS")
    if not dst.parent.exists() or not dst.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    shutil.copy2(str(src),str(dst))
    return {"source":str(src),"destination":str(dst.resolve(strict=True)),"bytes":int(dst.stat().st_size),"sha256":hashlib.sha256(dst.read_bytes()).hexdigest(),"overwrote":False}

def filesystem_delete(call,path_value):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("DELETE_TARGET_NOT_FILE")
    if path.stat().st_size>2*1024*1024: raise ValueError("DELETE_FILE_TOO_LARGE")
    preimage=_store_preimage(path,call.get("call_id") or "delete","hara.files.delete")
    if not preimage: raise ValueError("PREIMAGE_REQUIRED")
    expected=preimage.get("sha256")
    if hashlib.sha256(path.read_bytes()).hexdigest()!=expected: raise ValueError("PREIMAGE_SOURCE_MISMATCH")
    path.unlink()
    if path.exists(): raise ValueError("DELETE_VERIFY_FAILED")
    return {"path":str(path),"deleted":True,"preimage_id":preimage.get("preimage_id"),"preimage_sha256":expected}

def mark_device_offline(config):
    try:
        try: config=load_config()
        except Exception: pass
        result = post_json(
            config["HARA_COMMANDER_URL"] + "/api/device/offline",
            config["HARA_DEVICE_TOKEN"],
            {"device_id":config["HARA_DEVICE_ID"],"agent_version":AGENT_VERSION,"architecture":config["HARA_DEVICE_ARCH"],"approval_mode":effective_approval_mode(config)},
            timeout=5,
        )
        ok = isinstance(result, dict) and result.get("ok") is True and result.get("state") == "OFFLINE"
        append_console_event("AGENT_OFFLINE", state="OFFLINE" if ok else "FAILED")
        return ok
    except Exception as exc:
        append_console_event("OFFLINE_SYNC_ERROR", state="FAILED", error_code=safe_error_code(exc))
        return False

def start_operator_console():
    config = load_config()
    approval_mode=str(config.get("HARA_COMMANDER_APPROVAL_MODE") or "ASK_EVERY_ACTION").upper()
    if approval_mode not in APPROVAL_MODES: raise RuntimeError("DEVICE_APPROVAL_MODE_INVALID")
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    existing = read_operator_session()
    if existing and int(existing.get("owner_pid") or 0) != os.getpid():
        raise RuntimeError("OPERATOR_SESSION_ALREADY_ACTIVE")
    session = {
        "schema":"hara.commander-operator-session.v1",
        "owner_pid":os.getpid(),
        "owner_start_marker":_pid_start_marker(os.getpid()),
        "started_at_epoch":int(time.time()),
        "started_at_utc":utcnow(),
        "device_id":config["HARA_DEVICE_ID"],
        "authorization":"LOCAL_OPERATOR_TERMINAL",
        "approval_mode":approval_mode,
        "agent_version":AGENT_VERSION,
    }
    tmp = SESSION_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(SESSION_FILE)
    os.chmod(SESSION_FILE, 0o600)
    append_console_event("SESSION_OPEN", state="AUTHORIZED")
    print("")
    print("H.A.R.A. Labs — Commander")
    print("=" * 58)
    print("Sessão local autorizada para clientes de IA")
    print("Computador:", platform.node())
    print("Device ID :", config["HARA_DEVICE_ID"])
    print("Agent     :", AGENT_VERSION)
    print("Aprovação :", "automática nesta sessão" if approval_mode=="SESSION_TRUSTED" else "confirmar cada ação")
    print("")
    print("Comandos permitidos nesta sessão:")
    print("  hara.health / hara.ping / hara.device.info")
    print("  hara.system.uptime / hara.system.resources / hara.workspace.inspect")
    print("  hara.processes.list")
    print("  hara.files.info / hash / diff / search / list")
    print("  hara.files.read / hara.files.read_many")
    approval_label="sessão autorizada" if approval_mode=="SESSION_TRUSTED" else "aprovação por ação"
    print(f"  hara.files.create_directory / write / edit / move / copy  [{approval_label}]")
    print(f"  hara.files.delete  [preimage + {approval_label}]")
    print(f"  hara.files.preimages.list / rollback  [rollback: {approval_label}]")
    print("  hara.process.sessions / output")
    print(f"  hara.process.run / start / interact / kill  [{approval_label}]")
    print("  hara.functions.list / hara.functions.describe")
    print("  hara.functions.invoke (compatibilidade; somente funções governadas)")
    print("  hara.receipts.get")
    print("")
    print("Origem     : OpenAI / cliente MCP autorizado")
    print("Acesso     : ativo somente enquanto este terminal permanecer aberto")
    print("Argumentos sensíveis, tokens e segredos nunca são exibidos.")
    print("Cada ação será mostrada abaixo com tool, função, estado e receipt.")
    print("Pressione Ctrl+C para revogar o acesso imediatamente.")
    print("-" * 58)
    position = CONSOLE_EVENTS_FILE.stat().st_size if CONSOLE_EVENTS_FILE.exists() else 0
    try:
        while True:
            current = read_operator_session()
            if not current or int(current.get("owner_pid") or 0) != os.getpid():
                print("\nSessão encerrada externamente.")
                break
            if CONSOLE_EVENTS_FILE.is_file():
                with CONSOLE_EVENTS_FILE.open("r", encoding="utf-8") as handle:
                    handle.seek(position)
                    while True:
                        raw = handle.readline()
                        if not raw:
                            break
                        position = handle.tell()
                        try:
                            payload = json.loads(raw)
                        except Exception:
                            continue
                        print(_format_console_event(payload), flush=True)
                        if payload.get("event") == "APPROVAL_REQUIRED" and payload.get("approval_id"):
                            approval_id=str(payload.get("approval_id"))
                            summary=str(payload.get("action_summary") or payload.get("tool_id") or "mutação")
                            try:
                                answer=input(f"\nAutorizar {summary}? [y/N]: ").strip().lower()
                            except EOFError:
                                answer=""
                            decision="APPROVED" if answer in ("y","yes","s","sim") else "DENIED"
                            _,res_path=_approval_paths(approval_id)
                            response={"schema":"hara.commander-local-approval-response.v1","approval_id":approval_id,"decision":decision,"decided_at_utc":utcnow()}
                            tmp=res_path.with_suffix(".tmp"); tmp.write_text(json.dumps(response,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(tmp,0o600); tmp.replace(res_path); os.chmod(res_path,0o600)
                            print(f"LOCAL_APPROVAL={decision}",flush=True)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nEncerrando acesso do H.A.R.A. Commander...")
    finally:
        try:
            current = json.loads(SESSION_FILE.read_text(encoding="utf-8")) if SESSION_FILE.is_file() else {}
            if not current or int(current.get("owner_pid") or 0) == os.getpid():
                SESSION_FILE.unlink(missing_ok=True)
        except Exception as exc:
            SESSION_FILE.unlink(missing_ok=True)
            append_console_event("SESSION_CLEANUP_ERROR", state="FAILED", error_code=safe_error_code(exc))
        if effective_approval_mode(config)!="PERSISTENT_TRUSTED":
            killed=cleanup_process_sessions()
            if killed: append_console_event("PROCESS_REVOKE",state="KILLED",action_summary=f"managed_processes={killed}")
            if transport_mode(config)!="LOCAL_TUNNEL":
                mark_device_offline(config)
        append_console_event("SESSION_CLOSE", state="REVOKED")
        print("HARA_COMMANDER_SESSION=INACTIVE")

def session_status():
    session = read_operator_session()
    print("HARA_COMMANDER_SESSION=" + ("ACTIVE" if session else "INACTIVE"))
    if session:
        print("SESSION_STARTED_AT_UTC=" + str(session.get("started_at_utc") or ""))
        print("HARA_COMMANDER_APPROVAL_MODE=" + str(session.get("approval_mode") or "ASK_EVERY_ACTION"))
    print("SECRET_MATERIAL_EXPOSED=FALSE")

def stop_operator_session():
    existed = SESSION_FILE.is_file()
    SESSION_FILE.unlink(missing_ok=True)
    try:
        config = load_config()
        if effective_approval_mode(config)!="PERSISTENT_TRUSTED" and transport_mode(config)!="LOCAL_TUNNEL":
            mark_device_offline(config)
    except Exception as exc:
        append_console_event("OFFLINE_SYNC_ERROR", state="FAILED", error_code=safe_error_code(exc))
    append_console_event("SESSION_CLOSE", state="REVOKED")
    print("HARA_COMMANDER_SESSION=INACTIVE")
    print("SESSION_WAS_ACTIVE=" + ("TRUE" if existed else "FALSE"))
    print("SECRET_MATERIAL_EXPOSED=FALSE")

def load_config():
    data = {}
    for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            data[key] = value
    required = ("HARA_COMMANDER_URL","HARA_DEVICE_ID","HARA_DEVICE_TOKEN","HARA_DEVICE_ARCH")
    if not all(data.get(k) for k in required):
        raise RuntimeError("DEVICE_CONFIG_INVALID")
    mode=str(data.get("HARA_COMMANDER_APPROVAL_MODE") or "ASK_EVERY_ACTION").upper()
    if mode not in APPROVAL_MODES: raise RuntimeError("DEVICE_APPROVAL_MODE_INVALID")
    data["HARA_COMMANDER_APPROVAL_MODE"]=mode
    transport=str(data.get("HARA_COMMANDER_TRANSPORT_MODE") or "OUTBOUND_RELAY").upper()
    if transport not in TRANSPORT_MODES: raise RuntimeError("DEVICE_TRANSPORT_MODE_INVALID")
    data["HARA_COMMANDER_TRANSPORT_MODE"]=transport
    return data
def set_approval_mode(value):
    raw=str(value or "").strip().lower()
    aliases={"ask":"ASK_EVERY_ACTION","per-action":"ASK_EVERY_ACTION","session":"SESSION_TRUSTED","trusted":"SESSION_TRUSTED","auto":"PERSISTENT_TRUSTED","always":"PERSISTENT_TRUSTED","persistent":"PERSISTENT_TRUSTED"}
    mode=aliases.get(raw,str(value or "").strip().upper())
    if mode not in APPROVAL_MODES: raise RuntimeError("DEVICE_APPROVAL_MODE_INVALID")
    lines=CONFIG_FILE.read_text(encoding="utf-8").splitlines()
    lines=[line for line in lines if not line.startswith("HARA_COMMANDER_APPROVAL_MODE=")]
    lines.append("HARA_COMMANDER_APPROVAL_MODE="+mode)
    tmp=CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(CONFIG_FILE); os.chmod(CONFIG_FILE,0o600)
    print("HARA_COMMANDER_APPROVAL_MODE="+mode)
    if operator_session_active(): print("SESSION_RESTART_REQUIRED=TRUE")

def _set_config_value(key,value):
    lines=CONFIG_FILE.read_text(encoding="utf-8").splitlines()
    lines=[line for line in lines if not line.startswith(str(key)+"=")]
    lines.append(str(key)+"="+str(value))
    tmp=CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(CONFIG_FILE); os.chmod(CONFIG_FILE,0o600)

def set_transport_mode(value):
    aliases={"local":"LOCAL_TUNNEL","tunnel":"LOCAL_TUNNEL","local-tunnel":"LOCAL_TUNNEL","relay":"OUTBOUND_RELAY","legacy":"OUTBOUND_RELAY"}
    mode=aliases.get(str(value or "").strip().lower(),str(value or "").strip().upper())
    if mode not in TRANSPORT_MODES: raise RuntimeError("DEVICE_TRANSPORT_MODE_INVALID")
    _set_config_value("HARA_COMMANDER_TRANSPORT_MODE",mode)
    print("HARA_COMMANDER_TRANSPORT_MODE="+mode)
    subprocess.run(["systemctl","--user","restart","hara-commander-agent.service"],check=False)
    print("AGENT_RESTART_REQUESTED=TRUE")

def transport_mode(config=None):
    if config is None: config=load_config()
    return str(config.get("HARA_COMMANDER_TRANSPORT_MODE") or "OUTBOUND_RELAY").upper()

def effective_approval_mode(config=None):
    if config is None:
        try: config=load_config()
        except Exception: config={}
    configured=str((config or {}).get("HARA_COMMANDER_APPROVAL_MODE") or "ASK_EVERY_ACTION").upper()
    if configured=="PERSISTENT_TRUSTED":
        return configured
    session=read_operator_session()
    if session:
        mode=str(session.get("approval_mode") or "").upper()
        if mode in APPROVAL_MODES:
            return mode
    return configured if configured in APPROVAL_MODES else "ASK_EVERY_ACTION"

def post_json(url, token, payload, timeout=25):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload,separators=(",",":")).encode(),
        method="POST",
        headers={
            "content-type":"application/json",
            "accept":"application/json",
            "authorization":"Bearer "+token,
            "user-agent":"HARA-Commander-Agent/"+AGENT_VERSION,
        },
    )
    try:
        with NO_REDIRECT_OPENER.open(req, timeout=timeout) as response:
            if response.status == 204:
                return None
            return json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code == 204:
            return None
        raise

def _function_spec(function_id):
    specs={
        "device.info":("DEVICE","Consulta informações básicas e não sensíveis deste computador."),
        "device.ping":("DEVICE","Valida conectividade ponta a ponta com este Agent."),
        "system.uptime":("SYSTEM","Consulta uptime e load average do sistema."),
        "system.resources":("SYSTEM","Consulta CPU, memória, swap, load average e capacidade do disco raiz sem shell."),
        "workspace.inspect":("WORKSPACE","Inspeciona metadados limitados de projeto e Git HEAD sem executar comandos externos."),
        "process.list":("PROCESS","Lista processos com metadados sanitizados, sem linha de comando ou ambiente."),
        "filesystem.info":("FILESYSTEM","Consulta metadados de um caminho sem ler conteúdo."),
        "filesystem.hash":("FILESYSTEM","Calcula SHA-256 e tamanho de um arquivo regular."),
        "filesystem.diff":("FILESYSTEM","Compara dois arquivos texto com diff unificado limitado."),
        "filesystem.search":("FILESYSTEM","Busca nomes de arquivos ou texto com limites de tempo, tamanho e quantidade."),
        "filesystem.list":("FILESYSTEM","Lista entradas e metadados de um diretório sem ler conteúdo de arquivos."),
        "filesystem.read":("FILESYSTEM","Lê um intervalo limitado de um arquivo texto acessível ao usuário local."),
        "filesystem.read_many":("FILESYSTEM","Lê intervalos limitados de até dez arquivos texto sem abortar o lote por falha individual."),
    }
    if function_id not in specs: raise ValueError("UNKNOWN_FUNCTION_ID")
    domain,description=specs[function_id]
    return {
        "function_id":function_id,"state":"ACTIVE","IDENTITY":{"domain":domain},
        "PURPOSE":{"description_pt_br":description},
        "EXECUTION_SEMANTICS":{"risk_class":"READ_ONLY","change_intent_required":False},
        "AUTHORITY":{"risk_class":"READ_ONLY","change_intent_required":False,"fail_closed":True},
        "FAILURE_ROLLBACK":{"fail_closed":True},
    }

def catalog():
    return {
        "registered_function_count":len(FUNCTION_IDS),
        "executable_function_count":len(FUNCTION_IDS),
        "active_function_count":len(FUNCTION_IDS),
        "domains":["DEVICE","SYSTEM","WORKSPACE","PROCESS","FILESYSTEM"],
        "functions":[{"function_id":fid,"state":"ACTIVE"} for fid in FUNCTION_IDS],
    }

def describe(function_id):
    return _function_spec(function_id)

def device_info(config):
    return {
        "device_id":config["HARA_DEVICE_ID"],"hostname":platform.node(),
        "platform":platform.system().upper(),"platform_release":platform.release(),
        "architecture":config["HARA_DEVICE_ARCH"],"python_version":platform.python_version(),
        "agent_version":AGENT_VERSION,"approval_mode":effective_approval_mode(config),"tunnel_mode":"OUTBOUND_RELAY",
    }

def device_ping(config):
    return {"pong":True,"hostname":platform.node(),"device_id":config["HARA_DEVICE_ID"],"agent_version":AGENT_VERSION,"at_utc":utcnow()}

def system_uptime():
    uptime=float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    load=os.getloadavg()
    return {"uptime_seconds":round(uptime,2),"load_average_1m":load[0],"load_average_5m":load[1],"load_average_15m":load[2]}

def system_resources():
    mem={}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8",errors="replace").splitlines():
            if ":" not in line: continue
            key,raw=line.split(":",1)
            m=re.search(r"([0-9]+)",raw)
            if m: mem[key]=int(m.group(1))*1024
    except (FileNotFoundError,PermissionError,OSError):
        mem={}
    disk=shutil.disk_usage("/")
    load=os.getloadavg()
    return {
        "cpu_logical":int(os.cpu_count() or 0),
        "load_average_1m":load[0],"load_average_5m":load[1],"load_average_15m":load[2],
        "memory_total_bytes":mem.get("MemTotal"),"memory_available_bytes":mem.get("MemAvailable"),
        "swap_total_bytes":mem.get("SwapTotal"),"swap_free_bytes":mem.get("SwapFree"),
        "root_disk_total_bytes":int(disk.total),"root_disk_used_bytes":int(disk.used),"root_disk_free_bytes":int(disk.free),
    }

def _workspace_git_metadata(root):
    marker=root/".git"
    if not marker.exists(): return {"present":False}
    try:
        gitdir=marker
        if marker.is_file():
            raw=marker.read_text(encoding="utf-8",errors="replace")[:4096].strip()
            if not raw.lower().startswith("gitdir:"): return {"present":True,"branch":None,"head_oid":None,"head_state":"UNRESOLVED"}
            value=raw.split(":",1)[1].strip()
            gitdir=(root/value).resolve(strict=True) if not Path(value).is_absolute() else Path(value).resolve(strict=True)
        common=gitdir
        common_file=gitdir/"commondir"
        if common_file.is_file():
            common_raw=common_file.read_text(encoding="utf-8",errors="replace")[:4096].strip()
            if common_raw:
                common=(gitdir/common_raw).resolve(strict=True) if not Path(common_raw).is_absolute() else Path(common_raw).resolve(strict=True)
        head=(gitdir/"HEAD").read_text(encoding="utf-8",errors="replace")[:4096].strip()
        branch=None; oid=None; state="DETACHED"
        if head.startswith("ref: "):
            ref=head[5:].strip()
            branch=ref[len("refs/heads/"):] if ref.startswith("refs/heads/") else ref
            state="BRANCH"
            for base in (gitdir,common):
                refpath=base/ref
                if refpath.is_file():
                    candidate=refpath.read_text(encoding="utf-8",errors="replace")[:128].strip()
                    if re.fullmatch(r"[0-9a-fA-F]{40,64}",candidate):
                        oid=candidate.lower(); break
            packed=common/"packed-refs"
            if oid is None and packed.is_file() and packed.stat().st_size <= 4*1024*1024:
                for line in packed.read_text(encoding="utf-8",errors="replace").splitlines():
                    if line.startswith("#") or line.startswith("^") or " " not in line: continue
                    candidate,name=line.split(" ",1)
                    if name.strip()==ref and re.fullmatch(r"[0-9a-fA-F]{40,64}",candidate):
                        oid=candidate.lower(); break
        elif re.fullmatch(r"[0-9a-fA-F]{40,64}",head):
            oid=head.lower()
        return {"present":True,"branch":branch,"head_oid":oid,"head_state":state,"dirty_state":"UNKNOWN_NOT_EVALUATED"}
    except (FileNotFoundError,PermissionError,OSError,ValueError):
        return {"present":True,"branch":None,"head_oid":None,"head_state":"UNRESOLVED","dirty_state":"UNKNOWN_NOT_EVALUATED"}

def workspace_inspect(path_value,max_entries=80):
    target=Path(path_value).expanduser().resolve(strict=True)
    start=target if target.is_dir() else target.parent
    markers=(".git","pyproject.toml","package.json","Cargo.toml","go.mod","pom.xml","build.gradle","build.gradle.kts","requirements.txt","CMakeLists.txt","Makefile")
    root=start; root_marker=None
    current=start
    for _ in range(13):
        found=next((name for name in markers if (current/name).exists()),None)
        if found:
            root=current; root_marker=found; break
        if current.parent==current: break
        current=current.parent
    max_entries=max(1,min(200,int(max_entries)))
    children=[]; discovered=[]; scan_truncated=False
    try:
        with os.scandir(root) as it:
            for item in it:
                if len(discovered)>=2000:
                    scan_truncated=True; break
                try:
                    kind="symlink" if item.is_symlink() else "directory" if item.is_dir(follow_symlinks=False) else "file" if item.is_file(follow_symlinks=False) else "other"
                    discovered.append({"name":item.name,"type":kind})
                except (FileNotFoundError,PermissionError,OSError):
                    continue
        discovered.sort(key=lambda item:item["name"].lower())
        children=discovered[:max_entries]
    except PermissionError:
        children=[]; discovered=[]
    manifests=[name for name in markers if name!=".git" and (root/name).is_file()]
    return {
        "requested_path":str(target),"root":str(root),"root_marker":root_marker,
        "manifests":manifests,"entries":children,"entry_count":len(children),
        "entries_truncated":scan_truncated or len(discovered)>max_entries,
        "git":_workspace_git_metadata(root),
        "shell_invoked":False,"external_command_invoked":False,
    }

def process_list(limit=50):
    out=[]
    for name in os.listdir("/proc"):
        if not name.isdigit(): continue
        pid=int(name); base=Path("/proc")/name
        try:
            comm=(base/"comm").read_text(encoding="utf-8",errors="replace").strip()[:160]
            state=None; rss_kb=0
            for line in (base/"status").read_text(encoding="utf-8",errors="replace").splitlines():
                if line.startswith("State:"): state=line.split(":",1)[1].strip()[:80]
                elif line.startswith("VmRSS:"):
                    m=re.search(r"([0-9]+)",line); rss_kb=int(m.group(1)) if m else 0
            out.append({"pid":pid,"name":comm,"state":state,"rss_kb":rss_kb})
        except (FileNotFoundError,PermissionError,ProcessLookupError):
            continue
    out.sort(key=lambda item:(-int(item.get("rss_kb") or 0), int(item["pid"])))
    return {"count":min(len(out),limit),"processes":out[:limit],"command_lines_exposed":False,"environment_exposed":False}

def filesystem_info(path_value):
    path=Path(path_value).expanduser().resolve(strict=True)
    st=path.lstat()
    kind="symlink" if path.is_symlink() else "directory" if path.is_dir() else "file" if path.is_file() else "other"
    return {
        "path":str(path),"name":path.name,"type":kind,
        "size_bytes":int(st.st_size) if kind=="file" else None,
        "mode_octal":oct(st.st_mode & 0o777),
        "modified_at_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),
    }

def filesystem_hash(path_value):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    h=hashlib.sha256(); total=0
    with path.open("rb") as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b""):
            total+=len(chunk)
            if total>128*1024*1024: raise ValueError("HASH_FILE_TOO_LARGE")
            h.update(chunk)
    return {"path":str(path),"bytes":total,"sha256":h.hexdigest()}

def filesystem_diff(left_value,right_value,max_lines=200):
    left=Path(left_value).expanduser().resolve(strict=True); right=Path(right_value).expanduser().resolve(strict=True)
    for path in (left,right):
        if not path.is_file(): raise ValueError("PATH_NOT_FILE")
        if path.stat().st_size>2*1024*1024: raise ValueError("FILE_TOO_LARGE")
        with path.open("rb") as fh:
            if b"\x00" in fh.read(4096): raise ValueError("BINARY_FILE_DENIED")
    a=left.read_text(encoding="utf-8",errors="replace").splitlines()
    b=right.read_text(encoding="utf-8",errors="replace").splitlines()
    lines=list(difflib.unified_diff(a,b,fromfile=str(left),tofile=str(right),lineterm=""))
    cap=max(1,min(400,int(max_lines))); chosen=lines[:cap]
    return {"left":str(left),"right":str(right),"different":bool(lines),"line_count":len(chosen),"diff":"\n".join(chosen),"truncated":len(lines)>cap}

def filesystem_search(path_value,search_type,pattern,max_results=50,include_hidden=False,ignore_case=True,file_glob=""):
    root=Path(path_value).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError("PATH_NOT_DIRECTORY")
    if search_type not in ("files","content"): raise ValueError("SEARCH_TYPE_INVALID")
    if not pattern or len(pattern)>256: raise ValueError("SEARCH_PATTERN_INVALID")
    max_results=max(1,min(100,int(max_results)))
    deadline=time.monotonic()+3.0
    scan_cap=5000
    scanned=0; matches=[]; truncated=False
    needle=pattern.lower() if ignore_case else pattern
    for current,dirs,files in os.walk(root):
        if time.monotonic()>deadline or scanned>=scan_cap:
            truncated=True; break
        if not include_hidden:
            dirs[:]=[d for d in dirs if not d.startswith(".")]
            files=[f for f in files if not f.startswith(".")]
        for name in files:
            if time.monotonic()>deadline or scanned>=scan_cap:
                truncated=True; break
            scanned+=1
            if file_glob and not fnmatch.fnmatch(name,file_glob): continue
            path=Path(current)/name
            rel=str(path.relative_to(root))
            if search_type=="files":
                hay=name.lower() if ignore_case else name
                if needle in hay:
                    matches.append({"path":rel,"type":"file"})
            else:
                try:
                    st=path.stat()
                    if st.st_size>2*1024*1024: continue
                    with path.open("rb") as fh:
                        if b"\x00" in fh.read(4096): continue
                    with path.open("r",encoding="utf-8",errors="replace") as fh:
                        for line_no,line in enumerate(fh,1):
                            hay=line.lower() if ignore_case else line
                            if needle in hay:
                                snippet=line.rstrip("\n")[:300]
                                matches.append({"path":rel,"line":line_no,"text":snippet})
                                if len(matches)>=max_results: break
                except (FileNotFoundError,PermissionError,OSError):
                    continue
            if len(matches)>=max_results:
                truncated=True; break
        if truncated and len(matches)>=max_results: break
    return {"path":str(root),"search_type":search_type,"pattern":pattern,"count":len(matches),"matches":matches[:max_results],"scanned_files":scanned,"truncated":truncated}

def filesystem_list(path_value,limit=100,depth=1):
    root=Path(path_value).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError("PATH_NOT_DIRECTORY")
    limit=max(1,min(200,int(limit))); depth=max(1,min(5,int(depth)))
    entries=[]; truncated=False
    def walk(current,level):
        nonlocal truncated
        if truncated or level>depth: return
        try: children=sorted(current.iterdir(),key=lambda e:e.name.lower())
        except PermissionError: return
        for entry in children:
            if len(entries)>=limit: truncated=True; return
            try:
                st=entry.lstat(); kind="symlink" if entry.is_symlink() else "directory" if entry.is_dir() else "file" if entry.is_file() else "other"
                entries.append({"path":str(entry.relative_to(root)),"name":entry.name,"type":kind,"size_bytes":int(st.st_size) if kind=="file" else None,"depth":level})
                if kind=="directory" and level<depth: walk(entry,level+1)
            except (FileNotFoundError,PermissionError,OSError):
                continue
    walk(root,1)
    return {"path":str(root),"count":len(entries),"entries":entries,"depth":depth,"truncated":truncated}

def filesystem_read(path_value,offset=0,length=200):
    path=Path(path_value).expanduser().resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    if path.stat().st_size > 2*1024*1024: raise ValueError("FILE_TOO_LARGE")
    lines=[]; binary=False
    with path.open("rb") as fh:
        head=fh.read(4096)
        binary=b"\x00" in head
    if binary: raise ValueError("BINARY_FILE_DENIED")
    with path.open("r",encoding="utf-8",errors="replace") as fh:
        for idx,line in enumerate(fh):
            if idx < offset: continue
            if len(lines)>=length: break
            lines.append(line.rstrip("\n"))
    text="\n".join(lines)
    if len(text)>65536: text=text[:65536]+"\n[HARA_COMMANDER_OUTPUT_TRUNCATED]"
    return {"path":str(path),"offset":offset,"line_count":len(lines),"text":text}

def filesystem_read_many(paths,offset=0,length=100):
    out=[]
    for raw in paths[:10]:
        try:
            item=filesystem_read(str(raw),offset,length)
            out.append({"path":item["path"],"state":"PASS","offset":item["offset"],"line_count":item["line_count"],"text":item["text"]})
        except Exception as exc:
            out.append({"path":str(raw),"state":"FAILED","error_code":safe_error_code(exc)})
    return {"count":len(out),"files":out,"offset":offset,"length":length}

def invoke(config, function_id, arguments):
    if function_id not in FUNCTION_IDS: raise ValueError("UNKNOWN_FUNCTION_ID")
    argv=arguments.get("argv") if isinstance(arguments,dict) else None
    if not isinstance(argv,list): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
    if function_id=="device.info":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=device_info(config)
    elif function_id=="device.ping":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=device_ping(config)
    elif function_id=="system.uptime":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=system_uptime()
    elif function_id=="system.resources":
        if argv!=[]: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=system_resources()
    elif function_id=="workspace.inspect":
        if len(argv)<1 or len(argv)>2: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        max_entries=int(argv[1]) if len(argv)>=2 else 80
        if not 1<=max_entries<=200: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=workspace_inspect(str(argv[0]),max_entries)
    elif function_id=="process.list":
        if len(argv)>1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        limit=int(argv[0]) if argv else 50
        if not 1<=limit<=200: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=process_list(limit)
    elif function_id=="filesystem.hash":
        if len(argv)!=1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_hash(str(argv[0]))
    elif function_id=="filesystem.diff":
        if len(argv)<2 or len(argv)>3: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_diff(str(argv[0]),str(argv[1]),int(argv[2]) if len(argv)>=3 else 200)
    elif function_id=="filesystem.search":
        if len(argv)<3 or len(argv)>7: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_search(str(argv[0]),str(argv[1]),str(argv[2]),int(argv[3]) if len(argv)>=4 else 50,argv[4]=="1" if len(argv)>=5 else False,argv[5]!="0" if len(argv)>=6 else True,str(argv[6]) if len(argv)>=7 else "")
    elif function_id=="filesystem.info":
        if len(argv)!=1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_info(str(argv[0]))
    elif function_id=="filesystem.list":
        if len(argv)<1 or len(argv)>3: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        limit=int(argv[1]) if len(argv)>=2 else 100; depth=int(argv[2]) if len(argv)>=3 else 1
        if not 1<=limit<=200 or not 1<=depth<=5: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_list(str(argv[0]),limit,depth)
    elif function_id=="filesystem.read_many":
        if len(argv)<3 or len(argv)>12: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        offset=int(argv[0]); length=int(argv[1]); paths=argv[2:]
        if offset<0 or not 1<=length<=100 or not 1<=len(paths)<=10: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_read_many(paths,offset,length)
    elif function_id=="filesystem.read":
        if len(argv)<1 or len(argv)>3: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        offset=int(argv[1]) if len(argv)>=2 else 0; length=int(argv[2]) if len(argv)>=3 else 200
        if offset<0 or not 1<=length<=400: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_read(str(argv[0]),offset,length)
    return {"function_id":function_id,"risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(result,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}

def write_receipt(config, call, state, result=None):
    RECEIPT_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    tool_id = str(call.get("tool_id") or "")
    result_binding = "NONE"
    result_stdout_sha256 = None
    if tool_id == "hara.functions.invoke" or tool_id in DIRECT_TOOL_FUNCTIONS or _is_mutation_tool(tool_id) or _is_process_tool(tool_id):
        stdout = str((result or {}).get("stdout") or "")
        result_binding = "STDOUT_SHA256_V1"
        result_stdout_sha256 = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    approval=call.get("_local_approval") or {}
    mutation=_is_mutation_tool(tool_id)
    approval_mode=str(approval.get("mode") or "ASK_EVERY_ACTION") if mutation else None
    preimage=(result or {}).get("preimage_sha256") if isinstance(result,dict) else None
    preimage_id=(result or {}).get("preimage_id") if isinstance(result,dict) else None
    rollback_preimage_id=(result or {}).get("rollback_preimage_id") if isinstance(result,dict) else None
    receipt = {
        "schema":"hara.commander-device-receipt.v1",
        "request_id":str(call.get("request_id") or ""),
        "device_id":config["HARA_DEVICE_ID"],
        "tool_id":tool_id,
        "function_id_if_any":(call.get("payload") or {}).get("function_id") or DIRECT_TOOL_FUNCTIONS.get(tool_id) or ((result or {}).get("function_id") if isinstance(result,dict) else None),
        "transport_mode":"OUTBOUND_RELAY",
        "operational_authority":"HARA_SERVICES",
        "execution_authority":"HARA_COMMANDER_AGENT",
        "mutation_class":_mutation_class(tool_id),
        "human_approval_required":bool(mutation and approval_mode=="ASK_EVERY_ACTION"),
        "human_approval_state":approval.get("state") if mutation else None,
        "local_authorization_mode":approval_mode,
        "authorization_source":approval.get("source") if mutation else None,
        "preimage_sha256":preimage,
        "preimage_id":preimage_id,
        "rollback_preimage_id":rollback_preimage_id,
        "state":state,
        "payload_values_persisted":False,
        "result_binding":result_binding,
        "result_stdout_sha256":result_stdout_sha256,
        "completed_at_utc":utcnow(),
    }
    raw=json.dumps(receipt,sort_keys=True,separators=(",",":")).encode()
    sha=hashlib.sha256(raw).hexdigest()
    path=RECEIPT_DIR/(sha+".json")
    path.write_bytes(raw)
    os.chmod(path,0o600)
    return sha

def read_receipt(identifier):
    value=str(identifier or "").lower()
    if len(value)!=64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("RECEIPT_IDENTIFIER_INVALID")
    path=RECEIPT_DIR/(value+".json")
    if not path.is_file():
        raise ValueError("RECEIPT_NOT_FOUND")
    return json.loads(path.read_text(encoding="utf-8"))
def execute_tool(config, call):
    tool=str(call.get("tool_id") or "")
    payload=call.get("payload") or {}
    if tool=="hara.health":
        result={
            "services_bridge_state":"PASS",
            "hara_services_state":"PASS",
            "registered_function_count":len(FUNCTION_IDS),
            "executable_function_count":len(FUNCTION_IDS),
            "authority":"HARA_SERVICES",
            "device":device_info(config),
        }
    elif tool=="hara.functions.list":
        if payload: raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
        result=catalog()
    elif tool=="hara.functions.describe":
        result=describe(str(payload.get("function_id") or ""))
    elif tool=="hara.functions.invoke":
        result=invoke(config,str(payload.get("function_id") or ""),payload.get("arguments") or {})
    elif tool in DIRECT_TOOL_FUNCTIONS:
        fid=DIRECT_TOOL_FUNCTIONS[tool]
        if tool in ("hara.device.info","hara.ping","hara.system.uptime","hara.system.resources"):
            if payload: raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
            argv=[]
        elif tool=="hara.workspace.inspect":
            if "path" not in payload or any(k not in ("path","max_entries") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
            if "max_entries" in payload: argv.append(str(payload["max_entries"]))
        elif tool=="hara.processes.list":
            if any(k not in ("limit",) for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[] if "limit" not in payload else [str(payload["limit"])]
        elif tool=="hara.files.hash":
            if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
        elif tool=="hara.files.diff":
            if not {"left","right"}.issubset(payload) or any(k not in ("left","right","max_lines") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["left"]),str(payload["right"]),str(payload.get("max_lines",200))]
        elif tool=="hara.files.search":
            required={"path","search_type","pattern"}
            allowed=required|{"max_results","include_hidden","ignore_case","file_glob"}
            if not required.issubset(payload) or any(k not in allowed for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"]),str(payload["search_type"]),str(payload["pattern"]),str(payload.get("max_results",50)),"1" if payload.get("include_hidden") else "0","0" if payload.get("ignore_case") is False else "1",str(payload.get("file_glob", ""))]
        elif tool=="hara.files.info":
            if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
        elif tool=="hara.files.list":
            if "path" not in payload or any(k not in ("path","limit","depth") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
            if "limit" in payload or "depth" in payload: argv.append(str(payload.get("limit",100)))
            if "depth" in payload: argv.append(str(payload["depth"]))
        elif tool=="hara.files.read_many":
            required={"paths"}; allowed=required|{"offset","length"}
            if not required.issubset(payload) or any(k not in allowed for k in payload) or not isinstance(payload.get("paths"),list): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            paths=payload["paths"]
            if not 1<=len(paths)<=10: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload.get("offset",0)),str(payload.get("length",100))]+[str(x) for x in paths]
        elif tool=="hara.files.read":
            if "path" not in payload or any(k not in ("path","offset","length") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
            if "offset" in payload or "length" in payload: argv.append(str(payload.get("offset",0)))
            if "length" in payload: argv.append(str(payload["length"]))
        result=invoke(config,fid,{"argv":argv})
    elif tool=="hara.files.preimages.list":
        if any(k not in ("limit","path") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_preimages_list(int(payload.get("limit",50)),payload.get("path"))
        result={"function_id":"filesystem.preimages.list","risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.rollback":
        if set(payload)!={"preimage_id"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_rollback(call,str(payload["preimage_id"]))
        result={"function_id":"filesystem.rollback","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_id":str(payload["preimage_id"]),"preimage_sha256":data.get("restored_sha256"),"rollback_preimage_id":data.get("rollback_preimage_id")}
    elif tool=="hara.process.sessions":
        if payload: raise ValueError("TOOL_PAYLOAD_MUST_BE_EMPTY")
        data=process_sessions()
        result={"function_id":"process.sessions","risk_class":"READ_ONLY","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.run":
        if "command" not in payload or any(k not in ("command","cwd","timeout_ms","max_lines") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_run(str(payload["command"]),payload.get("cwd"),int(payload.get("timeout_ms",3000)),int(payload.get("max_lines",200)))
        result={"function_id":"process.run","risk_class":"PROCESS_EXECUTION","process_exit_code":data.get("exit_code") if isinstance(data.get("exit_code"),int) else None,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.start":
        if "command" not in payload or any(k not in ("command","cwd","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_start(str(payload["command"]),payload.get("cwd"),int(payload.get("timeout_ms",1000)))
        result={"function_id":"process.start","risk_class":"PROCESS_EXECUTION","process_exit_code":data.get("exit_code") if isinstance(data.get("exit_code"),int) else None,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.output":
        if "session_id" not in payload or any(k not in ("session_id","offset","length","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=_process_output_payload(_process_get(str(payload["session_id"])),payload.get("offset"),int(payload.get("length",200)),int(payload.get("timeout_ms",500)))
        result={"function_id":"process.output","risk_class":"READ_ONLY","process_exit_code":data.get("exit_code") if isinstance(data.get("exit_code"),int) else None,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.interact":
        if not {"session_id","input"}.issubset(payload) or any(k not in ("session_id","input","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_interact(str(payload["session_id"]),str(payload["input"]),int(payload.get("timeout_ms",1000)))
        result={"function_id":"process.interact","risk_class":"PROCESS_EXECUTION","process_exit_code":data.get("exit_code") if isinstance(data.get("exit_code"),int) else None,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.kill":
        if "session_id" not in payload or any(k not in ("session_id","force") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_kill(str(payload["session_id"]),bool(payload.get("force",False)))
        result={"function_id":"process.kill","risk_class":"PROCESS_EXECUTION","process_exit_code":data.get("exit_code") if isinstance(data.get("exit_code"),int) else None,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.create_directory":
        if set(payload)-{"path","parents"} or "path" not in payload: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_create_directory(str(payload["path"]),payload.get("parents",True))
        result={"function_id":"filesystem.create_directory","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,**({"preimage_sha256":data.get("preimage_sha256")} if data.get("preimage_sha256") else {})}
    elif tool=="hara.files.write":
        if set(payload)-{"path","content","mode"} or not {"path","content"}.issubset(payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_write(call,str(payload["path"]),str(payload["content"]),str(payload.get("mode","rewrite")))
        result={"function_id":"filesystem.write","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.files.edit":
        if set(payload)-{"path","old_text","new_text","replace_all"} or not {"path","old_text","new_text"}.issubset(payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_edit(call,str(payload["path"]),str(payload["old_text"]),str(payload["new_text"]),bool(payload.get("replace_all",False)))
        result={"function_id":"filesystem.edit","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.files.move":
        if set(payload)!={"source","destination"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_move(str(payload["source"]),str(payload["destination"]))
        result={"function_id":"filesystem.move","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.copy":
        if set(payload)!={"source","destination"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_copy(str(payload["source"]),str(payload["destination"]))
        result={"function_id":"filesystem.copy","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.files.delete":
        if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_delete(call,str(payload["path"]))
        result={"function_id":"filesystem.delete","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_id":data.get("preimage_id"),"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.receipts.get":
        result=read_receipt(payload.get("receipt_id_or_sha256"))
        return {
            "state":"PASS","operational_authority":"HARA_SERVICES",
            "runtime_authority_from_chatgpt":False,"mutation_performed":False,
            "result":result,"blocker":None,
        }
    else:
        raise ValueError("TOOL_ID_INVALID")
    sha=write_receipt(config,call,"PASS",result)
    mutation=_is_mutation_tool(tool)
    if mutation and isinstance(result,dict):
        approval=(call.get("_local_approval") or {})
        result["human_approval_state"]=approval.get("state")
        result["local_authorization_mode"]=approval.get("mode")
        result["authorization_source"]=approval.get("source")
    return {
        "state":"PASS","operational_authority":"HARA_SERVICES",
        "runtime_authority_from_chatgpt":False,"mutation_performed":mutation,
        "result":result,"blocker":None,"bridge_receipt_sha256":sha,
    }
def complete(config, call, state, result, error_code=None):
    body={"call_id":call["call_id"],"state":state,"result":result}
    if error_code: body["error_code"]=error_code
    post_json(config["HARA_COMMANDER_URL"]+"/api/device/calls/complete",config["HARA_DEVICE_TOKEN"],body)

def execute_call(config,call):
    started=time.monotonic()
    call["_transport"]="OUTBOUND_RELAY"
    budget_reservation=None
    budget_committed=False
    if effective_approval_mode(config)!="PERSISTENT_TRUSTED" and not operator_session_active():
        code="LOCAL_OPERATOR_SESSION_REQUIRED"
        append_console_event("DENIED",call,state="DENIED",error_code=code)
        complete(config,call,"FAILED",{
            "state":"DENIED","operational_authority":"LOCAL_OPERATOR_SESSION",
            "runtime_authority_from_chatgpt":False,"mutation_performed":False,
            "result":{},"blocker":{"code":code},
        },code)
        return
    append_console_event("RECEIVED",call,state="PENDING")
    try:
        budget_reservation=local_budget_reserve(config,call)
        if _is_mutation_tool(call.get("tool_id")):
            call["_local_approval"]=request_local_approval(call)
        append_console_event("EXECUTING",call,state="EXECUTING")
        result=execute_tool(config,call)
        budget_commit=None
        if budget_reservation:
            budget_commit=local_budget_commit(call.get("request_id"))
            budget_committed=True
        complete(config,call,"COMPLETED",result)
        if budget_commit and budget_commit.get("exhausted"):
            try:
                refresh_product_lease(config)
                append_console_event("LOCAL_BUDGET_ROLLOVER",call,state="READY")
            except Exception as refresh_exc:
                append_console_event(
                    "PRODUCT_LEASE_DEGRADED",
                    call,
                    state="DEGRADED",
                    error_code=safe_error_code(refresh_exc),
                )
        append_console_event(
            "PASS",call,state="COMPLETED",
            receipt_sha256=result.get("bridge_receipt_sha256") if isinstance(result,dict) else None,
            duration_ms=round((time.monotonic()-started)*1000),
        )
    except Exception as exc:
        code=safe_error_code(exc)
        if budget_reservation and not budget_committed:
            try:
                local_budget_release(call.get("request_id"))
            except Exception:
                pass
        operational = local_mcp_operational_error(code,"",{}) is not None
        append_console_event(
            "OPERATIONAL" if operational else "DENIED",
            call,
            state="EXPECTED" if operational else "FAILED",
            error_code=code,
            duration_ms=round((time.monotonic()-started)*1000),
        )
        complete(config,call,"FAILED",{
            "state":"DENIED","operational_authority":"LOCAL_OPERATOR_SESSION",
            "runtime_authority_from_chatgpt":False,"mutation_performed":False,
            "result":{},"blocker":{"code":code},
        },code)

def self_test():
    global RECEIPT_DIR
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        RECEIPT_DIR=Path(d)
        cfg={"HARA_DEVICE_ID":"selftest","HARA_DEVICE_ARCH":"test"}
        base={"call_id":"c","request_id":"selftest-001","payload":{}}
        assert execute_tool(cfg,{**base,"tool_id":"hara.health"})["state"]=="PASS"
        listing=execute_tool(cfg,{**base,"request_id":"selftest-002","tool_id":"hara.functions.list"})
        assert any(x["function_id"]==FUNCTION_ID for x in listing["result"]["functions"])
        assert any(x["function_id"]=="system.uptime" for x in listing["result"]["functions"])
        assert any(x["function_id"]=="system.resources" for x in listing["result"]["functions"])
        assert any(x["function_id"]=="workspace.inspect" for x in listing["result"]["functions"])
        desc=execute_tool(cfg,{**base,"request_id":"selftest-003","tool_id":"hara.functions.describe","payload":{"function_id":FUNCTION_ID}})
        assert desc["result"]["EXECUTION_SEMANTICS"]["risk_class"]=="READ_ONLY"
        inv=execute_tool(cfg,{**base,"request_id":"selftest-004","tool_id":"hara.functions.invoke","payload":{"function_id":FUNCTION_ID,"arguments":{"argv":[]}}})
        uptime=execute_tool(cfg,{**base,"request_id":"selftest-004b","tool_id":"hara.functions.invoke","payload":{"function_id":"system.uptime","arguments":{"argv":[]}}})
        assert "uptime_seconds" in json.loads(uptime["result"]["stdout"])
        resources=execute_tool(cfg,{**base,"request_id":"selftest-resources","tool_id":"hara.system.resources","payload":{}})
        assert json.loads(resources["result"]["stdout"])["cpu_logical"]>=1
        workspace=execute_tool(cfg,{**base,"request_id":"selftest-workspace","tool_id":"hara.workspace.inspect","payload":{"path":d,"max_entries":20}})
        workspace_data=json.loads(workspace["result"]["stdout"]); assert workspace_data["root"]==str(Path(d).resolve()) and workspace_data["external_command_invoked"] is False
        procs=execute_tool(cfg,{**base,"request_id":"selftest-004c","tool_id":"hara.functions.invoke","payload":{"function_id":"process.list","arguments":{"argv":["3"]}}})
        assert len(json.loads(procs["result"]["stdout"])["processes"])<=3
        direct_ping=execute_tool(cfg,{**base,"request_id":"selftest-004d","tool_id":"hara.ping","payload":{}})
        assert json.loads(direct_ping["result"]["stdout"])["pong"] is True
        direct_proc=execute_tool(cfg,{**base,"request_id":"selftest-004e","tool_id":"hara.processes.list","payload":{"limit":2}})
        assert len(json.loads(direct_proc["result"]["stdout"])["processes"])<=2
        mut_call={**base,"call_id":"selftest-mut","request_id":"selftest-004f","tool_id":"hara.files.write","payload":{"path":str(Path(d)/"mut.txt"),"content":"alpha","mode":"rewrite"},"_local_approval":{"state":"APPROVED"}}
        mut=execute_tool(cfg,mut_call)
        assert mut["mutation_performed"] is True
        mut_receipt=read_receipt(mut["bridge_receipt_sha256"])
        assert mut_receipt["mutation_class"]=="FILESYSTEM_MUTATION_V1" and mut_receipt["human_approval_state"]=="APPROVED"
        src=Path(d)/"copy-source.txt"; src.write_text("copy-me",encoding="utf-8")
        cp=execute_tool(cfg,{**base,"call_id":"selftest-copy","request_id":"selftest-copy","tool_id":"hara.files.copy","payload":{"source":str(src),"destination":str(Path(d)/"copy-dest.txt")},"_local_approval":{"state":"APPROVED"}})
        assert json.loads(cp["result"]["stdout"])["sha256"]==hashlib.sha256(b"copy-me").hexdigest()
        doomed=Path(d)/"delete-me.txt"; doomed.write_text("restore-me",encoding="utf-8")
        deleted=execute_tool(cfg,{**base,"call_id":"selftest-delete","request_id":"selftest-delete","tool_id":"hara.files.delete","payload":{"path":str(doomed)},"_local_approval":{"state":"APPROVED"}})
        deleted_data=json.loads(deleted["result"]["stdout"]); assert not doomed.exists() and deleted_data["preimage_id"].startswith("HARA-PREIMAGE-")
        restore=execute_tool(cfg,{**base,"call_id":"selftest-delete-rollback","request_id":"selftest-delete-rollback","tool_id":"hara.files.rollback","payload":{"preimage_id":deleted_data["preimage_id"]},"_local_approval":{"state":"APPROVED"}})
        assert doomed.read_text(encoding="utf-8")=="restore-me"
        target=Path(d)/"rollback.txt"; target.write_text("before",encoding="utf-8")
        write2=execute_tool(cfg,{**base,"call_id":"selftest-preimage-write","request_id":"selftest-preimage-write","tool_id":"hara.files.write","payload":{"path":str(target),"content":"after","mode":"rewrite"},"_local_approval":{"state":"APPROVED"}})
        write2_data=json.loads(write2["result"]["stdout"]); pid=write2_data["preimage_id"]
        assert pid.startswith("HARA-PREIMAGE-") and target.read_text()=="after"
        plist=filesystem_preimages_list(10,str(target)); assert any(x["preimage_id"]==pid for x in plist["preimages"])
        rb=execute_tool(cfg,{**base,"call_id":"selftest-rollback","request_id":"selftest-rollback","tool_id":"hara.files.rollback","payload":{"preimage_id":pid},"_local_approval":{"state":"APPROVED"}})
        rb_data=json.loads(rb["result"]["stdout"]); assert target.read_text()=="before" and rb_data["rollback_preimage_id"].startswith("HARA-PREIMAGE-")
        rb_receipt=read_receipt(rb["bridge_receipt_sha256"]); assert rb_receipt["mutation_class"]=="FILESYSTEM_ROLLBACK_V1"
        run_call={**base,"call_id":"selftest-run","request_id":"selftest-run","tool_id":"hara.process.run","payload":{"command":"printf 'oneshot\\n'","timeout_ms":500,"max_lines":20},"_local_approval":{"state":"APPROVED"}}
        run=execute_tool(cfg,run_call); run_data=json.loads(run["result"]["stdout"])
        assert run["mutation_performed"] is True and run_data["state"]=="EXITED" and "oneshot" in run_data["text"] and run_data["session_retained"] is False
        assert run_data["run_id"] not in PROCESS_SESSIONS
        timeout_run=execute_tool(cfg,{**base,"call_id":"selftest-run-timeout","request_id":"selftest-run-timeout","tool_id":"hara.process.run","payload":{"command":"sleep 2","timeout_ms":100,"max_lines":20},"_local_approval":{"state":"APPROVED"}})
        timeout_data=json.loads(timeout_run["result"]["stdout"]); assert timeout_data["timed_out"] is True and timeout_data["session_retained"] is False
        failed_proc=execute_tool(cfg,{**base,"call_id":"selftest-proc-exit7","request_id":"selftest-proc-exit7","tool_id":"hara.process.start","payload":{"command":"exit 7","timeout_ms":500},"_local_approval":{"state":"APPROVED"}})
        failed_data=json.loads(failed_proc["result"]["stdout"]); assert failed_data["state"]=="EXITED" and failed_data["exit_code"]==7 and failed_proc["result"]["process_exit_code"]==7
        PROCESS_SESSIONS.pop(failed_data["session_id"],None)
        proc_call={**base,"call_id":"selftest-proc","request_id":"selftest-004g","tool_id":"hara.process.start","payload":{"command":"printf 'hello\n'","timeout_ms":300},"_local_approval":{"state":"APPROVED"}}
        proc=execute_tool(cfg,proc_call); proc_data=json.loads(proc["result"]["stdout"]); sid=proc_data["session_id"]
        assert proc["mutation_performed"] is True and sid.startswith("HARA-PROC-")
        pout=execute_tool(cfg,{**base,"call_id":"selftest-procout","request_id":"selftest-004h","tool_id":"hara.process.output","payload":{"session_id":sid,"length":20,"timeout_ms":100}})
        pout_data=json.loads(pout["result"]["stdout"])
        observed="\n".join([str(proc_data.get("text") or ""),str(proc_data.get("partial") or ""),str(pout_data.get("text") or ""),str(pout_data.get("partial") or "")])
        assert "hello" in observed
        proc_receipt=read_receipt(proc["bridge_receipt_sha256"]); assert proc_receipt["mutation_class"]=="PROCESS_EXECUTION_V1"
        assert "secret=<redacted>" in _redact_command_preview("echo secret=abc123")
        long_call=execute_tool(cfg,{**base,"call_id":"selftest-long-proc","request_id":"selftest-long-proc","tool_id":"hara.process.start","payload":{"command":"sleep 30","timeout_ms":100},"_local_approval":{"state":"APPROVED"}})
        longp=json.loads(long_call["result"]["stdout"]); longsid=longp["session_id"]
        assert _process_get(longsid).get("exit_code") is None and long_call["result"]["process_exit_code"] is None
        assert cleanup_process_sessions() >= 1
        _drain_process(_process_get(longsid),100)
        sha=inv["bridge_receipt_sha256"]
        got=execute_tool(cfg,{**base,"request_id":"selftest-005","tool_id":"hara.receipts.get","payload":{"receipt_id_or_sha256":sha}})
        assert got["result"]["tool_id"]=="hara.functions.invoke"
        expected_stdout_sha=hashlib.sha256(str(inv["result"]["stdout"]).encode("utf-8")).hexdigest()
        assert got["result"]["result_binding"]=="STDOUT_SHA256_V1"
        assert got["result"]["result_stdout_sha256"]==expected_stdout_sha
        try:
            execute_tool(cfg,{**base,"request_id":"selftest-006","tool_id":"hara.functions.invoke","payload":{"function_id":"shell.run","arguments":{"argv":[]}}})
            raise AssertionError("ARBITRARY_FUNCTION_NOT_DENIED")
        except ValueError as exc:
            assert str(exc)=="UNKNOWN_FUNCTION_ID"
    global SESSION_FILE, CONSOLE_EVENTS_FILE, OPERATIONS_DB_FILE, APPROVAL_DIR, CONFIG_FILE
    old_config_file=CONFIG_FILE
    with tempfile.TemporaryDirectory() as session_dir:
        SESSION_FILE=Path(session_dir)/"operator-session.json"
        CONSOLE_EVENTS_FILE=Path(session_dir)/"console-events.jsonl"
        OPERATIONS_DB_FILE=Path(session_dir)/"operations.sqlite3"
        APPROVAL_DIR=Path(session_dir)/"approvals"
        CONFIG_FILE=Path(session_dir)/"device.env"
        CONFIG_FILE.write_text("HARA_COMMANDER_URL=https://commander.invalid\nHARA_DEVICE_ID=selftest\nHARA_DEVICE_TOKEN=selftest-token\nHARA_DEVICE_ARCH=x86_64\nHARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION\n",encoding="utf-8")
        assert operator_session_active() is False
        SESSION_FILE.write_text(json.dumps({
            "schema":"hara.commander-operator-session.v1",
            "owner_pid":os.getpid(),
            "owner_start_marker":_pid_start_marker(os.getpid()),
            "started_at_epoch":int(time.time()),
            "started_at_utc":utcnow(),
        }),encoding="utf-8")
        assert operator_session_active() is True
        append_console_event("SELFTEST",{"request_id":"r","tool_id":"hara.health","payload":{"secret":"never"}})
        event=json.loads(CONSOLE_EVENTS_FILE.read_text(encoding="utf-8").splitlines()[-1])
        assert event["payload_values_exposed"] is False
        assert event["secret_material_exposed"] is False
        assert "secret" not in event
        approval_call={"call_id":"approval-selftest","request_id":"approval-r","tool_id":"hara.files.create_directory","payload":{"path":"/tmp/hara-approval-selftest"}}
        try:
            request_local_approval(approval_call,timeout_seconds=1)
            raise AssertionError("OLD_SESSION_MUTATION_NOT_DENIED")
        except ValueError as exc:
            assert str(exc)=="LOCAL_OPERATOR_SESSION_UPGRADE_REQUIRED"
        session=json.loads(SESSION_FILE.read_text(encoding="utf-8")); session["agent_version"]=AGENT_VERSION; session["approval_mode"]="ASK_EVERY_ACTION"
        SESSION_FILE.write_text(json.dumps(session,sort_keys=True,separators=(",",":")),encoding="utf-8")
        import threading
        def approve_selftest():
            req_path,res_path=_approval_paths("approval-selftest")
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline and not req_path.exists(): time.sleep(0.02)
            assert req_path.exists()
            response={"schema":"hara.commander-local-approval-response.v1","approval_id":"approval-selftest","decision":"APPROVED","decided_at_utc":utcnow()}
            res_path.parent.mkdir(parents=True,exist_ok=True); res_path.write_text(json.dumps(response),encoding="utf-8")
        thread=threading.Thread(target=approve_selftest,daemon=True); thread.start()
        approval=request_local_approval(approval_call,timeout_seconds=2); thread.join(timeout=1)
        assert approval["state"]=="APPROVED" and approval["mode"]=="ASK_EVERY_ACTION"
        session["approval_mode"]="SESSION_TRUSTED"
        SESSION_FILE.write_text(json.dumps(session,sort_keys=True,separators=(",",":")),encoding="utf-8")
        trusted=request_local_approval(approval_call,timeout_seconds=1)
        assert trusted["state"]=="APPROVED" and trusted["mode"]=="SESSION_TRUSTED" and trusted["source"]=="LOCAL_OPERATOR_SESSION"
        CONFIG_FILE.write_text("HARA_COMMANDER_URL=https://commander.invalid\nHARA_DEVICE_ID=selftest\nHARA_DEVICE_TOKEN=selftest-token\nHARA_DEVICE_ARCH=x86_64\nHARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n",encoding="utf-8")
        SESSION_FILE.unlink(missing_ok=True)
        persistent=request_local_approval(approval_call,timeout_seconds=1)
        assert persistent["state"]=="APPROVED" and persistent["mode"]=="PERSISTENT_TRUSTED" and persistent["source"]=="DEVICE_ENROLLMENT_POLICY"
        local_devices=local_simple_mcp_call(load_config(),"list_devices",{})
        assert local_devices["devices"][0]["state"]=="ONLINE"
    CONFIG_FILE=old_config_file
    assert len(local_simple_mcp_tools())==24
    assert tuple(tool["name"] for tool in local_simple_mcp_tools())==LOCAL_SIMPLE_MCP_TOOL_NAMES
    mapped_tool,mapped_payload=_local_simple_map({"HARA_DEVICE_ID":"selftest"},"start_process",{"command":"printf hi"})
    assert mapped_tool=="hara.process.run" and mapped_payload["max_lines"]==200
    mapped_interactive,_=_local_simple_map({"HARA_DEVICE_ID":"selftest"},"start_process",{"command":"python3 -i","interactive":True})
    assert mapped_interactive=="hara.process.start"
    local_usage=local_simple_mcp_call({"HARA_DEVICE_ID":"selftest"},"get_usage_stats",{})
    assert local_usage["relay_calls_per_local_tool_call"]==0
    schemas={tool["name"]:tool["inputSchema"]["properties"] for tool in local_simple_mcp_tools()}
    assert schemas["read_file"]["offset"]["maximum"]==1000000 and schemas["read_file"]["length"]["maximum"]==400
    assert schemas["read_multiple_files"]["length"]["maximum"]==100
    assert schemas["write_file"]["content"]["maxLength"]==65536
    assert schemas["edit_block"]["old_string"]["maxLength"]==32768 and schemas["edit_block"]["new_string"]["maxLength"]==32768
    assert schemas["list_directory"]["depth"]["maximum"]==5 and schemas["list_directory"]["limit"]["maximum"]==200
    assert schemas["search"]["pattern"]["maxLength"]==256 and schemas["search"]["max_results"]["maximum"]==100 and schemas["search"]["file_glob"]["maxLength"]==180
    assert schemas["list_processes"]["limit"]["maximum"]==200
    assert schemas["read_process_output"]["session_id"]["maxLength"]==180 and schemas["read_process_output"]["timeout_ms"]["maximum"]==3000
    assert schemas["interact_with_process"]["input"]["maxLength"]==4096 and schemas["interact_with_process"]["timeout_ms"]["maximum"]==3000
    long_tool,long_payload=_local_simple_map({"HARA_DEVICE_ID":"selftest"},"start_process",{"command":"sleep 12","timeout_ms":20000})
    assert long_tool=="hara.process.start" and long_payload["timeout_ms"]==3000 and "max_lines" not in long_payload
    missing_state=local_mcp_operational_error("FILENOTFOUNDERROR","get_file_info",{"path":"/tmp/missing"})
    assert missing_state["state"]=="NOT_FOUND" and missing_state["blocker"]["retryable"] is False
    session_state=local_mcp_operational_error("PROCESS_SESSION_NOT_FOUND","read_process_output",{"session_id":"missing"})
    assert session_state["result"]["recommended_tool"]=="list_sessions"
    assert local_mcp_operational_error("POLICY_DENIED","ping",{}) is None
    print("COMMANDER_LOCAL_MCP_TOOL_COUNT=24")
    print("COMMANDER_LOCAL_MCP_RELAY_CALLS_PER_LOCAL_TOOL=0")
    print("COMMANDER_LOCAL_MCP_PROCESS_ONE_SHOT_DEFAULT=PASS")
    print("COMMANDER_LOCAL_MCP_DOWNSTREAM_BOUNDS=PASS")
    print("COMMANDER_LOCAL_MCP_OPERATIONAL_ERRORS=PASS")
    print("COMMANDER_LOCAL_MCP_LONG_PROCESS_AUTOROUTE=PASS")
    print("COMMANDER_PROCESS_EXIT_CODE_PROPAGATION=PASS")
    print("COMMANDER_LINUX_OPERATOR_SESSION_GATE=PASS")
    print("COMMANDER_LOCAL_MUTATION_APPROVAL=PASS")
    print("COMMANDER_PERSISTENT_TRUSTED_NO_SESSION=PASS")
    print("COMMANDER_PERSISTENT_TRUSTED_LOCAL_MCP_ONLINE=PASS")
    print("COMMANDER_LINUX_CONSOLE_SANITIZATION=PASS")
    print("COMMANDER_LINUX_FIVE_TOOL_BRIDGE=PASS")
    print("COMMANDER_ARBITRARY_FUNCTION=DENIED")


LOCAL_SIMPLE_MCP_TOOL_NAMES = (
    "list_devices","get_config","get_usage_stats","get_activity","ping","get_device_info",
    "read_file","read_multiple_files","write_file","edit_block","create_directory","list_directory",
    "move_file","copy_file","delete_file","search","get_file_info","list_processes","start_process",
    "read_process_output","interact_with_process","kill_process","list_sessions","get_recent_tool_calls",
)

def _mcp_schema(properties=None, required=None):
    return {
        "type":"object",
        "properties":properties or {},
        "required":required or [],
        "additionalProperties":False,
    }

def local_simple_mcp_tools():
    string={"type":"string"}
    path={"type":"string","minLength":1,"maxLength":4096}
    computer={"type":"string","minLength":1,"maxLength":120}
    integer={"type":"integer"}
    boolean={"type":"boolean"}
    specs=[
        ("list_devices","List Devices","List this local Commander device.",_mcp_schema()),
        ("get_config","Get Config","Get local Commander configuration and capabilities.",_mcp_schema({"computer":computer})),
        ("get_usage_stats","Get Usage Stats","Describe local MCP transaction mode. Local calls do not use the cloud relay.",_mcp_schema()),
        ("get_activity","Get Activity","Get privacy-safe local Commander event metadata.",_mcp_schema({"limit":{"type":"integer","minimum":1,"maximum":100},"window":{"type":"string","enum":["24h","7d","30d"]}})),
        ("ping","Ping","Check the local Commander Agent.",_mcp_schema({"computer":computer})),
        ("get_device_info","Get Device Info","Get local device and Agent information.",_mcp_schema({"computer":computer})),
        ("read_file","Read File","Read a text file.",_mcp_schema({"computer":computer,"path":path,"offset":{"type":"integer","minimum":0,"maximum":1000000},"length":{"type":"integer","minimum":1,"maximum":400}},["path"])),
        ("read_multiple_files","Read Multiple Files","Read multiple text files in one call.",_mcp_schema({"computer":computer,"paths":{"type":"array","items":path,"minItems":1,"maxItems":10},"offset":{"type":"integer","minimum":0,"maximum":1000000},"length":{"type":"integer","minimum":1,"maximum":100}},["paths"])),
        ("write_file","Write File","Write or append text to a file.",_mcp_schema({"computer":computer,"path":path,"content":{"type":"string","maxLength":65536},"mode":{"type":"string","enum":["rewrite","append"]}},["path","content"])),
        ("edit_block","Edit Block","Apply a focused text replacement.",_mcp_schema({"computer":computer,"path":path,"old_string":{"type":"string","minLength":1,"maxLength":32768},"new_string":{"type":"string","maxLength":32768},"replace_all":boolean},["path","old_string","new_string"])),
        ("create_directory","Create Directory","Create a directory.",_mcp_schema({"computer":computer,"path":path,"parents":boolean},["path"])),
        ("list_directory","List Directory","List directory contents.",_mcp_schema({"computer":computer,"path":path,"depth":{"type":"integer","minimum":1,"maximum":5},"limit":{"type":"integer","minimum":1,"maximum":200}},["path"])),
        ("move_file","Move File","Move or rename a file or directory.",_mcp_schema({"computer":computer,"source":path,"destination":path},["source","destination"])),
        ("copy_file","Copy File","Copy a file or directory.",_mcp_schema({"computer":computer,"source":path,"destination":path},["source","destination"])),
        ("delete_file","Delete File","Delete a file with reversible preimage protection.",_mcp_schema({"computer":computer,"path":path},["path"])),
        ("search","Search","Search file names or text content.",_mcp_schema({"computer":computer,"path":path,"pattern":{"type":"string","minLength":1,"maxLength":256},"search_type":{"type":"string","enum":["files","content"]},"max_results":{"type":"integer","minimum":1,"maximum":100},"include_hidden":boolean,"ignore_case":boolean,"file_glob":{"type":"string","maxLength":180}},["path","pattern"])),
        ("get_file_info","Get File Info","Get file metadata.",_mcp_schema({"computer":computer,"path":path},["path"])),
        ("list_processes","List Processes","List running processes.",_mcp_schema({"computer":computer,"limit":{"type":"integer","minimum":1,"maximum":200}})),
        ("start_process","Start Process","Run a command. Defaults to bounded one-shot execution; interactive=true keeps a managed session. Requests above 10 seconds are automatically routed to a managed session.",_mcp_schema({"computer":computer,"command":{"type":"string","minLength":1,"maxLength":4096},"cwd":path,"timeout_ms":{"type":"integer","minimum":100,"maximum":30000},"max_lines":{"type":"integer","minimum":1,"maximum":500},"interactive":boolean},["command"])),
        ("read_process_output","Read Process Output","Read a managed process session.",_mcp_schema({"computer":computer,"session_id":{"type":"string","minLength":1,"maxLength":180},"offset":{"type":"integer","minimum":0,"maximum":1000000},"length":{"type":"integer","minimum":1,"maximum":500},"timeout_ms":{"type":"integer","minimum":0,"maximum":3000}},["session_id"])),
        ("interact_with_process","Interact With Process","Send input to a managed process session.",_mcp_schema({"computer":computer,"session_id":{"type":"string","minLength":1,"maxLength":180},"input":{"type":"string","maxLength":4096},"timeout_ms":{"type":"integer","minimum":0,"maximum":3000}},["session_id","input"])),
        ("kill_process","Kill Process","Terminate a managed process session.",_mcp_schema({"computer":computer,"session_id":{"type":"string","minLength":1,"maxLength":180},"force":boolean},["session_id"])),
        ("list_sessions","List Sessions","List managed process sessions.",_mcp_schema({"computer":computer})),
        ("get_recent_tool_calls","Get Recent Tool Calls","Get privacy-safe local call metadata.",_mcp_schema({"computer":computer,"tool":{"type":"string"},"limit":{"type":"integer","minimum":1,"maximum":100}})),
    ]
    mutation={"write_file","edit_block","create_directory","move_file","copy_file","delete_file","start_process","interact_with_process","kill_process"}
    destructive={"write_file","edit_block","move_file","delete_file","interact_with_process","kill_process"}
    open_world={"start_process","interact_with_process"}
    return [
        {
            "name":name,
            "title":title,
            "description":description,
            "inputSchema":schema,
            "annotations":{
                "readOnlyHint":name not in mutation,
                "destructiveHint":name in destructive,
                "idempotentHint":name not in mutation,
                "openWorldHint":name in open_world,
            },
        }
        for name,title,description,schema in specs
    ]

def _local_simple_device_guard(config,args):
    requested=str((args or {}).get("computer") or "").strip()
    if requested and requested not in {str(config.get("HARA_DEVICE_ID") or ""),str(platform.node() or "")}:
        raise ValueError("LOCAL_MCP_DEVICE_TARGET_MISMATCH")

def _local_recent_events(limit=50,tool=None,window="7d"):
    snap=local_activity_snapshot(window,limit=limit,include_events=True)
    events=snap.get("events") or []
    if tool:
        events=[x for x in events if str(x.get("tool_id") or "")==str(tool)]
    return {
        "events":events[:max(1,min(100,int(limit)))],
        "summary":snap.get("summary") or {},
        "diagnostics":snap.get("diagnostics") or {},
        "window":snap.get("window") or {},
        "source":"LOCAL_SQLITE",
        "metadata_only":True,
        "detail_location":"LOCAL_DEVICE",
        "cloud_history_persisted":False,
    }

def _local_simple_map(config,name,args):
    args=dict(args or {})
    _local_simple_device_guard(config,args)
    computer=args.pop("computer",None)
    if name=="ping": return "hara.ping",{}
    if name=="get_device_info": return "hara.device.info",{}
    if name=="read_file":
        return "hara.files.read",{"path":str(args["path"]),**({"offset":int(args["offset"])} if "offset" in args else {}),**({"length":int(args["length"])} if "length" in args else {})}
    if name=="read_multiple_files":
        return "hara.files.read_many",{"paths":[str(x) for x in args["paths"]],**({"offset":int(args["offset"])} if "offset" in args else {}),**({"length":int(args["length"])} if "length" in args else {})}
    if name=="write_file": return "hara.files.write",{"path":str(args["path"]),"content":str(args["content"]),"mode":str(args.get("mode","rewrite"))}
    if name=="edit_block": return "hara.files.edit",{"path":str(args["path"]),"old_text":str(args["old_string"]),"new_text":str(args["new_string"]),"replace_all":bool(args.get("replace_all",False))}
    if name=="create_directory": return "hara.files.create_directory",{"path":str(args["path"]),"parents":bool(args.get("parents",True))}
    if name=="list_directory": return "hara.files.list",{"path":str(args["path"]),**({"depth":int(args["depth"])} if "depth" in args else {}),**({"limit":int(args["limit"])} if "limit" in args else {})}
    if name=="move_file": return "hara.files.move",{"source":str(args["source"]),"destination":str(args["destination"])}
    if name=="copy_file": return "hara.files.copy",{"source":str(args["source"]),"destination":str(args["destination"])}
    if name=="delete_file": return "hara.files.delete",{"path":str(args["path"])}
    if name=="search":
        return "hara.files.search",{"path":str(args["path"]),"pattern":str(args["pattern"]),"search_type":str(args.get("search_type","files")),**({"max_results":int(args["max_results"])} if "max_results" in args else {}),**({"include_hidden":bool(args["include_hidden"])} if "include_hidden" in args else {}),**({"ignore_case":bool(args["ignore_case"])} if "ignore_case" in args else {}),**({"file_glob":str(args["file_glob"])} if args.get("file_glob") else {})}
    if name=="get_file_info": return "hara.files.info",{"path":str(args["path"])}
    if name=="list_processes":
        return "hara.processes.list",({"limit":int(args["limit"])} if "limit" in args else {})
    if name=="start_process":
        requested_timeout=int(args.get("timeout_ms",3000))
        managed=bool(args.get("interactive",False)) or requested_timeout>10000
        payload={"command":str(args["command"]),"timeout_ms":min(requested_timeout,3000) if managed else requested_timeout}
        if args.get("cwd"): payload["cwd"]=str(args["cwd"])
        if not managed: payload["max_lines"]=int(args.get("max_lines",200))
        return ("hara.process.start" if managed else "hara.process.run"),payload
    if name=="read_process_output":
        return "hara.process.output",{"session_id":str(args["session_id"]),**({"offset":int(args["offset"])} if "offset" in args else {}),**({"length":int(args["length"])} if "length" in args else {}),**({"timeout_ms":int(args["timeout_ms"])} if "timeout_ms" in args else {})}
    if name=="interact_with_process":
        return "hara.process.interact",{"session_id":str(args["session_id"]),"input":str(args["input"]),**({"timeout_ms":int(args["timeout_ms"])} if "timeout_ms" in args else {})}
    if name=="kill_process": return "hara.process.kill",{"session_id":str(args["session_id"]),"force":bool(args.get("force",False))}
    if name=="list_sessions": return "hara.process.sessions",{}
    raise ValueError("LOCAL_MCP_TOOL_INVALID")

def require_local_product_authority(config):
    if transport_mode(config)!="LOCAL_TUNNEL":
        return None
    with _ops_connect() as conn:
        lease=_active_verified_product_lease(conn,config)
    if not lease:
        raise ValueError("PRODUCT_LEASE_REQUIRED")
    if str(lease.get("transport_mode") or "")!="LOCAL_TUNNEL":
        raise ValueError("PRODUCT_LEASE_TRANSPORT_MISMATCH")
    return lease

def local_tunnel_usage(config,lease,request_id):
    if not lease: return None
    mode=str(lease.get("usage_mode") or "")
    if mode=="UNMETERED": return None
    if mode!="LOCAL_BUDGET":
        raise ValueError("LOCAL_TUNNEL_USAGE_MODE_UNSUPPORTED")
    with _ops_connect() as conn:
        rows=conn.execute(
            """SELECT budget_id,period_key,allocated_units,expires_at_utc
                 FROM local_budget_blocks
                WHERE tenant_id=? AND device_id=? AND entitlement_id=?
                  AND plan_code=? AND meter_id=? AND state='ACTIVE'
                  AND expires_at_utc>?
                ORDER BY issued_at_utc ASC""",
            (
                str(lease.get("tenant_id") or ""),str(lease.get("device_id") or ""),
                str(lease.get("entitlement_id") or ""),str(lease.get("plan_code") or ""),
                str(lease.get("meter_id") or ""),utcnow(),
            ),
        ).fetchall()
        for row in rows:
            committed,reserved=_budget_counts(conn,row["budget_id"])
            if int(row["allocated_units"])-committed-reserved>=1:
                return {"mode":"LOCAL_BUDGET","units":1,"period_key":str(row["period_key"]),"budget_id":str(row["budget_id"])}
    raise ValueError("LOCAL_BUDGET_EXHAUSTED")

def local_simple_mcp_call(config,name,args):
    if name not in LOCAL_SIMPLE_MCP_TOOL_NAMES:
        raise ValueError("LOCAL_MCP_TOOL_INVALID")
    _local_simple_device_guard(config,args or {})
    lease=require_local_product_authority(config)
    if name=="list_devices":
        authorized=effective_approval_mode(config)=="PERSISTENT_TRUSTED" or operator_session_active()
        return {"devices":[{"computer":platform.node(),"device_id":config.get("HARA_DEVICE_ID"),"agent_version":AGENT_VERSION,"state":"ONLINE" if authorized else "LOCAL_SESSION_REQUIRED","transport":"LOCAL_STDIO","product_transport_mode":transport_mode(config)}]}
    if name=="get_config":
        return {"computer":platform.node(),"device_id":config.get("HARA_DEVICE_ID"),"agent_version":AGENT_VERSION,"approval_mode":effective_approval_mode(config),"transport":"LOCAL_STDIO","product_transport_mode":transport_mode(config),"tools":list(LOCAL_SIMPLE_MCP_TOOL_NAMES)}
    if name=="get_usage_stats":
        return {"mode":"LOCAL_TUNNEL" if transport_mode(config)=="LOCAL_TUNNEL" else "LOCAL_MCP","relay_calls_per_local_tool_call":0,"cloud_quota_consumed_by_local_tool_call":False,"metadata_only":True}
    if name=="get_activity":
        return _local_recent_events((args or {}).get("limit",50),window=(args or {}).get("window","7d"))
    if name=="get_recent_tool_calls":
        return _local_recent_events((args or {}).get("limit",50),(args or {}).get("tool"),(args or {}).get("window","7d"))
    if effective_approval_mode(config)!="PERSISTENT_TRUSTED" and not operator_session_active():
        raise ValueError("LOCAL_OPERATOR_SESSION_REQUIRED")
    tool_id,payload=_local_simple_map(config,name,args or {})
    started=time.monotonic()
    request_id="HARA-LOCAL-MCP-"+uuid.uuid4().hex
    call={
        "call_id":"HARA-LOCAL-MCP-"+uuid.uuid4().hex,
        "request_id":request_id,
        "tool_id":tool_id,
        "payload":payload,
        "_transport":"LOCAL_MCP",
    }
    usage=local_tunnel_usage(config,lease,request_id)
    if usage: call["usage"]=usage
    budget_reservation=None
    budget_committed=False
    append_console_event("RECEIVED",call,state="PENDING")
    if _is_mutation_tool(tool_id):
        call["_local_approval"]=request_local_approval(call)
    append_console_event("EXECUTING",call,state="EXECUTING")
    try:
        budget_reservation=local_budget_reserve(config,call)
        result=execute_tool(config,call)
        if budget_reservation:
            local_budget_commit(call.get("request_id"))
            budget_committed=True
    except Exception as exc:
        code=safe_error_code(exc)
        if budget_reservation and not budget_committed:
            try: local_budget_release(call.get("request_id"))
            except Exception: pass
        operational = local_mcp_operational_error(code,name,args) is not None
        append_console_event(
            "OPERATIONAL" if operational else "DENIED",
            call,
            state="EXPECTED" if operational else "FAILED",
            error_code=code,
            duration_ms=round((time.monotonic()-started)*1000),
        )
        raise
    append_console_event("PASS",call,state="COMPLETED",receipt_sha256=result.get("bridge_receipt_sha256"),duration_ms=round((time.monotonic()-started)*1000))
    return result

def local_mcp_operational_error(code,name,args):
    common={
        "runtime_authority_from_chatgpt":False,
        "mutation_performed":False,
        "customer_services_relay":False,
        "transport":"LOCAL_STDIO",
    }
    def build(state,category,retryable,result=None):
        value={
            "state":state,**common,
            "blocker":{"code":code,"category":category,"retryable":bool(retryable)},
            "result":result or {},
        }
        if isinstance(args,dict) and args.get("computer"):
            value["computer"]=str(args.get("computer"))[:120]
        return value
    if code in {"PRODUCT_LEASE_REQUIRED","PRODUCT_LEASE_EXPIRED","PRODUCT_LEASE_TRANSPORT_MISMATCH"}:
        return build("AUTHORIZATION_EXPIRED","PRODUCT_AUTHORIZATION",False,{"reauthorize_url":"https://commander.haralabs.com.br/#devices","lease_required":True})
    if code=="DEVICE_OFFLINE":
        return build("UNAVAILABLE","DEVICE_AVAILABILITY",True,{"available":False,"device_state":"OFFLINE"})
    if code in {"DEVICE_BUSY","CHANNEL_TRANSIENT_BUSY"}:
        return build("BUSY","DEVICE_AVAILABILITY",True,{"available":True,"busy":True})
    if code in {"DEVICE_CALL_TIMEOUT","CHANNEL_TRANSIENT_TIMEOUT"}:
        return build("TIMEOUT","DEVICE_EXECUTION",True,{"completed":False})
    if code in {"FILENOTFOUNDERROR","FILE_NOT_FOUND","PARENT_DIRECTORY_NOT_FOUND","FILESYSTEM_PARENT_NOT_FOUND","PREIMAGE_NOT_FOUND","RECEIPT_NOT_FOUND","EDIT_MATCH_NOT_FOUND"}:
        result={"exists":False}
        if code=="PARENT_DIRECTORY_NOT_FOUND": result["recommended_tool"]="create_directory"
        if code=="PREIMAGE_NOT_FOUND": result["recommended_tool"]="list_preimages"
        category="ROLLBACK_STATE" if code=="PREIMAGE_NOT_FOUND" else "AUDIT_STATE" if code=="RECEIPT_NOT_FOUND" else "EDIT_MATCH" if code=="EDIT_MATCH_NOT_FOUND" else "FILESYSTEM_STATE"
        return build("NOT_FOUND",category,False,result)
    if code=="PROCESS_SESSION_NOT_FOUND":
        return build("NOT_FOUND","PROCESS_STATE",False,{"exists":False,"recommended_tool":"list_sessions"})
    if code=="PROCESS_SESSION_EXITED":
        return build("TERMINAL","PROCESS_STATE",False,{"session_state":"EXITED"})
    if code in {"DESTINATION_EXISTS","PATH_EXISTS_NOT_DIRECTORY","FILESYSTEM_PATH_EXISTS","FILEEXISTSERROR"}:
        return build("CONFLICT","FILESYSTEM_STATE",False,{"conflict":True})
    if code=="EDIT_MATCH_AMBIGUOUS":
        return build("NEEDS_INPUT","EDIT_MATCH",False,{"selection_required":True})
    if code in {"PATH_NOT_FILE","PATH_NOT_DIRECTORY","FILESYSTEM_NOT_DIRECTORY","SOURCE_NOT_FILE","DELETE_TARGET_NOT_FILE","ROLLBACK_TARGET_NOT_FILE","PROCESS_CWD_INVALID","ISADIRECTORYERROR","NOTADIRECTORYERROR"}:
        return build("INVALID_TARGET","FILESYSTEM_STATE",False,{"valid_target":False})
    if code=="BINARY_FILE_DENIED":
        return build("UNSUPPORTED_CONTENT","FILESYSTEM_CONTENT",False,{"text_required":True})
    if code in {"FILE_TOO_LARGE","HASH_FILE_TOO_LARGE","COPY_FILE_TOO_LARGE","DELETE_FILE_TOO_LARGE","PREIMAGE_FILE_TOO_LARGE","WRITE_TOO_LARGE"}:
        return build("LIMIT_EXCEEDED","PAYLOAD_LIMIT",False,{"within_limit":False})
    return None

def _stdio_mcp_write(payload):
    sys.stdout.write(json.dumps(payload,separators=(",",":"),ensure_ascii=False)+"\n")
    sys.stdout.flush()

def run_local_mcp_stdio():
    config=load_config()
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    session_id="HARA-MCP-SESSION-"+uuid.uuid4().hex
    session_started_at_utc=utcnow()
    session_started_monotonic=time.monotonic()
    append_console_event("LOCAL_MCP_SESSION_START",state="ACTIVE",action_summary="session_open")
    if transport_mode(config)=="LOCAL_TUNNEL" and local_metering_sync_due():
        threading.Thread(
            target=_local_metering_sync_background,
            args=(config,"MCP_START",session_id,session_started_at_utc),
            daemon=True,
            name="hara-metering-start",
        ).start()
    try:
        for raw in sys.stdin:
            if len(raw)>2*1024*1024:
                _stdio_mcp_write({"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"REQUEST_TOO_LARGE"}})
                continue
            raw=raw.strip()
            if not raw: continue
            try:
                msg=json.loads(raw)
            except Exception:
                _stdio_mcp_write({"jsonrpc":"2.0","id":None,"error":{"code":-32700,"message":"PARSE_ERROR"}})
                continue
            req_id=msg.get("id")
            method=str(msg.get("method") or "")
            params=msg.get("params") or {}
            if method.startswith("notifications/"):
                continue
            name=""
            args={}
            try:
                if method=="initialize":
                    result={"protocolVersion":"2025-06-18","capabilities":{"tools":{"listChanged":False}},"serverInfo":{"name":"H.A.R.A. Commander Local","version":AGENT_VERSION},"instructions":"Local MCP. Start a H.A.R.A. Commander operator session before executing computer tools."}
                elif method=="ping":
                    result={}
                elif method=="tools/list":
                    result={"tools":local_simple_mcp_tools()}
                elif method=="tools/call":
                    name=str(params.get("name") or "")
                    args=params.get("arguments") or {}
                    value=local_simple_mcp_call(config,name,args)
                    result={"content":[{"type":"text","text":json.dumps(value,separators=(",",":"),ensure_ascii=False)}],"structuredContent":value}
                else:
                    _stdio_mcp_write({"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":"METHOD_NOT_FOUND"}})
                    continue
                _stdio_mcp_write({"jsonrpc":"2.0","id":req_id,"result":result})
            except Exception as exc:
                code=safe_error_code(exc)
                operational=local_mcp_operational_error(code,name,args)
                if operational is not None:
                    _stdio_mcp_write({"jsonrpc":"2.0","id":req_id,"result":{"content":[{"type":"text","text":json.dumps(operational,separators=(",",":"),ensure_ascii=False)}],"structuredContent":operational}})
                else:
                    _stdio_mcp_write({"jsonrpc":"2.0","id":req_id,"result":{"isError":True,"content":[{"type":"text","text":json.dumps({"ok":False,"code":code},separators=(",",":"))}]}})
    finally:
        duration=max(0,int(time.monotonic()-session_started_monotonic))
        append_console_event("LOCAL_MCP_SESSION_STOP",state="CLOSED",action_summary=f"duration_seconds={duration}")
        if (
            transport_mode(config)=="LOCAL_TUNNEL"
            and duration>=LOCAL_METERING_MIN_INTERVAL_SECONDS
            and local_metering_sync_due()
        ):
            local_metering_sync(config,"MCP_STOP",session_id,session_started_at_utc,duration)

def commander_doctor():
    config=load_config()
    mode=effective_approval_mode(config)
    transport=transport_mode(config)
    runtime={}
    try:
        if STATUS_FILE.is_file(): runtime=json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        runtime={}

    cloud_health=False
    try:
        req=urllib.request.Request(config["HARA_COMMANDER_URL"]+"/api/health",method="GET",headers={"accept":"application/json","user-agent":"HARA-Commander-Doctor/"+AGENT_VERSION})
        with NO_REDIRECT_OPENER.open(req,timeout=5) as response:
            obj=json.loads(response.read().decode() or "{}")
            cloud_health=response.status==200 and obj.get("ok") is True and obj.get("service")=="hara-commander"
    except Exception:
        cloud_health=False

    if transport=="LOCAL_TUNNEL":
        lease_ok=False
        lease_until=""
        try:
            with _ops_connect() as conn:
                lease=_active_verified_product_lease(conn,config)
            lease_ok=bool(lease and str(lease.get("transport_mode") or "")=="LOCAL_TUNNEL")
            lease_until=str((lease or {}).get("valid_until_utc") or "")
        except Exception:
            lease_ok=False
        tunnel_rc,_=_openai_tunnel_doctor(capture=True)
        tunnel_ok=tunnel_rc==0
        overall=lease_ok and tunnel_ok
        print("HARA_COMMANDER_DOCTOR="+("PASS" if overall else "DEGRADED"))
        print("HARA_COMMANDER_AGENT_VERSION="+AGENT_VERSION)
        print("HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL")
        print("HARA_COMMANDER_LOCAL_AUTHORIZATION="+("PASS" if lease_ok else "EXPIRED"))
        print("HARA_COMMANDER_LOCAL_AUTHORIZATION_UNTIL_UTC="+lease_until)
        print("HARA_COMMANDER_OPENAI_TUNNEL="+("PASS" if tunnel_ok else "FAIL"))
        print("HARA_COMMANDER_CONTROL_PLANE_HEALTH="+("PASS" if cloud_health else "DEGRADED_OPTIONAL"))
        print("HARA_COMMANDER_TOOL_DATA_PLANE=LOCAL_DIRECT")
        print("SECRET_MATERIAL_EXPOSED=FALSE")
        return 0 if overall else 2

    print("HARA_COMMANDER_DOCTOR="+("PASS" if cloud_health else "DEGRADED"))
    print("HARA_COMMANDER_AGENT_VERSION="+AGENT_VERSION)
    print("HARA_COMMANDER_APPROVAL_MODE="+mode)
    print("HARA_COMMANDER_BACKGROUND_AUTHORIZED="+("TRUE" if mode=="PERSISTENT_TRUSTED" else "FALSE"))
    print("HARA_COMMANDER_SESSION="+("ACTIVE" if operator_session_active() else "INACTIVE"))
    print("HARA_COMMANDER_REMOTE_HEALTH="+("PASS" if cloud_health else "FAIL"))
    print("HARA_COMMANDER_LAST_HEARTBEAT_UTC="+str(runtime.get("last_successful_heartbeat_at_utc") or ""))
    print("SECRET_MATERIAL_EXPOSED=FALSE")
    return 0 if cloud_health else 2

def build_support_report():
    config=load_config()
    runtime={}
    try:
        if STATUS_FILE.is_file(): runtime=json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        runtime={}

    activity=local_activity_snapshot("24h",limit=1,include_events=False)
    lease_summary=None
    budget_summary=None
    recent_receipts=[]
    try:
        with _ops_connect() as conn:
            row=conn.execute(
                "SELECT lease_json,valid_until_utc,CASE WHEN lease_token IS NULL THEN 0 ELSE 1 END AS signed FROM product_lease WHERE singleton=1"
            ).fetchone()
            if row:
                lease=json.loads(str(row["lease_json"]))
                lease_summary={
                    "plan_code":lease.get("plan_code"),
                    "usage_mode":lease.get("usage_mode"),
                    "period_kind":lease.get("period_kind"),
                    "valid_until_utc":row["valid_until_utc"],
                    "signed_token_present":bool(row["signed"]),
                }
            block=conn.execute(
                """SELECT budget_id,allocated_units,state,expires_at_utc
                     FROM local_budget_blocks
                    ORDER BY issued_at_utc DESC
                    LIMIT 1"""
            ).fetchone()
            if block:
                committed,reserved=_budget_counts(conn,block["budget_id"])
                allocated=int(block["allocated_units"] or 0)
                budget_summary={
                    "budget_id":str(block["budget_id"]),
                    "state":str(block["state"]),
                    "allocated_units":allocated,
                    "committed_units":committed,
                    "reserved_units":reserved,
                    "remaining_units":max(0,allocated-committed-reserved),
                    "expires_at_utc":block["expires_at_utc"],
                }
            recent_receipts=[
                str(x["receipt_sha256"])
                for x in conn.execute(
                    """SELECT DISTINCT receipt_sha256
                         FROM activity_events
                        WHERE receipt_sha256 IS NOT NULL
                          AND length(receipt_sha256)=64
                        ORDER BY event_id DESC
                        LIMIT 10"""
                ).fetchall()
            ]
    except Exception:
        lease_summary=None
        budget_summary=None
        recent_receipts=[]

    db_stat=None
    try:
        if OPERATIONS_DB_FILE.is_file():
            db_stat={
                "present":True,
                "bytes":int(OPERATIONS_DB_FILE.stat().st_size),
                "mode":oct(OPERATIONS_DB_FILE.stat().st_mode & 0o777)[2:],
            }
    except Exception:
        db_stat=None

    report={
        "schema":"hara.commander-support-report.v2",
        "platform":"LINUX",
        "computer":platform.node(),
        "device_id":config.get("HARA_DEVICE_ID"),
        "agent_version":AGENT_VERSION,
        "approval_mode":effective_approval_mode(config),
        "product_transport_mode":transport_mode(config),
        "operator_session_active":operator_session_active(),
        "last_successful_heartbeat_at_utc":runtime.get("last_successful_heartbeat_at_utc"),
        "last_runtime_error_code":runtime.get("last_runtime_error_code"),
        "last_runtime_error_at_utc":runtime.get("last_runtime_error_at_utc"),
        "activity_24h":{
            "summary":activity.get("summary") or {},
            "slo":activity.get("slo") or {},
            "top_errors":((activity.get("diagnostics") or {}).get("top_errors") or []),
        },
        "product_lease":lease_summary,
        "local_budget":budget_summary,
        "operations_db":db_stat,
        "recent_receipt_sha256":recent_receipts,
        "privacy":{
            "secret_material_exposed":False,
            "customer_content_included":False,
            "command_content_included":False,
            "payload_content_included":False,
            "result_content_included":False,
        },
    }
    return report

def commander_support():
    report=build_support_report()
    print(json.dumps(report,sort_keys=True,separators=(",",":"),ensure_ascii=False))
    return 0

def authorize_local_tunnel():
    config=load_config()
    code=getpass.getpass("Código de autorização do Commander: ").strip()
    if not code: raise RuntimeError("DEVICE_AUTHORIZATION_CODE_REQUIRED")
    payload=refresh_product_lease(config,authorization_code=code,requested_transport="LOCAL_TUNNEL")
    lease=payload.get("product_lease") or {}
    usage_sync=payload.get("usage_sync") or {}
    if usage_sync.get("accepted") is True:
        _local_meta_set("local_metering_last_sync_at_utc",str(usage_sync.get("synced_at_utc") or utcnow()))
        _local_meta_set("local_metering_last_event","LEASE_AUTHORIZATION")
    _set_config_value("HARA_COMMANDER_TRANSPORT_MODE","LOCAL_TUNNEL")
    print("HARA_COMMANDER_LOCAL_TUNNEL_AUTHORIZED=PASS")
    print("AUTHORIZATION_VALID_UNTIL_UTC="+str(lease.get("valid_until_utc") or ""))
    subprocess.run(["systemctl","--user","restart","hara-commander-agent.service"],check=False)
    print("AGENT_RESTART_REQUESTED=TRUE")
    return 0

def _tunnel_client_binary():
    bundled=DATA_DIR/"tunnel-client"
    if bundled.is_file() and os.access(bundled,os.X_OK):
        return str(bundled)
    return shutil.which("tunnel-client")

def _tunnel_runtime_env():
    env=os.environ.copy()
    if TUNNEL_ENV_FILE.is_file():
        mode=stat.S_IMODE(TUNNEL_ENV_FILE.stat().st_mode)
        if mode & 0o077:
            raise RuntimeError("OPENAI_TUNNEL_ENV_PERMISSIONS_INVALID")
        for raw in TUNNEL_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if raw.startswith("CONTROL_PLANE_API_KEY="):
                value=raw.split("=",1)[1].strip()
                if not re.fullmatch(r"[A-Za-z0-9_.-]{20,512}",value):
                    raise RuntimeError("OPENAI_TUNNEL_API_KEY_INVALID")
                env["CONTROL_PLANE_API_KEY"]=value
                break
    if not env.get("CONTROL_PLANE_API_KEY"):
        raise RuntimeError("OPENAI_TUNNEL_API_KEY_MISSING")
    return env

def _openai_tunnel_doctor(capture=False):
    binary=_tunnel_client_binary()
    if not binary:
        return 12,None
    try:
        env=_tunnel_runtime_env()
    except Exception:
        return 13,None
    kwargs={"env":env,"check":False,"timeout":30}
    if capture:
        kwargs.update({"stdout":subprocess.PIPE,"stderr":subprocess.STDOUT,"text":True})
    result=subprocess.run([binary,"doctor","--profile",TUNNEL_PROFILE,"--explain"],**kwargs)
    return int(result.returncode),getattr(result,"stdout",None)

def configure_openai_tunnel():
    binary=_tunnel_client_binary()
    if not binary:
        print("HARA_COMMANDER_TUNNEL_CLIENT=MISSING")
        print("OPENAI_TUNNEL_DOCS=https://developers.openai.com/api/docs/guides/secure-mcp-tunnels")
        return 12
    tunnel_id=input("OpenAI tunnel_id: ").strip()
    api_key=getpass.getpass("OpenAI tunnel runtime API key: ").strip()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]{16,180}",tunnel_id):
        raise RuntimeError("OPENAI_TUNNEL_ID_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{20,512}",api_key):
        raise RuntimeError("OPENAI_TUNNEL_API_KEY_INVALID")
    if any(ch.isspace() for ch in binary): raise RuntimeError("OPENAI_TUNNEL_BINARY_PATH_UNSAFE")
    TUNNEL_ENV_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    TUNNEL_ENV_FILE.write_text("CONTROL_PLANE_API_KEY="+api_key+"\n",encoding="utf-8")
    os.chmod(TUNNEL_ENV_FILE,0o600)
    env=os.environ.copy(); env["CONTROL_PLANE_API_KEY"]=api_key
    mcp_command=shlex.quote(str(Path.home()/".local/bin/hara-commander"))+" mcp"
    subprocess.run([
        binary,"init","--sample","sample_mcp_stdio_local",
        "--profile",TUNNEL_PROFILE,"--tunnel-id",tunnel_id,
        "--health-listen-addr","127.0.0.1:0",
        "--mcp-command",mcp_command,
    ],env=env,check=True)
    TUNNEL_UNIT_FILE.parent.mkdir(parents=True,exist_ok=True)
    TUNNEL_UNIT_FILE.write_text(
        "[Unit]\nDescription=H.A.R.A. Commander OpenAI Secure MCP Tunnel\nAfter=network-online.target\n\n"
        "[Service]\nType=simple\nEnvironmentFile=%h/.config/hara-commander/openai-tunnel.env\n"
        f"ExecStart={binary} run --profile {TUNNEL_PROFILE}\nRestart=on-failure\nRestartSec=15\n\n"
        "[Install]\nWantedBy=default.target\n",encoding="utf-8")
    _set_config_value("HARA_COMMANDER_TRANSPORT_MODE","LOCAL_TUNNEL")
    subprocess.run(["systemctl","--user","restart","hara-commander-agent.service"],check=False)
    subprocess.run(["systemctl","--user","daemon-reload"],check=False)
    subprocess.run(["systemctl","--user","enable","--now","hara-commander-openai-tunnel.service"],check=False)
    print("HARA_COMMANDER_OPENAI_TUNNEL_CONFIGURED=PASS")
    print("HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL")
    print("NEXT_STEP=Generate a 6-hour authorization code in commander.haralabs.com.br and run hara-commander authorize")
    return 0

def openai_tunnel_status():
    rc,_=_openai_tunnel_doctor(capture=False)
    return rc

def main():
    if "--version" in sys.argv:
        print(AGENT_VERSION); return
    if "--self-test" in sys.argv:
        self_test(); return
    if len(sys.argv)>1 and sys.argv[1]=="mcp":
        run_local_mcp_stdio(); return
    if len(sys.argv)>1 and sys.argv[1]=="doctor":
        raise SystemExit(commander_doctor())
    if len(sys.argv)>1 and sys.argv[1]=="support":
        raise SystemExit(commander_support())
    if len(sys.argv)>1 and sys.argv[1]=="authorize":
        raise SystemExit(authorize_local_tunnel())
    if len(sys.argv)>1 and sys.argv[1]=="transport-mode":
        if len(sys.argv)==2:
            print("HARA_COMMANDER_TRANSPORT_MODE="+transport_mode()); return
        if len(sys.argv)==3:
            set_transport_mode(sys.argv[2]); return
        raise SystemExit(64)
    if len(sys.argv)>2 and sys.argv[1]=="tunnel" and sys.argv[2]=="configure":
        raise SystemExit(configure_openai_tunnel())
    if len(sys.argv)>2 and sys.argv[1]=="tunnel" and sys.argv[2]=="status":
        raise SystemExit(openai_tunnel_status())
    if "--session-start" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="start"):
        start_operator_console(); return
    if len(sys.argv)>1 and sys.argv[1]=="approval-mode":
        if len(sys.argv)==2:
            print("HARA_COMMANDER_APPROVAL_MODE="+load_config().get("HARA_COMMANDER_APPROVAL_MODE","ASK_EVERY_ACTION")); return
        if len(sys.argv)==3:
            set_approval_mode(sys.argv[2]); return
        raise SystemExit(64)
    if "--session-status" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="status"):
        session_status(); return
    if "--session-stop" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="stop"):
        stop_operator_session(); return
    if len(sys.argv) > 1 and sys.argv[1] in {"help", "--help", "-h"}:
        print("Usage: hara-commander [start|status|stop|mcp|authorize|tunnel configure|tunnel status|doctor|support|transport-mode [local-tunnel|relay]|approval-mode [ask|session|always]|help]")
        return
    if len(sys.argv) > 1:
        print("HARA_COMMANDER_UNKNOWN_COMMAND=" + str(sys.argv[1]), file=sys.stderr)
        print("Usage: hara-commander [start|status|stop|mcp|authorize|tunnel configure|tunnel status|doctor|support|transport-mode [local-tunnel|relay]|approval-mode [ask|session|always]|help]", file=sys.stderr)
        raise SystemExit(64)
    config=load_config()
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    local_portal_server=start_local_portal_server(config)
    if not try_write_runtime_status(started_at=utcnow(), error_code=None, error_at=None):
        raise RuntimeError("RUNTIME_STATUS_STARTUP_WRITE_FAILED")
    if transport_mode(config)=="LOCAL_TUNNEL":
        append_console_event("AGENT_LOCAL_TUNNEL",state="CONTROL_ONLY",action_summary="cloud_polling=disabled")
        while True:
            time.sleep(60)
    last_heartbeat=0.0
    last_product_lease=0.0
    poll_hot_until=time.monotonic()+CALL_POLL_STARTUP_HOT_SECONDS
    last_error_code=None
    last_error_write=0.0
    rate_limit_backoff_seconds=0
    rate_limit_backoff_until=0.0
    was_authorized=False
    persistent=effective_approval_mode(config)=="PERSISTENT_TRUSTED"
    if not operator_session_active() and not persistent:
        mark_device_offline(config)
        append_console_event("AGENT_INERT", state="LOCAL_SESSION_REQUIRED")
    elif persistent:
        append_console_event("AGENT_ONLINE",state="PERSISTENT_TRUSTED")
    while True:
        now=time.monotonic()
        persistent=effective_approval_mode(config)=="PERSISTENT_TRUSTED"
        authorized=persistent or operator_session_active()
        if not authorized:
            if was_authorized:
                killed=cleanup_process_sessions()
                if killed: append_console_event("PROCESS_REVOKE",state="KILLED",action_summary=f"managed_processes={killed}")
            was_authorized=False
            time.sleep(1)
            continue
        if not was_authorized:
            last_heartbeat=0.0
            poll_hot_until=now+CALL_POLL_STARTUP_HOT_SECONDS
            append_console_event("AGENT_ONLINE",state="PERSISTENT_TRUSTED" if persistent else "AUTHORIZED")
            was_authorized=True
        if now < rate_limit_backoff_until:
            time.sleep(min(5.0, max(0.1, rate_limit_backoff_until-now)))
            continue
        try:
            if now-last_heartbeat>=HEARTBEAT_SECONDS:
                post_json(config["HARA_COMMANDER_URL"]+"/api/device/heartbeat",config["HARA_DEVICE_TOKEN"],{
                    "device_id":config["HARA_DEVICE_ID"],"architecture":config["HARA_DEVICE_ARCH"],"agent_version":AGENT_VERSION,
                    "approval_mode":effective_approval_mode(config),
                    "activity_snapshots":local_activity_heartbeat_snapshot(),
                })
                last_heartbeat=now
                last_error_code=None
                try_write_runtime_status(heartbeat_at=utcnow(),error_code=None,error_at=None)
            if now-last_product_lease>=PRODUCT_LEASE_REFRESH_SECONDS:
                try:
                    refresh_product_lease(config)
                    last_product_lease=now
                except Exception as exc:
                    append_console_event(
                        "PRODUCT_LEASE_DEGRADED",
                        state="DEGRADED",
                        error_code=safe_error_code(exc),
                    )
            call=post_json(config["HARA_COMMANDER_URL"]+"/api/device/calls/next",config["HARA_DEVICE_TOKEN"],{})
            if call:
                poll_hot_until=time.monotonic()+CALL_POLL_HOT_WINDOW_SECONDS
                execute_call(config,call)
            rate_limit_backoff_seconds=0
            rate_limit_backoff_until=0.0
        except Exception as exc:
            code=safe_error_code(exc)
            if code == "HTTP_429":
                rate_limit_backoff_seconds = min(
                    RATE_LIMIT_BACKOFF_MAX_SECONDS,
                    RATE_LIMIT_BACKOFF_INITIAL_SECONDS if rate_limit_backoff_seconds <= 0
                    else rate_limit_backoff_seconds * 2,
                )
                rate_limit_backoff_until=time.monotonic()+rate_limit_backoff_seconds
                poll_hot_until=0.0
                append_console_event(
                    "TRANSPORT_BACKOFF",
                    state="DEGRADED",
                    error_code=code,
                    action_summary=f"retry_after_seconds={rate_limit_backoff_seconds}",
                )
            if code != last_error_code or now-last_error_write>=60:
                try_write_runtime_status(error_code=code,error_at=utcnow())
                last_error_code=code
                last_error_write=now
        sleep_seconds=CALL_POLL_HOT_SECONDS if time.monotonic()<poll_hot_until else CALL_POLL_IDLE_SECONDS
        time.sleep(sleep_seconds)

if __name__=="__main__":
    main()
