#!/usr/bin/env python3
"""Read-only Cloudflare D1 -> H.A.R.A. Storage Agent event collector.

No customer command payloads; no MCP relay; no new Cloudflare endpoints.
The Storage host holds a narrowly scoped D1 READ token (never logged).
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sqlite3
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_CONFIG = Path.home()/".config/hara-commander-collector/collector.env"
DEFAULT_DATABASE = Path.home()/".local/state/hara-commander-collector/agent-events.sqlite3"
SQL = (
    "SELECT event_id,device_id,tenant_id,event_type,event_at_utc,received_at_utc,"
    "session_duration_seconds,local_lifetime_units,agent_version "
    "FROM commander_device_agent_telemetry "
    "WHERE (received_at_utc > ?) OR (received_at_utc = ? AND event_id > ?) "
    "ORDER BY received_at_utc,event_id LIMIT ?"
)
EVENT_ID_RE = re.compile(r"^HARA-AGENT-EVENT-[0-9a-f]{32}$")
ALLOWED_EVENTS = {"AGENT_START","AGENT_HEARTBEAT","AGENT_STOP"}


def config_read(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ValueError("STORAGE_COLLECTOR_CONFIG_MISSING")
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise ValueError("STORAGE_COLLECTOR_CONFIG_OWNER_INVALID")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise ValueError("STORAGE_COLLECTOR_CONFIG_PERMISSIONS_INSECURE")
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        if "=" not in text:
            raise ValueError("STORAGE_COLLECTOR_CONFIG_SYNTAX_INVALID")
        key, value = text.split("=", 1)
        if key not in {"CF_ACCOUNT_ID","CF_D1_DATABASE_ID","CF_D1_READ_TOKEN"}:
            raise ValueError("STORAGE_COLLECTOR_CONFIG_KEY_INVALID")
        result[key] = value.strip().strip('"').strip("'")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", result.get("CF_ACCOUNT_ID", "")):
        raise ValueError("STORAGE_COLLECTOR_ACCOUNT_ID_MISSING")
    if not re.fullmatch(r"[a-fA-F0-9-]{36}", result.get("CF_D1_DATABASE_ID", "")):
        raise ValueError("STORAGE_COLLECTOR_DATABASE_ID_MISSING")
    if len(result.get("CF_D1_READ_TOKEN", "")) < 20:
        raise ValueError("STORAGE_COLLECTOR_READ_TOKEN_MISSING")
    return result


def open_db(path: Path) -> sqlite3.Connection:
    if path.is_symlink():
        raise ValueError("STORAGE_COLLECTOR_DB_SYMLINK_DENIED")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    conn = sqlite3.connect(path, timeout=8)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS agent_events(
        event_id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        tenant_id TEXT NOT NULL,
        event_type TEXT NOT NULL CHECK(event_type IN ('AGENT_START','AGENT_HEARTBEAT','AGENT_STOP')),
        event_at_utc TEXT NOT NULL,
        received_at_utc TEXT NOT NULL,
        session_duration_seconds INTEGER NOT NULL,
        local_lifetime_units INTEGER NOT NULL,
        agent_version TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_agent_events_received
        ON agent_events(received_at_utc,event_id);
      CREATE INDEX IF NOT EXISTS idx_agent_events_tenant
        ON agent_events(tenant_id,received_at_utc);
      CREATE TABLE IF NOT EXISTS collector_state(
        singleton INTEGER PRIMARY KEY CHECK (singleton=1),
        last_received_at_utc TEXT NOT NULL,
        last_event_id TEXT NOT NULL
      );
      INSERT OR IGNORE INTO collector_state(singleton,last_received_at_utc,last_event_id)
        VALUES(1,'','');
    """)
    conn.commit()
    os.chmod(path,0o600)
    for suffix in ("-wal","-shm"):
        sidecar = Path(str(path)+suffix)
        if sidecar.exists():
            os.chmod(sidecar,0o600)
    return conn


def cursor(db: sqlite3.Connection) -> tuple[str,str]:
    row = db.execute(
        "SELECT last_received_at_utc,last_event_id FROM collector_state WHERE singleton=1"
    ).fetchone()
    return str(row[0]),str(row[1])


def validate_row(item: object) -> tuple:
    if not isinstance(item, dict):
        raise ValueError("COLLECTOR_EVENT_INVALID")
    event_id = str(item.get("event_id") or "")
    if not EVENT_ID_RE.fullmatch(event_id):
        raise ValueError("COLLECTOR_EVENT_ID_INVALID")
    event_type = str(item.get("event_type") or "")
    if event_type not in ALLOWED_EVENTS:
        raise ValueError("COLLECTOR_EVENT_TYPE_INVALID")
    device_id = str(item.get("device_id") or "")
    tenant_id = str(item.get("tenant_id") or "")
    when = str(item.get("event_at_utc") or "")
    received = str(item.get("received_at_utc") or "")
    if not device_id or len(device_id)>180 or not tenant_id or len(tenant_id)>180:
        raise ValueError("COLLECTOR_DEVICE_ID_INVALID")
    if not received or len(received)>64 or not when or len(when)>64:
        raise ValueError("COLLECTOR_EVENT_TIME_INVALID")
    try:
        duration = int(item["session_duration_seconds"])
        lifetime = int(item["local_lifetime_units"])
    except (ValueError,TypeError,KeyError):
        raise ValueError("COLLECTOR_COUNTER_INVALID") from None
    if not 0<=duration<=30*86400 or not 0<=lifetime<=10**12:
        raise ValueError("COLLECTOR_COUNTER_OUT_OF_RANGE")
    version = str(item.get("agent_version") or "")
    if len(version)>80:
        raise ValueError("COLLECTOR_AGENT_VERSION_INVALID")
    return event_id,device_id,tenant_id,event_type,when,received,duration,lifetime,version


def fetch_d1(config: dict, mark: tuple[str,str], limit: int) -> list[dict]:
    account = config["CF_ACCOUNT_ID"]
    database = config["CF_D1_DATABASE_ID"]
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query"
    payload = json.dumps({"sql":SQL,"params":[mark[0],mark[0],mark[1],limit]}).encode()
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization":"Bearer "+config["CF_D1_READ_TOKEN"],
            "Content-Type":"application/json",
            "Accept":"application/json",
            "User-Agent":"HARA-Commander-Storage-Collector/1",
        },
    )
    try:
        with urllib.request.urlopen(req,timeout=20) as response:
            raw=response.read(4*1024*1024+1)
            if len(raw)>4*1024*1024:
                raise RuntimeError("CLOUDFLARE_D1_RESPONSE_TOO_LARGE")
            reply=json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("CLOUDFLARE_D1_HTTP_"+str(exc.code)) from None
    except urllib.error.URLError:
        raise RuntimeError("CLOUDFLARE_D1_UNREACHABLE") from None
    if not isinstance(reply,dict) or reply.get("success") is not True:
        raise RuntimeError("CLOUDFLARE_D1_QUERY_FAILED")
    blocks=reply.get("result")
    if isinstance(blocks,dict):
        blocks=[blocks]
    if not isinstance(blocks,list) or len(blocks)!=1 or blocks[0].get("success") is False:
        raise RuntimeError("CLOUDFLARE_D1_RESPONSE_INVALID")
    rows=blocks[0].get("results")
    if not isinstance(rows,list) or len(rows)>limit:
        raise RuntimeError("CLOUDFLARE_D1_PAGE_INVALID")
    return rows


def persist(db: sqlite3.Connection, items: list[dict]) -> int:
    current=cursor(db)
    count=0
    if not items:
        return 0
    tuples=[validate_row(item) for item in items]
    for entry in tuples:
        key=(entry[5],entry[0])
        if key<=current:
            raise ValueError("COLLECTOR_CURSOR_NONMONOTONIC")
        current=key
    try:
        db.execute("BEGIN IMMEDIATE")
        for entry in tuples:
            result=db.execute(
                "INSERT OR IGNORE INTO agent_events VALUES(?,?,?,?,?,?,?,?,?)",
                entry,
            )
            count+=int(result.rowcount or 0)
        db.execute(
            "UPDATE collector_state SET last_received_at_utc=?,last_event_id=? WHERE singleton=1",
            current,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return count


def collect(db: sqlite3.Connection, fetch, *, page_limit=200, max_pages=8) -> tuple[int,int]:
    accepted=0
    pages=0
    for _ in range(max_pages):
        rows=fetch(cursor(db),page_limit)
        if not rows:
            break
        accepted+=persist(db,rows)
        pages+=1
        if len(rows)<page_limit:
            break
    return accepted,pages


def self_test():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory(prefix="hara-storage-collector-") as folder:
        with open_db(Path(folder)/"events.sqlite3") as db:
            a="HARA-AGENT-EVENT-"+("1"*32)
            b="HARA-AGENT-EVENT-"+("2"*32)
            c="HARA-AGENT-EVENT-"+("3"*32)
            def event(eid,at):
                return dict(event_id=eid,device_id="d1",tenant_id="t1",
                    event_type="AGENT_HEARTBEAT",event_at_utc=at,received_at_utc=at,
                    session_duration_seconds=3600,local_lifetime_units=4,agent_version="0.3.43")
            incoming=[event(a,"2026-10-08T20:00:00.000Z"),
                event(b,"2026-10-08T20:00:00.000Z"),
                event(c,"2026-10-08T21:00:00.000Z")]
            # Verify Cloudflare API route and parameterized read-only SQL.
            from unittest.mock import patch
            from io import BytesIO
            def fake_urlopen(request,timeout=20):
                assert request.full_url.endswith("/d1/database/22222222-2222-2222-2222-222222222222/query")
                body=json.loads(request.data)
                assert body["sql"]==SQL and body["params"]==["","","",2]
                assert body["sql"].lstrip().startswith("SELECT ")
                assert request.get_header("Authorization")=="Bearer SAMPLE_READ_TOKEN_NOT_A_SECRET"
                reply={"success":True,"result":[{"success":True,"results":incoming[:2]}]}
                return BytesIO(json.dumps(reply).encode())
            with patch.object(urllib.request,"urlopen",fake_urlopen):
                fetched=fetch_d1({
                    "CF_ACCOUNT_ID":"1"*32,
                    "CF_D1_DATABASE_ID":"22222222-2222-2222-2222-222222222222",
                    "CF_D1_READ_TOKEN":"SAMPLE_READ_TOKEN_NOT_A_SECRET",
                },("",""),2)
                assert len(fetched)==2 and fetched[0]["event_id"]==a
            print("STORAGE_COLLECTOR_READ_ONLY_D1_API=PASS")
            def mock(mark,limit):
                return [x for x in incoming
                    if (x["received_at_utc"],x["event_id"])>mark][:limit]
            assert collect(db,mock,page_limit=2,max_pages=8)==(3,2)
            assert collect(db,mock,page_limit=2,max_pages=8)==(0,0)
            assert cursor(db)==(incoming[-1]["received_at_utc"],c)
            assert db.execute("SELECT count(*) FROM agent_events").fetchone()[0]==3
            try:
                persist(db,[dict(incoming[0],event_type="UNTRUSTED")])
                raise AssertionError("unexpected event admitted")
            except ValueError:
                pass
            print("STORAGE_COLLECTOR_PAGINATION=PASS")
            print("STORAGE_COLLECTOR_IDEMPOTENCE=PASS")
            print("STORAGE_COLLECTOR_CURSOR=PASS")
            print("STORAGE_COLLECTOR_ALLOWLIST=PASS")
            print("STORAGE_COLLECTOR_SELF_TEST=PASS")


def main() -> int:
    parser=argparse.ArgumentParser(description="Read-only D1 Agent telemetry collector")
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--status",action="store_true")
    parser.add_argument("--config",type=Path,default=DEFAULT_CONFIG)
    parser.add_argument("--db",type=Path,default=DEFAULT_DATABASE)
    parser.add_argument("--page-limit",type=int,default=200)
    parser.add_argument("--max-pages",type=int,default=8)
    args=parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not 1<=args.page_limit<=500 or not 1<=args.max_pages<=20:
        raise ValueError("COLLECTOR_BATCH_LIMIT_INVALID")
    with open_db(args.db) as db:
        if args.status:
            count=db.execute("SELECT count(*) FROM agent_events").fetchone()[0]
            mark=cursor(db)
            print("STORAGE_COLLECTOR_EVENTS="+str(count))
            print("STORAGE_COLLECTOR_CURSOR_RECEIVED_UTC="+mark[0])
            print("STORAGE_COLLECTOR_READY=LOCAL")
            return 0
        conf=config_read(args.config)
        records,pages=collect(
            db,lambda mark,limit:fetch_d1(conf,mark,limit),
            page_limit=args.page_limit,max_pages=args.max_pages,
        )
        print("STORAGE_COLLECTOR_ACCEPTED="+str(records))
        print("STORAGE_COLLECTOR_PAGES="+str(pages))
        print("STORAGE_COLLECTOR_STATE=PASS")
    return 0

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("STORAGE_COLLECTOR_STATE=FAIL:"+str(exc),file=sys.stderr)
        raise SystemExit(1)
