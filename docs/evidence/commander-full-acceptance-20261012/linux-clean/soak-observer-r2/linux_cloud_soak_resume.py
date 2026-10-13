#!/usr/bin/env python3
"""Resume the existing owned DEV read-only observer; default mode validates without HTTP/SSH."""
import argparse,fcntl,hashlib,importlib.util,json,os,secrets,signal,stat,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path("/tmp_hara/commander-win50-utf8-20261012")
E=ROOT/"docs/evidence/commander-full-acceptance-20261012/linux-clean"
OWN=E/"soak-observer-r2"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
CHECKPOINT=OWN/"application-budget-checkpoint.json"
WITNESS_PROBE=E/"probe53_identity_witness.py"
COMMIT_PROBE=E/"probe53_local_budget_commit.py"
WITNESS_SHA="6455f2c7440c93ed2ec26f3a22eb603379fbc81ded5637d585235c1dc9bc0eb0"
COMMIT_SHA="546086641b08ad1b7cf981867a223b87b40a8393e07a16d3cc251874f703d5a2"
sp=importlib.util.spec_from_file_location("observer_core",OWN/"observer_core.py")
core=importlib.util.module_from_spec(sp);sp.loader.exec_module(core)
require=core.require
class Clock:
 def utcnow(self):return datetime.now(timezone.utc)
 def monotonic(self):return time.monotonic()
 def sleep(self,seconds):time.sleep(min(1,seconds))
def read_json(path,private=True):
 require(path.is_absolute() and not path.is_symlink() and path.is_file() and path.stat().st_uid==os.getuid(),"QA_OWNED_REGULAR_INPUT_REQUIRED")
 require(path.stat().st_size<=2*1024*1024,"QA_INPUT_TOO_LARGE")
 if private:require(stat.S_IMODE(path.stat().st_mode)==0o600,"QA_PRIVATE_INPUT_REQUIRED")
 raw=path.read_bytes();return json.loads(raw),hashlib.sha256(raw).hexdigest()
def atomic(path,value):
 require(path.is_absolute() and path.parent.resolve()==OWN.resolve(),"QA_REPORT_OWN_DIRECTORY_REQUIRED")
 if path.exists():require(not path.is_symlink() and path.is_file() and path.stat().st_uid==os.getuid(),"QA_REPORT_LEAF_REQUIRED")
 tmp=path.with_name("."+path.name+"."+secrets.token_hex(10)+".tmp")
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w") as out:
  json.dump(value,out,sort_keys=True);out.write("\n");out.flush();os.fsync(out.fileno())
 os.replace(tmp,path);dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(dfd)
 finally:os.close(dfd)
def probe(path,pin,args):
 require(not path.is_symlink() and path.is_file() and path.stat().st_uid==os.getuid() and hashlib.sha256(path.read_bytes()).hexdigest()==pin,"QA_READ_ONLY_PROBE_PIN")
 p=subprocess.run(["/usr/bin/python3","-I","-B",str(path),*args],capture_output=True,timeout=30)
 require(p.returncode==0,"QA_READ_ONLY_PROBE_UNCONFIRMED")
 value=json.loads(p.stdout)
 require(isinstance(value,dict),"QA_READ_ONLY_PROBE_JSON_REQUIRED")
 return value
def native_witness():
 return probe(WITNESS_PROBE,WITNESS_SHA,["--label","observer-r2-"+secrets.token_hex(8)])
def local_commit(request_id):
 value=probe(COMMIT_PROBE,COMMIT_SHA,["--request-id",request_id])
 require(value.get("state")=="PASS_LOCAL_COMMITTED1" and value.get("local_commit_confirmed") is True,"QA_LOCAL_COMMIT_UNCONFIRMED")
 debits=value.get("debit_metadata");require(isinstance(debits,list) and len(debits)==1 and isinstance(debits[0],dict),"QA_LOCAL_COMMIT_METADATA_MISSING")
 debit=debits[0]
 # These properties come from the exact SHA-pinned readonly SQLite helper.
 return {**debit,"sqlite_open_mode":"ro","query_only":True}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--resume-snapshot",type=Path)
 p.add_argument("--fixture",type=Path)
 p.add_argument("--report",type=Path,default=OWN/"soak-cloud-r2-status.json")
 p.add_argument("--run",action="store_true")
 p.add_argument("--one-application",action="store_true")
 p.add_argument("--make-snapshot",action="store_true")
 p.add_argument("--prior-report",type=Path)
 p.add_argument("--reconciliation",type=Path)
 p.add_argument("--witness-json",type=Path)
 p.add_argument("--old-observer-stopped-confirmed",action="store_true")
 p.add_argument("--snapshot-output",type=Path,default=OWN/"resume-snapshot.json")
 p.add_argument("--old-observer-stopped-at-utc")
 a=p.parse_args();clock=Clock()
 if a.make_snapshot:
  require(not a.run and a.prior_report and a.reconciliation and a.witness_json,"QA_SNAPSHOT_INPUTS_REQUIRED")
  prior,ph=read_json(a.prior_report);recon,rh=read_json(a.reconciliation,private=False);w,_=read_json(a.witness_json)
  snap={"schema":core.RESUME_SCHEMA,"report":prior,"reconciliation":recon,"native_handoff_witness":w,
   "old_observer_stopped_confirmed":a.old_observer_stopped_confirmed,"old_observer_stopped_at_utc":a.old_observer_stopped_at_utc,"frozen_at_utc":core.stamp(clock.utcnow()),"report_source_sha256":ph,"reconciliation_source_sha256":rh}
  report,_,_=core.build_report(snap,clock.utcnow());atomic(a.snapshot_output,snap)
  print(json.dumps({"state":"SNAPSHOT_CREATED_NO_EXTERNAL_REQUESTS","resume_ready":report["resume_ready"],"application_count":report["application_count"],"unidentified_reservations":report["baseline_unidentified_application_reservations"],"path":str(a.snapshot_output)}));return 0
 require(a.resume_snapshot is not None,"QA_RESUME_SNAPSHOT_REQUIRED")
 snap,snapshot_sha=read_json(a.resume_snapshot)
 prepared,_,_=core.build_report(snap,clock.utcnow())
 if not a.run:
  print(json.dumps({"state":"VALIDATED_NO_EXTERNAL_REQUESTS","resume_ready":prepared["resume_ready"],"application_count":prepared["application_count"],"max_applications":200,"started_at_utc":core.START,"deadline_at_utc":core.DEADLINE,"unidentified_reservations":prepared["baseline_unidentified_application_reservations"],"historical_pending_request_ids":prepared["historical_pending_request_ids"],"historical_failure_count":prepared["historical_failure_count"],"handoff_probe_performed":False}));return 0
 require(a.fixture is not None,"QA_PRIVATE_FIXTURE_REQUIRED")
 require(prepared["resume_ready"],"QA_HISTORY_NOT_RECONCILED_OR_OLD_OBSERVER_NOT_STOPPED")
 # One fixed checkpoint protects sequential replays even if --report changes.
 lock=os.open(ROOT/"apps/commander/.generated/full-acceptance-20261012/linux-cloud-probe.lock",os.O_RDWR|os.O_NOFOLLOW)
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 if CHECKPOINT.exists():
  checkpoint,checkpoint_sha=read_json(CHECKPOINT)
  core.checkpoint_guard(snap,checkpoint,checkpoint_sha)
 require(hashlib.sha256(a.resume_snapshot.read_bytes()).hexdigest()==snapshot_sha,"QA_SNAPSHOT_DRIFT")
 state=core.Observer(snap,clock,lambda r:None).remaining_state()
 if state:
  prepared["state"]=state;atomic(a.report,prepared);print(json.dumps({"state":state,"application_count":prepared["application_count"],"external_requests":0}));return 0
 fixture,fixture_sha=read_json(a.fixture)
 require(fixture.get("environment")=="DEV" and fixture.get("dev_origin")==DEV and fixture.get("tenant_id","").startswith("HARA-ACCEPT-T-"),"QA_DEV_FIXTURE_SCOPE")
 def save_report(report):
  atomic(CHECKPOINT,report)
  if a.report!=CHECKPOINT:atomic(a.report,report)
 fresh=native_witness()
 observer=core.Observer(snap,clock,save_report,fresh)
 remote_sp=importlib.util.spec_from_file_location("qa_remote",ROOT/"apps/commander/scripts/commander_remote_customer_dev_acceptance.py")
 remote=importlib.util.module_from_spec(remote_sp);remote_sp.loader.exec_module(remote)
 data=remote.fixtures.read_private(a.fixture)
 def request(kind,body):
  require(hashlib.sha256(a.fixture.read_bytes()).hexdigest()==fixture_sha,"QA_FIXTURE_DRIFT")
  require(body.keys()<=({"request_id","tool_id","device_id","payload"} if kind=="enqueue" else {"call_id"}),"QA_REQUEST_FIELDS")
  if kind=="enqueue":
   require(body["tool_id"]=="hara.device.info" and body["device_id"]==core.DEVICE and body["payload"]=={},"QA_READ_ONLY_ENQUEUE_SCOPE")
   path="/api/internal/device/calls"
  else:require(kind=="status","QA_REQUEST_KIND");path="/api/internal/device/calls/status"
  payload={**body,"issuer":data["issuer"],"subject":data["external_subject"]}
  return remote.request(data,"POST",path,payload,internal=True,cookie=False)
 stopped=False
 def stop(signum,frame):
  nonlocal stopped
  stopped=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 observer.report["state"]="RUNNING_RESUMED_SOAK";observer.save(observer.report)
 now=clock.utcnow();prior_last=prepared.get("last_observed_at_utc")
 next_due=clock.monotonic()+max(0,600-((now-core.dt(prior_last)).total_seconds() if prior_last else 600))
 final=None
 while not stopped:
  final=observer.remaining_state()
  if final:break
  if clock.monotonic()<next_due:clock.sleep(min(1,next_due-clock.monotonic()));continue
  record=observer.apply("HARA-QA-LINUX-RO-"+secrets.token_hex(12),request,local_commit)
  observer.report["elapsed_seconds"]=int((clock.utcnow()-core.dt(core.START)).total_seconds())
  if not record["terminal_confirmed"]:
   final="STOPPED_PENDING_CALL_RECONCILIATION";break
  observer.report["state"]="RUNNING_RESUMED_SOAK";observer.save(observer.report)
  if a.one_application:final="ONE_APPLICATION_COMPLETE_PENDING_REVIEW";break
  next_due=clock.monotonic()+600
 final=final or "CANCELLED_PENDING_RECONCILIATION"
 observer.report.update(state=final,finished_at_utc=core.stamp(clock.utcnow()))
 observer.report["phases"][-1]["state"]=final
 observer.save(observer.report)
 print(json.dumps({"state":final,"application_count":observer.report["application_count"],"success_count":observer.report["success_count"],"failure_count":observer.report["failure_count"],"phase":observer.report["phases"][-1],"historical_failure_count":observer.report["historical_failure_count"],"content_retained":False}))
 return 0 if observer.report["phases"][-1]["failure_count"]==0 else 1
if __name__=="__main__":
 try:raise SystemExit(main())
 except Exception as error:
  print(json.dumps({"state":"FAILED_TO_RUN_OR_RESUME","error_code":core.safe_code(str(error)),"error_type":type(error).__name__,"private_output":False}));raise SystemExit(1)
