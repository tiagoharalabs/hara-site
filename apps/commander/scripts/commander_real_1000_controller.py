#!/usr/bin/env python3
"""Bounded real DEV 1,000-Agent controller; prepare is offline, run defaults to 2.

Services retains Cloudflare/canary/fixture credentials. An owned VM receives
individual device.env credentials and five frozen Agent modules only. No
automatic retry of enrollment, D1 mutation, Agent start or application calls.
A private fsynced journal precedes every fixture mutation and all dispatches.
"""
from __future__ import annotations
import argparse, base64, concurrent.futures, hashlib, importlib.util, json, math
import os, re, secrets, shlex, shutil, stat, subprocess, threading, time, uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
BASE=Path("/tmp_hara/commander-real-1000")
EVIDENCE=ROOT/"docs/evidence/commander-full-acceptance-20261012/capacity-1000"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DBID="698afbb9-e4eb-4c4e-98f2-f5abe28219d3"
AGENT_FILES=("experimental/event_v2_websocket.py","experimental/event_v2_agent_loop.py",
             "experimental/event_v2_customer_agent.py","experimental/event_v2_telemetry.py","public/agent/linux.py")
HELPERS=("scripts/commander_real_1000_vm_manager.py","scripts/commander_real_1000_controller.py",
         "scripts/commander_real_1000_capacity_plan.py","scripts/full_acceptance_dev_fixtures.py",
         "scripts/commander_fresh_customer_dev_acceptance.py","scripts/commander_event_v2_transient_live_probe.py")
PIN_FILES=AGENT_FILES+HELPERS+("wrangler.dev.jsonc",)
CANARY=Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-product-current/apps/commander/.generated/mcp-product-dev-canary-token")
UUID_RE=r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}"

def need(ok,code):
    if not ok:raise RuntimeError(code)

def error_code(exc):
    value=str(exc)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_:.-]{0,159}",value) else type(exc).__name__.upper()

def now():return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def private_dir(path,create=False):
    if create:path.mkdir(parents=True,exist_ok=True,mode=0o700)
    s=path.lstat()
    need(stat.S_ISDIR(s.st_mode) and not stat.S_ISLNK(s.st_mode) and s.st_uid==os.getuid(),"CAPACITY_PRIVATE_DIRECTORY")
    need(stat.S_IMODE(s.st_mode)==0o700,"CAPACITY_PRIVATE_DIRECTORY_MODE")

def private_read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s=os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600,"CAPACITY_PRIVATE_FILE")
        return json.load(f)

def atomic(path,obj):
    private_dir(path.parent)
    temp=path.parent/("."+path.name+"-"+secrets.token_hex(8))
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(obj,f,indent=2,sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
        if path.exists():private_read(path)
        os.replace(temp,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)

def validate_run_id(value):
    need(re.fullmatch(r"cap1k-[a-z0-9-]{12,48}",value),"CAPACITY_RUN_ID")
    return value

def prepare(run_id,expected):
    validate_run_id(run_id);need(re.fullmatch(UUID_RE,expected),"CAPACITY_BACKEND_PIN")
    private_dir(BASE,True)
    home=BASE/run_id;need(not home.exists(),"CAPACITY_RUN_EXISTS");private_dir(home,True)
    pins={}
    for rel in PIN_FILES:
        p=APP/rel;need(p.is_file() and not p.is_symlink(),"CAPACITY_SOURCE_FILE")
        dst=home/"source/apps/commander"/rel;dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(dst,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as f:f.write(p.read_bytes())
        pins[rel]=sha(dst)
    source=(home/"source/apps/commander/public/agent/linux.py").read_text()
    need(re.search(r'AGENT_VERSION\s*=\s*["\x27]0\.3\.54["\x27]',source) is not None,"CAPACITY_SIGNED_AGENT_VERSION")
    readback=ROOT/"docs/evidence/commander-full-acceptance-20261012/full-054/dev-readback-r2.json"
    public=json.loads(readback.read_text())
    served=[x for x in public.get("signed_public54_files",[]) if x.get("path")=="agent/linux.py"]
    need(public.get("state")=="PASS" and len(served)==1 and served[0]["sha256"]==pins["public/agent/linux.py"],"CAPACITY_DEV_SIGNED_SOURCE_PIN")
    cfg=json.loads((home/"source/apps/commander/wrangler.dev.jsonc").read_text())
    need(cfg.get("name")=="hara-commander-dev-v2" and cfg.get("vars",{}).get("ENVIRONMENT")=="DEV","CAPACITY_DEV_CONFIG")
    need(cfg["d1_databases"][0]["database_id"]==DBID,"CAPACITY_DEV_DATABASE")
    need(cfg.get("vars",{}).get("DEV_SAFE_ERROR_DIAGNOSTICS_ENABLED")=="true","CAPACITY_SAFE_DIAGNOSTICS")
    manifest=dict(schema="hara.commander-real-1000-frozen.v1",run_id=run_id,expected_backend_version=expected,
        source_sha256=pins,source_frozen_at_utc=now(),controller_sha256=sha(Path(__file__).resolve()))
    atomic(home/"manifest.json",manifest)
    atomic(home/"journal.json",dict(schema="hara.commander-real-1000-private-journal.v1",
        run_id=run_id,environment="DEV",state="PREPARED",rows=[],budget_used=0,cleanup_used=0,events=[]))
    ev=EVIDENCE/run_id;private_dir(ev,True)
    atomic(ev/"prepared.json",dict(**manifest,state="PREPARED_NOT_EXECUTED",secrets_printed=False,
        bulk_load_started=False,agent_processes_launched=0))
    return dict(state="PREPARED_NOT_EXECUTED",run_id=run_id,source_sha256=pins,
                private_home=str(home),evidence=str(ev/"prepared.json"))

class Controller:
    def __init__(self,run_id,ssh_config,*,mode="short",max_agents=2,bulk_enabled=False,cleanup_only=False):
        validate_run_id(run_id);need(mode in ("short","soak24"),"CAPACITY_MODE")
        need(max_agents in (2,1000),"CAPACITY_AGENT_BOUND")
        need(max_agents==2 or bulk_enabled,"CAPACITY_BULK_OPTION_REQUIRED")
        # The current single-VM runner is the native transport smoke. Root's
        # distributed fleet assignments must be implemented before bulk launch.
        need(max_agents==2,"CAPACITY_DISTRIBUTED_ASSIGNMENTS_REQUIRED")
        self.home=BASE/run_id;private_dir(self.home)
        self.manifest=private_read(self.home/"manifest.json")
        self.journal=private_read(self.home/"journal.json")
        need(self.journal["run_id"]==run_id and self.journal["environment"]=="DEV","CAPACITY_JOURNAL_SCOPE")
        self.run_id=run_id;self.mode=mode;self.max_agents=max_agents;self.lock=threading.RLock()
        self.frozen=self.home/"source/apps/commander";self.verify_sources()
        self.plan=module("capacity_plan_"+secrets.token_hex(4),self.frozen/"scripts/commander_real_1000_capacity_plan.py")
        self.budget=self.plan.Budget(60000 if mode=="soak24" else 20000)
        self.budget.used=self.journal["budget_used"];self.budget.cleanup_used=self.journal["cleanup_used"]
        self.fresh=module("capacity_fresh_"+secrets.token_hex(4),self.frozen/"scripts/commander_fresh_customer_dev_acceptance.py")
        self.probe=module("capacity_probe_"+secrets.token_hex(4),self.frozen/"scripts/commander_event_v2_transient_live_probe.py")
        self.original_d1=self.fresh.d1
        self.fresh.WRANGLER=ROOT/"node_modules/.bin/wrangler"
        # frozen helper's APP/DEV_CONFIG already point at the frozen source tree.
        self.fresh.d1=lambda sql:self.d1(sql)
        self.original_post=self.probe.post_json
        self.probe.post_json=lambda path,token,body:self.post(path,token,body)
        self.token=self.probe.load_token(CANARY) if not cleanup_only else ""
        config=private_read(Path(ssh_config))
        need(set(config)=={"config_path","host_alias","manager_path","guest_base_parent","vm_uuid","host_pin_file","profile"},"CAPACITY_SSH_FIELDS")
        need(config["host_alias"]=="cap1000" and re.fullmatch(UUID_RE,config["vm_uuid"]),"CAPACITY_VM_IDENTITY")
        need(re.fullmatch(r"/home/[a-z0-9_-]+/hara-capacity1000",config["guest_base_parent"]),"CAPACITY_GUEST_SCOPE")
        need(config["manager_path"]==config["guest_base_parent"]+"/commander_real_1000_vm_manager.py","CAPACITY_MANAGER_PATH")
        sshpath=Path(config["config_path"])
        s=sshpath.lstat()
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600,"CAPACITY_SSH_CONFIG")
        self.ssh=["ssh","-F",str(sshpath),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes",config["host_alias"]]
        self.remote_cmd=" ".join(shlex.quote(v) for v in ("/usr/bin/python3","-B",config["manager_path"],
                        "--base",config["guest_base_parent"]+"/"+run_id))
        self.host_pin=private_read(Path(config["host_pin_file"]))["libvirt_memory_pin"]
        need(self.host_pin["uuid"]==config["vm_uuid"] and self.host_pin["memory_kib"]==60*1024*1024 and
             self.host_pin["current_memory_kib"]==60*1024*1024 and self.host_pin["vcpus"]==8,"CAPACITY_LIBVIRT_PREPARED_PIN")
        self.config=config;self.start=time.monotonic();self.started_wall=time.time()
        self.deadline=self.start+(7200 if mode=="short" else 25*3600)
        self.ev=EVIDENCE/run_id;private_dir(self.ev,True)
        self.audit=dict(schema="hara.commander-real-1000-execution.v1",run_id=run_id,environment="DEV",
            state=self.journal["state"],started_at_utc=now(),max_agents=max_agents,mode=mode,
            expected_backend_version=self.manifest["expected_backend_version"],source_sha256=self.manifest["source_sha256"],
            vm_uuid=config["vm_uuid"],auth_mode="EXACT_OWNED_PRESEEDED_QA",actual_human_oauth_logins=0,
            physical_agent_hosts=1,max_create_concurrency=2,max_probe_concurrency=20,
            stages=[],waves=[],observations=[],cleanup_state="PENDING",customer_payloads_exported=False,
            real_1000_short_passed=False,real_1000_24h_passed=False,real_72h_passed=False,
            cloud_internal_rpc_counter="UNKNOWN_NOT_CERTIFIED",D1_statement_counter="UNKNOWN_NOT_CERTIFIED",
            WS_control_frame_counter="UNKNOWN_NOT_CERTIFIED",cloud_metrics_collected=False,
            free_and_pro_quota_cases=False,owned_mutation_replay_cases=False,recovery_cases_pass=False)
    def verify_sources(self):
        need(sha(Path(__file__).resolve())==self.manifest["controller_sha256"],"CAPACITY_CONTROLLER_DRIFT")
        for rel,value in self.manifest["source_sha256"].items():
            p=self.home/"source/apps/commander"/rel
            need(p.is_file() and not p.is_symlink() and sha(p)==value,"CAPACITY_FROZEN_SOURCE_DRIFT")
    def save(self):
        with self.lock:atomic(self.home/"journal.json",self.journal)
    def update_row(self,row,**changes):
        with self.lock:row.update(changes);self.save()
    def host_runtime_pin(self):
        # Read-only, own UUID, pinned memory and host reserve after VM allocation.
        script="""import json,os,pathlib,subprocess,sys,time,xml.etree.ElementTree as E
p=subprocess.run(['sudo','-n','virsh','-c','qemu:///system','dumpxml',sys.argv[1]],capture_output=True,text=True,timeout=20)
assert p.returncode==0
r=E.fromstring(p.stdout)
m={}
for l in pathlib.Path('/proc/meminfo').read_text().splitlines():
 k,v,*_=l.split()
 if k=='MemAvailable:':m['memory_available_bytes']=int(v)*1024
print(json.dumps(dict(uuid=r.findtext('uuid'),memory_kib=int(r.findtext('memory')),current_memory_kib=int(r.findtext('currentMemory')),vcpus=int(r.findtext('vcpu')),cpu_count=os.cpu_count(),quota=int(r.findtext('cputune/global_quota') or '-1'),period=int(r.findtext('cputune/global_period') or '0'),at_unix=time.time(),**m)))"""
        cmd=" ".join(shlex.quote(x) for x in ("/usr/bin/python3","-c",script,self.config["vm_uuid"]))
        p=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",cmd],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        need(p.returncode==0,"CAPACITY_HOST_PIN_READ")
        value=json.loads(p.stdout)
        need(value["uuid"]==self.config["vm_uuid"] and value["memory_kib"]==60*1024*1024 and
             value["current_memory_kib"]==60*1024*1024 and value["vcpus"]==8,"CAPACITY_LIBVIRT_RUNTIME_PIN")
        need(value["memory_available_bytes"]>=16*1024**3,"CAPACITY_HOST_RUNTIME_MEMORY")
        need(value["period"]>0 and 0<value["quota"]<=value["period"]*value["cpu_count"]*.25,"CAPACITY_HOST_VM_CPU_CAP")
        return value
    def emit(self):
        with self.lock:
            self.audit.update(elapsed_seconds=round(time.monotonic()-self.start,3),updated_at_utc=now(),
                application_http_and_d1_commands=self.budget.used,cleanup_commands=self.budget.cleanup_used,
                cleanup_reserved_commands=self.budget.cleanup_reserve)
            atomic(self.ev/"status.json",self.audit)
    def before(self,kind,*,cleanup=False,amount=1):
        with self.lock:
            self.budget.before_dispatch(amount,cleanup=cleanup)
            self.journal["budget_used"]=self.budget.used;self.journal["cleanup_used"]=self.budget.cleanup_used
            self.journal["events"].append(dict(kind=kind,at_utc=now(),state="DISPATCH_RESERVED",
                amount=amount,cleanup=cleanup))
            self.save()
    def d1(self,sql,cleanup=False):
        self.before("D1_COMMAND",cleanup=cleanup)
        return self.original_d1(sql)
    def rows(self,sql,cleanup=False):
        out=self.d1(sql,cleanup=cleanup);value=out[-1].get("results")
        need(isinstance(value,list),"CAPACITY_D1_ROWS");return value
    def post(self,path,token,body):
        self.before("APPLICATION_HTTP")
        return self.original_post(path,token,body)
    def backend(self):
        self.before("DEV_VERSION_READ")
        p=subprocess.run([str(self.fresh.WRANGLER),"deployments","list","--config",
            str(self.frozen/"wrangler.dev.jsonc"),"--json"],cwd=self.frozen,text=True,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        need(p.returncode==0,"CAPACITY_BACKEND_READ")
        value=json.loads(p.stdout);need(isinstance(value,list) and bool(value),"CAPACITY_BACKEND_EMPTY")
        latest=max(value,key=lambda item:str(item.get("created_on") or ""))
        versions=latest.get("versions") or []
        need(len(versions)==1 and versions[0].get("percentage")==100,"CAPACITY_BACKEND_SPLIT")
        version=versions[0].get("version_id")
        need(version==self.manifest["expected_backend_version"],"CAPACITY_BACKEND_DRIFT")
        return dict(version_id=version,checked_at_utc=now())
    def remote(self,body,*,timeout=150):
        p=subprocess.run(self.ssh+[self.remote_cmd],input=json.dumps(body,separators=(",",":")),
            text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        try:out=json.loads(p.stdout)
        except Exception:raise RuntimeError("CAPACITY_REMOTE_OUTCOME_UNKNOWN") from None
        need(isinstance(out,dict),"CAPACITY_REMOTE_OBJECT")
        if p.returncode or out.get("state")!="PASS":
            code=out.get("code")
            raise RuntimeError("CAPACITY_REMOTE_"+(code if isinstance(code,str) and re.fullmatch(r"[A-Z0-9_]{1,96}",code) else "FAILED"))
        return out
    def init_vm(self):
        self.journal["remote_init"]="DISPATCH_RESERVED";self.save()
        hashes={name:self.manifest["source_sha256"][name] for name in AGENT_FILES}
        out=self.remote(dict(action="init",run_id=self.run_id,source_sha256=hashes,
            sources_b64={name:base64.b64encode((self.frozen/name).read_bytes()).decode() for name in AGENT_FILES},
            runtime_seconds=7200 if self.mode=="short" else 25*3600,
            manager_sha256=self.manifest["source_sha256"]["scripts/commander_real_1000_vm_manager.py"],profile=self.config["profile"]))
        self.journal["remote_init"]="PASS";self.audit["vm_supervisor"]=out;self.save();self.emit()
    def allocate_fixture(self,index):
        # Registration survives D1/enroll timeout or partial SQL creation.
        suffix=hashlib.sha256(self.run_id.encode()).hexdigest()[:12]+"-"+str(index)+"-"+secrets.token_hex(8)
        prefix="HARA-CAP1K-"
        row=dict(index=index,tenant_id=prefix+"T-"+suffix,subject_id=prefix+"S-"+suffix,
            identity_id=prefix+"I-"+suffix,entitlement_id=prefix+"E-"+suffix,pairing_id=prefix+"P-"+suffix,
            external_subject="cap1k-"+suffix,issuer=self.fresh.ISSUER,state="PLANNED",collision_checked=False)
        root=self.home/("fixture-"+str(index));private_dir(root,True)
        data=dict(pairing_token=secrets.token_urlsafe(32),created_at_utc=now())
        atomic(root/"secrets.json",data);row["private_root"]=str(root)
        with self.lock:
            need(not any(v["index"]==index for v in self.journal["rows"]),"CAPACITY_FIXTURE_INDEX_DUPLICATE")
            self.journal["rows"].append(row);self.save()
        return row,data
    def create_one(self,index):
        row,data=self.allocate_fixture(index);q=self.fresh.q
        existing=self.rows("SELECT tenant_id FROM tenants WHERE tenant_id="+q(row["tenant_id"])+
            " UNION ALL SELECT subject_id AS tenant_id FROM users WHERE subject_id="+q(row["subject_id"])+
            " UNION ALL SELECT identity_binding_id AS tenant_id FROM identity_bindings WHERE issuer="+q(row["issuer"])+
            " AND external_subject="+q(row["external_subject"])+";")
        need(not existing,"CAPACITY_IDENTITY_COLLISION")
        self.update_row(row,collision_checked=True)
        stamp=data["created_at_utc"];expiry=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(timespec="seconds").replace("+00:00","Z")
        sql=f"""
INSERT INTO tenants VALUES ({q(row['tenant_id'])},'Capacity QA DEV','ACTIVE','DEV',{q(stamp)});
INSERT INTO users(subject_id,tenant_id,oidc_issuer,oidc_subject,email,display_name,state,role,created_at_utc)
VALUES ({q(row['subject_id'])},{q(row['tenant_id'])},{q(row['issuer'])},{q(row['external_subject'])},NULL,'Capacity QA DEV','ACTIVE','OWNER',{q(stamp)});
INSERT INTO identity_bindings VALUES ({q(row['identity_id'])},{q(row['subject_id'])},'PRIMARY_OIDC',{q(row['issuer'])},{q(row['external_subject'])},'ACTIVE',{q(stamp)},NULL);
INSERT INTO entitlements VALUES ({q(row['entitlement_id'])},{q(row['tenant_id'])},{q(row['subject_id'])},'TRIAL','ACTIVE',{q(stamp)},NULL);
INSERT INTO device_pairing_tokens(pairing_id,token_hash,tenant_id,subject_id,created_at_utc,expires_at_utc,consumed_at_utc,superseded_at_utc)
VALUES ({q(row['pairing_id'])},{q(self.fresh.b64url_sha256(data['pairing_token']))},{q(row['tenant_id'])},{q(row['subject_id'])},{q(stamp)},{q(expiry)},NULL,NULL);
"""
        self.update_row(row,state="D1_CREATE_DISPATCH_RESERVED")
        self.d1(sql);self.update_row(row,state="D1_CREATED")
        self.before("ENROLL_HTTP");self.update_row(row,state="ENROLL_DISPATCH_RESERVED")
        # This helper performs one HTTP request, no retry, and only returns own device credentials.
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError,URLError
        request=Request(DEV+"/api/device/enroll",data=json.dumps(dict(pairing_token=data["pairing_token"],
            device_name=self.run_id+"-"+str(index),platform="LINUX",architecture="x86_64",
            agent_version="0.3.54",approval_mode="PERSISTENT_TRUSTED")).encode(),method="POST",
            headers={"content-type":"application/json","accept":"application/json","user-agent":"HARA-Commander-Capacity-DEV/1"})
        try:
            with urlopen(request,timeout=20) as response:value=json.loads(response.read())
        except HTTPError as exc:raise RuntimeError("CAPACITY_ENROLL_HTTP_"+str(exc.code)) from None
        except (URLError,TimeoutError):raise RuntimeError("CAPACITY_ENROLL_OUTCOME_UNKNOWN") from None
        device=value.get("device_id");token=value.get("device_token")
        need(isinstance(device,str) and re.fullmatch(r"HARA-DEVICE-[A-Za-z0-9._:-]{1,180}",device),"CAPACITY_DEVICE_ID")
        need(isinstance(token,str) and re.fullmatch(r"[A-Za-z0-9._~-]{32,512}",token),"CAPACITY_DEVICE_TOKEN")
        atomic(Path(row["private_root"])/"device.json",dict(device_id=device,device_token=token))
        self.update_row(row,device_id=device,state="ENROLLED")
        return row
    def select(self,rows):
        q=self.fresh.q;values=",".join("("+",".join(q(v) for v in (r["tenant_id"],r["subject_id"],r["device_id"],now()))+")" for r in rows)
        self.d1("INSERT INTO commander_device_selections(tenant_id,subject_id,device_id,selected_at_utc) VALUES "+
            values+" ON CONFLICT(tenant_id,subject_id) DO UPDATE SET device_id=excluded.device_id,selected_at_utc=excluded.selected_at_utc;")
    def start_batch(self,rows):
        for row in rows:self.update_row(row,state="VM_START_DISPATCH_RESERVED")
        # Count Agent's initial durable reconciliation conservatively before start.
        self.before("AGENT_DURABLE_RECONCILIATION_ALLOWANCE",amount=len(rows))
        records=[dict(index=r["index"],**private_read(Path(r["private_root"])/"device.json")) for r in rows]
        result=self.remote(dict(action="start",records=records))
        by_index={r["index"]:r for r in result["started"]}
        need(set(by_index)=={r["index"] for r in rows},"CAPACITY_VM_START_BINDINGS")
        for row in rows:
            need(by_index[row["index"]]["device_id"]==row["device_id"],"CAPACITY_VM_DEVICE_BINDING")
            self.update_row(row,state="STARTED",pid=by_index[row["index"]]["pid"],start_ticks=by_index[row["index"]]["start_ticks"])
        self.save()
    def status(self,count,*,require_connected=True):
        self.verify_sources();out=self.remote(dict(action="status"))
        rows=out["rows"];need(len(rows)==count,"CAPACITY_VM_COUNT")
        expected={r["index"]:r for r in self.journal["rows"] if r.get("pid")}
        need(len(expected)==count,"CAPACITY_JOURNAL_COUNT")
        for row in rows:
            own=expected.get(row["index"]);need(own is not None and row["device_id"]==own["device_id"],"CAPACITY_VM_STATUS_BINDING")
            need(row.get("pid")==own["pid"] and row.get("start_ticks")==own["start_ticks"],"CAPACITY_VM_STATUS_PID")
            need(row["alive"] is True,"CAPACITY_AGENT_LOST")
            if require_connected:need(row["connected"] is True and not row.get("error_code"),"CAPACITY_CONNECTION_LOST")
        host=self.host_runtime_pin()
        self.audit["latest_host_runtime_pin"]=host
        out["resources"]["nominal_vm_memory_bytes"]=60*1024**3
        out["resources"]["libvirt_nominal_memory_verified"]=True
        out["resources"]["bound_domain_uuid"]=self.config["vm_uuid"]
        stage_count=100 if count in (0,2) else count
        self.plan.guest_stage_preflight(out["resources"],stage_count,alive_agents=count,
            rss_total_bytes=out["rss_total_bytes"],rss_p99_bytes=out["rss_p99_bytes"])
        return out
    def ready(self,count):
        until=time.monotonic()+75
        while time.monotonic()<until:
            out=self.status(count,require_connected=False)
            if all(r["connected"] and not r.get("error_code") for r in out["rows"]):return out
            time.sleep(.5)
        raise RuntimeError("CAPACITY_CONNECT_DEADLINE")
    def check_response(self,obj,device):
        self.probe.require_transient_common(obj)
        need(obj.get("state")=="COMPLETED","CAPACITY_CALL_NOT_COMPLETED")
        need(obj.get("device_id")==device,"CAPACITY_TENANT_OR_DEVICE_MISMATCH")
    def full_probe(self,row,attempt):
        request=attempt["invoke_request_id"];subject=row["external_subject"];device=row["device_id"]
        start=time.perf_counter()
        result=self.probe.transient_call(self.token,subject,attempt["health_request_id"],"hara.health",{})
        self.check_response(result,device)
        invoke_start=time.perf_counter()
        first=self.probe.transient_call(self.token,subject,request,"hara.functions.invoke",
            {"function_id":"device.info","arguments":{"argv":[]}})
        invoke_ms=(time.perf_counter()-invoke_start)*1000
        self.check_response(first,device)
        receipt=first.get("receipt_sha256")
        need(isinstance(receipt,str) and re.fullmatch(r"[0-9a-f]{64}",receipt),"CAPACITY_RECEIPT")
        need(first.get("execution_mode")=="EXECUTE_OR_REPLAY" and first.get("usage",{}).get("state")=="COMMITTED","CAPACITY_FIRST_COMMIT")
        replay=self.probe.transient_call(self.token,subject,request,"hara.functions.invoke",
            {"function_id":"device.info","arguments":{"argv":[]}})
        self.check_response(replay,device)
        need(replay.get("execution_mode")=="REPLAY_ONLY" and replay.get("usage",{}).get("state")=="COMMITTED","CAPACITY_REPLAY_COMMIT")
        need(replay.get("receipt_sha256")==receipt and replay.get("learning_signal",{}).get("outcome")=="REPLAYED","CAPACITY_REPLAY_RECEIPT")
        expected=row.get("expected_consumed_units",0)+1
        for usage in (first.get("usage",{}),replay.get("usage",{})):
            need(usage.get("consumed_units")==expected and usage.get("remaining_units")==10000-expected,"CAPACITY_EXACT_ONE_FREE_DEBIT")
        self.update_row(row,last_request_id=request,last_receipt=receipt,expected_consumed_units=expected)
        return dict(latency_ms=invoke_ms,cycle_ms=(time.perf_counter()-start)*1000,receipt_sha256=receipt,
                    exact_one_free_debit=True)
    def wave(self,rows,full=True):
        record=dict(sequence=len(self.audit["waves"])+1,state="RUNNING",kind="FULL" if full else "HEALTH",
            started_at_utc=now(),attempts=[dict(index=r["index"],state="PENDING",
            health_request_id="CAP1K-HEALTH-"+uuid.uuid4().hex,
            invoke_request_id="CAP1K-INVOKE-"+uuid.uuid4().hex) for r in rows])
        self.audit["waves"].append(record);self.emit()
        def call(row,attempt):
            start=time.perf_counter()
            try:
                if full:return self.full_probe(row,attempt)
                value=self.probe.transient_call(self.token,row["external_subject"],attempt["health_request_id"],"hara.health",{})
                self.check_response(value,row["device_id"])
                return dict(latency_ms=(time.perf_counter()-start)*1000)
            finally:attempt.update(elapsed_ms=(time.perf_counter()-start)*1000,completed_at_utc=now())
        successes=[];errors=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(20,len(rows))) as pool:
            futures={pool.submit(call,row,attempt):attempt for row,attempt in zip(rows,record["attempts"])}
            for future in concurrent.futures.as_completed(futures):
                attempt=futures[future]
                try:
                    value=future.result();successes.append(value);attempt.update(state="PASS",**value)
                except Exception as exc:
                    code=error_code(exc);errors.append(code);attempt.update(state="FAIL",error_code=code,error_class=type(exc).__name__)
                    if isinstance(exc,self.probe.ProbeError) and exc.safe_diagnostics:attempt["http_diagnostics"]=dict(exc.safe_diagnostics)
        latencies=sorted(x["latency_ms"] for x in successes)
        pct=lambda p:latencies[min(len(latencies)-1,max(0,math.ceil(len(latencies)*p)-1))] if latencies else None
        summary=dict(count=len(rows),successful=len(successes),errors=errors,p95_ms=pct(.95),p99_ms=pct(.99))
        record.update(state="FAIL" if errors else "PASS",summary=summary,completed_at_utc=now())
        self.save();self.emit()
        need(not errors,"CAPACITY_PROBE_ERROR_"+(errors[0] if errors else "NONE"))
        if full:
            proof=self.remote(dict(action="ledgers",records=[dict(index=r["index"],request_id=r["last_request_id"]) for r in rows]))
            by_index={r["index"]:r for r in proof["ledgers"]}
            need(len(by_index)==len(rows) and all(by_index[r["index"]]["receipt_sha256"]==r["last_receipt"] for r in rows),"CAPACITY_EXACT_LEDGER_RECEIPTS")
            record["local_ledger_bindings"]=proof["ledgers"];self.emit()
        need(summary["p95_ms"]<=6000 and summary["p99_ms"]<=12000,"CAPACITY_LATENCY_SLO")
        return summary
    def cleanup(self):
        self.audit["cleanup_state"]="RUNNING";self.emit();errors=[]
        if self.journal.get("remote_init"):
            try:
                result=self.remote(dict(action="cleanup"))
                need(result.get("remaining")==0 and result.get("credentials_removed") is True,"CAPACITY_VM_CLEANUP")
                self.audit["vm_cleanup"]=result
            except Exception as exc:errors.append(error_code(exc))
        rows=self.journal["rows"]
        eligible=[r for r in rows if r.get("collision_checked") is True]
        if eligible:
            q=self.fresh.q
            schema=self.rows("SELECT t.name AS table_name,p.name AS column_name FROM sqlite_master AS t "+
                "JOIN pragma_table_info(t.name) AS p WHERE t.type='table' AND t.name NOT LIKE 'sqlite_%';",cleanup=True)
            columns={}
            for item in schema:
                name=item["table_name"];need(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name),"CAPACITY_TABLE_NAME")
                columns.setdefault(name,set()).add(item["column_name"])
            ordered=["commander_device_calls","commander_device_selections","commander_device_authorization_codes",
                "commander_device_metering_events","commander_device_usage_daily","commander_device_usage_totals",
                "commander_device_agent_telemetry","commander_device_telemetry_snapshot","commander_device_budget_blocks",
                "commander_tenant_budget_baselines","commander_devices","device_pairing_tokens","entitlements",
                "commander_beta_access_requests","portal_sessions","identity_bindings","users","tenants"]
            extras=sorted(t for t,c in columns.items() if t not in ordered and ("tenant_id" in c or "subject_id" in c))
            ordered=extras+ordered
            owned_prefix="HARA-CAP1K-";run_prefix=hashlib.sha256(self.run_id.encode()).hexdigest()[:12]
            for offset in range(0,len(eligible),10):
                subset=eligible[offset:offset+10]
                need(all(r["tenant_id"].startswith(owned_prefix+"T-"+run_prefix+"-") and
                    r["subject_id"].startswith(owned_prefix+"S-"+run_prefix+"-") for r in subset),"CAPACITY_CLEANUP_SCOPE")
                tenants=",".join(q(r["tenant_id"]) for r in subset);subjects=",".join(q(r["subject_id"]) for r in subset)
                statements=[];checks=[]
                for table in ordered:
                    c=columns.get(table,set())
                    clause="tenant_id IN ("+tenants+")" if "tenant_id" in c else ("subject_id IN ("+subjects+")" if "subject_id" in c else None)
                    if clause:
                        statements.append("DELETE FROM "+table+" WHERE "+clause+";")
                        checks.append("SELECT "+q(table)+" AS table_name,COUNT(*) AS n FROM "+table+" WHERE "+clause)
                self.d1("\n".join(statements),cleanup=True)
                remaining=self.rows(" UNION ALL ".join(checks)+";",cleanup=True)
                need(all(r["n"]==0 for r in remaining),"CAPACITY_CLEANUP_ROWS_REMAIN")
                for row in subset:row["state"]="CLEANED"
                self.save()
        if not errors:
            for row in rows:
                root=Path(row["private_root"]);need(root.parent==self.home and root.name=="fixture-"+str(row["index"]),"CAPACITY_PRIVATE_CLEANUP_SCOPE")
                if root.exists():private_dir(root);shutil.rmtree(root)
            self.journal["cleanup_state"]="PASS";self.audit["cleanup_state"]="PASS"
            self.audit["cleaned_fixture_count"]=len(rows);self.audit["credentials_removed"]=True
        else:
            self.journal["cleanup_state"]="FAIL";self.audit["cleanup_state"]="FAIL";self.audit["cleanup_errors"]=errors
        self.save();self.emit()
        need(not errors,"CAPACITY_CLEANUP_FAILED")
    def run(self):
        need(self.journal["state"]=="PREPARED","CAPACITY_NO_AUTOMATIC_RERUN")
        self.journal["state"]="STARTING";self.audit["state"]="STARTING";self.save();self.emit()
        terminal=None;proof=None
        try:
            self.audit["backend_start"]=self.backend();self.host_runtime_pin();self.init_vm();self.status(0)
            stages=(2,) if self.max_agents==2 else (100,250,500,1000)
            for count in stages:
                self.backend()
                if self.journal["rows"]:
                    last=self.status(len(self.journal["rows"]))
                    self.plan.guest_stage_preflight(last["resources"],count,alive_agents=len(self.journal["rows"]),
                        rss_total_bytes=last["rss_total_bytes"],rss_p99_bytes=last["rss_p99_bytes"])
                previous=len(self.journal["rows"])
                for offset in range(previous,count,2):
                    self.verify_sources()
                    need(time.monotonic()<self.deadline,"CAPACITY_HARD_DEADLINE")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                        new=list(pool.map(self.create_one,range(offset,min(count,offset+2))))
                    self.start_batch(new)
                rows=sorted(self.journal["rows"],key=lambda r:r["index"])
                self.select(rows[previous:])
                snapshot=self.ready(count)
                need(len({r["tenant_id"] for r in rows})==count,"CAPACITY_INDEPENDENT_TENANTS")
                result=self.wave(rows)
                self.audit["stages"].append(dict(agents=count,tenants=count,resources=snapshot["resources"],
                    rss_total_bytes=snapshot["rss_total_bytes"],probe=result,state="PASS",at_utc=now()))
                self.audit["state"]="RAMP_RUNNING";self.emit()
                print(json.dumps(dict(stage="RAMP",agents=count,state="PASS")),flush=True)
            rows=sorted(self.journal["rows"],key=lambda r:r["index"])
            continuous_start=time.monotonic()
            seconds=30 if self.max_agents==2 else (1200 if self.mode=="short" else 86400)
            end=continuous_start+seconds;next_health=continuous_start;next_full=continuous_start+8640
            self.audit["state"]="SMOKE_RUNNING" if self.max_agents==2 else "CONTINUOUS_RUNNING";self.emit()
            while time.monotonic()<end:
                need(time.monotonic()<self.deadline,"CAPACITY_HARD_DEADLINE")
                snapshot=self.status(len(rows))
                if time.monotonic()>=next_health:
                    self.backend()
                    subset=rows if len(rows)<=20 else [rows[(len(self.audit["observations"])*20+j)%len(rows)] for j in range(20)]
                    result=self.wave(subset,full=False)
                    self.audit["observations"].append(dict(at_utc=now(),elapsed_seconds=time.monotonic()-continuous_start,
                        connected_agents=len(rows),resources=snapshot["resources"],probe=result))
                    next_health=time.monotonic()+60;self.emit()
                if self.mode=="soak24" and self.max_agents==1000 and time.monotonic()>=next_full:
                    self.wave(rows);next_full+=8640
                time.sleep(max(0,min(5,end-time.monotonic())))
            final=self.wave(rows);self.audit["backend_end"]=self.backend()
            proof=dict(backend_pin_unchanged=True,source_pins_match=True,actual_agents=len(rows),
                actual_tenants=len({r["tenant_id"] for r in rows}),connected_agents=len(rows),
                agents_with_valid_receipts=len({r["index"] for r in rows if r.get("last_receipt")}),
                continuous_seconds=time.monotonic()-continuous_start,agent_losses=0,
                tenant_or_receipt_mismatches=0,duplicate_executions_or_charges=0,unexpected_errors=0,
                p95_ms=max(w["summary"]["p95_ms"] for w in self.audit["waves"]),
                p99_ms=max(w["summary"]["p99_ms"] for w in self.audit["waves"]),cleanup_state="PENDING",
                cloud_metrics_collected=False,free_and_pro_quota_cases=False,owned_mutation_replay_cases=False,
                recovery_cases_pass=False)
            self.audit["observation"]=proof
            self.audit["state"]="SMOKE_COMPLETED" if self.max_agents==2 else "DURATION_COMPLETED"
        except BaseException as exc:
            terminal=error_code(exc);self.audit.update(state="FAIL",error_code=terminal,failed_at_utc=now());self.emit()
        finally:
            try:self.cleanup()
            except BaseException as exc:self.audit.update(cleanup_state="FAIL",cleanup_error_code=error_code(exc))
            self.journal["state"]=self.audit["state"];self.save()
            if proof:
                proof["cleanup_state"]=self.audit["cleanup_state"]
                verdict=self.plan.stage_verdict(proof,self.mode);self.audit["gate_verdict"]=verdict
                self.audit["real_1000_short_passed"]=self.mode=="short" and verdict["state"]=="PASS"
                self.audit["real_1000_24h_passed"]=self.mode=="soak24" and verdict["state"]=="PASS"
            self.audit["finished_at_utc"]=now();self.emit()
            print(json.dumps(dict(state=self.audit["state"],error_code=terminal,cleanup=self.audit["cleanup_state"],
                real_1000_short_passed=self.audit["real_1000_short_passed"],real_1000_24h_passed=self.audit["real_1000_24h_passed"])),flush=True)
        return 0 if self.audit["state"] in ("SMOKE_COMPLETED","DURATION_COMPLETED") and self.audit["cleanup_state"]=="PASS" else 1

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id",required=True);p.add_argument("--prepare",action="store_true")
    p.add_argument("--run",action="store_true");p.add_argument("--cleanup",action="store_true")
    p.add_argument("--expected-backend-version");p.add_argument("--ssh-config")
    p.add_argument("--mode",choices=("short","soak24"),default="short")
    p.add_argument("--max-agents",type=int,choices=(2,1000),default=2);p.add_argument("--bulk-enabled",action="store_true")
    a=p.parse_args();need(sum((a.prepare,a.run,a.cleanup))==1,"CAPACITY_ACTION")
    if a.prepare:
        need(a.expected_backend_version is not None,"CAPACITY_BACKEND_PIN_REQUIRED")
        print(json.dumps(prepare(a.run_id,a.expected_backend_version),sort_keys=True));return 0
    need(a.ssh_config is not None,"CAPACITY_SSH_CONFIG_REQUIRED")
    c=Controller(a.run_id,a.ssh_config,mode=a.mode,max_agents=a.max_agents,bulk_enabled=a.bulk_enabled,cleanup_only=a.cleanup)
    if a.cleanup:c.cleanup();print(json.dumps(dict(state="PASS",cleanup=c.audit["cleanup_state"])));return 0
    return c.run()

if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(state="HOLD",code=error_code(exc),secrets_printed=False)));raise SystemExit(1)
