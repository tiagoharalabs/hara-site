#!/usr/bin/env python3
"""Bounded, independently tenanted REAL DEV WSS ramp and 72h soak.

No PROD/Fleet modifications. Auth identities are QA-preseeded DEV identities,
not OAuth humans or independent physical machines. Owner-only credentials.
All child Agents, tenants and credentials are cleaned in finally; terminal
evidence never claims 24/72h until elapsed. Run under a bounded systemd unit.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, importlib.util, json, math, os
import re, secrets, shutil, signal, sqlite3, stat, subprocess, threading, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
BASE = Path("/tmp_hara/commander-full-acceptance-dev-soak")
EVIDENCE = ROOT / "docs/evidence/commander-full-acceptance-20261012/real-dev-soak"
SOURCES = ("experimental/event_v2_websocket.py", "experimental/event_v2_agent_loop.py",
           "experimental/event_v2_customer_agent.py", "experimental/event_v2_telemetry.py",
           "public/agent/linux.py")
DEV = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
MAX_AGENTS = 100
MAX_PROBE_CONCURRENCY = 20
RECOVERY_GRACE_SECONDS = 30.0
MAX_CLOUD_HTTP = 3000
PILOT_SECONDS = 20 * 60
INTERVAL_SECONDS = 10 * 60
HARD_DEADLINE_SECONDS = 72 * 60 * 60
SCRIPT_HASH = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m
fixtures = module("soak_fixtures", APP / "scripts/full_acceptance_dev_fixtures.py")
probe = module("soak_probe", APP / "scripts/commander_event_v2_transient_live_probe.py")
lab = module("soak_lab", APP / "scripts/commander_event_v2_dev_multidevice_lab.py")

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def error_code(exc):
    value = str(exc)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_:-]{0,159}", value) else type(exc).__name__.upper()

def require(value, code):
    if not value: raise RuntimeError(code)

def private_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd,"w") as f: json.dump(obj,f,indent=2); f.write("\n")

def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    os.chmod(temp,0o600); temp.replace(path)

def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else {}

def resources(pids=()):
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key,value,*_ = line.split(); mem[key.rstrip(":")] = int(value)
    rss = 0
    for pid in pids:
        p = Path("/proc") / str(pid) / "status"
        try:
            for line in p.read_text().splitlines():
                if line.startswith("VmRSS:"): rss += int(line.split()[1]) * 1024
        except FileNotFoundError: pass
    return dict(memory_available_bytes=mem["MemAvailable"]*1024,
                load_1m=os.getloadavg()[0], cpu_count=os.cpu_count(),
                agent_rss_bytes=rss)

def resource_guard(count, pids=()):
    r=resources(pids)
    require(r["memory_available_bytes"] >= (2*1024**3 + count*64*1024**2), "SOAK_MEMORY_BUDGET")
    require(r["load_1m"] < max(2,(r["cpu_count"] or 1)*0.7), "SOAK_CPU_BUDGET")
    require(r["agent_rss_bytes"] < 6*1024**3, "SOAK_AGENT_RSS_BUDGET")
    return r



def dev_backend_version():
    fixtures.guard();lab.load_dev_config()
    p=subprocess.run([str(fixtures.fresh.WRANGLER),"deployments","list","--config",str(APP/"wrangler.dev.jsonc"),"--json"],
        cwd=APP,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    require(p.returncode==0,"SOAK_DEV_VERSION_READ")
    payload=json.loads(p.stdout)
    require(isinstance(payload,list) and bool(payload),"SOAK_DEV_DEPLOYMENTS_EMPTY")
    latest=max(payload,key=lambda item:str(item.get("created_on") or ""))
    versions=latest.get("versions") or []
    require(len(versions)==1 and float(versions[0].get("percentage") or 0)==100,"SOAK_DEV_SPLIT_VERSION")
    version=str(versions[0].get("version_id") or "")
    require(re.fullmatch(r"[0-9a-f-]{36}",version),"SOAK_DEV_VERSION_ID")
    return dict(version_id=version,deployment_id=latest.get("id"),created_at_utc=latest.get("created_on"))

def bounded_recovery(connected, alive, *, clock=time.monotonic, wait=time.sleep, grace=RECOVERY_GRACE_SECONDS):
    """Allow a normal reconnect only within a measured 30-second window."""
    begin=clock()
    while True:
        require(alive(),"SOAK_AGENT_EXITED")
        elapsed=clock()-begin
        if connected():
            require(elapsed<=grace,"SOAK_RECOVERY_DEADLINE")
            return elapsed
        require(elapsed<grace,"SOAK_RECOVERY_DEADLINE")
        wait(min(.25,grace-elapsed))

def recovery_boundary_test():
    class Clock:
        def __init__(self): self.now=0.0
        def clock(self):return self.now
        def wait(self,seconds):self.now+=seconds
    c=Clock()
    require(bounded_recovery(lambda:c.now>=7,lambda:True,clock=c.clock,wait=c.wait)==7,"RECOVERY_7S")
    for availability in (None,31):
        c=Clock()
        try:bounded_recovery(lambda:availability is not None and c.now>=availability,lambda:True,clock=c.clock,wait=c.wait)
        except RuntimeError as exc:
            require(str(exc)=="SOAK_RECOVERY_DEADLINE" and c.now==30,"RECOVERY_DEADLINE_FAILURE")
        else:raise RuntimeError("RECOVERY_DEADLINE_MISSING")
    c=Clock()
    try:bounded_recovery(lambda:False,lambda:c.now<2.5,clock=c.clock,wait=c.wait)
    except RuntimeError as exc:
        require(str(exc)=="SOAK_AGENT_EXITED" and c.now==2.5,"RECOVERY_DEAD_PID")
    else:raise RuntimeError("RECOVERY_DEAD_PID_MISSING")
    return {"timed_cases":4,"grace_seconds":30,"status":"PASS"}

class Runner:
    def __init__(self, run_id, hours=72, max_agents=100, expected_backend_version=None):
        require(re.fullmatch(r"soak-[a-z0-9-]{12,48}",run_id), "SOAK_RUN_ID")
        require(hours in (24,72), "SOAK_DURATION_BOUND")
        require(max_agents in (2,10,25,100), "SOAK_AGENT_BOUND")
        self.run_id=run_id; self.home=BASE/run_id; self.ev=EVIDENCE/run_id
        require(not self.home.exists(), "SOAK_RUN_ALREADY_EXISTS")
        self.home.mkdir(parents=True,mode=0o700); self.ev.mkdir(parents=True)
        self.start=time.monotonic(); self.deadline=self.start+hours*3600
        self.max_agents=max_agents; self.hours=hours; self.rows=[]; self.lock=threading.Lock()
        self.http_calls=0; self.d1_commands=0; self.token=probe.load_token(fixtures.CANARY)
        original_d1=fixtures.fresh.d1
        def counted_d1(sql):
            self.cloud_budget(1)
            with self.lock:self.d1_commands += 1
            return original_d1(sql)
        fixtures.fresh.d1=counted_d1
        self.audit=dict(schema="hara.commander-real-dev-soak.v1",run_id=run_id,
            state="STARTING",environment="DEV",auth_mode="PRESEEDED_QA_IDENTITIES",
            actual_physical_machines=1,actual_oauth_human_logins=0,
            max_agents=max_agents,max_probe_concurrency=20,max_cloud_http=MAX_CLOUD_HTTP,
            pilot_required_seconds=PILOT_SECONDS,soak_requested_hours=hours,
            started_at_utc=now(),hard_deadline_utc=datetime.fromtimestamp(time.time()+hours*3600,timezone.utc).isoformat(),
            script_sha256=SCRIPT_HASH,source_sha256={},stages=[],observations=[],recovery=[],
            customer_content_saved=False,prod_mutations=False,
            twenty_four_hours_passed=False,seventy_two_hours_passed=False,cleanup_state="PENDING",
            recovery_grace_seconds=RECOVERY_GRACE_SECONDS,connection_recoveries=[])
        fixtures.guard(); lab.load_dev_config()
        require(fixtures.fresh.DEV_ORIGIN==DEV and probe.DEV_ORIGIN==DEV,"SOAK_DEV_ORIGIN")
        self.stage()
        if expected_backend_version:
            require(re.fullmatch(r"[0-9a-f-]{36}",expected_backend_version),"SOAK_BACKEND_EXPECTED_ID")
            self.cloud_budget(1)
            deployed=dev_backend_version()
            require(deployed["version_id"]==expected_backend_version,"SOAK_DEV_BACKEND_VERSION_MISMATCH")
            self.audit["backend_at_start"]=deployed
        self.emit()

    def stage(self):
        for relative in SOURCES:
            src=APP/relative; dst=self.home/"source/apps/commander"/relative
            require(src.is_file() and not src.is_symlink(),"SOAK_SOURCE_INVALID")
            dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            dst.write_bytes(src.read_bytes()); os.chmod(dst,0o600)
            self.audit["source_sha256"][relative]=hashlib.sha256(dst.read_bytes()).hexdigest()
        self.source=self.home/"source/apps/commander/experimental/event_v2_agent_loop.py"

    def emit(self):
        self.audit["elapsed_seconds"]=round(time.monotonic()-self.start,3)
        self.audit["cloud_application_http_and_d1_commands"]=self.http_calls
        self.audit["d1_commands"]=self.d1_commands
        self.audit["updated_at_utc"]=now()
        atomic_json(self.ev/"status.json",self.audit)

    def cloud_budget(self, amount):
        with self.lock:
            require(self.http_calls+amount <= MAX_CLOUD_HTTP,"SOAK_CLOUD_CALL_LIMIT")
            self.http_calls += amount

    def owned_pid(self,row):
        proc=row.get("proc")
        if not proc or proc.poll() is not None: return False
        pid=proc.pid
        cmd=Path("/proc")/str(pid)/"cmdline"
        try: raw=cmd.read_bytes().split(b"\0")
        except FileNotFoundError: return False
        require(str(self.source).encode() in raw,"SOAK_PID_COMMAND_MISMATCH")
        status=Path("/proc")/str(pid)
        require(status.stat().st_uid==os.getuid(),"SOAK_PID_OWNER")
        return True

    def start_agent(self,row):
        require(not self.owned_pid(row),"SOAK_AGENT_ALREADY_ACTIVE")
        env=os.environ.copy()
        env["XDG_CONFIG_HOME"]=str(row["root"]/"xdg-config")
        env["XDG_DATA_HOME"]=str(row["root"]/"xdg-data")
        env["PYTHONDONTWRITEBYTECODE"]="1"
        self.cloud_budget(1) # bounded initial durable reconciliation HTTP
        log=open(row["root"]/"agent.log","ab"); os.chmod(row["root"]/"agent.log",0o600)
        row["proc"]=subprocess.Popen(["/usr/bin/python3","-B",str(self.source)],
            env=env,cwd=row["root"],stdout=log,stderr=log,stdin=subprocess.DEVNULL)
        log.close(); row["pid"]=row["proc"].pid
        private_write(row["root"]/("agent-"+str(row["pid"])+".pid"),dict(pid=row["pid"],source=str(self.source)))

    def stop_agent(self,row):
        if self.owned_pid(row):
            row["proc"].terminate()
            try: row["proc"].wait(timeout=15)
            except subprocess.TimeoutExpired:
                require(self.owned_pid(row),"SOAK_STOP_PID_CHANGED")
                row["proc"].kill(); row["proc"].wait(timeout=5)

    def connected(self,row):
        if not self.owned_pid(row): return False
        status=read_json(row["root"]/"xdg-data/hara-commander/event-v2-status.json")
        return status.get("connected") is True and not status.get("last_error_code")


    def connection_snapshot(self,rows):
        output=[]
        for row in rows:
            status=read_json(row["root"]/"xdg-data/hara-commander/event-v2-status.json")
            output.append(dict(index=row["index"],pid=row.get("pid"),
                alive=self.owned_pid(row),connected=status.get("connected"),
                last_error_code=status.get("last_error_code"),
                connected_at_utc=status.get("connected_at_utc"),
                disconnected_at_utc=status.get("disconnected_at_utc"),
                updated_at_utc=status.get("updated_at_utc")))
        return output

    def require_connection(self,rows):
        if all(self.connected(row) for row in rows):return
        record=dict(at_utc=now(),state="RECOVERING",before=self.connection_snapshot(rows),
            grace_seconds=RECOVERY_GRACE_SECONDS)
        self.audit["connection_recoveries"].append(record);self.emit()
        begin=time.monotonic()
        try:
            elapsed=bounded_recovery(lambda:all(self.connected(row) for row in rows),
                lambda:all(self.owned_pid(row) for row in rows))
        except Exception:
            record.update(state="FAIL",observed_down_seconds=time.monotonic()-begin,
                after=self.connection_snapshot(rows))
            self.emit();raise
        record.update(state="RECOVERED",observed_down_seconds=elapsed,after=self.connection_snapshot(rows))
        self.emit()

    def wait_ready(self,rows,timeout=75):
        stop=time.monotonic()+timeout
        while time.monotonic()<stop:
            if all(self.connected(row) for row in rows): return
            time.sleep(0.5)
        raise RuntimeError("SOAK_AGENT_CONNECT_TIMEOUT")

    def create_one(self,index):
        path=fixtures.create("soak-"+self.run_id[-8:]+"-"+str(index))
        data=fixtures.read_private(path)
        row=dict(index=index,fixture_path=path,root=self.home/("device-"+str(index)),
                 tenant_id=data["tenant_id"],subject_id=data["subject_id"],subject=data["external_subject"])
        with self.lock: self.rows.append(row)
        require(data["dev_origin"]==DEV and row["tenant_id"].startswith("HARA-ACCEPT-T-"),"SOAK_FIXTURE_GUARD")
        self.cloud_budget(1)
        device_id,device_token=lab.enroll(data["pairing_token"],"acceptance-"+self.run_id+"-"+str(index))
        row["device_id"]=device_id
        folder=row["root"]/"xdg-config/hara-commander"; folder.mkdir(parents=True,mode=0o700)
        envpath=folder/"device.env"
        fd=os.open(envpath,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w") as f:
            f.write("HARA_COMMANDER_URL="+DEV+"\nHARA_DEVICE_ID="+device_id+"\nHARA_DEVICE_TOKEN="+device_token+"\nHARA_DEVICE_ARCH=x86_64\n")
        del device_token; del data
        self.start_agent(row)
        return row

    def selection(self,rows):
        q=fixtures.fresh.q
        values=",".join("("+",".join(q(v) for v in (r["tenant_id"],r["subject_id"],r["device_id"],now()))+")" for r in rows)
        fixtures.fresh.d1("INSERT INTO commander_device_selections (tenant_id,subject_id,device_id,selected_at_utc) VALUES "+values+" ON CONFLICT(tenant_id,subject_id) DO UPDATE SET device_id=excluded.device_id,selected_at_utc=excluded.selected_at_utc;")

    def health(self,row):
        self.cloud_budget(1)
        start=time.perf_counter()
        result=probe.transient_call(self.token,row["subject"],"SOAK-HEALTH-"+secrets.token_hex(12),"hara.health",{})
        probe.require_transient_common(result)
        require(result.get("state")=="COMPLETED","SOAK_HEALTH_STATE")
        require(result.get("device_id")==row["device_id"],"SOAK_CROSS_TENANT_DEVICE")
        return dict(success=True,latency_ms=(time.perf_counter()-start)*1000)

    def full_probe(self,row):
        self.cloud_budget(3)
        result=probe.run(self.token,row["subject"],row["device_id"],20)
        row["last_request_id"]=result["request_id"]; row["last_receipt"]=result["receipt_sha256"]
        return dict(success=True,latency_ms=result["invoke_ms"],replay_ms=result["replay_ms"],
                    request_id=result["request_id"],receipt_sha256=result["receipt_sha256"])

    def wave(self,rows,full=False):
        results=[]; errors=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(20,len(rows))) as pool:
            future_map={pool.submit(self.full_probe if full else self.health,row):row for row in rows}
            for f in concurrent.futures.as_completed(future_map):
                try: results.append(f.result())
                except Exception as exc: errors.append(error_code(exc))
        latencies=sorted(r["latency_ms"] for r in results)
        percentile=lambda p:latencies[min(len(latencies)-1,max(0,math.ceil(len(latencies)*p)-1))] if latencies else None
        summary=dict(count=len(rows),successful=len(results),errors=errors,
                     success_fraction=len(results)/len(rows),p95_ms=percentile(.95),p99_ms=percentile(.99),
                     request_and_receipt_bindings=[dict(request_id=r["request_id"],receipt_sha256=r["receipt_sha256"]) for r in results if "request_id" in r])
        require(not errors,"SOAK_PROBE_ERROR__"+(errors[0] if errors else "NONE"))
        require(summary["success_fraction"]>=.99,"SOAK_SUCCESS_SLO")
        require(summary["p95_ms"]<=6000 and summary["p99_ms"]<=12000,"SOAK_LATENCY_SLO")
        return summary

    def ledger(self,row):
        folder=row["root"]/"xdg-data/hara-commander/transient-ledger"
        matches=[]
        for p in folder.glob("*.json"):
            v=read_json(p)
            if v.get("request_id")==row["last_request_id"]: matches.append(v)
        require(len(matches)==1,"SOAK_LEDGER_EXECUTION_COUNT")
        require(not any("payload" in v or "arguments" in v for v in matches),"SOAK_LEDGER_CUSTOMER_ARGUMENTS")
        # The local replay ledger intentionally contains own QA device.info results.
        # We never export that result, persist remote payloads or invoke customer commands.
        return matches[0]

    def restart_replay(self,row,kind):
        before=self.ledger(row)
        oldpid=row["pid"]; self.stop_agent(row)
        if kind=="DISCONNECT": time.sleep(3)
        self.start_agent(row); self.wait_ready([row])
        self.cloud_budget(1)
        result=probe.transient_call(self.token,row["subject"],row["last_request_id"],"hara.functions.invoke",
            {"function_id":"device.info","arguments":{"argv":[]}})
        probe.require_transient_common(result)
        require(result.get("state")=="COMPLETED" and result.get("execution_mode")=="REPLAY_ONLY","SOAK_RESTART_REPLAY")
        require(result.get("receipt_sha256")==row["last_receipt"],"SOAK_RESTART_RECEIPT_CHANGED")
        after=self.ledger(row)
        require(before==after,"SOAK_RESTART_LEDGER_CHANGED")
        self.audit["recovery"].append(dict(kind=kind,old_pid=oldpid,new_pid=row["pid"],
                request_id=row["last_request_id"],same_receipt=True,ledger_unchanged=True,replay_only=True))
        self.emit()

    def cleanup_rows(self,rows):
        if not rows:return
        fixtures.guard()
        for row in rows:self.stop_agent(row)
        # Delete only exact, validated owned tenant/subject IDs. Never plans/grants
        # or template quota configuration. Discover columns once, SQL batch10.
        q=fixtures.fresh.q
        tables=fixtures.fresh.rows("SELECT name FROM sqlite_master WHERE type='table';")
        known={v["name"] for v in tables}
        ordered=["commander_device_calls","commander_device_selections","commander_device_authorization_codes",
          "commander_device_metering_events","commander_device_usage_daily","commander_device_usage_totals",
          "commander_device_agent_telemetry","commander_device_telemetry_snapshot",
          "commander_device_budget_blocks","commander_tenant_budget_baselines","commander_devices",
          "device_pairing_tokens","entitlements","commander_beta_access_requests",
          "portal_sessions","identity_bindings","users","tenants"]
        columns={}
        for table in ordered:
            if table in known: columns[table]={v["name"] for v in fixtures.fresh.rows("SELECT name FROM pragma_table_info("+q(table)+");")}
        for start in range(0,len(rows),10):
            subset=rows[start:start+10]
            require(all(r["tenant_id"].startswith("HARA-ACCEPT-T-") and r["subject_id"].startswith("HARA-ACCEPT-S-") for r in subset),"SOAK_CLEANUP_SCOPE")
            tenants=",".join(q(r["tenant_id"]) for r in subset); subjects=",".join(q(r["subject_id"]) for r in subset)
            clauses=[]
            for table in ordered:
                cols=columns.get(table,set())
                if "tenant_id" in cols:clauses.append("DELETE FROM "+table+" WHERE tenant_id IN ("+tenants+");")
                elif "subject_id" in cols:clauses.append("DELETE FROM "+table+" WHERE subject_id IN ("+subjects+");")
            fixtures.fresh.d1("\n".join(clauses))
            counts=fixtures.fresh.rows("SELECT COUNT(*) AS n FROM tenants WHERE tenant_id IN ("+tenants+");")
            require(counts==[{"n":0}],"SOAK_CLEANUP_REMAINING_TENANT")
            for row in subset:
                row["cleaned"]=True
                Path(row["fixture_path"]).unlink(missing_ok=True)
                # Own QA directory only, exact parent/run ID, no symlink traversal.
                require(row["root"].parent==self.home,"SOAK_CLEANUP_ROOT")
                if row["root"].exists():shutil.rmtree(row["root"])
        self.audit.setdefault("cleaned_fixture_count",0)
        self.audit["cleaned_fixture_count"]+=len(rows)
        self.emit()

    def run(self):
        terminal_error=None
        try:
            for count in (2,10,25,100):
                if count>self.max_agents:break
                budget=resource_guard(count,[r["pid"] for r in self.rows if "pid" in r and not r.get("cleaned")])
                previous=len(self.rows)
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    new=list(pool.map(self.create_one,range(previous,count)))
                self.selection(new); self.wait_ready(self.rows)
                require(len({r["tenant_id"] for r in self.rows})==count,"SOAK_DUPLICATE_TENANT")
                stage=dict(agent_count=count,independent_tenants=count,resources_before=budget,
                    resources_after=resources([r["pid"] for r in self.rows]),probe=self.wave(self.rows,full=True),
                    completed_at_utc=now(),state="PASS")
                self.audit["stages"].append(stage); self.audit["state"]="RAMP_RUNNING"; self.emit()
                print(json.dumps(dict(stage="RAMP",agents=count,state="PASS")),flush=True)
            keep=sorted(self.rows,key=lambda r:r["index"])[:2]
            for row,kind in zip(keep,("PROCESS_RESTART","DISCONNECT")):self.restart_replay(row,kind)
            self.cleanup_rows([r for r in self.rows if r not in keep])
            self.audit["state"]="PILOT_RUNNING"; self.audit["retained_agents"]=len(keep); self.emit()
            pilot_start=time.monotonic(); self.deadline=pilot_start+self.hours*3600
            self.audit["soak_started_at_utc"]=now()
            self.audit["hard_deadline_utc"]=datetime.fromtimestamp(time.time()+self.hours*3600,timezone.utc).isoformat()
            while time.monotonic()-pilot_start < PILOT_SECONDS:
                require(time.monotonic()<self.deadline,"SOAK_DEADLINE")
                self.require_connection(keep)
                observation=dict(at_utc=now(),elapsed_seconds=time.monotonic()-self.start,
                    resources=resource_guard(2,[r["pid"] for r in keep]),probe=self.wave(keep))
                self.audit["observations"].append(observation);self.emit()
                time.sleep(max(0,min(60,PILOT_SECONDS-(time.monotonic()-pilot_start))))
            self.audit["pilot_passed"]=True;self.audit["pilot_elapsed_seconds"]=time.monotonic()-pilot_start
            self.audit["state"]="SOAK_STARTED"; self.emit()
            print(json.dumps(dict(stage="PILOT",elapsed_seconds=self.audit["pilot_elapsed_seconds"],state="PASS",soak="STARTED")),flush=True)
            soak_start=pilot_start; next_probe=time.monotonic()
            while time.monotonic()<self.deadline:
                self.require_connection(keep)
                if time.monotonic()>=next_probe:
                    observation=dict(at_utc=now(),elapsed_seconds=time.monotonic()-self.start,
                        resources=resource_guard(2,[r["pid"] for r in keep]),probe=self.wave(keep))
                    self.audit["observations"].append(observation)
                    elapsed=time.monotonic()-soak_start
                    self.audit["soak_elapsed_seconds"]=elapsed
                    self.audit["twenty_four_hours_passed"]=elapsed>=24*3600
                    self.audit["seventy_two_hours_passed"]=elapsed>=72*3600
                    self.emit();next_probe=time.monotonic()+INTERVAL_SECONDS
                time.sleep(min(30,max(0,self.deadline-time.monotonic())))
            elapsed=time.monotonic()-soak_start
            self.audit["soak_elapsed_seconds"]=elapsed
            self.audit["state"]="DURATION_COMPLETED"
            # Requested hours count the continuous pilot plus soak, and never include setup.
            self.audit["twenty_four_hours_passed"]=elapsed>=24*3600
            self.audit["seventy_two_hours_passed"]=elapsed>=72*3600
            self.wave(keep,full=True)
        except BaseException as exc:
            terminal_error=error_code(exc)
            self.audit["agent_status_at_error"]=self.connection_snapshot([r for r in self.rows if not r.get("cleaned")])
            self.audit["state"]="FAIL";self.audit["error_code"]=terminal_error
        finally:
            try:
                self.cleanup_rows([r for r in self.rows if not r.get("cleaned")])
                self.audit["cleanup_state"]="PASS"
                self.audit["own_agents_remaining"]=sum(1 for r in self.rows if self.owned_pid(r))
                self.audit["credentials_removed"]=True
            except Exception as exc:
                self.audit["cleanup_state"]="FAIL";self.audit["cleanup_error_code"]=error_code(exc)
            self.audit["finished_at_utc"]=now();self.emit()
            print(json.dumps(dict(state=self.audit["state"],error_code=terminal_error,cleanup=self.audit["cleanup_state"])),flush=True)
        return 0 if self.audit["state"]=="DURATION_COMPLETED" and self.audit["cleanup_state"]=="PASS" else 1


def pid_guard_negative_test():
    fake=object.__new__(Runner)
    fake.source=Path("/tmp_hara/commander-qa-unrelated/never-this-command.py")
    proc=subprocess.Popen(["/usr/bin/sleep","10"],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    row={"proc":proc}
    try:
        try:fake.stop_agent(row)
        except RuntimeError as exc:
            require(str(exc)=="SOAK_PID_COMMAND_MISMATCH","PID_GUARD_WRONG_FAILURE")
        else:raise RuntimeError("PID_GUARD_MISSING")
        require(proc.poll() is None,"PID_GUARD_TERMINATED_OTHER_COMMAND")
    finally:
        proc.terminate();proc.wait(timeout=5)
    return {"status":"PASS","wrong_command_refused":True,"process_preserved_before_owned_cleanup":True}

def self_check():
    require(MAX_AGENTS==100 and MAX_PROBE_CONCURRENCY==20,"SOAK_BOUNDS")
    require(MAX_CLOUD_HTTP==3000 and PILOT_SECONDS==1200 and HARD_DEADLINE_SECONDS==259200,"SOAK_TIME_CALL_BOUNDS")
    require(DEV.endswith(".workers.dev"),"SOAK_DEV")
    require("finally:" in Path(__file__).read_text(),"SOAK_FINALLY")
    print(json.dumps(dict(self_check="PASS",scope="REAL_DEV_ONLY",max_agents=100,max_concurrency=20,max_http=3000,recovery_boundaries=recovery_boundary_test(),pid_guard=pid_guard_negative_test())))

def main():
    p=argparse.ArgumentParser();p.add_argument("--self-check",action="store_true")
    p.add_argument("--run-id");p.add_argument("--expected-backend-version");p.add_argument("--hours",type=int,default=72);p.add_argument("--max-agents",type=int,default=100)
    a=p.parse_args()
    if a.self_check:self_check();return 0
    require(bool(a.run_id),"SOAK_RUN_ID_REQUIRED")
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    return Runner(a.run_id,a.hours,a.max_agents,a.expected_backend_version).run()

if __name__=="__main__":raise SystemExit(main())
