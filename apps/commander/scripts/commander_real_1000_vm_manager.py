#!/usr/bin/env python3
"""Owned-VM Agent supervisor. JSON stdin carries individual device credentials only.

One bounded systemd user unit owns all children. A local private queue avoids
one SSH connection per Agent. Never accepts arbitrary shell commands or tokens
for Cloudflare/admin access. This is test infrastructure, not product evidence.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, math, os, re, resource, shutil
import signal, stat, subprocess, sys, time
from pathlib import Path

DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
SOURCES=("experimental/event_v2_websocket.py","experimental/event_v2_agent_loop.py",
         "experimental/event_v2_customer_agent.py","experimental/event_v2_telemetry.py",
         "public/agent/linux.py")
MAX_INPUT=2*1024*1024
GIB=1024**3

def need(ok,code):
    if not ok:raise RuntimeError(code)

def safe_code(exc):
    value=str(exc)
    return value if re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}",value) else type(exc).__name__.upper()

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def private_dir(path,create=False):
    if create:path.mkdir(mode=0o700)
    s=path.lstat()
    need(stat.S_ISDIR(s.st_mode) and not stat.S_ISLNK(s.st_mode) and s.st_uid==os.getuid(),"VM_DIRECTORY_UNSAFE")
    need(stat.S_IMODE(s.st_mode)==0o700,"VM_DIRECTORY_MODE")

def secure_read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        s=os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o600,"VM_FILE_UNSAFE")
        return json.load(f)

def atomic(path,obj,exclusive=False):
    private_dir(path.parent)
    temp=path.parent/("."+path.name+"-"+os.urandom(8).hex())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(obj,f,separators=(",",":"),sort_keys=True);f.write("\n");f.flush();os.fsync(f.fileno())
        if exclusive:
            os.link(temp,path,follow_symlinks=False);temp.unlink()
        else:
            if path.exists():secure_read(path)
            os.replace(temp,path)
        fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    finally:temp.unlink(missing_ok=True)

def checked_base(value):
    path=Path(value)
    home=Path.home().resolve()
    need(path.is_absolute() and path.parent==home/"hara-capacity1000" and re.fullmatch(r"cap1k-[a-z0-9-]{12,48}",path.name),"VM_BASE_SCOPE")
    private_dir(path.parent)
    return path

def proc_identity(pid):
    try:
        root=Path("/proc")/str(pid)
        raw=(root/"stat").read_text()
        after=raw.rsplit(")",1)[1].split()
        # fields after comm start at state(field3): starttime field22=>index19.
        if after[0]=="Z":return None
        cmd=(root/"cmdline").read_bytes().split(b"\0")
        return dict(pid=pid,start_ticks=int(after[19]),uid=root.stat().st_uid,cmd=cmd)
    except FileNotFoundError:return None

def identity_matches(expected,source,uid=None):
    current=proc_identity(expected["pid"])
    if current is None:return False
    need(current["start_ticks"]==expected["start_ticks"],"VM_PID_START_CHANGED")
    need(current["uid"]==(os.getuid() if uid is None else uid),"VM_PID_OWNER_CHANGED")
    need(current["cmd"][:3]==[b"/usr/bin/python3",b"-B",str(source).encode()],"VM_PID_COMMAND_CHANGED")
    return True

def stop_exact(row,source):
    if not row.get("pid"):return
    expected=dict(pid=row["pid"],start_ticks=row["start_ticks"])
    need(hasattr(os,"pidfd_open") and hasattr(signal,"pidfd_send_signal"),"VM_PIDFD_REQUIRED")
    try:fd=os.pidfd_open(row["pid"],0)
    except ProcessLookupError:return
    try:
        if not identity_matches(expected,source):return
        # Kernel-bound PIDFD closes the identity-check/signal PID reuse race.
        try:signal.pidfd_send_signal(fd,signal.SIGTERM)
        except ProcessLookupError:return
        import select
        poll=select.poll();poll.register(fd,select.POLLIN)
        if poll.poll(15000):return
        try:signal.pidfd_send_signal(fd,signal.SIGKILL)
        except ProcessLookupError:return
        need(bool(poll.poll(5000)),"VM_STOP_TIMEOUT")
    finally:os.close(fd)

class Manager:
    def __init__(self,base):
        self.base=base;private_dir(base)
        self.state=secure_read(base/"state.json")
        self.source=base/"source/apps/commander/experimental/event_v2_agent_loop.py"
        self.verify_sources()
    def verify_sources(self):
        for name,sha in self.state["source_sha256"].items():
            p=self.base/"source/apps/commander"/name
            need(p.is_file() and not p.is_symlink() and digest(p)==sha,"VM_SOURCE_DRIFT")
        need(digest(Path(__file__).resolve())==self.state["manager_sha256"],"VM_MANAGER_DRIFT")
    def save(self):atomic(self.base/"state.json",self.state)
    def rowroot(self,index):
        need(type(index) is int and 0<=index<1000,"VM_INDEX")
        return self.base/("device-"+str(index))
    def start(self,records):
        need(isinstance(records,list) and 1<=len(records)<=2,"VM_BATCH_BOUND")
        need(time.time()<self.state["deadline_unix"],"VM_DEADLINE")
        self.verify_sources()
        result=[]
        for entry in records:
            need(set(entry)=={"index","device_id","device_token"},"VM_START_FIELDS")
            index=entry["index"];root=self.rowroot(index)
            need(str(index) not in self.state["rows"],"VM_DUPLICATE_INDEX")
            need(len(self.state["rows"])<self.state["profile"]["max_agents"],"VM_SHARD_AGENT_LIMIT")
            device=entry["device_id"];token=entry["device_token"]
            need(isinstance(device,str) and re.fullmatch(r"HARA-DEVICE-[A-Za-z0-9._:-]{1,180}",device),"VM_DEVICE_ID")
            need(isinstance(token,str) and re.fullmatch(r"[A-Za-z0-9._~-]{32,512}",token),"VM_DEVICE_TOKEN")
            private_dir(root,True)
            for p in (root/"xdg-config",root/"xdg-data",root/"xdg-config/hara-commander"):private_dir(p,True)
            cfg=root/"xdg-config/hara-commander/device.env"
            fd=os.open(cfg,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"w") as f:
                f.write("HARA_COMMANDER_URL="+DEV+"\nHARA_DEVICE_ID="+device+"\nHARA_DEVICE_TOKEN="+token+"\nHARA_DEVICE_ARCH=x86_64\n")
                f.flush();os.fsync(f.fileno())
            # Persist registration before spawn; a partial spawn remains discoverable.
            row=dict(index=index,device_id=device,state="REGISTERED",config_sha256=digest(cfg))
            self.state["rows"][str(index)]=row;self.save()
            env={k:v for k,v in os.environ.items() if k in ("PATH","LANG","LC_ALL","TZ")}
            env.update(HOME=str(Path.home()),XDG_CONFIG_HOME=str(root/"xdg-config"),
                       XDG_DATA_HOME=str(root/"xdg-data"),PYTHONDONTWRITEBYTECODE="1")
            fd=os.open(root/"agent.log",os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,"ab") as log:
                proc=subprocess.Popen(["/usr/bin/python3","-B",str(self.source)],env=env,cwd=root,
                    stdout=log,stderr=log,stdin=subprocess.DEVNULL)
            current=proc_identity(proc.pid)
            need(current is not None,"VM_AGENT_IMMEDIATE_EXIT")
            row.update(pid=proc.pid,start_ticks=current["start_ticks"],uid=os.getuid(),state="STARTED")
            self.save();result.append(dict(index=index,pid=proc.pid,start_ticks=current["start_ticks"],device_id=device))
        return dict(state="PASS",started=result)
    def snapshot(self):
        self.verify_sources();rows=[];rss=[]
        for row in self.state["rows"].values():
            alive=identity_matches(row,self.source) if row.get("pid") else False
            data={}
            if alive:
                p=self.rowroot(row["index"])/"xdg-data/hara-commander/event-v2-status.json"
                try:data=secure_read(p)
                except FileNotFoundError:pass
                n=0
                for line in (Path("/proc")/str(row["pid"])/"status").read_text().splitlines():
                    if line.startswith("VmRSS:"):n=int(line.split()[1])*1024
                rss.append(n)
            raw_error=data.get("last_error_code")
            error=raw_error if isinstance(raw_error,str) and re.fullmatch(r"[A-Z0-9_:.-]{1,120}",raw_error) else (None if not raw_error else "UNCLASSIFIED")
            rows.append(dict(index=row["index"],device_id=row["device_id"],pid=row.get("pid"),
                start_ticks=row.get("start_ticks"),alive=alive,connected=alive and data.get("connected") is True,
                error_code=error,rss_bytes=n if alive else 0))
        mem={}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k,v,*_=line.split()
            if k in ("MemTotal:","MemAvailable:","SwapTotal:","SwapFree:"):mem[k.rstrip(":")]=int(v)*1024
        fs=os.statvfs(self.base);cg=Path("/sys/fs/cgroup/cgroup.controllers")
        snapshot=dict(schema="hara.commander-capacity-resource-snapshot.v1",role="Guest",at_unix=time.time(),
            memory_total_bytes=mem["MemTotal"],memory_available_bytes=mem["MemAvailable"],
            swap_total_bytes=mem["SwapTotal"],swap_free_bytes=mem["SwapFree"],cpu_count=os.cpu_count(),
            load_1m=os.getloadavg()[0],disk_available_bytes=fs.f_bavail*fs.f_frsize,
            open_files_soft=resource.getrlimit(resource.RLIMIT_NOFILE)[0],
            open_files_hard=resource.getrlimit(resource.RLIMIT_NOFILE)[1],
            cgroup_v2=cg.is_file(),cgroup_controllers=cg.read_text().split() if cg.is_file() else [])
        p99=sorted(rss)[min(len(rss)-1,max(0,math.ceil(len(rss)*.99)-1))] if rss else 0
        return dict(state="PASS",rows=rows,resources=snapshot,rss_total_bytes=sum(rss),
                    rss_p99_bytes=p99,source_pins_match=True,supervisor_cgroup=self.state.get("supervisor_cgroup"))
    def ledger(self,index,request_id):
        need(isinstance(request_id,str) and re.fullmatch(r"CAP1K-[A-Z]+-[0-9a-f]{32}",request_id),"VM_REQUEST_ID")
        folder=self.rowroot(index)/"xdg-data/hara-commander/transient-ledger"
        found=[]
        for p in folder.glob("*.json"):
            v=secure_read(p)
            if v.get("request_id")==request_id:
                need("payload" not in v and "arguments" not in v,"VM_LEDGER_PAYLOAD")
                receipt=v.get("result",{}).get("bridge_receipt_sha256")
                need(isinstance(receipt,str) and re.fullmatch(r"[0-9a-f]{64}",receipt),"VM_LEDGER_RECEIPT")
                found.append(dict(sha256=digest(p),request_id=request_id,receipt_sha256=receipt))
        need(len(found)==1,"VM_LEDGER_EXACT_COUNT")
        return dict(state="PASS",ledger=found[0])
    def recover_spawn_registration(self):
        # A supervisor crash after fork but before PID journal commit is recoverable
        # only inside this exact unit, using UID+frozen command+private XDG root.
        expected_cgroup=self.state.get("supervisor_cgroup")
        need(isinstance(expected_cgroup,str) and bool(expected_cgroup),"VM_CGROUP_REGISTRATION")
        found=[]
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():continue
            current=proc_identity(int(proc.name))
            if not current or current["uid"]!=os.getuid():continue
            if current["cmd"][:3]!=[b"/usr/bin/python3",b"-B",str(self.source).encode()]:continue
            need((proc/"cgroup").read_text().strip()==expected_cgroup,"VM_CHILD_CGROUP_CHANGED")
            env=(proc/"environ").read_bytes().split(b"\0")
            candidates=[v.split(b"=",1)[1] for v in env if v.startswith(b"XDG_CONFIG_HOME=")]
            matches=[row for row in self.state["rows"].values()
                     if candidates==[str(self.rowroot(row["index"])/"xdg-config").encode()]]
            need(len(matches)==1,"VM_PARTIAL_SPAWN_SCOPE")
            row=matches[0]
            if row.get("pid"):need(row["pid"]==current["pid"] and row["start_ticks"]==current["start_ticks"],"VM_DUPLICATE_OWN_AGENT")
            else:
                row.update(pid=current["pid"],start_ticks=current["start_ticks"],uid=current["uid"],state="RECOVERED_PARTIAL_SPAWN")
                self.save()
            found.append(current)
        return found
    def remove_credentials(self):
        for row in self.state["rows"].values():
            root=self.rowroot(row["index"])
            if root.exists():private_dir(root);shutil.rmtree(root)
        # Queued starts can contain device credentials, even when no Agent spawned.
        for p in (self.base/"queue").glob("*.json"):
            need(re.fullmatch(r"[0-9a-f]{32}\.json",p.name),"VM_QUEUE_NAME")
            secure_read(p);p.unlink()
        self.state["credentials_removed"]=not any(self.rowroot(r["index"]).exists() for r in self.state["rows"].values()) and not list((self.base/"queue").glob("*.json"))
        need(self.state["credentials_removed"],"VM_CREDENTIALS_REMAIN")
    def stop_all(self):
        self.verify_sources();self.recover_spawn_registration()
        for row in self.state["rows"].values():stop_exact(row,self.source)
        remaining=len(self.recover_spawn_registration())
        need(remaining==0,"VM_OWN_AGENTS_REMAIN")
        self.state["stopped"]=True;self.save()
        return dict(state="PASS",remaining=remaining)
    def action(self,obj):
        self.verify_sources()
        action=obj.get("action")
        if action=="start":return self.start(obj["records"])
        if action=="status":return self.snapshot()
        if action=="ledger":return self.ledger(obj["index"],obj["request_id"])
        if action=="ledgers":
            records=obj.get("records")
            need(isinstance(records,list) and 1<=len(records)<=1000,"VM_LEDGER_BATCH")
            return dict(state="PASS",ledgers=[dict(index=r["index"],**self.ledger(r["index"],r["request_id"])["ledger"]) for r in records])
        if action=="stop":return self.stop_all()
        if action=="cleanup":
            result=self.stop_all();self.remove_credentials()
            self.state["finished"]=True;self.save()
            return dict(**result,credentials_removed=True)
        raise RuntimeError("VM_ACTION")

def initialize(base,obj):
    need(set(obj)=={"action","run_id","source_sha256","sources_b64","runtime_seconds","manager_sha256","profile"},"VM_INIT_FIELDS")
    need(obj["run_id"]==base.name,"VM_RUN_ID")
    seconds=obj["runtime_seconds"]
    need(type(seconds) is int and seconds in (7200,25*3600),"VM_RUNTIME_BOUND")
    need(set(obj["source_sha256"])==set(SOURCES) and set(obj["sources_b64"])==set(SOURCES),"VM_SOURCE_LIST")
    need(obj["manager_sha256"]==digest(Path(__file__).resolve()),"VM_MANAGER_PIN")
    profile=obj["profile"]
    need(isinstance(profile,dict) and set(profile)=={"max_agents","memory_floor_bytes","memory_high_bytes","memory_max_bytes","cpu_quota_percent","expected_uid","expected_hostname"},"VM_PROFILE_FIELDS")
    for key in ("max_agents","memory_floor_bytes","memory_high_bytes","memory_max_bytes","cpu_quota_percent","expected_uid"):
        need(type(profile[key]) is int and profile[key]>0,"VM_PROFILE_NUMBER")
    import socket
    need(profile["expected_uid"]==os.getuid() and profile["expected_hostname"]==socket.gethostname(),"VM_PROFILE_IDENTITY")
    need(2<=profile["max_agents"]<=1000 and profile["cpu_quota_percent"]<=os.cpu_count()*25,"VM_PROFILE_CPU_BOUND")
    need(0<profile["memory_high_bytes"]<=profile["memory_max_bytes"],"VM_PROFILE_MEMORY_BOUND")
    available=int(next(x.split()[1] for x in Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:")))*1024
    need(available>=profile["memory_max_bytes"]+profile["memory_floor_bytes"],"VM_PROFILE_MEMORY_AVAILABLE")
    private_dir(base,True)
    for sub in ("queue","results"):private_dir(base/sub,True)
    for name in SOURCES:
        raw=base64.b64decode(obj["sources_b64"][name],validate=True)
        sha=obj["source_sha256"][name]
        need(re.fullmatch(r"[0-9a-f]{64}",sha) and hashlib.sha256(raw).hexdigest()==sha,"VM_SOURCE_PIN")
        p=base/"source/apps/commander"/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as f:f.write(raw)
    unit="hara-cap1k-"+hashlib.sha256(base.name.encode()).hexdigest()[:20]
    state=dict(run_id=base.name,rows={},source_sha256=obj["source_sha256"],
        manager_sha256=obj["manager_sha256"],deadline_unix=time.time()+seconds,unit=unit,profile=profile,finished=False)
    atomic(base/"state.json",state,True)
    properties=("MemoryHigh="+str(profile["memory_high_bytes"]),"MemoryMax="+str(profile["memory_max_bytes"]),
                "CPUQuota="+str(profile["cpu_quota_percent"])+"%","TasksMax=8192","LimitNOFILE=8192",
                "RuntimeMaxSec="+str(seconds),"Restart=no","KillMode=mixed","TimeoutStopSec=30")
    argv=["systemd-run","--user","--quiet","--unit="+unit]
    argv += ["--property="+x for x in properties]
    argv += ["/usr/bin/python3","-B",str(Path(__file__).resolve()),"--base",str(base),"--serve"]
    p=subprocess.run(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    need(p.returncode==0,"VM_SUPERVISOR_START")
    return dict(state="PASS",unit=unit,deadline_unix=state["deadline_unix"],credentials_received=0)

def server(base):
    manager=Manager(base)
    raw=Path("/proc/self/cgroup").read_text().strip()
    need(manager.state["unit"] in raw,"VM_SUPERVISOR_CGROUP")
    manager.state["supervisor_cgroup"]=raw
    manager.state["supervisor_pid"]=os.getpid();manager.save()
    signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    signal.signal(signal.SIGINT,lambda *_:(_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        while not manager.state.get("finished"):
            need(time.time()<manager.state["deadline_unix"],"VM_DEADLINE")
            manager.verify_sources()
            for path in sorted((base/"queue").glob("*.json")):
                need(re.fullmatch(r"[0-9a-f]{32}\.json",path.name),"VM_QUEUE_NAME")
                obj=secure_read(path)
                try:result=manager.action(obj)
                except Exception as exc:result=dict(state="FAIL",code=safe_code(exc))
                atomic(base/"results"/path.name,result,True);path.unlink(missing_ok=True)
                if manager.state.get("finished"):break
            time.sleep(.2)
    finally:
        # Never assert zero processes or removed credentials after a guarded
        # shutdown fails; systemd still bounds and terminates this own cgroup.
        try:
            manager.stop_all();manager.remove_credentials()
            manager.state["finished"]=True
        except Exception as exc:
            manager.state["cleanup_error"]=safe_code(exc);manager.state["credentials_removed"]=False
        manager.save()

def dispatch(base,obj):
    if obj.get("action")=="init":return initialize(base,obj)
    private_dir(base)
    state=secure_read(base/"state.json")
    if state.get("finished") and obj.get("action") in ("stop","cleanup"):
        return dict(state="PASS",remaining=0,credentials_removed=state.get("credentials_removed") is True)
    need(not state.get("finished"),"VM_SUPERVISOR_FINISHED")
    name=os.urandom(16).hex()+".json";atomic(base/"queue"/name,obj,True)
    result=base/"results"/name;until=time.monotonic()+120
    while time.monotonic()<until:
        if result.exists():
            out=secure_read(result);result.unlink();return out
        time.sleep(.1)
    raise RuntimeError("VM_COMMAND_OUTCOME_UNKNOWN")

def main():
    p=argparse.ArgumentParser();p.add_argument("--base",required=True);p.add_argument("--serve",action="store_true")
    args=p.parse_args();base=checked_base(args.base)
    if args.serve:server(base);return 0
    raw=sys.stdin.buffer.read(MAX_INPUT+1);need(len(raw)<=MAX_INPUT,"VM_INPUT_BOUND")
    obj=json.loads(raw);need(isinstance(obj,dict),"VM_INPUT_OBJECT")
    out=dispatch(base,obj);print(json.dumps(out,separators=(",",":"),sort_keys=True))
    return 0 if out.get("state")=="PASS" else 1

if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(state="FAIL",code=safe_code(exc))));raise SystemExit(1)
