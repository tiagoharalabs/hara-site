#!/usr/bin/env python3
import base64
import codecs
import contextlib
import hashlib
import hmac
import json
import getpass
import subprocess
import fnmatch
import difflib
import errno
import fcntl
import shutil
import os
import platform
import pwd
import pty
import re
import select
import shlex
import signal
import sqlite3
import stat
import sys
import termios
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
MAX_PREIMAGE_ENTRIES = 4096
MAX_PREIMAGE_STORE_BYTES = 256 * 1024 * 1024
PREIMAGE_CUSTODY_LOCK = threading.RLock()
FILE_MUTATION_THREAD_LOCK = threading.RLock()
FILE_MUTATION_LOCK_WAIT_SECONDS = 5.0
SESSION_MAX_SECONDS = 12 * 60 * 60
PRODUCT_LEASE_REFRESH_SECONDS = 4 * 60 * 60
LOCAL_METERING_MIN_INTERVAL_SECONDS = 60 * 60
AGENT_TELEMETRY_INTERVAL_SECONDS = 60 * 60
TRANSPORT_MODES = {"OUTBOUND_RELAY","LOCAL_TUNNEL"}
TUNNEL_PROFILE = "hara-commander"
TUNNEL_ENV_FILE = CONFIG_FILE.parent / "openai-tunnel.env"
TUNNEL_PROFILE_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "tunnel-client/hara-commander.yaml"
TUNNEL_UNIT_FILE = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config"))) / "systemd/user/hara-commander-openai-tunnel.service"
HEARTBEAT_SECONDS = 60
CALL_POLL_HOT_SECONDS = 2
CALL_POLL_IDLE_SECONDS = 10
CALL_POLL_IMMEDIATE_BATCH = 8
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
PROCESS_RESULT_TOMBSTONES = {}
PROCESS_ADMISSION_LOCK = threading.RLock()
PROCESS_STARTING = 0
MAX_PROCESS_LINES = 5000
MAX_PROCESS_LINE_CHARS = 8192
MAX_PROCESS_BUFFER_CHARS = 2 * 1024 * 1024
MAX_PROCESS_PAGE_JSON_BYTES = 60 * 1024
MAX_PROCESS_ACTIVE_SESSIONS = 16
MAX_PROCESS_RETAINED_SESSIONS = 48
PROCESS_IDLE_REVIEW_SECONDS = 30 * 60
PROCESS_FINISHED_RETENTION_SECONDS = 60 * 60
MAX_PROCESS_ONESHOT_RESULTS = 8
MAX_PROCESS_RESULT_TOMBSTONES = 128
PROCESS_RESULT_TOMBSTONE_SECONDS = 24 * 60 * 60
COMPLETION_RESULT_MAX_BYTES = 240 * 1024
COMPLETION_OUTBOX_MAX_PENDING = 256
# The server's normal claim TTL is 50s and async approval is at most 900s.
# ACKED rows keep only a tombstone for an hour; unresolved results are held
# within the pending cap for reconciliation instead of silently discarded.
COMPLETION_OUTBOX_ACK_RETENTION_SECONDS = 60 * 60

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
      CREATE TABLE IF NOT EXISTS completion_outbox (
        call_id TEXT PRIMARY KEY,
        request_id TEXT NOT NULL,
        tool_id TEXT NOT NULL,
        input_sha256 TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('INTENT','READY','ACKED')),
        body_json TEXT,
        created_epoch INTEGER NOT NULL,
        updated_epoch INTEGER NOT NULL,
        acked_epoch INTEGER
      );
      CREATE INDEX IF NOT EXISTS idx_completion_outbox_pending
        ON completion_outbox(status, updated_epoch);
    """)
    lease_columns={row["name"] for row in conn.execute("PRAGMA table_info(product_lease)")}
    if "lease_token" not in lease_columns:
        conn.execute("ALTER TABLE product_lease ADD COLUMN lease_token TEXT")
        conn.commit()
    outbox_columns={row["name"] for row in conn.execute("PRAGMA table_info(completion_outbox)")}
    for name,definition in (("quarantined_epoch","INTEGER"),("retry_after_epoch","INTEGER NOT NULL DEFAULT 0"),
                            ("attempt_count","INTEGER NOT NULL DEFAULT 0"),("last_error_code","TEXT")):
        if name not in outbox_columns:
            try:
                conn.execute(f"ALTER TABLE completion_outbox ADD COLUMN {name} {definition}")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower(): raise
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

@contextlib.contextmanager
def _history_activity_lock():
    """Cross-process advisory lock on the existing owner-controlled data dir.

    No lock file can accidentally be created root-owned by sudo.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor=os.open(str(DATA_DIR),os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor,fcntl.LOCK_UN)
        os.close(descriptor)


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
    "EDIT_MATCH_AMBIGUOUS","PROCESS_SESSION_EXITED","PROCESS_SESSION_NOT_FOUND","PROCESS_RESULT_EXPIRED",
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

def _agent_telemetry_prepare_queue(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS agent_telemetry_outbox ("
        "event_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, created_at_utc TEXT NOT NULL)"
    )

def agent_telemetry_enqueue(config,event_type,session_id,session_started_monotonic):
    """Persist metadata-only presence before any external network attempt."""
    event=str(event_type or "").strip().upper()
    if event not in {"AGENT_START","AGENT_HEARTBEAT","AGENT_STOP"}:
        raise ValueError("AGENT_TELEMETRY_EVENT_INVALID")
    if transport_mode(config)!="LOCAL_TUNNEL":
        return None
    event_id="HARA-AGENT-EVENT-"+uuid.uuid4().hex
    payload={
        "schema":"hara.commander-agent-telemetry.v1",
        "event_id":event_id,
        "event_type":event,
        "session_id":str(session_id),
        "event_at_utc":utcnow(),
        "session_duration_seconds":max(0,int(time.monotonic()-session_started_monotonic)),
        "agent_version":AGENT_VERSION,
        "transport_mode":"LOCAL_TUNNEL",
        "usage_report":local_usage_report(config),
        "metadata_only":True,
        "customer_content_included":False,
    }
    with _ops_connect() as conn:
        _agent_telemetry_prepare_queue(conn)
        conn.execute(
            "INSERT OR IGNORE INTO agent_telemetry_outbox(event_id,payload_json,created_at_utc) VALUES(?,?,?)",
            (event_id,json.dumps(payload,separators=(",",":"),sort_keys=True),utcnow()),
        )
        conn.commit()
    return event_id

def agent_telemetry_flush(config,limit=6):
    """Best-effort bounded upload; pending events survive outages and restarts."""
    if transport_mode(config)!="LOCAL_TUNNEL":
        return {"accepted":0,"pending":0}
    with _ops_connect() as conn:
        _agent_telemetry_prepare_queue(conn)
        rows=conn.execute(
            "SELECT event_id,payload_json FROM agent_telemetry_outbox ORDER BY created_at_utc,event_id LIMIT ?",
            (max(1,min(32,int(limit))),),
        ).fetchall()
    sent=0
    for row in rows:
        try:
            payload=json.loads(row["payload_json"])
            response=post_json(
                config["HARA_COMMANDER_URL"]+"/api/device/metering-sync",
                config["HARA_DEVICE_TOKEN"],payload,timeout=8,
            ) or {}
            accepted=response.get("accepted") is True
            early=str(response.get("code") or "")=="LOCAL_AGENT_HEARTBEAT_EARLY"
            if not accepted and not early:
                break
            with _ops_connect() as conn:
                conn.execute("DELETE FROM agent_telemetry_outbox WHERE event_id=?",(row["event_id"],))
                conn.commit()
            sent+=int(accepted)
            append_console_event(
                "AGENT_TELEMETRY_SYNC",state="SYNCED" if accepted else "THROTTLED",
                action_summary="event="+str(payload.get("event_type")),
            )
        except Exception as exc:
            append_console_event(
                "AGENT_TELEMETRY_DEGRADED",state="DEGRADED",
                error_code=safe_error_code(exc),action_summary="event_upload_retry_later",
            )
            break
    with _ops_connect() as conn:
        pending=int(conn.execute("SELECT COUNT(*) FROM agent_telemetry_outbox").fetchone()[0])
    return {"accepted":sent,"pending":pending}

def agent_telemetry_emit(config,event_type,session_id,session_started_monotonic):
    try:
        agent_telemetry_enqueue(config,event_type,session_id,session_started_monotonic)
        return agent_telemetry_flush(config)
    except Exception as exc:
        append_console_event(
            "AGENT_TELEMETRY_DEGRADED",state="DEGRADED",
            error_code=safe_error_code(exc),action_summary="event="+str(event_type),
        )
        return {"accepted":0,"degraded":True}

def run_local_tunnel_agent_telemetry(config):
    """One service lifecycle: START, at most one scheduled hourly event, STOP."""
    session_id="HARA-AGENT-SESSION-"+uuid.uuid4().hex
    started_at=time.monotonic()
    stop_requested=threading.Event()
    old_term_handler=signal.getsignal(signal.SIGTERM)
    def _handle_stop(_signum,_frame):
        stop_requested.set()
    signal.signal(signal.SIGTERM,_handle_stop)
    try:
        agent_telemetry_emit(config,"AGENT_START",session_id,started_at)
        last_heartbeat=time.monotonic()
        while not stop_requested.wait(60):
            now=time.monotonic()
            if now-last_heartbeat>=AGENT_TELEMETRY_INTERVAL_SECONDS:
                agent_telemetry_emit(config,"AGENT_HEARTBEAT",session_id,started_at)
                last_heartbeat=now
    finally:
        agent_telemetry_emit(config,"AGENT_STOP",session_id,started_at)
        signal.signal(signal.SIGTERM,old_term_handler)

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
    with _history_activity_lock():
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

def _checked_path_text(path_value):
    text=str(path_value or "")
    if not text or len(text)>4096 or any(ord(ch)<32 or ord(ch)==127 for ch in text):
        raise ValueError("PATH_VALUE_INVALID")
    return text

def _lexical_path(path_value):
    raw=Path(_checked_path_text(path_value)).expanduser()
    return Path(os.path.abspath(os.fspath(raw)))

@contextlib.contextmanager
def _file_mutation_guard(*paths):
    # A directory inode is shared by local Agent processes, regardless of
    # XDG_DATA_HOME or spelling through a symlinked parent. Hold its flock
    # through the CAS check, preimage, mutation and receipt hash. Two-parent
    # operations acquire directory locks in inode order to avoid deadlock.
    with FILE_MUTATION_THREAD_LOCK:
        descriptors=[]
        canonical_paths=[]
        try:
            seen=set()
            for path in paths:
                parent=Path(path).parent
                try:
                    resolved=parent.resolve(strict=True)
                except (OSError,RuntimeError) as exc:
                    raise ValueError("PARENT_DIRECTORY_NOT_FOUND") from exc
                if not resolved.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
                canonical_paths.append(resolved/Path(path).name)
                flags=os.O_RDONLY|os.O_DIRECTORY|getattr(os,"O_CLOEXEC",0)|getattr(os,"O_NOFOLLOW",0)
                try:
                    fd=os.open(str(resolved),flags)
                except OSError as exc:
                    raise ValueError("FILE_MUTATION_LOCK_UNAVAILABLE") from exc
                st=os.fstat(fd)
                key=(int(st.st_dev),int(st.st_ino))
                if key in seen:
                    os.close(fd)
                else:
                    seen.add(key); descriptors.append((key,fd))
            deadline=time.monotonic()+max(0.0,float(FILE_MUTATION_LOCK_WAIT_SECONDS))
            for _,fd in sorted(descriptors):
                while True:
                    try:
                        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        break
                    except OSError as exc:
                        if exc.errno==errno.EINTR: continue
                        if exc.errno not in {errno.EAGAIN,errno.EWOULDBLOCK}:
                            raise ValueError("FILE_MUTATION_LOCK_UNAVAILABLE") from exc
                        remaining=deadline-time.monotonic()
                        if remaining<=0: raise ValueError("FILE_MUTATION_BUSY")
                        time.sleep(min(0.05,remaining))
            # Use the same resolved parent that was locked, even if the
            # caller reached it through an alias that changes later.
            yield tuple(canonical_paths)
        finally:
            # Closing these descriptions releases flock even after a crash.
            # Never turn a completed mutation into a false pre-write failure.
            for _,fd in descriptors:
                try: os.close(fd)
                except OSError: pass

def _leaf_kind(path):
    try:
        mode=path.lstat().st_mode
    except FileNotFoundError:
        return "missing"
    if stat.S_ISLNK(mode): return "symlink"
    if stat.S_ISDIR(mode): return "directory"
    if stat.S_ISREG(mode): return "file"
    return "other"

def _reject_mutation_symlink(path):
    if _leaf_kind(path)=="symlink":
        raise ValueError("SYMLINK_MUTATION_DENIED")

def _validate_expected_sha256(value):
    if value is None: return None
    text=str(value).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}",text):
        raise ValueError("FILE_PRECONDITION_INVALID")
    return text

def _read_regular_nofollow(path,max_bytes):
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
    try:
        fd=os.open(str(path),flags)
    except OSError as exc:
        if exc.errno==errno.ELOOP: raise ValueError("SYMLINK_MUTATION_DENIED")
        raise
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode): raise ValueError("PATH_NOT_FILE")
        chunks=[]; total=0
        while True:
            chunk=os.read(fd,1024*1024)
            if not chunk: break
            total+=len(chunk)
            if total>max_bytes: raise ValueError("HASH_FILE_TOO_LARGE")
            chunks.append(chunk)
        return b"".join(chunks),st
    finally:
        os.close(fd)

def _sha256_regular_file(path,max_bytes=128*1024*1024):
    data,_=_read_regular_nofollow(path,max_bytes)
    return hashlib.sha256(data).hexdigest(),len(data)

def _enforce_file_precondition(path,expected_sha256):
    expected=_validate_expected_sha256(expected_sha256)
    if expected is None: return None
    if _leaf_kind(path)!="file": raise ValueError("FILE_PRECONDITION_FAILED")
    actual,_=_sha256_regular_file(path,max_bytes=2*1024*1024)
    if not hmac.compare_digest(actual,expected): raise ValueError("FILE_PRECONDITION_FAILED")
    return actual


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
    path=_lexical_path(path)
    if _leaf_kind(path)=="missing": return None
    _reject_mutation_symlink(path)
    if _leaf_kind(path)!="file": return None
    data,st=_read_regular_nofollow(path,2*1024*1024)
    sha=hashlib.sha256(data).hexdigest()
    preimage_id="HARA-PREIMAGE-"+uuid.uuid4().hex
    with PREIMAGE_CUSTODY_LOCK:
        PREIMAGE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
        # Preserve existing rollback history. Do not auto-delete old snapshots;
        # reject new file mutations before they exhaust customer disk capacity.
        existing=list(PREIMAGE_DIR.glob("HARA-PREIMAGE-*.bin"))
        if len(existing)>=MAX_PREIMAGE_ENTRIES:
            raise ValueError("PREIMAGE_CAPACITY_EXCEEDED")
        current_bytes=0
        for item in existing:
            if item.is_symlink() or not item.is_file():
                raise ValueError("PREIMAGE_STORAGE_UNSAFE")
            current_bytes+=item.stat().st_size
            if current_bytes+len(data)>MAX_PREIMAGE_STORE_BYTES:
                raise ValueError("PREIMAGE_CAPACITY_EXCEEDED")
        meta_path,data_path=_preimage_paths(preimage_id)
        data_tmp=data_path.with_suffix(".tmp")
        data_tmp.write_bytes(data); os.chmod(data_tmp,0o600); os.replace(data_tmp,data_path); os.chmod(data_path,0o600)
        meta={
            "schema":"hara.commander-file-preimage.v1",
            "preimage_id":preimage_id,"original_path":str(path),"sha256":sha,"bytes":len(data),
            "mode":int(st.st_mode & 0o777),"device":int(st.st_dev),"inode":int(st.st_ino),
            "mtime_ns":int(st.st_mtime_ns),"size_bytes":int(st.st_size),
            "source_call_id":str(call_id or "")[:180],"source_tool":str(source_tool or "")[:120] or None,
            "created_at_utc":utcnow(),
        }
        meta_tmp=meta_path.with_suffix(".tmp")
        meta_tmp.write_text(json.dumps(meta,sort_keys=True,separators=(",",":")),encoding="utf-8"); os.chmod(meta_tmp,0o600); os.replace(meta_tmp,meta_path); os.chmod(meta_path,0o600)
        return meta

def _discard_preimage(preimage):
    if not preimage: return
    try:
        meta_path,data_path=_preimage_paths(preimage.get("preimage_id"))
        meta_path.unlink(missing_ok=True); data_path.unlink(missing_ok=True)
    except Exception:
        pass

def _assert_path_matches_preimage(path,preimage):
    if not preimage: raise ValueError("PREIMAGE_REQUIRED")
    _reject_mutation_symlink(path)
    try: st=path.lstat()
    except FileNotFoundError: raise ValueError("FILE_PRECONDITION_FAILED")
    if not stat.S_ISREG(st.st_mode): raise ValueError("FILE_PRECONDITION_FAILED")
    for key,observed in (("device",st.st_dev),("inode",st.st_ino),("size_bytes",st.st_size),("mtime_ns",st.st_mtime_ns)):
        expected=preimage.get(key)
        if expected is not None and int(expected)!=int(observed): raise ValueError("FILE_PRECONDITION_FAILED")
    sha,_=_sha256_regular_file(path,max_bytes=2*1024*1024)
    if not hmac.compare_digest(sha,str(preimage.get("sha256") or "")): raise ValueError("FILE_PRECONDITION_FAILED")
    return sha


def filesystem_preimages_list(limit=50,path_filter=None):
    PREIMAGE_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    wanted=None
    if path_filter:
        wanted=str(Path(_checked_path_text(path_filter)).expanduser().resolve(strict=False))
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
    target=_lexical_path(str(meta["original_path"]))
    with _file_mutation_guard(target) as (locked_target,):
        return _filesystem_rollback_locked(call,preimage_id,meta,data,locked_target)

def _filesystem_rollback_locked(call,preimage_id,meta,data,target):
    _reject_mutation_symlink(target)
    if _leaf_kind(target) not in {"missing","file"}: raise ValueError("ROLLBACK_TARGET_NOT_FILE")
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
    # A command may print arbitrary binary-like output without line breaks.
    # Keep both the incomplete line and retained history bounded in RAM.
    combined=str(session.get("partial",""))+str(text)
    parts=combined.split("\n")
    partial=parts.pop() if parts else ""
    if len(partial)>MAX_PROCESS_LINE_CHARS:
        partial=partial[-MAX_PROCESS_LINE_CHARS:]
        session["truncated"]=True
    session["partial"]=partial

    history=session["lines"]
    total=session.get("_buffer_chars")
    if total is None:
        total=sum(len(line) for line in history)
    for line in parts:
        if len(line)>MAX_PROCESS_LINE_CHARS:
            line=line[-MAX_PROCESS_LINE_CHARS:]
            session["truncated"]=True
        history.append(line)
        total+=len(line)

    # Use bulk front eviction for line-count pressure, then enforce a byte-ish
    # character budget. Output is already decoded as text by _drain_process.
    excess=len(history)-MAX_PROCESS_LINES
    if excess>0:
        total-=sum(len(line) for line in history[:excess])
        del history[:excess]
        session["base_line"]+=excess
        session["truncated"]=True
    removed=0
    while total>MAX_PROCESS_BUFFER_CHARS and removed<len(history):
        total-=len(history[removed])
        removed+=1
    if removed:
        del history[:removed]
        session["base_line"]+=removed
        session["truncated"]=True
    session["_buffer_chars"]=max(0,total)
    session["cursor"]=max(session.get("cursor",0),session["base_line"])

def _append_process_bytes(session,data,final=False):
    # PTY read boundaries need not coincide with UTF-8 character boundaries.
    decoder=session.get("_output_decoder")
    if decoder is None:
        decoder=codecs.getincrementaldecoder("utf-8")("replace")
        session["_output_decoder"]=decoder
    decoded=decoder.decode(data,final=final)
    if decoded:
        _append_process_output(session,decoded)

def _drain_completed_process_output(session):
    """Consume buffered PTY output after waitpid and before closing the master.

    The master is nonblocking (set by process_start). A descendant could keep
    the slave fd open, so never wait for EOF indefinitely or retain unbounded
    data. _append_process_output applies the existing 2 MiB/5,000-line cap.
    """
    fd=int(session.get("fd",-1))
    if fd<0: return
    max_bytes=4*1024*1024
    deadline=time.monotonic()+0.25
    consumed=0
    while consumed<max_bytes and time.monotonic()<deadline:
        try:
            data=os.read(fd,min(65536,max_bytes-consumed))
        except InterruptedError:
            continue
        except BlockingIOError:
            break
        except OSError as exc:
            # A Linux PTY raises EIO when its last slave closes.
            if exc.errno in (errno.EIO,errno.EBADF): break
            session["truncated"]=True
            break
        if not data: break
        _append_process_bytes(session,data)
        consumed+=len(data)
    if consumed>=max_bytes or time.monotonic()>=deadline:
        # Mark potential loss rather than silently claim complete output.
        session["truncated"]=True


def _process_update_state(session):
    with session.get("_io_lock") or contextlib.nullcontext():
        if session.get("exit_code") is not None: return
        try:
            pid,status=os.waitpid(int(session["pid"]),os.WNOHANG)
        except ChildProcessError:
            pid=int(session["pid"]); status=0
        if pid:
            # waitpid reports process completion before PTY master bytes have
            # necessarily been consumed; never close the fd first.
            session["exit_code"]=os.waitstatus_to_exitcode(status) if hasattr(os,"waitstatus_to_exitcode") else 0
            session["finished_monotonic"]=time.monotonic()
            try:
                _drain_completed_process_output(session)
                _append_process_bytes(session,b"",final=True)
                if session.get("partial"):
                    _append_process_output(session,"\n")
            finally:
                try: os.close(int(session["fd"]))
                except OSError: pass
                session["fd"]=-1

def _drain_process(session,wait_ms=0):
    with session.get("_io_lock") or contextlib.nullcontext():
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
            _append_process_bytes(session,data)
            if time.monotonic()>=deadline: break
        _process_update_state(session)

def _collect_process_output(session):
    # At most MAX_PROCESS_ACTIVE_SESSIONS collectors exist. The same lock used
    # by foreground reads keeps PTY bytes, decoder state and close ordered.
    while session.get("exit_code") is None and not session.get("_collector_stop"):
        try:
            _drain_process(session,100)
        except Exception:
            with session["_io_lock"]:
                session["truncated"]=True
                session["collector_failed"]=True
            return
        # Avoid spinning if a live process closes stdout without exiting.
        time.sleep(0.01)

def _retire_process_session(sid,session,now):
    PROCESS_SESSIONS.pop(sid,None)
    if session.get("one_shot_result"):
        PROCESS_RESULT_TOMBSTONES[sid]=now
        if len(PROCESS_RESULT_TOMBSTONES)>MAX_PROCESS_RESULT_TOMBSTONES:
            oldest=min(PROCESS_RESULT_TOMBSTONES,key=PROCESS_RESULT_TOMBSTONES.get)
            PROCESS_RESULT_TOMBSTONES.pop(oldest,None)

def _prune_process_sessions():
    now=time.monotonic()
    for sid,retired in list(PROCESS_RESULT_TOMBSTONES.items()):
        if now-retired>=PROCESS_RESULT_TOMBSTONE_SECONDS:
            PROCESS_RESULT_TOMBSTONES.pop(sid,None)
    if len(PROCESS_RESULT_TOMBSTONES)>MAX_PROCESS_RESULT_TOMBSTONES:
        for sid,_ in sorted(PROCESS_RESULT_TOMBSTONES.items(),key=lambda pair:pair[1])[:len(PROCESS_RESULT_TOMBSTONES)-MAX_PROCESS_RESULT_TOMBSTONES]:
            PROCESS_RESULT_TOMBSTONES.pop(sid,None)
    for sid,session in list(PROCESS_SESSIONS.items()):
        if session.get("exit_code") is None:
            _process_update_state(session)
        if session.get("exit_code") is not None:
            completed=float(session.get("finished_monotonic",now))
            if now-completed>=PROCESS_FINISHED_RETENTION_SECONDS:
                _retire_process_session(sid,session,now)

    oneshots=sorted(
        ((sid,s) for sid,s in PROCESS_SESSIONS.items() if s.get("one_shot_result")),
        key=lambda pair:float(pair[1].get("finished_monotonic",now)),
    )
    for sid,session in oneshots[:max(0,len(oneshots)-MAX_PROCESS_ONESHOT_RESULTS)]:
        _retire_process_session(sid,session,now)

    # Process results remain available for a bounded period, but never allow
    # an unlimited number of finished sessions to pin their output in RAM.
    if len(PROCESS_SESSIONS)>=MAX_PROCESS_RETAINED_SESSIONS:
        finished=sorted(
            ((sid,s) for sid,s in PROCESS_SESSIONS.items() if s.get("exit_code") is not None),
            key=lambda pair:float(pair[1].get("finished_monotonic",0)),
        )
        for sid,session in finished:
            if len(PROCESS_SESSIONS)<MAX_PROCESS_RETAINED_SESSIONS: break
            _retire_process_session(sid,session,now)


def _process_get(session_id):
    _prune_process_sessions()
    sid=str(session_id or "")
    session=PROCESS_SESSIONS.get(sid)
    if not session:
        if sid in PROCESS_RESULT_TOMBSTONES: raise ValueError("PROCESS_RESULT_EXPIRED")
        raise ValueError("PROCESS_SESSION_NOT_FOUND")
    return session

def _process_capacity_warning(active):
    return active>=max(1,(MAX_PROCESS_ACTIVE_SESSIONS*3+3)//4)

def _process_output_payload(session,offset=None,length=200,wait_ms=0):
    _drain_process(session,wait_ms)
    with session.get("_io_lock") or contextlib.nullcontext():
        session["last_client_activity_at_utc"]=utcnow()
        session["last_client_activity_monotonic"]=time.monotonic()
        base=int(session.get("base_line",0)); lines=session.get("lines",[])
        start=int(session.get("cursor",base)) if offset is None else int(offset)
        truncated_before=start<base
        if start<base: start=base
        rel=max(0,start-base)
        selected=[]; page_bytes=0
        for line in lines[rel:rel+max(1,min(500,int(length)))]:
            encoded=len(json.dumps(line,ensure_ascii=False).encode("utf-8"))-2
            added=encoded+(2 if selected else 0)
            if selected and page_bytes+added>MAX_PROCESS_PAGE_JSON_BYTES: break
            selected.append(line); page_bytes+=added
        next_offset=start+len(selected)
        if offset is None: session["cursor"]=next_offset
        state="EXITED" if session.get("exit_code") is not None else "RUNNING"
        return {"session_id":session["session_id"],"pid":session["pid"],"state":state,"exit_code":session.get("exit_code"),"offset":start,"next_offset":next_offset,"base_line":base,"total_lines":base+len(lines),"text":"\n".join(selected),"partial":session.get("partial","")[:1000],"truncated_before":truncated_before,"buffer_truncated":bool(session.get("truncated")),"result_kind":"ONE_SHOT_RESULT" if session.get("one_shot_result") else "MANAGED_SESSION"}

def _abort_process_start(pid,fd,session=None):
    """Bound cleanup if admission succeeded but the caller cannot receive a session id."""
    if session is not None: session["_collector_stop"]=True
    try: os.killpg(int(pid),signal.SIGKILL)
    except OSError:
        try: os.kill(int(pid),signal.SIGKILL)
        except OSError: pass
    lock=session.get("_io_lock") if session is not None else contextlib.nullcontext()
    with lock:
        if session is not None: session["exit_code"]=-1
        current_fd=int(session.get("fd",fd)) if session is not None else int(fd)
        if current_fd>=0:
            try: os.close(current_fd)
            except OSError: pass
        if session is not None: session["fd"]=-1
    collector=session.get("_collector_thread") if session is not None else None
    if collector is not None and collector.is_alive(): collector.join(timeout=0.25)
    deadline=time.monotonic()+0.25
    while time.monotonic()<deadline:
        try: reaped,_=os.waitpid(int(pid),os.WNOHANG)
        except (ChildProcessError,OSError): break
        if reaped: break
        time.sleep(0.01)

def process_start(command,cwd=None,timeout_ms=1000,*,non_interactive=False,owner_request_id=None,owner_subject_id=None):
    global PROCESS_STARTING
    command=str(command or "")
    if not command or len(command)>4096 or "\x00" in command: raise ValueError("PROCESS_COMMAND_INVALID")
    work=Path(_checked_path_text(cwd)).expanduser().resolve(strict=True) if cwd else Path.home()
    if not work.is_dir(): raise ValueError("PROCESS_CWD_INVALID")
    with PROCESS_ADMISSION_LOCK:
        _prune_process_sessions()
        running=sum(s.get("exit_code") is None for s in PROCESS_SESSIONS.values())
        if running+PROCESS_STARTING>=MAX_PROCESS_ACTIVE_SESSIONS or len(PROCESS_SESSIONS)+PROCESS_STARTING>=MAX_PROCESS_RETAINED_SESSIONS:
            raise ValueError("PROCESS_SESSION_CAPACITY_EXCEEDED")
        PROCESS_STARTING+=1
    reserved=True; registered=False; pid=-1; fd=-1; session=None; sid=None
    try:
        pid,fd=pty.fork()
        if pid==0:
            try:
                os.chdir(work)
                child_env=os.environ.copy()
                if non_interactive:
                    # One-shot commands cannot answer pager prompts. Keep the
                    # interactive process.start environment untouched.
                    child_env.update(PAGER="cat",GIT_PAGER="cat",PSQL_PAGER="cat")
                os.execve("/bin/bash",["/bin/bash","-lc",command],child_env)
            except Exception:
                os._exit(127)
        os.set_blocking(fd,False)
        sid="HARA-PROC-"+uuid.uuid4().hex
        started_at=utcnow()
        session={"session_id":sid,"pid":pid,"fd":fd,"started_at_utc":started_at,
                 "last_client_activity_at_utc":started_at,"last_client_activity_monotonic":time.monotonic(),
                 "owner_request_id":str(owner_request_id or ""),"owner_subject_id":str(owner_subject_id or ""),
                 "non_interactive":bool(non_interactive),
                 "command_sha256":hashlib.sha256(command.encode()).hexdigest(),"cwd":str(work),"lines":[],"partial":"","base_line":0,"cursor":0,"truncated":False,"exit_code":None,"_io_lock":threading.RLock()}
        collector=threading.Thread(target=_collect_process_output,args=(session,),name="hara-process-output",daemon=True)
        session["_collector_thread"]=collector
        collector.start()
        with PROCESS_ADMISSION_LOCK:
            running=sum(s.get("exit_code") is None for s in PROCESS_SESSIONS.values())
            PROCESS_SESSIONS[sid]=session
            registered=True
            PROCESS_STARTING-=1
            reserved=False
            active=running+(session.get("exit_code") is None)
            capacity_warning=_process_capacity_warning(active) and not _process_capacity_warning(running)
        if capacity_warning:
            try:
                append_console_event("PROCESS_CAPACITY_WARNING",state="REVIEW_REQUIRED",
                                     action_summary=f"active={active};capacity={MAX_PROCESS_ACTIVE_SESSIONS}")
            except Exception as exc:
                session["capacity_warning_event_error_code"]=safe_error_code(exc)
        output=_process_output_payload(session,offset=None,length=200,wait_ms=timeout_ms)
        return {**output,"cwd":str(work),"command_sha256":session["command_sha256"],
                "command_preview":_redact_command_preview(command),"owner_request_id":session["owner_request_id"],
                "owner_subject_id":session["owner_subject_id"],"non_interactive":bool(non_interactive),
                "capacity_warning_event_error_code":session.get("capacity_warning_event_error_code")}
    except Exception:
        if registered:
            with PROCESS_ADMISSION_LOCK: PROCESS_SESSIONS.pop(sid,None)
        if pid>0: _abort_process_start(pid,fd,session)
        raise
    finally:
        if reserved:
            with PROCESS_ADMISSION_LOCK: PROCESS_STARTING-=1

def process_run(command,cwd=None,timeout_ms=3000,max_lines=200,*,owner_request_id=None,owner_subject_id=None):
    timeout_ms=max(100,min(10000,int(timeout_ms)))
    max_lines=max(1,min(500,int(max_lines)))
    started=process_start(command,cwd,0,non_interactive=True,
                          owner_request_id=owner_request_id,owner_subject_id=owner_subject_id)
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
    retain=next_offset<total or session.get("exit_code") is None
    if retain and session.get("exit_code") is not None:
        session["one_shot_result"]=True
    result={
        "run_id":sid,
        "session_id":sid if retain else None,
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
        "next_offset":next_offset,
        "base_line":base,
        "buffer_truncated":bool(output.get("buffer_truncated")),
        "output_truncated":bool(output.get("buffer_truncated")) or next_offset<total,
        "session_retained":bool(retain),
        "result_kind":"ONE_SHOT_RESULT" if session.get("one_shot_result") else "MANAGED_SESSION" if retain else None,
        "result_retention_deadline_utc":(datetime.now(timezone.utc)+timedelta(seconds=PROCESS_FINISHED_RETENTION_SECONDS)).isoformat() if session.get("one_shot_result") else None,
        "result_capacity_eviction_possible":bool(session.get("one_shot_result")),
        "termination_uncertain":bool(session.get("exit_code") is None),
    }
    if not retain: PROCESS_SESSIONS.pop(sid,None)
    return result

def process_sessions():
    _prune_process_sessions()
    items=[]
    now=time.monotonic()
    for sid,session in list(PROCESS_SESSIONS.items()):
        _drain_process(session,0)
        with session.get("_io_lock") or contextlib.nullcontext():
            running=session.get("exit_code") is None
            idle=max(0,int(now-float(session.get("last_client_activity_monotonic",now))))
            review=running and idle>=PROCESS_IDLE_REVIEW_SECONDS
            items.append({"session_id":sid,"pid":session["pid"],"state":"RUNNING" if running else "EXITED",
                          "exit_code":session.get("exit_code"),"started_at_utc":session["started_at_utc"],
                          "last_client_activity_at_utc":session.get("last_client_activity_at_utc"),
                          "idle_seconds":idle,"owner_review_required":review,
                          "blocking_reason":"NO_CLIENT_ACTIVITY" if review else None,
                          "owner_request_id":session.get("owner_request_id") or None,
                          "owner_subject_id":session.get("owner_subject_id") or None,
                          "capacity_warning_event_error_code":session.get("capacity_warning_event_error_code"),
                          "cwd":session["cwd"],"command_sha256":session["command_sha256"]})
    active=sum(item["state"]=="RUNNING" for item in items)
    return {"count":len(items),"active_count":active,"active_capacity":MAX_PROCESS_ACTIVE_SESSIONS,
            "capacity_warning":_process_capacity_warning(active),
            "idle_review_seconds":PROCESS_IDLE_REVIEW_SECONDS,"sessions":items}

def process_interact(session_id,input_text,timeout_ms=1000):
    session=_process_get(session_id)
    text=str(input_text or "")
    if len(text)>4096 or "\x00" in text: raise ValueError("PROCESS_INPUT_INVALID")
    data=(text+"\n").encode("utf-8")
    with session.get("_io_lock") or contextlib.nullcontext():
        _process_update_state(session)
        if session.get("exit_code") is not None or int(session.get("fd",-1))<0: raise ValueError("PROCESS_SESSION_EXITED")
        try:
            echo_mode="ENABLED" if termios.tcgetattr(int(session["fd"]))[3]&termios.ECHO else "DISABLED"
        except (OSError,ValueError,termios.error):
            echo_mode="UNKNOWN"
        input_bytes_sent=os.write(int(session["fd"]),data)
        session["last_client_activity_at_utc"]=utcnow()
        session["last_client_activity_monotonic"]=time.monotonic()
    output=_process_output_payload(session,offset=None,length=200,wait_ms=timeout_ms)
    more=output["state"]=="RUNNING" or output["next_offset"]<output["total_lines"]
    return {**output,"input_bytes_requested":len(data),"input_bytes_sent":input_bytes_sent,
            "input_write_complete":input_bytes_sent==len(data),"input_retry_safe":False,
            "pty_echo_mode_at_write":echo_mode,"output_semantics":"PTY_UNCLASSIFIED",
            "read_more_recommended":more,
            "continuation_tool":"read_process_output" if more else None}

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
    path=_lexical_path(path_value)
    _reject_mutation_symlink(path)
    existed=_leaf_kind(path)!="missing"
    if existed and _leaf_kind(path)!="directory": raise ValueError("PATH_EXISTS_NOT_DIRECTORY")
    path.mkdir(parents=bool(parents),exist_ok=True)
    return {"path":str(path.resolve()),"created":not existed,"parents":bool(parents)}

def filesystem_write(call,path_value,content,mode="rewrite",expected_sha256=None):
    with _file_mutation_guard(_lexical_path(path_value)) as (locked_path,):
        return _filesystem_write_locked(call,locked_path,content,mode,expected_sha256)

def _filesystem_write_locked(call,path_value,content,mode,expected_sha256):
    path=_lexical_path(path_value); _reject_mutation_symlink(path); kind=_leaf_kind(path)
    if kind not in {"missing","file"}: raise ValueError("PATH_NOT_FILE")
    data=str(content); encoded=data.encode("utf-8")
    if len(encoded)>65536: raise ValueError("WRITE_TOO_LARGE")
    expected=_validate_expected_sha256(expected_sha256)
    if expected is not None: _enforce_file_precondition(path,expected)
    preimage=_store_preimage(path,call.get("call_id") or "write","hara.files.write") if kind=="file" else None
    previous_sha=str(preimage.get("sha256") or "") if preimage else None
    if expected is not None and (not previous_sha or not hmac.compare_digest(previous_sha,expected)):
        _discard_preimage(preimage); raise ValueError("FILE_PRECONDITION_FAILED")
    if not path.parent.exists() or not path.parent.is_dir():
        _discard_preimage(preimage); raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    if preimage: _assert_path_matches_preimage(path,preimage)
    if mode=="append":
        flags=os.O_WRONLY|os.O_APPEND|getattr(os,"O_NOFOLLOW",0)
        try: fd=os.open(str(path),flags)
        except OSError as exc:
            if exc.errno==errno.ELOOP: raise ValueError("SYMLINK_MUTATION_DENIED")
            raise
        try: os.write(fd,encoded)
        finally: os.close(fd)
    elif mode=="rewrite":
        tmp=path.with_name("."+path.name+".hara-tmp-"+str(os.getpid()))
        tmp.write_text(data,encoding="utf-8"); os.replace(tmp,path)
    else:
        _discard_preimage(preimage); raise ValueError("WRITE_MODE_INVALID")
    current_sha,current_bytes=_sha256_regular_file(path,max_bytes=2*1024*1024)
    return {"path":str(path),"mode":mode,"bytes_written":len(encoded),"size_bytes":current_bytes,"previous_sha256":previous_sha,"sha256":current_sha,"precondition_checked":expected is not None,"preimage_id":preimage.get("preimage_id") if preimage else None,"preimage_sha256":preimage.get("sha256") if preimage else None}

def filesystem_edit(call,path_value,old_text,new_text,replace_all=False,expected_sha256=None):
    with _file_mutation_guard(_lexical_path(path_value)) as (locked_path,):
        return _filesystem_edit_locked(call,locked_path,old_text,new_text,replace_all,expected_sha256)

def _filesystem_edit_locked(call,path_value,old_text,new_text,replace_all,expected_sha256):
    path=_lexical_path(path_value); _reject_mutation_symlink(path)
    if _leaf_kind(path)!="file": raise ValueError("PATH_NOT_FILE")
    if path.stat().st_size>2*1024*1024: raise ValueError("FILE_TOO_LARGE")
    expected=_validate_expected_sha256(expected_sha256)
    if expected is not None: _enforce_file_precondition(path,expected)
    preimage=_store_preimage(path,call.get("call_id") or "edit","hara.files.edit")
    previous_sha=str(preimage.get("sha256") or "")
    if expected is not None and not hmac.compare_digest(previous_sha,expected):
        _discard_preimage(preimage); raise ValueError("FILE_PRECONDITION_FAILED")
    _,snapshot=_load_preimage(preimage["preimage_id"])
    try: text=snapshot.decode("utf-8",errors="strict")
    except UnicodeDecodeError: _discard_preimage(preimage); raise ValueError("BINARY_FILE_DENIED")
    count=text.count(old_text)
    if count==0: _discard_preimage(preimage); raise ValueError("EDIT_MATCH_NOT_FOUND")
    if not replace_all and count!=1: _discard_preimage(preimage); raise ValueError("EDIT_MATCH_AMBIGUOUS")
    updated=text.replace(old_text,new_text) if replace_all else text.replace(old_text,new_text,1)
    _assert_path_matches_preimage(path,preimage)
    tmp=path.with_name("."+path.name+".hara-tmp-"+str(os.getpid())); tmp.write_text(updated,encoding="utf-8"); os.replace(tmp,path)
    current_sha,current_bytes=_sha256_regular_file(path,max_bytes=2*1024*1024)
    return {"path":str(path),"replacements":count if replace_all else 1,"size_bytes":current_bytes,"previous_sha256":previous_sha,"sha256":current_sha,"precondition_checked":expected is not None,"preimage_id":preimage.get("preimage_id"),"preimage_sha256":preimage.get("sha256")}

def filesystem_move(source_value,destination_value):
    with _file_mutation_guard(_lexical_path(source_value),_lexical_path(destination_value)) as (locked_src,locked_dst):
        return _filesystem_move_locked(locked_src,locked_dst)

def _filesystem_move_locked(source_value,destination_value):
    src=_lexical_path(source_value); dst=_lexical_path(destination_value)
    source_kind=_leaf_kind(src)
    if source_kind=="missing": raise FileNotFoundError(str(src))
    if _leaf_kind(dst)!="missing": raise ValueError("DESTINATION_EXISTS")
    if not dst.parent.exists() or not dst.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    moved=shutil.move(str(src),str(dst))
    return {
        "source":str(src),"destination":str(_lexical_path(moved)),"source_type":source_kind,
        "symlink_preserved":source_kind=="symlink","overwrote":False,
    }

def filesystem_copy(source_value,destination_value):
    with _file_mutation_guard(_lexical_path(source_value),_lexical_path(destination_value)) as (locked_src,locked_dst):
        return _filesystem_copy_locked(locked_src,locked_dst)

def _filesystem_copy_locked(source_value,destination_value):
    src=_lexical_path(source_value); dst=_lexical_path(destination_value)
    if _leaf_kind(src)=="symlink": raise ValueError("SYMLINK_MUTATION_DENIED")
    if _leaf_kind(src)!="file": raise ValueError("SOURCE_NOT_FILE")
    if src.stat().st_size>2*1024*1024: raise ValueError("COPY_FILE_TOO_LARGE")
    if _leaf_kind(dst)!="missing": raise ValueError("DESTINATION_EXISTS")
    if not dst.parent.exists() or not dst.parent.is_dir(): raise ValueError("PARENT_DIRECTORY_NOT_FOUND")
    shutil.copy2(str(src),str(dst))
    sha,size=_sha256_regular_file(dst,max_bytes=2*1024*1024)
    return {"source":str(src),"destination":str(dst),"bytes":size,"sha256":sha,"overwrote":False}

def filesystem_delete(call,path_value,expected_sha256=None):
    with _file_mutation_guard(_lexical_path(path_value)) as (locked_path,):
        return _filesystem_delete_locked(call,locked_path,expected_sha256)

def _filesystem_delete_locked(call,path_value,expected_sha256):
    path=_lexical_path(path_value); _reject_mutation_symlink(path)
    expected=_validate_expected_sha256(expected_sha256)
    if _leaf_kind(path)!="file":
        raise ValueError("FILE_PRECONDITION_FAILED" if expected is not None else "DELETE_TARGET_NOT_FILE")
    if path.stat().st_size>2*1024*1024: raise ValueError("DELETE_FILE_TOO_LARGE")
    if expected is not None: _enforce_file_precondition(path,expected)
    preimage=_store_preimage(path,call.get("call_id") or "delete","hara.files.delete")
    previous_sha=str(preimage.get("sha256") or "") if preimage else ""
    if expected is not None and not hmac.compare_digest(previous_sha,expected):
        _discard_preimage(preimage); raise ValueError("FILE_PRECONDITION_FAILED")
    _assert_path_matches_preimage(path,preimage)
    path.unlink()
    if _leaf_kind(path)!="missing": raise ValueError("DELETE_VERIFY_FAILED")
    return {"path":str(path),"deleted":True,"deleted_sha256":previous_sha,"precondition_checked":expected is not None,"preimage_id":preimage.get("preimage_id"),"preimage_sha256":previous_sha}

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

def _manual_agent_systemctl(action):
    # Fixed, non-shell service control for the explicitly requested local user
    # service. Do not accept arbitrary systemctl verbs or unit names from MCP.
    if action not in {"start", "stop", "is-active", "is-enabled"}:
        raise ValueError("AGENT_SERVICE_ACTION_DENIED")
    try:
        result=subprocess.run(
            ["systemctl", "--user", action, "hara-commander-agent.service"],
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            timeout=12,check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("AGENT_SERVICE_CONTROL_UNAVAILABLE") from None
    if action in {"is-active","is-enabled"}:
        return result.returncode==0
    if result.returncode:
        raise RuntimeError("AGENT_SERVICE_"+action.upper()+"_FAILED")
    return True


def start_manual_operator_console():
    # Starting the local operator session also starts its disabled-by-default
    # daemon, so "hara-commander start" still works after a reboot. Closing
    # the terminal relinquishes only a service that this command started.
    if not sys.stdin.isatty():
        raise RuntimeError("LOCAL_OPERATOR_TERMINAL_REQUIRED")
    was_active=_manual_agent_systemctl("is-active")
    started_here=not was_active
    if started_here:
        _manual_agent_systemctl("start")
    try:
        start_operator_console()
    finally:
        if started_here and not _manual_agent_systemctl("is-enabled"):
            _manual_agent_systemctl("stop")


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
    print("Histórico (30 dias): hara-commander history [limite [before_id]]")
    print("Limpar histórico: sudo hara-commander history clear [somente administrador local]")
    print("Recibos de auditoria não são eliminados pela limpeza.")
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

def query_command_history(limit=50,before_id=0,now_utc=None):
    """Read only locally recorded COMMAND events from the previous 30 days.

    Do not project action_summary, argv, raw payload, device token or content.
    """
    if not isinstance(limit,int) or not 1<=limit<=200:
        raise ValueError("HISTORY_LIMIT_INVALID")
    if not isinstance(before_id,int) or before_id<0:
        raise ValueError("HISTORY_CURSOR_INVALID")
    now=now_utc if now_utc is not None else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("HISTORY_NOW_TZ_REQUIRED")
    cutoff=(now.astimezone(timezone.utc)-timedelta(days=30)).isoformat()
    params=(cutoff,before_id,before_id,limit+1)
    with _ops_connect() as conn:
        entries=conn.execute(
            """SELECT event_id,at_utc,event,state,tool_id,function_id,
                      request_id,error_code,receipt_sha256
               FROM activity_events
               WHERE at_utc>=?
                 AND tool_id IS NOT NULL AND tool_id != ''
                 AND (?=0 OR event_id<?)
               ORDER BY event_id DESC LIMIT ?""",
            params,
        ).fetchall()
    page=[dict(row) for row in entries[:limit]]
    page.reverse()
    return {"window_days":30,"items":page,
            "next_before_id":page[0]["event_id"] if len(entries)>limit and page else None}


def show_command_history(limit=50,before_id=0,now_utc=None):
    view=query_command_history(limit,before_id,now_utc)
    print("HARA_COMMANDER_HISTORY=LOCAL_READ_ONLY")
    print("HARA_COMMANDER_HISTORY_WINDOW_DAYS=30")
    print(f"HARA_COMMANDER_HISTORY_EVENTS={len(view['items'])}")
    for entry in view["items"]:
        line=_format_console_event(entry)
        print(f"#{entry['event_id']} {entry['at_utc']} {line}")
    if view["next_before_id"] is not None:
        print(f"HARA_COMMANDER_HISTORY_MORE=hara-commander history {limit} {view['next_before_id']}")
    print("HARA_COMMANDER_HISTORY_PRIVATE_ARGUMENTS_EXPOSED=FALSE")
    return view


def clear_local_history_data():
    """Admin-only helper: erase local display history, never audit receipts.

    Caller must have already passed root/sudo and explicit interactive consent.
    Test fixtures can exercise this low-level helper with a disposable data dir.
    """
    if read_operator_session() is not None:
        raise RuntimeError("HISTORY_CLEAR_ACTIVE_SESSION_DENIED")
    if not DATA_DIR.is_dir() or DATA_DIR.is_symlink():
        raise RuntimeError("HISTORY_LOCAL_STORAGE_UNSAFE")
    for path in (OPERATIONS_DB_FILE,CONSOLE_EVENTS_FILE,RECEIPT_DIR):
        if path.is_symlink():
            raise RuntimeError("HISTORY_STORAGE_SYMLINK_DENIED")
    with _history_activity_lock():
        with _ops_connect() as conn:
            count=conn.execute("SELECT COUNT(*) FROM activity_events").fetchone()[0]
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM activity_events")
            conn.commit()
        tmp=CONSOLE_EVENTS_FILE.with_name(".history-clear-"+uuid.uuid4().hex)
        try:
            with tmp.open("xb") as handle:
                os.fchmod(handle.fileno(),0o600)
                handle.flush()
                os.fsync(handle.fileno())
            tmp.replace(CONSOLE_EVENTS_FILE)
        finally:
            tmp.unlink(missing_ok=True)
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    receipt={"schema":"hara.commander-history-clear-receipt.v1",
             "at_utc":utcnow(),"cleared_event_rows":count,
             "actor":"LOCAL_SUDO_ADMIN","payload_values_exposed":False,
             "receipts_deleted":False,"outbox_modified":False}
    record=RECEIPT_DIR/("history-clear-"+uuid.uuid4().hex+".json")
    with record.open("x",encoding="utf-8") as h:
        os.fchmod(h.fileno(),0o600)
        json.dump(receipt,h,sort_keys=True,separators=(",",":"))
        h.write("\n")
    append_console_event("HISTORY_CLEARED",state="ADMIN_CONFIRMED")
    return receipt


def history_clear_admin():
    """Requires real local sudo, own TTY and strong typed consent."""
    if os.geteuid()!=0:
        raise RuntimeError("HISTORY_CLEAR_SUPERUSER_REQUIRED")
    if not sys.stdin.isatty():
        raise RuntimeError("HISTORY_CLEAR_LOCAL_TTY_REQUIRED")
    username=os.environ.get("SUDO_USER","")
    sudo_uid=os.environ.get("SUDO_UID","")
    if not username or username=="root" or not sudo_uid.isdecimal():
        raise RuntimeError("HISTORY_CLEAR_SUDO_CONTEXT_REQUIRED")
    user=pwd.getpwnam(username)
    if user.pw_uid==0 or int(sudo_uid)!=user.pw_uid:
        raise RuntimeError("HISTORY_CLEAR_SUDO_IDENTITY_INVALID")
    owner_dir=Path(user.pw_dir)/".local/share/hara-commander"
    if owner_dir.is_symlink() or not owner_dir.is_dir() or owner_dir.stat().st_uid!=user.pw_uid:
        raise RuntimeError("HISTORY_CLEAR_OWNER_DIR_INVALID")
    print(f"HARA_COMMANDER_HISTORY_CLEAR_TARGET={username}")
    print("Essa limpeza remove o histórico local visível (SQLite e JSONL).")
    print("Recibos de auditoria, identidade do dispositivo e pendências serão preservados.")
    print("Encerre antes a sessão interativa com Ctrl+C.")
    answer=input("Digite LIMPAR HISTORICO LOCAL para confirmar: ").strip()
    if answer!="LIMPAR HISTORICO LOCAL":
        raise RuntimeError("HISTORY_CLEAR_CONFIRMATION_DENIED")
    # Drop elevated rights irreversibly: SQLite WAL/JSONL stay user-owned.
    os.setgroups([])
    os.setgid(user.pw_gid)
    os.setuid(user.pw_uid)
    global DATA_DIR,RECEIPT_DIR,SESSION_FILE,CONSOLE_EVENTS_FILE,OPERATIONS_DB_FILE
    DATA_DIR=owner_dir
    RECEIPT_DIR=owner_dir/"receipts"
    SESSION_FILE=owner_dir/"operator-session.json"
    CONSOLE_EVENTS_FILE=owner_dir/"console-events.jsonl"
    OPERATIONS_DB_FILE=owner_dir/"operations.sqlite3"
    receipt=clear_local_history_data()
    print("HARA_COMMANDER_HISTORY_CLEAR=PASS")
    print(f"HARA_COMMANDER_HISTORY_EVENTS_CLEARED={receipt['cleared_event_rows']}")
    print("HARA_COMMANDER_AUDIT_RECEIPTS_PRESERVED=TRUE")


def session_status():
    session = read_operator_session()
    print("HARA_COMMANDER_SESSION=" + ("ACTIVE" if session else "INACTIVE"))
    if session:
        print("SESSION_STARTED_AT_UTC=" + str(session.get("started_at_utc") or ""))
        print("HARA_COMMANDER_APPROVAL_MODE=" + str(session.get("approval_mode") or "ASK_EVERY_ACTION"))
    try:
        print("HARA_COMMANDER_AGENT_SERVICE_ACTIVE=" + ("TRUE" if _manual_agent_systemctl("is-active") else "FALSE"))
        print("HARA_COMMANDER_AGENT_AUTOSTART=" + ("ON" if _manual_agent_systemctl("is-enabled") else "OFF"))
    except RuntimeError:
        print("HARA_COMMANDER_AGENT_SERVICE_STATUS=UNAVAILABLE")
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
    autostart=str(data.get("HARA_COMMANDER_TUNNEL_AUTOSTART") or "OFF").strip().upper()
    if autostart not in {"ON","OFF"}:
        raise RuntimeError("OPENAI_TUNNEL_AUTOSTART_INVALID")
    data["HARA_COMMANDER_TUNNEL_AUTOSTART"]=autostart
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
        "device.info":("DEVICE","Consulta informações básicas e não sensíveis deste computador.",{"argv":[],"result_hints":["device_id","hostname","agent_version","tunnel_mode"]}),
        "device.ping":("DEVICE","Valida conectividade ponta a ponta com este Agent.",{"argv":[],"result_hints":["pong","device_id","at_utc"]}),
        "system.uptime":("SYSTEM","Consulta uptime e load average do sistema.",{"argv":[],"result_hints":["uptime_seconds","load_average_1m","load_average_5m","load_average_15m"]}),
        "system.resources":("SYSTEM","Consulta CPU, memória, swap, load average, disco raiz e mount dos dados do Agent sem shell.",{"argv":[],"result_hints":["cpu_logical","memory_available_bytes","root_disk_free_bytes","agent_data_disk_free_bytes","agent_data_mount_fstype"]}),
        "workspace.inspect":("WORKSPACE","Inspeciona metadados limitados de projeto e Git HEAD sem executar comandos externos.",{"argv":["path","max_entries? (1..200)"],"bounded":True}),
        "process.list":("PROCESS","Lista processos com metadados sanitizados, sem linha de comando ou ambiente.",{"argv":["limit? (1..200)"],"result_hints":["returned_count","available_count","truncated"]}),
        "filesystem.info":("FILESYSTEM","Consulta metadados de um caminho sem ler conteúdo. Symlink leaf é reportado sem ser silenciosamente resolvido.",{"argv":["path"],"symlink_semantics":"LSTAT_LEAF","result_hints":["type","is_symlink","symlink_target","resolved_path"]}),
        "filesystem.hash":("FILESYSTEM","Calcula SHA-256 e tamanho de um arquivo regular, informando quando um symlink read-only foi seguido.",{"argv":["path"],"max_bytes":134217728,"result_hints":["sha256","bytes","followed_symlink","resolved_path"]}),
        "filesystem.diff":("FILESYSTEM","Compara dois arquivos texto com diff unificado limitado.",{"argv":["left","right","max_lines? (1..400)"],"bounded":True}),
        "filesystem.search":("FILESYSTEM","Busca nomes de arquivos ou texto com limites de tempo, tamanho e quantidade.",{"argv":["path","search_type(files|content)","pattern","max_results? (1..100)","include_hidden? (0|1)","ignore_case? (0|1)","file_glob?","offset? (0..10000)"],"continuation":{"input":"offset","output":"next_offset","flags":["has_more","scan_truncated","scan_incomplete","continuation_safe"],"incomplete_reason":"incomplete_reason"}}),
        "filesystem.list":("FILESYSTEM","Lista entradas e metadados de um diretório sem ler conteúdo de arquivos.",{"argv":["path","limit? (1..200)","depth? (1..5)","offset? (0..10000)"],"continuation":{"input":"offset","output":"next_offset","flags":["has_more","scan_incomplete","continuation_safe"],"incomplete_reason":"incomplete_reason"}}),
        "filesystem.read":("FILESYSTEM","Lê um intervalo limitado de linhas de um arquivo texto acessível ao usuário local.",{"argv":["path","offset? (0..1000000)","length? (1..400)"],"continuation":{"input":"offset","output":"next_offset","revision_hint":"file_revision_hint","flags":["has_more","eof","content_truncated","continuation_safe","file_changed_during_read"]},"cas_hash":"full_file_sha256 only for stable complete reads from offset zero of files up to 128 KiB; hash covers raw file bytes"}),
        "filesystem.read_many":("FILESYSTEM","Lê o mesmo intervalo de até dez arquivos texto sem abortar o lote por falha individual.",{"argv":["offset (0..1000000)","length (1..100)","path1..path10"],"partial_failure":True,"continuation_per_file":True,"summary_fields":["successful_count","failed_count","deferred_count","overall_status"],"cas_hash_per_file":"same bounded full_file_sha256 rule as filesystem.read"}),
    }
    if function_id not in specs: raise ValueError("UNKNOWN_FUNCTION_ID")
    domain,description,contract=specs[function_id]
    return {
        "function_id":function_id,"state":"ACTIVE","IDENTITY":{"domain":domain},
        "PURPOSE":{"description_pt_br":description},
        "EXECUTION_SEMANTICS":{"risk_class":"READ_ONLY","change_intent_required":False},
        "AUTHORITY":{"risk_class":"READ_ONLY","change_intent_required":False,"fail_closed":True},
        "FAILURE_ROLLBACK":{"fail_closed":True},
        "CONTRACT":contract,
    }

def catalog():
    functions=[]
    for fid in FUNCTION_IDS:
        spec=_function_spec(fid)
        functions.append({
            "function_id":fid,"state":"ACTIVE",
            "domain":spec["IDENTITY"]["domain"],
            "risk_class":spec["EXECUTION_SEMANTICS"]["risk_class"],
        })
    return {
        "registered_function_count":len(FUNCTION_IDS),
        "executable_function_count":len(FUNCTION_IDS),
        "active_function_count":len(FUNCTION_IDS),
        "domains":["DEVICE","SYSTEM","WORKSPACE","PROCESS","FILESYSTEM"],
        "functions":functions,
    }

def describe(function_id):
    return _function_spec(function_id)

def device_info(config):
    return {
        "device_id":config["HARA_DEVICE_ID"],"hostname":platform.node(),
        "platform":platform.system().upper(),"platform_release":platform.release(),
        "architecture":config["HARA_DEVICE_ARCH"],"python_version":platform.python_version(),
        "agent_version":AGENT_VERSION,"approval_mode":effective_approval_mode(config),
        "tunnel_mode":transport_mode(config),
    }

def device_ping(config):
    return {"pong":True,"hostname":platform.node(),"device_id":config["HARA_DEVICE_ID"],"agent_version":AGENT_VERSION,"at_utc":utcnow()}

def system_uptime():
    uptime=float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    load=os.getloadavg()
    return {"uptime_seconds":round(uptime,2),"load_average_1m":load[0],"load_average_5m":load[1],"load_average_15m":load[2]}

def _storage_mount_snapshot(mountinfo_text, data_dir, disk_usage=shutil.disk_usage):
    mounts=[]
    for line in str(mountinfo_text or "").splitlines():
        if " - " not in line: continue
        left,right=line.split(" - ",1)
        fields=left.split()
        after=right.split()
        if len(fields)<6 or not after: continue
        mount_path=re.sub(r"\\([0-7]{3})",lambda match: chr(int(match.group(1),8)),fields[4])
        if not mount_path.startswith("/"): continue
        mounts.append({"path":mount_path,"options":set(fields[5].split(",")),"fstype":after[0]})

    def mount_for(path):
        matches=[mount for mount in mounts if path==mount["path"] or path.startswith(mount["path"].rstrip("/")+"/")]
        return max(matches,key=lambda mount:len(mount["path"])) if matches else None

    root=mount_for("/")
    data_path=Path(data_dir).resolve(strict=False)
    data=mount_for(str(data_path))
    status="MOUNT_UNKNOWN"
    usage=None
    if data:
        if "ro" in data["options"] or "rw" not in data["options"]:
            status="MOUNT_READ_ONLY"
        else:
            current=data_path
            while not current.exists() and current.parent!=current:
                current=current.parent
            try:
                usage=disk_usage(current)
                status="MOUNT_READ_WRITE"
            except (OSError,ValueError):
                status="USAGE_UNAVAILABLE"
    return {
        "root_mount_fstype":root["fstype"] if root else None,
        "root_mount_read_only":("ro" in root["options"] or "rw" not in root["options"]) if root else None,
        "agent_data_mount_path":data["path"] if data else None,
        "agent_data_mount_fstype":data["fstype"] if data else None,
        "agent_data_mount_read_only":("ro" in data["options"] or "rw" not in data["options"]) if data else None,
        "agent_data_disk_status":status,
        "agent_data_disk_total_bytes":int(usage.total) if usage else None,
        "agent_data_disk_used_bytes":int(usage.used) if usage else None,
        "agent_data_disk_free_bytes":int(usage.free) if usage else None,
    }

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
    try:
        mountinfo=Path("/proc/self/mountinfo").read_text(encoding="utf-8",errors="replace")
    except (FileNotFoundError,PermissionError,OSError):
        mountinfo=""
    return {
        "cpu_logical":int(os.cpu_count() or 0),
        "load_average_1m":load[0],"load_average_5m":load[1],"load_average_15m":load[2],
        "memory_total_bytes":mem.get("MemTotal"),"memory_available_bytes":mem.get("MemAvailable"),
        "swap_total_bytes":mem.get("SwapTotal"),"swap_free_bytes":mem.get("SwapFree"),
        "root_disk_total_bytes":int(disk.total),"root_disk_used_bytes":int(disk.used),"root_disk_free_bytes":int(disk.free),
        **_storage_mount_snapshot(mountinfo,DATA_DIR),
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
    target=Path(_checked_path_text(path_value)).expanduser().resolve(strict=True)
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
    chosen=out[:limit]
    return {
        "count":len(chosen),"returned_count":len(chosen),"available_count":len(out),
        "truncated":len(out)>len(chosen),"processes":chosen,
        "command_lines_exposed":False,"environment_exposed":False,
    }

def filesystem_info(path_value):
    path=_lexical_path(path_value)
    st=path.lstat()
    kind=_leaf_kind(path)
    resolved_path=None
    symlink_target=None
    if kind=="symlink":
        try: symlink_target=os.readlink(path)
        except OSError: symlink_target=None
        try: resolved_path=str(path.resolve(strict=True))
        except (FileNotFoundError,PermissionError,OSError): resolved_path=None
    return {
        "path":str(path),"name":path.name,"type":kind,
        "size_bytes":int(st.st_size) if kind=="file" else None,
        "mode_octal":oct(st.st_mode & 0o777),
        "modified_at_utc":datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),
        "is_symlink":kind=="symlink","symlink_target":symlink_target,"resolved_path":resolved_path,
    }

def filesystem_hash(path_value):
    requested=_lexical_path(path_value)
    followed_symlink=_leaf_kind(requested)=="symlink"
    path=requested.resolve(strict=True)
    sha,total=_sha256_regular_file(path,max_bytes=128*1024*1024)
    return {"path":str(requested),"resolved_path":str(path),"followed_symlink":followed_symlink,"bytes":total,"sha256":sha}

def filesystem_diff(left_value,right_value,max_lines=200):
    left=Path(_checked_path_text(left_value)).expanduser().resolve(strict=True); right=Path(_checked_path_text(right_value)).expanduser().resolve(strict=True)
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

def filesystem_search(path_value,search_type,pattern,max_results=50,include_hidden=False,ignore_case=True,file_glob="",offset=0):
    root=Path(_checked_path_text(path_value)).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError("PATH_NOT_DIRECTORY")
    if search_type not in ("files","content"): raise ValueError("SEARCH_TYPE_INVALID")
    if not pattern or len(pattern)>256: raise ValueError("SEARCH_PATTERN_INVALID")
    max_results=max(1,min(100,int(max_results))); offset=max(0,min(10000,int(offset)))
    deadline=time.monotonic()+3.0; scan_cap=5000
    scanned=0; matches=[]; matched_seen=0; scan_truncated=False; has_more=False; stop=False
    limit_reason=None; permission_denied_count=0; io_error_count=0
    skipped_large_files_count=0; skipped_binary_files_count=0
    needle=pattern.lower() if ignore_case else pattern
    def record_error(exc):
        nonlocal permission_denied_count,io_error_count
        if isinstance(exc,PermissionError): permission_denied_count+=1
        else: io_error_count+=1
    def accept(match):
        nonlocal matched_seen,has_more
        index=matched_seen; matched_seen+=1
        if index < offset: return False
        if len(matches) < max_results:
            matches.append(match); return False
        has_more=True; return True
    for current,dirs,files in os.walk(root,onerror=record_error):
        now=time.monotonic()
        if now>deadline or scanned>=scan_cap:
            limit_reason="TIME_LIMIT" if now>deadline else "SCAN_LIMIT"
            scan_truncated=True; break
        dirs.sort(key=str.lower); files=sorted(files,key=str.lower)
        if not include_hidden:
            dirs[:]=[d for d in dirs if not d.startswith(".")]
            files=[f for f in files if not f.startswith(".")]
        for name in files:
            now=time.monotonic()
            if now>deadline or scanned>=scan_cap:
                limit_reason="TIME_LIMIT" if now>deadline else "SCAN_LIMIT"
                scan_truncated=True; stop=True; break
            scanned+=1
            if file_glob and not fnmatch.fnmatch(name,file_glob): continue
            path=Path(current)/name; rel=str(path.relative_to(root))
            if search_type=="files":
                hay=name.lower() if ignore_case else name
                if needle in hay and accept({"path":rel,"type":"file"}): stop=True; break
            else:
                try:
                    st=path.stat()
                    if st.st_size>2*1024*1024:
                        skipped_large_files_count+=1; continue
                    with path.open("rb") as fh:
                        if b"\x00" in fh.read(4096):
                            skipped_binary_files_count+=1; continue
                    with path.open("r",encoding="utf-8",errors="replace") as fh:
                        for line_no,line in enumerate(fh,1):
                            hay=line.lower() if ignore_case else line
                            if needle in hay:
                                if accept({"path":rel,"line":line_no,"text":line.rstrip("\n")[:300]}): stop=True; break
                    if stop: break
                except OSError as exc:
                    record_error(exc)
                    continue
        if stop: break
    incomplete_reason=limit_reason or ("PERMISSION_DENIED" if permission_denied_count else
        "IO_ERROR" if io_error_count else
        "CONTENT_EXCLUDED" if skipped_large_files_count or skipped_binary_files_count else None)
    scan_incomplete=incomplete_reason is not None
    continuation_safe=not scan_incomplete
    next_offset=offset+len(matches) if has_more and continuation_safe else None
    return {
        "path":str(root),"search_type":search_type,"pattern":pattern,"offset":offset,
        "count":len(matches),"matches":matches,"matched_seen":matched_seen,"scanned_files":scanned,
        "has_more":has_more,"next_offset":next_offset,"scan_truncated":scan_truncated,
        "scan_incomplete":scan_incomplete,"incomplete_reason":incomplete_reason,
        "permission_denied_count":permission_denied_count,"io_error_count":io_error_count,
        "skipped_large_files_count":skipped_large_files_count,
        "skipped_binary_files_count":skipped_binary_files_count,
        "continuation_safe":continuation_safe,"truncated":has_more or scan_incomplete,
    }

def filesystem_list(path_value,limit=100,depth=1,offset=0):
    root=Path(_checked_path_text(path_value)).expanduser().resolve(strict=True)
    if not root.is_dir(): raise ValueError("PATH_NOT_DIRECTORY")
    limit=max(1,min(200,int(limit))); depth=max(1,min(5,int(depth))); offset=max(0,min(10000,int(offset)))
    entries=[]; seen=0; has_more=False; permission_denied_count=0; io_error_count=0
    def record_error(exc):
        nonlocal permission_denied_count,io_error_count
        if isinstance(exc,PermissionError): permission_denied_count+=1
        else: io_error_count+=1
    def walk(current,level):
        nonlocal seen,has_more
        if has_more or level>depth: return
        try: children=sorted(current.iterdir(),key=lambda e:e.name.lower())
        except OSError as exc:
            record_error(exc); return
        for entry in children:
            if has_more: return
            try:
                st=entry.lstat(); kind="symlink" if entry.is_symlink() else "directory" if entry.is_dir() else "file" if entry.is_file() else "other"
                item={"path":str(entry.relative_to(root)),"name":entry.name,"type":kind,"size_bytes":int(st.st_size) if kind=="file" else None,"depth":level}
                index=seen; seen+=1
                if index>=offset:
                    if len(entries)<limit: entries.append(item)
                    else: has_more=True; return
                if kind=="directory" and level<depth: walk(entry,level+1)
            except OSError as exc:
                record_error(exc)
                continue
    walk(root,1)
    incomplete_reason="PERMISSION_DENIED" if permission_denied_count else "IO_ERROR" if io_error_count else None
    scan_incomplete=incomplete_reason is not None
    continuation_safe=not scan_incomplete
    return {
        "path":str(root),"offset":offset,"count":len(entries),"entries":entries,"depth":depth,
        "has_more":has_more,"next_offset":offset+len(entries) if has_more and continuation_safe else None,
        "scan_incomplete":scan_incomplete,"incomplete_reason":incomplete_reason,
        "permission_denied_count":permission_denied_count,"io_error_count":io_error_count,
        "continuation_safe":continuation_safe,"truncated":has_more or scan_incomplete,"visited_entries":seen,
    }

def _file_revision_hint(st):
    # Metadata only: a cheap pagination hint, not a content hash or CAS token.
    parts=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
    return hashlib.sha256(":".join(str(int(part)) for part in parts).encode("ascii")).hexdigest()

def filesystem_read(path_value,offset=0,length=200,max_encoded_text_bytes=96*1024):
    requested=_lexical_path(path_value)
    followed_symlink=_leaf_kind(requested)=="symlink"
    path=requested.resolve(strict=True)
    if not path.is_file(): raise ValueError("PATH_NOT_FILE")
    start_stat=path.stat()
    start_revision=_file_revision_hint(start_stat)
    file_size=int(start_stat.st_size)
    if file_size>2*1024*1024: raise ValueError("FILE_TOO_LARGE")
    with path.open("rb") as fh:
        if b"\x00" in fh.read(4096): raise ValueError("BINARY_FILE_DENIED")
    offset=max(0,int(offset)); length=max(1,min(400,int(length)))
    lines=[]; has_more=False; output_bytes=0; json_text_bytes=0; oversized_line=False
    max_encoded_text_bytes=max(256,min(96*1024,int(max_encoded_text_bytes)))
    with path.open("r",encoding="utf-8",errors="replace") as fh:
        for idx,line in enumerate(fh):
            if idx<offset: continue
            value=line.rstrip("\n")
            encoded=value.encode("utf-8")
            separator=1 if lines else 0
            json_separator=2 if lines else 0
            escaped_bytes=len(json.dumps(value,ensure_ascii=False).encode("utf-8"))-2
            if len(lines)>=length:
                has_more=True; break
            if (output_bytes+separator+len(encoded)>65536
                    or json_text_bytes+json_separator+escaped_bytes>max_encoded_text_bytes):
                if not lines:
                    # A single logical line cannot be resumed by line offset.
                    # Bound both UTF-8 and JSON escapes before returning a
                    # preview, and make the continuation limitation explicit.
                    low,high=0,min(len(value),65536)+1
                    while low+1<high:
                        middle=(low+high)//2
                        candidate=value[:middle]
                        if (len(candidate.encode("utf-8"))<=65536 and
                                len(json.dumps(candidate,ensure_ascii=False).encode("utf-8"))-2<=max_encoded_text_bytes):
                            low=middle
                        else:
                            high=middle
                    preview=value[:low]
                    lines.append(preview)
                    output_bytes=len(preview.encode("utf-8"))
                    oversized_line=True
                has_more=True
                break
            lines.append(value); output_bytes+=separator+len(encoded)
            json_text_bytes+=json_separator+escaped_bytes
    text="\n".join(lines)
    try: changed_during_read=_file_revision_hint(path.stat())!=start_revision
    except OSError: changed_during_read=True
    full_file_sha256=None
    if offset==0 and not has_more and not changed_during_read and file_size<=128*1024:
        # The full short file was already returned. A bounded raw-byte reread
        # yields a CAS token without losing CRLF or replacement-decoded bytes.
        try:
            raw,hash_stat=_read_regular_nofollow(path,128*1024)
            if (_file_revision_hint(hash_stat)!=start_revision
                    or _file_revision_hint(path.stat())!=start_revision):
                changed_during_read=True
            else:
                full_file_sha256=hashlib.sha256(raw).hexdigest()
        except (OSError,ValueError):
            changed_during_read=True
    if changed_during_read: has_more=True
    continuation_safe=not oversized_line and not changed_during_read
    next_offset=(offset+len(lines)) if has_more and continuation_safe else None
    return {
        "path":str(requested),"resolved_path":str(path),"followed_symlink":followed_symlink,
        "file_size_bytes":file_size,"offset":offset,"line_count":len(lines),"text":text,
        "has_more":has_more,"eof":not has_more,"next_offset":next_offset,
        "content_truncated":oversized_line,"continuation_safe":continuation_safe,
        "oversized_line":oversized_line,"file_revision_hint":start_revision,
        "file_changed_during_read":changed_during_read,
        "restart_offset":0 if changed_during_read else None,
        **({"full_file_sha256":full_file_sha256} if full_file_sha256 else {}),
    }

def filesystem_read_many(paths,offset=0,length=100):
    out=[]
    selected=paths[:10]
    def summarize(items):
        successful=sum(item["state"]=="PASS" for item in items)
        failed=sum(item["state"]=="FAILED" for item in items)
        deferred=sum(item["state"]=="DEFERRED" for item in items)
        changed=any(item.get("file_changed_during_read") for item in items)
        overall="PASS" if not failed and not deferred and not changed else "FAILED" if failed==len(items) else "PARTIAL"
        return {"count":len(items),"successful_count":successful,"failed_count":failed,
                "deferred_count":deferred,"overall_status":overall,"files":items,
                "offset":offset,"length":length}
    def packed_bytes(items):
        return len(json.dumps(summarize(items),
                              sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8"))
    for index,raw in enumerate(selected):
        try:
            remaining=len(selected)-index
            available=max(256,96*1024-packed_bytes(out))
            text_budget=max(256,min(96*1024,available//remaining-1024))
            observed_change=False
            while True:
                item=filesystem_read(str(raw),offset,length,text_budget)
                observed_change=observed_change or bool(item.get("file_changed_during_read"))
                if observed_change:
                    item={**item,"file_changed_during_read":True,"continuation_safe":False,
                          "has_more":True,"eof":False,"next_offset":None,"restart_offset":0}
                entry={
                    "path":item["path"],"state":"PASS","offset":item["offset"],"line_count":item["line_count"],"text":item["text"],
                    "has_more":item.get("has_more"),"eof":item.get("eof"),"next_offset":item.get("next_offset"),
                    "content_truncated":item.get("content_truncated"),
                    "continuation_safe":item.get("continuation_safe"),
                    "file_revision_hint":item.get("file_revision_hint"),
                    "file_changed_during_read":item.get("file_changed_during_read"),
                    "restart_offset":item.get("restart_offset"),
                }
                if not observed_change and item.get("full_file_sha256"):
                    entry["full_file_sha256"]=item["full_file_sha256"]
                if packed_bytes(out+[entry])<=96*1024:
                    out.append(entry)
                    break
                if text_budget<=256:
                    out.append({"path":str(raw),"state":"DEFERRED","offset":offset,
                                "line_count":0,"text":"","has_more":True,"eof":False,
                                "next_offset":None if observed_change else offset,
                                "content_truncated":False,
                                "continuation_safe":not observed_change,
                                "file_changed_during_read":observed_change,
                                "restart_offset":0 if observed_change else None,
                                "reason":"RESULT_BUDGET"})
                    break
                text_budget=max(256,text_budget//2)
        except Exception as exc:
            out.append({"path":str(raw),"state":"FAILED","error_code":safe_error_code(exc)})
    return summarize(out)

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
        if len(argv)<3 or len(argv)>8: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_search(str(argv[0]),str(argv[1]),str(argv[2]),int(argv[3]) if len(argv)>=4 else 50,argv[4]=="1" if len(argv)>=5 else False,argv[5]!="0" if len(argv)>=6 else True,str(argv[6]) if len(argv)>=7 else "",int(argv[7]) if len(argv)>=8 else 0)
    elif function_id=="filesystem.info":
        if len(argv)!=1: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_info(str(argv[0]))
    elif function_id=="filesystem.list":
        if len(argv)<1 or len(argv)>4: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        limit=int(argv[1]) if len(argv)>=2 else 100; depth=int(argv[2]) if len(argv)>=3 else 1; offset=int(argv[3]) if len(argv)>=4 else 0
        if not 1<=limit<=200 or not 1<=depth<=5 or not 0<=offset<=10000: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        result=filesystem_list(str(argv[0]),limit,depth,offset)
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
        "transport_mode":str(call.get("_transport") or "OUTBOUND_RELAY"),
        "operational_authority":"HARA_COMMANDER_LOCAL" if str(call.get("_transport") or "")=="LOCAL_MCP" else "HARA_SERVICES",
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
    local_transport=str(call.get("_transport") or "")=="LOCAL_MCP"
    operational_authority="HARA_COMMANDER_LOCAL" if local_transport else "HARA_SERVICES"
    if tool=="hara.health":
        result={
            "services_bridge_state":"BYPASSED_LOCAL" if local_transport else "PASS",
            "hara_services_state":"NOT_IN_DATA_PLANE" if local_transport else "PASS",
            "registered_function_count":len(FUNCTION_IDS),
            "executable_function_count":len(FUNCTION_IDS),
            "authority":operational_authority,
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
            allowed=required|{"max_results","include_hidden","ignore_case","file_glob","offset"}
            if not required.issubset(payload) or any(k not in allowed for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"]),str(payload["search_type"]),str(payload["pattern"]),str(payload.get("max_results",50)),"1" if payload.get("include_hidden") else "0","0" if payload.get("ignore_case") is False else "1",str(payload.get("file_glob", "")),str(payload.get("offset",0))]
        elif tool=="hara.files.info":
            if set(payload)!={"path"}: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"])]
        elif tool=="hara.files.list":
            if "path" not in payload or any(k not in ("path","limit","depth","offset") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
            argv=[str(payload["path"]),str(payload.get("limit",100)),str(payload.get("depth",1)),str(payload.get("offset",0))]
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
        data=process_run(str(payload["command"]),payload.get("cwd"),int(payload.get("timeout_ms",3000)),int(payload.get("max_lines",200)),
                         owner_request_id=call.get("request_id"),owner_subject_id=call.get("subject_id"))
        result={"function_id":"process.run","risk_class":"PROCESS_EXECUTION","process_exit_code":data.get("exit_code") if isinstance(data.get("exit_code"),int) else None,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False}
    elif tool=="hara.process.start":
        if "command" not in payload or any(k not in ("command","cwd","timeout_ms") for k in payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=process_start(str(payload["command"]),payload.get("cwd"),int(payload.get("timeout_ms",1000)),
                           owner_request_id=call.get("request_id"),owner_subject_id=call.get("subject_id"))
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
        if set(payload)-{"path","content","mode","expected_sha256"} or not {"path","content"}.issubset(payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_write(call,str(payload["path"]),str(payload["content"]),str(payload.get("mode","rewrite")),payload.get("expected_sha256"))
        result={"function_id":"filesystem.write","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.files.edit":
        if set(payload)-{"path","old_text","new_text","replace_all","expected_sha256"} or not {"path","old_text","new_text"}.issubset(payload): raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_edit(call,str(payload["path"]),str(payload["old_text"]),str(payload["new_text"]),bool(payload.get("replace_all",False)),payload.get("expected_sha256"))
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
        if set(payload)-{"path","expected_sha256"} or "path" not in payload: raise ValueError("FUNCTION_ARGUMENTS_DENIED")
        data=filesystem_delete(call,str(payload["path"]),payload.get("expected_sha256"))
        result={"function_id":"filesystem.delete","risk_class":"MUTATING","process_exit_code":0,"stdout":json.dumps(data,sort_keys=True,separators=(",",":"),ensure_ascii=False),"domain_success_inferred":False,"preimage_id":data.get("preimage_id"),"preimage_sha256":data.get("preimage_sha256")}
    elif tool=="hara.receipts.get":
        result=read_receipt(payload.get("receipt_id_or_sha256"))
        return {
            "state":"PASS","operational_authority":operational_authority,
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
        "state":"PASS","operational_authority":operational_authority,
        "runtime_authority_from_chatgpt":False,"mutation_performed":mutation,
        "result":result,"blocker":None,"bridge_receipt_sha256":sha,
    }
def complete(config, call, state, result, error_code=None):
    body={"call_id":call["call_id"],"state":state,"result":result}
    if error_code: body["error_code"]=error_code
    return post_json(config["HARA_COMMANDER_URL"]+"/api/device/calls/complete",config["HARA_DEVICE_TOKEN"],body)

def _completion_input_sha256(call):
    raw=json.dumps({
        "call_id":str(call.get("call_id") or ""),
        "request_id":str(call.get("request_id") or ""),
        "tool_id":str(call.get("tool_id") or ""),
        "payload":call.get("payload") or {},
    },sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _completion_outbox_intent(call):
    """Claim a call locally before execution; a duplicate may only replay."""
    identity=_completion_input_sha256(call)
    now=int(time.time())
    conn=_ops_connect()
    try:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM completion_outbox WHERE status='ACKED' AND acked_epoch<?",
                     (now-COMPLETION_OUTBOX_ACK_RETENTION_SECONDS,))
        row=conn.execute("SELECT * FROM completion_outbox WHERE call_id=?",(str(call["call_id"]),)).fetchone()
        if row:
            if (row["input_sha256"]!=identity or row["request_id"]!=str(call.get("request_id") or "")
                    or row["tool_id"]!=str(call.get("tool_id") or "")):
                raise ValueError("LOCAL_CALL_IDEMPOTENCY_CONFLICT")
            conn.commit()
            return dict(row),False
        count=conn.execute("SELECT COUNT(*) FROM completion_outbox WHERE status IN ('INTENT','READY')").fetchone()[0]
        if count>=COMPLETION_OUTBOX_MAX_PENDING:
            raise ValueError("LOCAL_COMPLETION_OUTBOX_FULL")
        conn.execute("""INSERT INTO completion_outbox
            (call_id,request_id,tool_id,input_sha256,status,created_epoch,updated_epoch)
            VALUES (?,?,?,?,'INTENT',?,?)""",
            (str(call["call_id"]),str(call.get("request_id") or ""),
             str(call.get("tool_id") or ""),identity,now,now))
        conn.commit()
        return None,True
    finally:
        conn.close()

def _completion_bounded_body(state,result,error_code=None):
    raw=json.dumps(result,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    if len(raw)>COMPLETION_RESULT_MAX_BYTES:
        if result.get("mutation_performed") is True:
            original=result.get("result") if isinstance(result.get("result"),dict) else {}
            safe={key:original[key] for key in ("function_id","risk_class","process_exit_code","domain_success_inferred") if key in original}
            result={"state":result.get("state") or "PASS",
                    "operational_authority":result.get("operational_authority"),
                    "runtime_authority_from_chatgpt":False,
                    "mutation_performed":True,
                    "bridge_receipt_sha256":result.get("bridge_receipt_sha256"),
                    "result":safe,"result_content_truncated":True}
        else:
            state="FAILED"
            error_code="DEVICE_RESULT_TOO_LARGE"
            result={"state":"FAILED","operational_authority":result.get("operational_authority"),
                    "runtime_authority_from_chatgpt":False,"mutation_performed":False,
                    "result":{},"blocker":{"code":error_code}}
    if len(json.dumps(result,separators=(",",":"),ensure_ascii=False).encode("utf-8"))>COMPLETION_RESULT_MAX_BYTES:
        raise ValueError("DEVICE_RESULT_TOO_LARGE")
    body={"state":state,"result":result}
    if error_code: body["error_code"]=error_code
    return body

def _completion_outbox_ready(call,body):
    raw=json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    conn=_ops_connect()
    try:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("SELECT status,body_json FROM completion_outbox WHERE call_id=?",
                         (str(call["call_id"]),)).fetchone()
        if not row: raise ValueError("LOCAL_COMPLETION_INTENT_MISSING")
        if row["status"]=="INTENT":
            conn.execute("UPDATE completion_outbox SET status='READY',body_json=?,updated_epoch=? WHERE call_id=? AND status='INTENT'",
                         (raw,int(time.time()),str(call["call_id"])))
        elif row["body_json"]!=raw:
            raise ValueError("LOCAL_COMPLETION_RESULT_CONFLICT")
        conn.commit()
        return body
    finally:
        conn.close()

def _completion_outbox_ack(call_id):
    conn=_ops_connect()
    try:
        conn.execute("PRAGMA synchronous=FULL")
        now=int(time.time())
        conn.execute("UPDATE completion_outbox SET status='ACKED',body_json=NULL,acked_epoch=?,updated_epoch=? WHERE call_id=? AND status='READY'",
                     (now,now,str(call_id)))
        conn.commit()
    finally:
        conn.close()

def _completion_outbox_fetch(call_id):
    conn=_ops_connect()
    try:
        row=conn.execute("SELECT * FROM completion_outbox WHERE call_id=?",(str(call_id),)).fetchone()
        if not row: raise ValueError("LOCAL_COMPLETION_INTENT_MISSING")
        return dict(row)
    finally:
        conn.close()

def _completion_outbox_delivery_failure(call_id,exc):
    code=safe_error_code(exc)
    terminal=isinstance(exc,urllib.error.HTTPError) and int(exc.code) in {400,401,403,404,409,410,422}
    now=int(time.time())
    conn=_ops_connect()
    try:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("SELECT attempt_count FROM completion_outbox WHERE call_id=? AND status='READY'",(str(call_id),)).fetchone()
        if row:
            attempts=int(row["attempt_count"] or 0)+1
            delay=0 if terminal else min(300,2**min(attempts,8))
            conn.execute("""UPDATE completion_outbox SET attempt_count=?,last_error_code=?,
                quarantined_epoch=?,retry_after_epoch=?,updated_epoch=?
                WHERE call_id=? AND status='READY'""",
                (attempts,code,now if terminal else None,now+delay,now,str(call_id)))
        conn.commit()
    finally:
        conn.close()
    return terminal,code

def completion_outbox_health():
    conn=_ops_connect()
    try:
        row=conn.execute("""SELECT COUNT(*) AS pending,
            SUM(CASE WHEN quarantined_epoch IS NOT NULL THEN 1 ELSE 0 END) AS quarantined,
            SUM(CASE WHEN quarantined_epoch IS NULL AND retry_after_epoch>? THEN 1 ELSE 0 END) AS retrying,
            MIN(CASE WHEN quarantined_epoch IS NULL AND retry_after_epoch>? THEN retry_after_epoch END) AS next_retry_epoch
            FROM completion_outbox WHERE status IN ('INTENT','READY')""",
            (int(time.time()),int(time.time()))).fetchone()
        return {"pending":int(row["pending"] or 0),"quarantined":int(row["quarantined"] or 0),
                "retrying":int(row["retrying"] or 0),"next_retry_epoch":row["next_retry_epoch"]}
    finally:
        conn.close()

def completion_outbox_retry(call_id):
    """Explicit local operator retry of the exact stored result, never execution."""
    conn=_ops_connect()
    try:
        conn.execute("PRAGMA synchronous=FULL")
        conn.execute("BEGIN IMMEDIATE")
        row=conn.execute("SELECT status,body_json FROM completion_outbox WHERE call_id=?",(str(call_id),)).fetchone()
        if not row or row["status"]!="READY" or not row["body_json"]:
            raise ValueError("LOCAL_COMPLETION_RETRY_NOT_FOUND")
        conn.execute("""UPDATE completion_outbox SET quarantined_epoch=NULL,retry_after_epoch=0,
            last_error_code=NULL,updated_epoch=? WHERE call_id=? AND status='READY'""",
            (int(time.time()),str(call_id)))
        conn.commit()
        return True
    finally:
        conn.close()

def completion_outbox_cli_status():
    health=completion_outbox_health()
    conn=_ops_connect()
    try:
        rows=conn.execute("""SELECT call_id,tool_id,status,created_epoch,attempt_count,
            last_error_code,quarantined_epoch,retry_after_epoch FROM completion_outbox
            WHERE status IN ('INTENT','READY') ORDER BY created_epoch,call_id LIMIT 20""").fetchall()
        print(json.dumps({"schema":"hara.commander-completion-outbox-status.v1",**health,
            "entries":[dict(row) for row in rows],"customer_payload_included":False},sort_keys=True))
    finally:
        conn.close()

def _completion_outbox_replay(config,row):
    call={"call_id":row["call_id"]}
    if row["status"]=="ACKED": return True
    if row.get("quarantined_epoch") is not None: raise ValueError("LOCAL_COMPLETION_QUARANTINED")
    if int(row.get("retry_after_epoch") or 0)>int(time.time()): return False
    if row["status"]=="INTENT":
        # A previous process stopped between intent and durable result.
        # Execution may have occurred; never run it again or claim no mutation.
        body=_completion_bounded_body("FAILED",{
            "state":"UNKNOWN","operational_authority":"HARA_COMMANDER_AGENT",
            "runtime_authority_from_chatgpt":False,"mutation_performed":None,
            "result":{},"blocker":{"code":"LOCAL_EXECUTION_OUTCOME_UNKNOWN"},
        },"LOCAL_EXECUTION_OUTCOME_UNKNOWN")
        _completion_outbox_ready(call,body)
    else:
        body=json.loads(row["body_json"])
    try:
        response=complete(config,call,body["state"],body["result"],body.get("error_code"))
        if not isinstance(response,dict) or response.get("ok") is not True:
            raise RuntimeError("DEVICE_COMPLETION_ACK_INVALID")
    except Exception as exc:
        terminal,code=_completion_outbox_delivery_failure(row["call_id"],exc)
        if terminal:
            append_console_event("RESULT_DELIVERY_QUARANTINED",state="QUARANTINED",error_code=code)
        raise
    _completion_outbox_ack(row["call_id"])
    return True

def flush_completion_outbox(config,limit=8):
    conn=_ops_connect()
    try:
        rows=[dict(row) for row in conn.execute(
            "SELECT * FROM completion_outbox WHERE status IN ('INTENT','READY') AND quarantined_epoch IS NULL AND retry_after_epoch<=? ORDER BY created_epoch,call_id LIMIT ?",
            (int(time.time()),max(1,min(8,int(limit))),)).fetchall()]
    finally:
        conn.close()
    delivered=0
    for row in rows:
        try:
            if _completion_outbox_replay(config,row): delivered+=1
        except Exception as exc:
            append_console_event("RESULT_DELIVERY_DEGRADED",state="PENDING",error_code=safe_error_code(exc))
            break
    return delivered

def completion_outbox_pending():
    conn=_ops_connect()
    try:
        return int(conn.execute(
            "SELECT COUNT(*) FROM completion_outbox WHERE status IN ('INTENT','READY')"
        ).fetchone()[0])
    finally:
        conn.close()

def _known_nonmutating_file_conflict(tool_id, code):
    # These branches in the file handlers reject before write/replace/unlink.
    # Other errors from a started mutation retain an uncertain outcome.
    if code in {"FILE_MUTATION_BUSY","FILE_MUTATION_LOCK_UNAVAILABLE"} and tool_id in FILESYSTEM_MUTATION_TOOLS:
        return {"state":"BUSY" if code=="FILE_MUTATION_BUSY" else "UNAVAILABLE",
                "category":"FILE_MUTATION_LOCK","retryable":False,
                "next_action":"RECHECK_FILE_THEN_NEW_REQUEST" if code=="FILE_MUTATION_BUSY" else "CHECK_DIRECTORY_LOCK_SUPPORT"}
    if code=="FILE_PRECONDITION_FAILED" and tool_id in {"hara.files.write","hara.files.edit","hara.files.delete"}:
        return {"state":"CONFLICT","category":"FILE_PRECONDITION",
                "next_action":"REHASH_CURRENT_FILE_BEFORE_RETRY"}
    if code=="EDIT_MATCH_AMBIGUOUS" and tool_id=="hara.files.edit":
        return {"state":"NEEDS_INPUT","category":"EDIT_MATCH",
                "next_action":"NARROW_EDIT_MATCH_OR_CONFIRM_REPLACE_ALL"}
    return None

def execute_call(config,call):
    started=time.monotonic()
    call["_transport"]="OUTBOUND_RELAY"
    existing,inserted=_completion_outbox_intent(call)
    if not inserted:
        try:
            _completion_outbox_replay(config,existing)
        except Exception as exc:
            append_console_event("RESULT_DELIVERY_DEGRADED",call,state="PENDING",error_code=safe_error_code(exc))
        return
    budget_reservation=None
    budget_commit=None
    execution_started=False
    try:
        if effective_approval_mode(config)!="PERSISTENT_TRUSTED" and not operator_session_active():
            raise ValueError("LOCAL_OPERATOR_SESSION_REQUIRED")
        append_console_event("RECEIVED",call,state="PENDING")
        budget_reservation=local_budget_reserve(config,call)
        if _is_mutation_tool(call.get("tool_id")):
            call["_local_approval"]=request_local_approval(call)
        append_console_event("EXECUTING",call,state="EXECUTING")
        execution_started=True
        result=execute_tool(config,call)
    except Exception as exc:
        code=safe_error_code(exc)
        file_conflict=_known_nonmutating_file_conflict(call.get("tool_id"),code) if execution_started else None
        uncertain=execution_started and _is_mutation_tool(call.get("tool_id")) and not file_conflict
        if budget_reservation:
            try:
                if uncertain: local_budget_commit(call.get("request_id"))
                else: local_budget_release(call.get("request_id"))
            except Exception as budget_exc:
                append_console_event("LOCAL_BUDGET_DEGRADED",call,state="DEGRADED",error_code=safe_error_code(budget_exc))
        operational = bool(file_conflict) or local_mcp_operational_error(code,"",{}) is not None
        append_console_event(
            "OUTCOME_UNKNOWN" if uncertain else ("OPERATIONAL" if operational else "DENIED"),
            call,
            state="UNKNOWN" if uncertain else ("EXPECTED" if operational else "FAILED"),
            error_code=code,
            duration_ms=round((time.monotonic()-started)*1000),
        )
        failure={"state":"UNKNOWN" if uncertain else (file_conflict["state"] if file_conflict else "DENIED"),
                 "operational_authority":"HARA_COMMANDER_AGENT" if uncertain or (file_conflict and file_conflict["category"]=="FILE_MUTATION_LOCK") else ("HARA_SERVICES" if file_conflict else "LOCAL_OPERATOR_SESSION"),
                 "runtime_authority_from_chatgpt":False,
                 "mutation_performed":None if uncertain else False,
                 "result":{},"blocker":{"code":code,**({"category":file_conflict["category"],
                    "retryable":file_conflict.get("retryable",False),
                    "next_action":file_conflict["next_action"]} if file_conflict else {})}}
        body=_completion_bounded_body("FAILED",failure,code)
    else:
        if budget_reservation:
            try:
                budget_commit=local_budget_commit(call.get("request_id"))
            except Exception as budget_exc:
                # The tool has already run; budget trouble cannot rewrite its
                # outcome or cause the mutation to execute again.
                append_console_event("LOCAL_BUDGET_DEGRADED",call,state="DEGRADED",error_code=safe_error_code(budget_exc))
        body=_completion_bounded_body("COMPLETED",result)

    # Persist the exact result before any network send. A failed/lost ACK
    # leaves READY for identical replay; it never enters the execution catch.
    _completion_outbox_ready(call,body)
    try:
        _completion_outbox_replay(config,_completion_outbox_fetch(call["call_id"]))
    except Exception as exc:
        append_console_event("RESULT_DELIVERY_DEGRADED",call,state="PENDING",error_code=safe_error_code(exc))
        return
    if budget_commit and budget_commit.get("exhausted"):
        try:
            refresh_product_lease(config)
            append_console_event("LOCAL_BUDGET_ROLLOVER",call,state="READY")
        except Exception as refresh_exc:
            append_console_event("PRODUCT_LEASE_DEGRADED",call,state="DEGRADED",error_code=safe_error_code(refresh_exc))
    if body["state"]=="COMPLETED":
        append_console_event("PASS",call,state="COMPLETED",
            receipt_sha256=body["result"].get("bridge_receipt_sha256"),
            duration_ms=round((time.monotonic()-started)*1000))

def self_test():
    global RECEIPT_DIR
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        RECEIPT_DIR=Path(d)
        # Give this fixture its own project boundary even when the host's
        # temporary parent contains a Git marker or another project manifest.
        (Path(d)/"pyproject.toml").write_text("[project]\nname = 'hara-agent-selftest'\nversion = '0.0.0'\n",encoding="utf-8")
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
        ("read_file","Read File","Read a text file. A stable complete read from offset zero of a file up to 128 KiB includes full_file_sha256 for expected_sha256.",_mcp_schema({"computer":computer,"path":path,"offset":{"type":"integer","minimum":0,"maximum":1000000},"length":{"type":"integer","minimum":1,"maximum":400}},["path"])),
        ("read_multiple_files","Read Multiple Files","Read multiple text files in one call. Each stable complete short file may include full_file_sha256 for expected_sha256.",_mcp_schema({"computer":computer,"paths":{"type":"array","items":path,"minItems":1,"maxItems":10},"offset":{"type":"integer","minimum":0,"maximum":1000000},"length":{"type":"integer","minimum":1,"maximum":100}},["paths"])),
        ("write_file","Write File","Write or append text to a file. expected_sha256 prevents overwriting a file that changed after it was read.",_mcp_schema({"computer":computer,"path":path,"content":{"type":"string","maxLength":65536},"mode":{"type":"string","enum":["rewrite","append"]},"expected_sha256":{"type":"string","pattern":"^[0-9a-fA-F]{64}$"}},["path","content"])),
        ("edit_block","Edit Block","Apply a focused text replacement. expected_sha256 adds optimistic concurrency protection.",_mcp_schema({"computer":computer,"path":path,"old_string":{"type":"string","minLength":1,"maxLength":32768},"new_string":{"type":"string","maxLength":32768},"replace_all":boolean,"expected_sha256":{"type":"string","pattern":"^[0-9a-fA-F]{64}$"}},["path","old_string","new_string"])),
        ("create_directory","Create Directory","Create a directory.",_mcp_schema({"computer":computer,"path":path,"parents":boolean},["path"])),
        ("list_directory","List Directory","List directory contents with offset-based continuation.",_mcp_schema({"computer":computer,"path":path,"depth":{"type":"integer","minimum":1,"maximum":5},"limit":{"type":"integer","minimum":1,"maximum":200},"offset":{"type":"integer","minimum":0,"maximum":10000}},["path"])),
        ("move_file","Move File","Move or rename a file or directory.",_mcp_schema({"computer":computer,"source":path,"destination":path},["source","destination"])),
        ("copy_file","Copy File","Copy one regular file to a new destination; symlink leaf sources are refused.",_mcp_schema({"computer":computer,"source":path,"destination":path},["source","destination"])),
        ("delete_file","Delete File","Delete a regular file with reversible preimage protection. Symlinks are refused; expected_sha256 can protect against deleting a changed file.",_mcp_schema({"computer":computer,"path":path,"expected_sha256":{"type":"string","pattern":"^[0-9a-fA-F]{64}$"}},["path"])),
        ("search","Search","Search file names or text content with offset-based continuation.",_mcp_schema({"computer":computer,"path":path,"pattern":{"type":"string","minLength":1,"maxLength":256},"search_type":{"type":"string","enum":["files","content"]},"max_results":{"type":"integer","minimum":1,"maximum":100},"include_hidden":boolean,"ignore_case":boolean,"file_glob":{"type":"string","maxLength":180},"offset":{"type":"integer","minimum":0,"maximum":10000}},["path","pattern"])),
        ("get_file_info","Get File Info","Get file metadata.",_mcp_schema({"computer":computer,"path":path},["path"])),
        ("list_processes","List Processes","List running processes.",_mcp_schema({"computer":computer,"limit":{"type":"integer","minimum":1,"maximum":200}})),
        ("start_process","Start Process","Run a command. Defaults to bounded one-shot execution; interactive=true keeps a managed session. Requests above 10 seconds are automatically routed to a managed session.",_mcp_schema({"computer":computer,"command":{"type":"string","minLength":1,"maxLength":4096},"cwd":path,"timeout_ms":{"type":"integer","minimum":100,"maximum":30000},"max_lines":{"type":"integer","minimum":1,"maximum":500},"interactive":boolean},["command"])),
        ("read_process_output","Read Process Output","Read a managed process session.",_mcp_schema({"computer":computer,"session_id":{"type":"string","minLength":1,"maxLength":180},"offset":{"type":"integer","minimum":0,"maximum":1000000},"length":{"type":"integer","minimum":1,"maximum":500},"timeout_ms":{"type":"integer","minimum":0,"maximum":3000}},["session_id"])),
        ("interact_with_process","Interact With Process","Send input to a managed process session. The reply reports bytes sent, PTY echo mode and whether read_process_output should continue; PTY text is not classified as program output.",_mcp_schema({"computer":computer,"session_id":{"type":"string","minLength":1,"maxLength":180},"input":{"type":"string","maxLength":4096},"timeout_ms":{"type":"integer","minimum":0,"maximum":3000}},["session_id","input"])),
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
    if name=="write_file": return "hara.files.write",{"path":str(args["path"]),"content":str(args["content"]),"mode":str(args.get("mode","rewrite")),**({"expected_sha256":str(args["expected_sha256"])} if args.get("expected_sha256") else {})}
    if name=="edit_block": return "hara.files.edit",{"path":str(args["path"]),"old_text":str(args["old_string"]),"new_text":str(args["new_string"]),"replace_all":bool(args.get("replace_all",False)),**({"expected_sha256":str(args["expected_sha256"])} if args.get("expected_sha256") else {})}
    if name=="create_directory": return "hara.files.create_directory",{"path":str(args["path"]),"parents":bool(args.get("parents",True))}
    if name=="list_directory": return "hara.files.list",{"path":str(args["path"]),**({"depth":int(args["depth"])} if "depth" in args else {}),**({"limit":int(args["limit"])} if "limit" in args else {}),**({"offset":int(args["offset"])} if "offset" in args else {})}
    if name=="move_file": return "hara.files.move",{"source":str(args["source"]),"destination":str(args["destination"])}
    if name=="copy_file": return "hara.files.copy",{"source":str(args["source"]),"destination":str(args["destination"])}
    if name=="delete_file": return "hara.files.delete",{"path":str(args["path"]),**({"expected_sha256":str(args["expected_sha256"])} if args.get("expected_sha256") else {})}
    if name=="search":
        return "hara.files.search",{"path":str(args["path"]),"pattern":str(args["pattern"]),"search_type":str(args.get("search_type","files")),**({"max_results":int(args["max_results"])} if "max_results" in args else {}),**({"include_hidden":bool(args["include_hidden"])} if "include_hidden" in args else {}),**({"ignore_case":bool(args["ignore_case"])} if "ignore_case" in args else {}),**({"file_glob":str(args["file_glob"])} if args.get("file_glob") else {}),**({"offset":int(args["offset"])} if "offset" in args else {})}
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
    if code=="PROCESS_RESULT_EXPIRED":
        return build("EXPIRED","PROCESS_RESULT",False,{"exists":False,"automatic_retry_allowed":False})
    if code=="PROCESS_SESSION_EXITED":
        return build("TERMINAL","PROCESS_STATE",False,{"session_state":"EXITED"})
    if code=="PATH_VALUE_INVALID":
        return build("INVALID_TARGET","FILESYSTEM_PATH",False,{"valid_target":False,"reason":"CONTROL_CHARACTER_OR_LENGTH"})
    if code=="FILE_PRECONDITION_FAILED":
        return build("CONFLICT","FILE_PRECONDITION",False,{"file_changed":True,"recommended_tool":"get_file_info"})
    if code=="FILE_MUTATION_BUSY":
        return build("BUSY","FILE_MUTATION_LOCK",False,{"recommended_tool":"get_file_info"})
    if code=="FILE_MUTATION_LOCK_UNAVAILABLE":
        return build("UNAVAILABLE","FILE_MUTATION_LOCK",False)
    if code=="SYMLINK_MUTATION_DENIED":
        return build("INVALID_TARGET","FILESYSTEM_SAFETY",False,{"symlink":True,"mutation_allowed":False,"recommended_tool":"get_file_info"})
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

    try:
        outbox=completion_outbox_health()
    except Exception:
        outbox={"pending":-1,"quarantined":-1,"retrying":-1,"next_retry_epoch":None}
    outbox_ok=outbox["quarantined"]==0 and outbox["pending"]>=0

    def print_outbox_health():
        print("HARA_COMMANDER_OUTBOX_PENDING="+str(outbox["pending"]))
        print("HARA_COMMANDER_OUTBOX_QUARANTINED="+str(outbox["quarantined"]))
        print("HARA_COMMANDER_OUTBOX_RETRYING="+str(outbox["retrying"]))
        print("HARA_COMMANDER_OUTBOX_NEXT_RETRY_EPOCH="+str(outbox["next_retry_epoch"] or ""))

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
        overall=lease_ok and tunnel_ok and outbox_ok
        print("HARA_COMMANDER_DOCTOR="+("PASS" if overall else "DEGRADED"))
        print("HARA_COMMANDER_AGENT_VERSION="+AGENT_VERSION)
        print("HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL")
        print("HARA_COMMANDER_LOCAL_AUTHORIZATION="+("PASS" if lease_ok else "EXPIRED"))
        print("HARA_COMMANDER_LOCAL_AUTHORIZATION_UNTIL_UTC="+lease_until)
        print("HARA_COMMANDER_OPENAI_TUNNEL="+("PASS" if tunnel_ok else "FAIL"))
        print("HARA_COMMANDER_CONTROL_PLANE_HEALTH="+("PASS" if cloud_health else "DEGRADED_OPTIONAL"))
        print("HARA_COMMANDER_TOOL_DATA_PLANE=LOCAL_DIRECT")
        print_outbox_health()
        print("SECRET_MATERIAL_EXPOSED=FALSE")
        return 0 if overall else 2

    overall=cloud_health and outbox_ok
    print("HARA_COMMANDER_DOCTOR="+("PASS" if overall else "DEGRADED"))
    print("HARA_COMMANDER_AGENT_VERSION="+AGENT_VERSION)
    print("HARA_COMMANDER_APPROVAL_MODE="+mode)
    print("HARA_COMMANDER_BACKGROUND_AUTHORIZED="+("TRUE" if mode=="PERSISTENT_TRUSTED" else "FALSE"))
    print("HARA_COMMANDER_SESSION="+("ACTIVE" if operator_session_active() else "INACTIVE"))
    print("HARA_COMMANDER_REMOTE_HEALTH="+("PASS" if cloud_health else "FAIL"))
    print("HARA_COMMANDER_LAST_HEARTBEAT_UTC="+str(runtime.get("last_successful_heartbeat_at_utc") or ""))
    print_outbox_health()
    print("SECRET_MATERIAL_EXPOSED=FALSE")
    return 0 if overall else 2

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
    if TUNNEL_UNIT_FILE.is_file() and TUNNEL_ENV_FILE.is_file():
        if tunnel_autostart_mode()=="ON":
            rc,_=_openai_tunnel_doctor(capture=True)
            if rc==0:
                _tunnel_systemctl("enable","--now",TUNNEL_UNIT_FILE.name)
                print("HARA_COMMANDER_TUNNEL_AUTOSTART=ACTIVE")
            else:
                print("HARA_COMMANDER_TUNNEL_AUTOSTART=PENDING_OPENAI_TUNNEL_DOCTOR")
        else:
            print("NEXT_COMMAND=hara-commander tunnel start")
    else:
        print("NEXT_COMMAND=hara-commander tunnel connect")
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

def tunnel_autostart_mode(config=None):
    if config is None: config=load_config()
    value=str(config.get("HARA_COMMANDER_TUNNEL_AUTOSTART") or "OFF").strip().upper()
    if value not in {"ON","OFF"}:
        raise RuntimeError("OPENAI_TUNNEL_AUTOSTART_INVALID")
    return value

def _tunnel_systemctl(*args,check=True):
    """The fixed user unit only; no sudo, arbitrary service names or shell."""
    env=os.environ.copy()
    runtime=Path("/run/user")/str(os.getuid())
    if not env.get("XDG_RUNTIME_DIR") and runtime.is_dir():
        env["XDG_RUNTIME_DIR"]=str(runtime)
    if not env.get("DBUS_SESSION_BUS_ADDRESS") and (runtime/"bus").exists():
        env["DBUS_SESSION_BUS_ADDRESS"]="unix:path="+str(runtime/"bus")
    result=subprocess.run(
        ["systemctl","--user",*args],
        env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,timeout=25,check=False,
    )
    if check and result.returncode!=0:
        raise RuntimeError("OPENAI_TUNNEL_SYSTEMD_COMMAND_FAILED")
    return result.returncode==0

def _tunnel_local_lease_active():
    try:
        config=load_config()
        with _ops_connect() as conn:
            lease=_active_verified_product_lease(conn,config)
        return bool(lease and str(lease.get("transport_mode") or "")=="LOCAL_TUNNEL")
    except Exception:
        return False

def _tunnel_lease_status_output():
    active=_tunnel_local_lease_active()
    print("HARA_COMMANDER_LOCAL_AUTHORIZATION="+("PASS" if active else "EXPIRED"))
    if not active:
        print("NEXT_AUTHORIZATION_COMMAND=hara-commander authorize")

def tunnel_start():
    if not TUNNEL_UNIT_FILE.is_file() or not TUNNEL_ENV_FILE.is_file():
        print("HARA_COMMANDER_TUNNEL=NOT_CONFIGURED")
        print("NEXT_COMMAND=hara-commander tunnel configure")
        return 12
    if not _tunnel_client_binary():
        print("HARA_COMMANDER_TUNNEL_CLIENT=MISSING")
        return 12
    _tunnel_runtime_env()
    if not _tunnel_local_lease_active():
        print("HARA_COMMANDER_TUNNEL=LOCAL_AUTHORIZATION_REQUIRED")
        print("NEXT_COMMAND=hara-commander authorize")
        return 13
    rc,_=_openai_tunnel_doctor(capture=True)
    if rc!=0:
        print("HARA_COMMANDER_TUNNEL=OPENAI_TUNNEL_DOCTOR_FAILED")
        return 14
    _tunnel_systemctl("start",TUNNEL_UNIT_FILE.name)
    active=_tunnel_systemctl("is-active","--quiet",TUNNEL_UNIT_FILE.name,check=False)
    print("HARA_COMMANDER_TUNNEL_ACTIVE="+("TRUE" if active else "FALSE"))
    print("HARA_COMMANDER_TUNNEL_AUTOSTART="+tunnel_autostart_mode())
    _tunnel_lease_status_output()
    return 0 if active else 2

def tunnel_stop():
    if not TUNNEL_UNIT_FILE.is_file():
        print("HARA_COMMANDER_TUNNEL=NOT_CONFIGURED")
        return 12
    _tunnel_systemctl("stop",TUNNEL_UNIT_FILE.name)
    print("HARA_COMMANDER_TUNNEL_ACTIVE=FALSE")
    print("HARA_COMMANDER_TUNNEL_AUTOSTART="+tunnel_autostart_mode())
    return 0

def set_tunnel_autostart(value):
    raw=str(value or "").strip().lower()
    if raw not in {"on","off"}:
        raise RuntimeError("OPENAI_TUNNEL_AUTOSTART_INVALID")
    mode=raw.upper()
    if TUNNEL_UNIT_FILE.is_file():
        if mode=="ON":
            if not TUNNEL_ENV_FILE.is_file():
                raise RuntimeError("OPENAI_TUNNEL_API_KEY_MISSING")
            _tunnel_runtime_env()
            if not _tunnel_local_lease_active():
                print("NEXT_COMMAND=hara-commander authorize")
                return 13
            rc,_=_openai_tunnel_doctor(capture=True)
            if rc!=0:
                print("HARA_COMMANDER_TUNNEL=OPENAI_TUNNEL_DOCTOR_FAILED")
                return 14
            _tunnel_systemctl("enable","--now",TUNNEL_UNIT_FILE.name)
        else:
            # Disabling boot start does not silently interrupt an active session.
            _tunnel_systemctl("disable",TUNNEL_UNIT_FILE.name)
    _set_config_value("HARA_COMMANDER_TUNNEL_AUTOSTART",mode)
    print("HARA_COMMANDER_TUNNEL_AUTOSTART="+mode)
    print("HARA_COMMANDER_TUNNEL_CONFIGURED="+("TRUE" if TUNNEL_UNIT_FILE.is_file() else "FALSE"))
    if mode=="OFF":
        print("HARA_COMMANDER_TUNNEL_CURRENT_SESSION=UNCHANGED")
        print("STOP_COMMAND=hara-commander tunnel stop")
    elif not TUNNEL_UNIT_FILE.is_file():
        print("NEXT_COMMAND=hara-commander tunnel configure")
    return 0

def configure_openai_tunnel():
    """One guided local setup, without uploading OpenAI credentials to HARA."""
    binary=_tunnel_client_binary()
    if not binary:
        print("HARA_COMMANDER_TUNNEL_CLIENT=MISSING")
        print("OPENAI_TUNNEL_DOCS=https://developers.openai.com/api/docs/guides/secure-mcp-tunnels")
        return 12
    print("OPENAI_TUNNEL_SETTINGS=https://platform.openai.com/settings/organization/tunnels")
    print("OPENAI_RUNTIME_KEY_SETTINGS=https://platform.openai.com/settings/organization/api-keys")
    print("CHATGPT_CONNECTION_TYPE=Tunnel")
    print("OPENAI_TUNNEL_DISTRIBUTION=PRIVATE_WORKSPACE_ONLY")
    if TUNNEL_ENV_FILE.exists() or TUNNEL_PROFILE_FILE.exists():
        print("HARA_COMMANDER_TUNNEL=ALREADY_CONFIGURED")
        print("NEXT_COMMAND=hara-commander tunnel status")
        return 12
    if TUNNEL_UNIT_FILE.exists():
        old=TUNNEL_UNIT_FILE.read_text(encoding="utf-8")
        if (f"ExecStart={binary} run --profile {TUNNEL_PROFILE}" not in old
            or "EnvironmentFile=%h/.config/hara-commander/openai-tunnel.env" not in old):
            raise RuntimeError("OPENAI_TUNNEL_EXISTING_UNIT_CONFLICT")
    tunnel_id=input("OpenAI tunnel_id: ").strip()
    api_key=getpass.getpass("OpenAI tunnel runtime API key (hidden): ").strip()
    if not re.fullmatch(r"tunnel_[A-Za-z0-9_-]{16,180}",tunnel_id):
        raise RuntimeError("OPENAI_TUNNEL_ID_INVALID")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{20,512}",api_key):
        raise RuntimeError("OPENAI_TUNNEL_API_KEY_INVALID")
    if any(ch.isspace() for ch in binary):
        raise RuntimeError("OPENAI_TUNNEL_BINARY_PATH_UNSAFE")
    env=os.environ.copy()
    env["CONTROL_PLANE_API_KEY"]=api_key
    mcp_command=shlex.quote(str(Path.home()/".local/bin/hara-commander"))+" mcp"
    TUNNEL_ENV_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    TUNNEL_PROFILE_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        result=subprocess.run([
            binary,"init","--sample","sample_mcp_stdio_local",
            "--profile",TUNNEL_PROFILE,"--tunnel-id",tunnel_id,
            "--health-listen-addr","127.0.0.1:0",
            "--control-plane-api-key-ref","env:CONTROL_PLANE_API_KEY",
            "--mcp-command",mcp_command,
        ],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30,check=False)
        if result.returncode!=0 or not TUNNEL_PROFILE_FILE.is_file():
            raise RuntimeError("OPENAI_TUNNEL_PROFILE_INIT_FAILED")
        if stat.S_IMODE(TUNNEL_PROFILE_FILE.stat().st_mode) & 0o077:
            raise RuntimeError("OPENAI_TUNNEL_PROFILE_PERMISSIONS_INVALID")
        fd=os.open(str(TUNNEL_ENV_FILE),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as config_file:
            config_file.write("CONTROL_PLANE_API_KEY="+api_key+"\n")
        rc,_=_openai_tunnel_doctor(capture=True)
        if rc!=0:
            raise RuntimeError("OPENAI_TUNNEL_DOCTOR_FAILED")
    except Exception:
        # Both files were absent before setup; a failed setup must not leave
        # a half-installed service or a customer credential on disk.
        TUNNEL_ENV_FILE.unlink(missing_ok=True)
        TUNNEL_PROFILE_FILE.unlink(missing_ok=True)
        print("HARA_COMMANDER_TUNNEL=SETUP_FAILED_CLEANED")
        raise
    finally:
        api_key=""
        env.pop("CONTROL_PLANE_API_KEY",None)
    unit_text=(
        "[Unit]\nDescription=H.A.R.A. Commander OpenAI Secure MCP Tunnel\n"
        "After=network-online.target\nWants=network-online.target\n\n"
        "[Service]\nType=simple\nUMask=0077\nNoNewPrivileges=true\n"
        "EnvironmentFile=%h/.config/hara-commander/openai-tunnel.env\n"
        "ExecStartPre=/usr/bin/test -r %h/.config/tunnel-client/hara-commander.yaml\n"
        f"ExecStart={binary} run --profile {TUNNEL_PROFILE}\n"
        "Restart=on-failure\nRestartSec=15\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    TUNNEL_UNIT_FILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not TUNNEL_UNIT_FILE.exists():
        fd=os.open(str(TUNNEL_UNIT_FILE),os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as output:
            output.write(unit_text)
    _tunnel_systemctl("daemon-reload")
    mode=tunnel_autostart_mode()
    if mode=="ON" and _tunnel_local_lease_active():
        _tunnel_systemctl("enable","--now",TUNNEL_UNIT_FILE.name)
        print("HARA_COMMANDER_TUNNEL_AUTOSTART=ACTIVE")
    else:
        _tunnel_systemctl("disable",TUNNEL_UNIT_FILE.name,check=False)
        print("HARA_COMMANDER_TUNNEL_AUTOSTART=PENDING_LOCAL_AUTHORIZATION" if mode=="ON" else "HARA_COMMANDER_TUNNEL_AUTOSTART=OFF")
    print("HARA_COMMANDER_OPENAI_TUNNEL_CONFIGURED=PASS")
    print("HARA_COMMANDER_TUNNEL_DATA_PLANE=LOCAL_MCP_STDIO")
    print("HARA_SERVICES_TOOL_RELAY=FALSE")
    print("NEXT_COMMAND=hara-commander authorize")
    print("CHATGPT_NEXT=Add custom MCP server > Tunnel > enter the OpenAI tunnel_id")
    return 0

def openai_tunnel_status():
    configured=TUNNEL_UNIT_FILE.is_file() and TUNNEL_ENV_FILE.is_file()
    print("HARA_COMMANDER_TUNNEL_CONFIGURED="+("TRUE" if configured else "FALSE"))
    print("HARA_COMMANDER_TUNNEL_AUTOSTART="+tunnel_autostart_mode())
    if not configured:
        print("HARA_COMMANDER_TUNNEL_ACTIVE=FALSE")
        print("NEXT_COMMAND=hara-commander tunnel configure")
        return 12
    active=_tunnel_systemctl("is-active","--quiet",TUNNEL_UNIT_FILE.name,check=False)
    print("HARA_COMMANDER_TUNNEL_ACTIVE="+("TRUE" if active else "FALSE"))
    _tunnel_lease_status_output()
    if not active:
        print("NEXT_COMMAND=hara-commander tunnel start")
        return 2
    rc,_=_openai_tunnel_doctor(capture=False)
    print("HARA_COMMANDER_TUNNEL_DOCTOR="+("PASS" if rc==0 else "DEGRADED"))
    return rc

def main():
    if "--version" in sys.argv:
        print(AGENT_VERSION); return
    if "--self-test" in sys.argv:
        self_test(); return
    if len(sys.argv)>1 and sys.argv[1]=="history":
        if sys.argv[2:]==["clear"]:
            history_clear_admin()
            return
        if len(sys.argv)>4:
            raise ValueError("HISTORY_USAGE_INVALID")
        values=sys.argv[2:]
        if any(not re.fullmatch(r"[0-9]+",item) for item in values):
            raise ValueError("HISTORY_ARGUMENT_INVALID")
        limit=int(values[0]) if values else 50
        before=int(values[1]) if len(values)==2 else 0
        show_command_history(limit,before)
        return
    if len(sys.argv)>1 and sys.argv[1]=="mcp":
        run_local_mcp_stdio(); return
    if len(sys.argv)>1 and sys.argv[1]=="doctor":
        raise SystemExit(commander_doctor())
    if len(sys.argv)==3 and sys.argv[1:3]==["outbox","status"]:
        completion_outbox_cli_status(); return
    if len(sys.argv)==4 and sys.argv[1:3]==["outbox","retry"]:
        completion_outbox_retry(sys.argv[3])
        print("HARA_COMMANDER_OUTBOX_SAME_RESULT_RETRY_QUEUED=TRUE"); return
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
    if len(sys.argv)==3 and sys.argv[1]=="tunnel" and sys.argv[2] in {"configure","connect"}:
        raise SystemExit(configure_openai_tunnel())
    if len(sys.argv)>2 and sys.argv[1]=="tunnel" and sys.argv[2]=="status":
        raise SystemExit(openai_tunnel_status())
    if len(sys.argv)>2 and sys.argv[1]=="tunnel" and sys.argv[2]=="start" and len(sys.argv)==3:
        raise SystemExit(tunnel_start())
    if len(sys.argv)>2 and sys.argv[1]=="tunnel" and sys.argv[2]=="stop" and len(sys.argv)==3:
        raise SystemExit(tunnel_stop())
    if len(sys.argv)>3 and sys.argv[1:3]==["tunnel","autostart"] and len(sys.argv)==4:
        raise SystemExit(set_tunnel_autostart(sys.argv[3]))
    if len(sys.argv)==3 and sys.argv[1:3]==["tunnel","autostart"]:
        print("HARA_COMMANDER_TUNNEL_AUTOSTART="+tunnel_autostart_mode()); return
    if "--session-start" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="start"):
        start_manual_operator_console(); return
    if len(sys.argv)>1 and sys.argv[1]=="approval-mode":
        if len(sys.argv)==2:
            print("HARA_COMMANDER_APPROVAL_MODE="+load_config().get("HARA_COMMANDER_APPROVAL_MODE","ASK_EVERY_ACTION")); return
        if len(sys.argv)==3:
            set_approval_mode(sys.argv[2]); return
        raise SystemExit(64)
    if "--session-status" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="status"):
        session_status(); return
    if "--session-stop" in sys.argv or (len(sys.argv)>1 and sys.argv[1]=="stop"):
        stop_operator_session()
        _manual_agent_systemctl("stop")
        return
    if len(sys.argv) > 1 and sys.argv[1] in {"help", "--help", "-h"}:
        print("Usage: hara-commander [start|status|stop|history [limit [before_id]]|history clear (sudo + confirmação)|mcp|authorize|outbox status|outbox retry CALL_ID|tunnel connect|tunnel configure|tunnel start|tunnel stop|tunnel status|tunnel autostart [on|off]|doctor|support|transport-mode [local-tunnel|relay]|approval-mode [ask|session|always]|help]")
        return
    if len(sys.argv) > 1:
        print("HARA_COMMANDER_UNKNOWN_COMMAND=" + str(sys.argv[1]), file=sys.stderr)
        print("Usage: hara-commander [start|status|stop|history [limit [before_id]]|history clear (sudo + confirmação)|mcp|authorize|outbox status|outbox retry CALL_ID|tunnel connect|tunnel configure|tunnel start|tunnel stop|tunnel status|tunnel autostart [on|off]|doctor|support|transport-mode [local-tunnel|relay]|approval-mode [ask|session|always]|help]", file=sys.stderr)
        raise SystemExit(64)
    config=load_config()
    RECEIPT_DIR.mkdir(parents=True,exist_ok=True,mode=0o700)
    local_portal_server=start_local_portal_server(config)
    if not try_write_runtime_status(started_at=utcnow(), error_code=None, error_at=None):
        raise RuntimeError("RUNTIME_STATUS_STARTUP_WRITE_FAILED")
    if transport_mode(config)=="LOCAL_TUNNEL":
        append_console_event("AGENT_LOCAL_TUNNEL",state="CONTROL_ONLY",action_summary="cloud_polling=disabled; telemetry_hourly=true")
        run_local_tunnel_agent_telemetry(config)
        return
    last_heartbeat=0.0
    last_product_lease=0.0
    poll_hot_until=time.monotonic()+CALL_POLL_STARTUP_HOT_SECONDS
    last_error_code=None
    last_error_write=0.0
    rate_limit_backoff_seconds=0
    rate_limit_backoff_until=0.0
    immediate_drain_count=0
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
            immediate_drain_count=0
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
            immediate_drain_count=0
            time.sleep(min(5.0, max(0.1, rate_limit_backoff_until-now)))
            continue
        call_completed=False
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
            flush_completion_outbox(config)
            outbox=completion_outbox_health()
            if outbox["quarantined"]:
                raise RuntimeError("DEVICE_COMPLETION_QUARANTINED")
            if outbox["pending"]:
                raise RuntimeError("DEVICE_COMPLETION_DELIVERY_PENDING")
            call=post_json(config["HARA_COMMANDER_URL"]+"/api/device/calls/next",config["HARA_DEVICE_TOKEN"],{})
            if call:
                poll_hot_until=time.monotonic()+CALL_POLL_HOT_WINDOW_SECONDS
                execute_call(config,call)
                immediate_drain_count+=1
                call_completed=True
            else:
                immediate_drain_count=0
            rate_limit_backoff_seconds=0
            rate_limit_backoff_until=0.0
        except Exception as exc:
            immediate_drain_count=0
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
        if call_completed and immediate_drain_count<CALL_POLL_IMMEDIATE_BATCH:
            # Check the durable outbox and authorization again before the
            # next claim. Keep execution serial and yield after eight calls.
            continue
        immediate_drain_count=0
        sleep_seconds=CALL_POLL_HOT_SECONDS if time.monotonic()<poll_hot_until else CALL_POLL_IDLE_SECONDS
        time.sleep(sleep_seconds)

if __name__=="__main__":
    main()
