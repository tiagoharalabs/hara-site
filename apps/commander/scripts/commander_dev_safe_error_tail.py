#!/usr/bin/env python3
"""Read-only pinned DEV tail; retain only validated safe incident metadata."""
import argparse,json,os,re,selectors,signal,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
CLASSES={"Error","TypeError","ReferenceError","SyntaxError","RangeError","AggregateError","DOMException","D1Error"}
CAUSES={"D1_CONSTRAINT","D1_TIMEOUT","D1_LIMIT","DO_RESET","DO_RPC_TIMEOUT","DO_STORAGE_LIMIT","WEBSOCKET_STATE","UNKNOWN"}
FUNCTIONS={"fetch","dispatchTransientDeviceCall","mcpTransientProductContext","mcpProductContext","resolveCustomerTargetDevice","resolveSelectedDevice","resolveOrBootstrapContext","requireMcpProductToken","recordLearningSignal","dispatchTransient","webSocketMessage","alarm","getByName","first","all"}
ROUTES={"TRANSIENT_CALL","MCP_AUTHORIZE","MCP_COMMIT","MCP_RELEASE","OTHER"}
def now():return datetime.now(timezone.utc).isoformat()
def safe_incident(value):
    if not isinstance(value,dict) or value.get("schema")!="hara.dev-safe-error-incident.v1" or value.get("environment")!="DEV":return None
    ident=value.get("incident_id");digest=value.get("message_sha256")
    if not isinstance(ident,str) or not re.fullmatch(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",ident):return None
    if not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest):return None
    if value.get("exception_class") not in CLASSES or value.get("safe_cause_class") not in CAUSES or value.get("route") not in ROUTES:return None
    frames=[]
    for x in value.get("stack_frames",[])[:4]:
        if isinstance(x,dict) and x.get("function") in FUNCTIONS and all(type(x.get(k)) is int and 1<=x[k]<=1000000 for k in ("line","column")):
            frames.append({k:x[k] for k in ("function","line","column")})
    return {"schema":value["schema"],"incident_id":ident,"environment":"DEV","route":value["route"],"exception_class":value["exception_class"],"safe_cause_class":value["safe_cause_class"],"message_sha256":digest,"message_digest_truncated":value.get("message_digest_truncated") is True,"stack_frames":frames,"observed_at_utc":now()}
def incidents_from_event(value):
    output=[]
    if not isinstance(value,dict):return output
    for log in value.get("logs",[]):
        if not isinstance(log,dict):continue
        for part in log.get("message",[]):
            if not isinstance(part,str) or len(part)>16000:continue
            try:incident=safe_incident(json.loads(part))
            except (ValueError,TypeError):incident=None
            if incident:output.append(incident)
    return output
def save(path,value):
    tmp=path.with_suffix(".tmp");tmp.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n");os.chmod(tmp,0o600);tmp.replace(path)
def main():
    p=argparse.ArgumentParser();p.add_argument("--pin",required=True);p.add_argument("--hours",type=int,choices=(24,72),default=72);a=p.parse_args()
    assert re.fullmatch(r"[0-9a-f-]{36}",a.pin)
    root=Path("/tmp_hara/commander-soak003-frozen-20261013")
    status=Path("/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/real-dev-soak/soak-20261013-root-003")
    status.mkdir(parents=True,exist_ok=True)
    dest=status/"safe-incidents.jsonl";assert not dest.exists(),"TAIL_ALREADY_STARTED"
    fd=os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    sink=os.fdopen(fd,"w")
    begin=time.monotonic();deadline=begin+a.hours*3600;stop=False
    def stopping(*unused):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,stopping);signal.signal(signal.SIGINT,stopping)
    proc=subprocess.Popen([str(root/"node_modules/.bin/wrangler"),"tail","hara-commander-dev-v2","--config",str(root/"apps/commander/wrangler.dev.jsonc"),"--format","json","--method","POST","--version-id",a.pin],cwd=root/"apps/commander",stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    sel=selectors.DefaultSelector();sel.register(proc.stdout,selectors.EVENT_READ,data="stdout");sel.register(proc.stderr,selectors.EVENT_READ,data="stderr")
    meta={"state":"RUNNING","backend_version_pin":a.pin,"started_at_utc":now(),"event_count":0,"incident_count":0,"stderr_bytes_discarded":0,"buffer_resets":0,"raw_output_saved":False,"product_requests_issued":0,"coverage_guaranteed":False}
    decoder=json.JSONDecoder();buf="";last=0
    try:
        while not stop and time.monotonic()<deadline and sel.get_map():
            for key,_ in sel.select(timeout=1):
                raw=os.read(key.fileobj.fileno(),65536)
                if not raw:sel.unregister(key.fileobj);continue
                if key.data=="stderr":meta["stderr_bytes_discarded"]+=len(raw);continue
                buf+=raw.decode("utf-8","replace")
                if len(buf)>1000000:buf="";meta["buffer_resets"]+=1;continue
                while buf.strip():
                    buf=buf.lstrip()
                    if not buf.startswith("{"):
                        n=buf.find("\n")
                        if n<0:break
                        buf=buf[n+1:];continue
                    try:value,end=decoder.raw_decode(buf)
                    except json.JSONDecodeError:break
                    buf=buf[end:];meta["event_count"]+=1;meta["last_event_at_utc"]=now()
                    for incident in incidents_from_event(value):
                        assert meta["incident_count"]<3000,"TAIL_INCIDENT_BOUND"
                        sink.write(json.dumps(incident,sort_keys=True)+"\n");sink.flush();meta["incident_count"]+=1
            if time.monotonic()-last>=30:
                meta["elapsed_seconds"]=round(time.monotonic()-begin,3);save(status/"safe-tail-status.json",meta);last=time.monotonic()
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid,signal.SIGTERM)
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=5)
        sink.close();sel.close()
        meta.update(state="STOPPED" if stop else "ENDED",ended_at_utc=now(),tail_exit_code=proc.returncode,elapsed_seconds=round(time.monotonic()-begin,3))
        save(status/"safe-tail-status.json",meta)
    return 0
if __name__=="__main__":raise SystemExit(main())
