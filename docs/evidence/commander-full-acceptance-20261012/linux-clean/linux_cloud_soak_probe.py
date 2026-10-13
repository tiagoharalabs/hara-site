#!/usr/bin/env python3
"""Read-only real DEV cloud calls to the exact enrolled Linux QA device."""
import argparse,fcntl,hashlib,importlib.util,json,os,re,secrets,signal,stat,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path("/tmp_hara/commander-win50-utf8-20261012")
E=ROOT/"docs/evidence/commander-full-acceptance-20261012/linux-clean"
DEV="https://hara-commander-dev-v2.tiago-sartori.workers.dev"
DEVICE="HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889"
def require(ok,code):
 if not ok:raise RuntimeError(code)
def utc():return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def safe_code(value):
 value=str(value or "UNKNOWN")
 return value if re.fullmatch("[A-Z0-9_:-]{1,100}",value) else "UNCLASSIFIED_ERROR"
def atomic(path,data):
 tmp=path.with_name("."+path.name+"."+secrets.token_hex(8)+".tmp")
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 with os.fdopen(fd,"w") as out:
  json.dump(data,out,sort_keys=True);out.write("\n");out.flush();os.fsync(out.fileno())
 os.replace(tmp,path)
 dfd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(dfd)
 finally:os.close(dfd)
def main():
 p=argparse.ArgumentParser();p.add_argument("--fixture",type=Path,required=True);p.add_argument("--preflight-only",action="store_true");a=p.parse_args()
 require(a.fixture.is_absolute() and not a.fixture.is_symlink() and stat.S_IMODE(a.fixture.stat().st_mode)==0o600,"QA_PRIVATE_FIXTURE_REQUIRED")
 fixture_sha=hashlib.sha256(a.fixture.read_bytes()).hexdigest()
 sp=importlib.util.spec_from_file_location("qa_remote",ROOT/"apps/commander/scripts/commander_remote_customer_dev_acceptance.py");remote=importlib.util.module_from_spec(sp);sp.loader.exec_module(remote)
 data=remote.fixtures.read_private(a.fixture)
 require(data.get("environment")=="DEV" and data.get("dev_origin")==DEV,"QA_DEV_ORIGIN_REQUIRED")
 require(data.get("tenant_id","").startswith("HARA-ACCEPT-T-"),"QA_TENANT_SCOPE_REQUIRED")
 require(json.loads((E/"native-053-re-enroll.json").read_text()).get("device_id")==DEVICE,"QA_ENROLLMENT_BINDING_REQUIRED")
 holder=json.loads((E/"soak-053-status.json").read_text())
 require(holder.get("device_id")==DEVICE and holder.get("state")=="RUNNING","QA_NATIVE_HOLDER_REQUIRED")
 holder_start=datetime.fromisoformat(holder["started_at_utc"].replace("Z","+00:00"))
 deadline_utc=holder_start+timedelta(seconds=86400)-timedelta(seconds=45)
 remaining=(deadline_utc-datetime.now(timezone.utc)).total_seconds()
 require(remaining>1200,"QA_SOAK_WINDOW_REQUIRED")
 lock=os.open(ROOT/"apps/commander/.generated/full-acceptance-20261012/linux-cloud-probe.lock",os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 started=time.monotonic();deadline=started+remaining;stopped=False;next_due=started
 seen_receipts=set()
 report={"schema":"hara.commander-linux-real-cloud-soak.v1","state":"STARTING","device_id":DEVICE,"environment":"DEV","started_at_utc":utc(),"holder_started_at_utc":holder["started_at_utc"],"deadline_at_utc":deadline_utc.isoformat().replace("+00:00","Z"),"scope":"normal_DEV_internal_bridge_to_actual_enrolled_VM_Agent","tool":"hara.device.info","pilot_seconds":1200,"pilot_interval_seconds":60,"soak_interval_seconds":600,"max_applications":200,"application_count":0,"success_count":0,"failure_count":0,"quota_units_observed":0,"identity_failures":0,"receipt_failures":0,"latency_sum_seconds":0.0,"latency_min_seconds":None,"latency_max_seconds":None,"failures_by_code":{},"pilot_calls":0,"pilot_success":0,"receipt_count":0,"receipt_sample_first":None,"receipt_sample_last":None,"receipt_chain_sha256":None,"last_observed_at_utc":None,"content_retained":False,"fixture_or_canary_token_copied":False,"human_ASK_inputs_generated":False,"backend_mock_used":False,"signed_agent_modified":False}
 def save():atomic(E/"soak-cloud-status.json",report)
 def request(method,path,body=None,cookie=False):
  require(hashlib.sha256(a.fixture.read_bytes()).hexdigest()==fixture_sha,"QA_FIXTURE_DRIFT")
  return remote.request(data,method,path,body,internal=not cookie,cookie=cookie)
 def stop(signum,frame):
  nonlocal stopped
  stopped=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 status,initial=request("GET","/api/portal/dashboard",cookie=True)
 report["quota_dashboard_before_http"]=status
 report["quota_dashboard_scope"]="optional_fixture_portal_session; seeded_2h_cookie_expired; not_OAuth_proof"
 report["quota_evidence_scope"]="CLOUD_QUOTA1_per_call_metadata_and_application_ceiling; D1_reconciliation_by_fixture_owner"
 usage=initial.get("usage") or {}
 report["quota_before"]={k:usage[k] for k in ("metered","limit","used","remaining","plan_code") if k in usage}
 deny_body={"issuer":data["issuer"],"subject":data["external_subject"],"request_id":"HARA-QA-LINUX-GRANT-DENY-"+secrets.token_hex(10),"tool_id":"hara.files.write","device_id":DEVICE,"payload":{"path":"/home/commanderqa/commander-qa/cloud-grant-denial-marker.txt","content":"QA must not apply","mode":"rewrite"}}
 http,denied=request("POST","/api/internal/device/calls",deny_body)
 report["grant_denial"]={"http":http,"code":safe_code(denied.get("code")),"call_enqueued":bool(denied.get("call_id"))}
 require(http==403 and denied.get("code")=="GRANT_MISSING" and not denied.get("call_id"),"QA_REMOTE_WRITE_GRANT_DENIAL_FAILED")
 save()
 while time.monotonic()<deadline and not stopped and report["application_count"]<200:
  now=time.monotonic()
  if now<next_due:
   time.sleep(min(1,next_due-now));continue
  elapsed=now-started;is_pilot=elapsed<1200
  if not is_pilot and "pilot_result" not in report:
   report["pilot_result"]={"elapsed_seconds":int(elapsed),"calls":report["pilot_calls"],"success":report["pilot_success"],"state":"PASS" if report["pilot_calls"]==20 and report["pilot_success"]==20 else "FAIL"}
   atomic(E/"soak-cloud-pilot20.json",report["pilot_result"])
  body={"issuer":data["issuer"],"subject":data["external_subject"],"request_id":"HARA-QA-LINUX-RO-"+secrets.token_hex(12),"tool_id":"hara.device.info","device_id":DEVICE,"payload":{}}
  before=time.monotonic();report["application_count"]+=1
  if is_pilot:report["pilot_calls"]+=1
  error=None;receipt=None
  try:
   http,call=request("POST","/api/internal/device/calls",body)
   require(http in (200,201) and bool(call.get("call_id")),"ENQUEUE_"+safe_code(call.get("code") or "HTTP_"+str(http)))
   require(call.get("usage_mode")=="CLOUD_QUOTA" and call.get("usage_units")==1,"QA_QUOTA_CALL_METADATA_INVALID")
   end=min(time.monotonic()+40,deadline);result={}
   while time.monotonic()<end:
    status,result=request("POST","/api/internal/device/calls/status",{"issuer":data["issuer"],"subject":data["external_subject"],"call_id":call["call_id"]})
    require(status==200,"QA_CALL_STATUS_HTTP")
    if result.get("state") in ("COMPLETED","FAILED","EXPIRED","CANCELLED"):break
    time.sleep(.5)
   require(result.get("device_id")==DEVICE,"QA_RESULT_IDENTITY_MISMATCH")
   require(result.get("state")=="COMPLETED" and not result.get("error_code"),"RESULT_"+safe_code(result.get("error_code") or result.get("state")))
   proof=result.get("result") or {};r=proof.get("result") or {}
   require(proof.get("state")=="PASS" and proof.get("mutation_performed") is False and r.get("risk_class")=="READ_ONLY" and r.get("function_id")=="device.info" and r.get("process_exit_code")==0,"QA_RESULT_OPERATION_INVALID")
   receipt=proof.get("bridge_receipt_sha256")
   require(isinstance(receipt,str) and re.fullmatch("[0-9a-f]{64}",receipt) and receipt not in seen_receipts,"QA_RECEIPT_INVALID")
   report["quota_units_observed"]+=1;report["success_count"]+=1
   seen_receipts.add(receipt);report["receipt_count"]+=1
   if report["receipt_sample_first"] is None:report["receipt_sample_first"]=receipt
   report["receipt_sample_last"]=receipt
   report["receipt_chain_sha256"]=hashlib.sha256(((report["receipt_chain_sha256"] or "")+receipt).encode()).hexdigest()
   if is_pilot:report["pilot_success"]+=1
  except Exception as failure:
   error=safe_code(str(failure));report["failure_count"]+=1
   report["failures_by_code"][error]=report["failures_by_code"].get(error,0)+1
   if error=="QA_RESULT_IDENTITY_MISMATCH":report["identity_failures"]+=1
   if error=="QA_RECEIPT_INVALID":report["receipt_failures"]+=1
  latency=round(time.monotonic()-before,3)
  report["latency_sum_seconds"]=round(report["latency_sum_seconds"]+latency,3)
  report["latency_min_seconds"]=latency if report["latency_min_seconds"] is None else min(report["latency_min_seconds"],latency)
  report["latency_max_seconds"]=latency if report["latency_max_seconds"] is None else max(report["latency_max_seconds"],latency)
  report["latency_mean_seconds"]=round(report["latency_sum_seconds"]/report["application_count"],3)
  report.update(state="RUNNING_PILOT" if is_pilot else "RUNNING_SOAK",last_observed_at_utc=utc(),elapsed_seconds=int(time.monotonic()-started),last_error_code=error)
  save()
  if a.preflight_only:break
  next_due=now+(60 if is_pilot else 600)
 report["state"]="PREFLIGHT_PASS" if a.preflight_only and report["success_count"]==1 else "CANCELLED" if stopped else "ELAPSED_PENDING_NATIVE_HOLDER_REVIEW"
 report["finished_at_utc"]=utc()
 http,last=request("GET","/api/portal/dashboard",cookie=True);usage=last.get("usage") or {}
 report["quota_after"]={k:usage[k] for k in ("metered","limit","used","remaining","plan_code") if k in usage}
 report["final_dashboard_http"]=http;save()
 print(json.dumps({"state":report["state"],"application_count":report["application_count"],"success_count":report["success_count"],"failure_count":report["failure_count"],"pilot_result":report.get("pilot_result"),"content_retained":False}))
 return 0 if report["failure_count"]==0 else 1
if __name__=="__main__":
 try:raise SystemExit(main())
 except Exception as error:
  print(json.dumps({"state":"FAILED_TO_RUN","error_code":safe_code(str(error)),"error_type":type(error).__name__,"secret_output":False}));raise SystemExit(1)