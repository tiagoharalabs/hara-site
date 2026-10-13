#!/usr/bin/env python3
"""Read-only DEV tail correction: omit invalid sampling-rate=1; sanitize all event data."""
from pathlib import Path
import importlib.util,json,subprocess,os,signal,hashlib,re
from datetime import datetime,timezone
root=Path("/tmp_hara/commander-win50-utf8-20261012");ev=root/"docs/evidence/commander-full-acceptance-20261012/real-dev-soak"
p=ev/"pilot002_bounded_diagnostic.py";s=importlib.util.spec_from_file_location("tail_safe",p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
d=json.loads((ev/"pilot002-diagnostic-002/diagnostic-status.json").read_text());start=datetime.fromisoformat(d["pilot_started_at_utc"].replace("Z","+00:00"));remaining=max(20,min(650,int(1200-(datetime.now(timezone.utc)-start).total_seconds()+30)))
proc=subprocess.Popen([str(root/"node_modules/.bin/wrangler"),"tail","hara-commander-dev-v2","--config",str(root/"apps/commander/wrangler.dev.jsonc"),"--format","json","--method","POST","--version-id",m.PIN],cwd=root/"apps/commander",stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
try: out,err=proc.communicate(timeout=remaining)
except subprocess.TimeoutExpired:
 os.killpg(proc.pid,signal.SIGTERM)
 try:out,err=proc.communicate(timeout=10)
 except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate(timeout=5)
text=out.decode(errors="replace");decoder=json.JSONDecoder();events=[];pos=0
while pos<len(text):
 n=text.find("{",pos)
 if n<0:break
 try:v,end=decoder.raw_decode(text[n:])
 except json.JSONDecodeError:pos=n+1;continue
 pos=n+end
 if isinstance(v,dict) and ("event" in v or "outcome" in v):events.append(m.scrub_tail(v))
stderr=err.decode(errors="replace");kind="NONE" if not stderr else "OTHER"
for pattern,cat in [(r"403|forbidden|permission","PERMISSION"),(r"401|unauthorized|authentication","AUTH"),(r"socket|connection|ECONN|network|timed.?out","NETWORK"),(r"sampling rate.*between","SAMPLING_OPTION"),(r"filter|invalid.*option","FILTER")]:
 if re.search(pattern,stderr,re.I):kind=cat;break
safe=root/".generated/pilot002-diagnostics";safe.mkdir(parents=True,exist_ok=True,mode=0o700);os.chmod(safe,0o700);dest=safe/"corrected-tail-sanitized.json";dest.write_text(json.dumps(events,indent=2)+"\n");os.chmod(dest,0o600)
report={"schema":"hara.pilot002-readonly-tail-subscription.v1","scope":"DEV POST pinnedversion only; no new product calls; sampling filter omitted; raw stdout/stderr discarded","capture_bound_seconds":remaining,"event_count":len(events),"exception_count":sum(bool(x["exceptions"]) for x in events),"outcomes":{k:sum(x["outcome"]==k for x in events) for k in sorted(set(x["outcome"] for x in events))},"statuses":{str(k):sum(x["status"]==k for x in events) for k in sorted(set(x["status"] for x in events),key=str)},"tail_exit_code":proc.returncode,"stderr_class":kind,"stderr_sha256":hashlib.sha256(err).hexdigest(),"private_safe_path":str(dest),"raw_bytes_discarded":len(out)+len(err),"initial_tail_gap":"invalid sampling-rate1 exited before subscription"}
(ev/"pilot002-tail-subscription-corrected-readback.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report))
