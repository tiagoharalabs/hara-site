#!/usr/bin/env python3
"""Pure bookkeeping/polling for the owned Linux53 observer; adapters perform no work at import."""
import copy, hashlib, re
from datetime import datetime, timezone

DEVICE="HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889"
AGENT53="db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e"
START="2026-10-13T02:02:22Z"
DEADLINE="2026-10-14T01:49:23Z"
MAX_APPLICATIONS=200
RESUME_SCHEMA="hara.commander-linux-cloud-resume-snapshot.v1"
REPORT_SCHEMA="hara.commander-linux-real-cloud-soak.v2"
TERMINAL={"COMPLETED","FAILED","EXPIRED","CANCELLED"}

def require(ok,code):
 if not ok:raise RuntimeError(code)
def safe_code(value):
 value=str(value or "UNKNOWN")
 return value if re.fullmatch("[A-Z0-9_:-]{1,100}",value) else "UNCLASSIFIED_ERROR"
def dt(value):
 parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
 require(parsed.tzinfo is not None,"UTC_TIMESTAMP_REQUIRED")
 return parsed.astimezone(timezone.utc)
def stamp(value):return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")
def integer(value):return type(value) is int and value>=0
def usage_error(mode,units):
 return None if mode in ("CLOUD_QUOTA","LOCAL_BUDGET") and type(units) is int and units==1 else "QA_USAGE_METADATA_INVALID"
def safe_id(value,prefix):
 require(isinstance(value,str) and value.startswith(prefix) and re.fullmatch("[A-Za-z0-9:_-]{1,160}",value),"QA_IDENTIFIER_INVALID")
 return value
def receipt(value):
 require(isinstance(value,str) and re.fullmatch("[0-9a-f]{64}",value),"QA_RECEIPT_INVALID")
 return value
def witness(value,now):
 require(isinstance(value,dict),"QA_NATIVE_WITNESS_REQUIRED")
 result={
 "device_id":value.get("device_id"),"agent_version":value.get("agent_version"),
 "agent_source_sha256":value.get("agent_source_sha256",value.get("agent_sha256")),
 "agent_pid":value.get("agent_pid"),"agent_start_marker":str(value.get("agent_start_marker") or ""),
 "agent_started_at_utc":value.get("agent_started_at_utc"),
 "operator_pid":value.get("operator_pid",value.get("owner_pid")),
 "operator_start_marker":str(value.get("operator_start_marker",value.get("owner_start_marker")) or ""),
 "approval_mode":value.get("approval_mode",value.get("operator_mode")),
 "observed_at_utc":value.get("observed_at_utc"),
 }
 require(result["device_id"]==DEVICE and result["agent_version"]=="0.3.53" and result["agent_source_sha256"]==AGENT53,"QA_NATIVE_AGENT_IDENTITY")
 require(integer(result["agent_pid"]) and result["agent_pid"]>1 and integer(result["operator_pid"]) and result["operator_pid"]>1,"QA_NATIVE_PID_REQUIRED")
 require(re.fullmatch("[0-9]+",result["agent_start_marker"]) and re.fullmatch("[0-9]+",result["operator_start_marker"]),"QA_NATIVE_START_MARKER_REQUIRED")
 require(result["agent_started_at_utc"] and dt(result["agent_started_at_utc"])<=now,"QA_NATIVE_AGENT_START_REQUIRED")
 require(result["approval_mode"]=="ASK_EVERY_ACTION","QA_NATIVE_ASK_REQUIRED")
 require(abs((now-dt(result["observed_at_utc"])).total_seconds())<=120,"QA_NATIVE_WITNESS_STALE")
 return result
def same_native(first,last):
 return all(first[k]==last[k] for k in ("device_id","agent_version","agent_source_sha256","agent_pid","agent_start_marker","agent_started_at_utc","operator_pid","operator_start_marker","approval_mode"))
def committed(value,request_id):
 require(isinstance(value,dict),"QA_LOCAL_COMMIT_PROOF_REQUIRED")
 require(value.get("device_id")==DEVICE and value.get("request_id")==request_id,"QA_LOCAL_COMMIT_IDENTITY")
 require(value.get("state")=="COMMITTED" and type(value.get("units")) is int and value["units"]==1,"QA_LOCAL_COMMIT_REQUIRED")
 require(value.get("sqlite_open_mode")=="ro" and value.get("query_only") is True,"QA_LOCAL_COMMIT_READ_ONLY_PROOF")
 return {"request_id":request_id,"device_id":DEVICE,"budget_id":safe_id(value.get("budget_id"),"HARA-BUDGET-"),"state":"COMMITTED","units":1,"sqlite_open_mode":"ro","query_only":True}

def checkpoint_guard(snapshot,checkpoint,checkpoint_sha):
 require(checkpoint.get("schema")==REPORT_SCHEMA and checkpoint.get("device_id")==DEVICE and checkpoint.get("started_at_utc")==START and checkpoint.get("deadline_at_utc")==DEADLINE and checkpoint.get("max_applications")==MAX_APPLICATIONS,"QA_DURABLE_CHECKPOINT_SCOPE")
 require(integer(checkpoint.get("application_count")) and checkpoint["application_count"]<=MAX_APPLICATIONS,"QA_DURABLE_CHECKPOINT_COUNTER")
 require(snapshot["report"]["application_count"]>=checkpoint["application_count"],"QA_SNAPSHOT_APPLICATION_ROLLBACK")
 require(snapshot["report_source_sha256"]==checkpoint_sha,"QA_LATEST_DURABLE_CHECKPOINT_REQUIRED")
def build_report(snapshot,now,current_witness=None):
 require(snapshot.get("schema")==RESUME_SCHEMA,"QA_RESUME_SCHEMA")
 prior=copy.deepcopy(snapshot.get("report"));require(isinstance(prior,dict),"QA_PRIOR_REPORT_REQUIRED")
 require(prior.get("schema") in ("hara.commander-linux-real-cloud-soak.v1",REPORT_SCHEMA),"QA_PRIOR_REPORT_SCHEMA")
 require(prior.get("device_id")==DEVICE and prior.get("environment")=="DEV","QA_PRIOR_IDENTITY")
 require(prior.get("started_at_utc")==START and prior.get("deadline_at_utc")==DEADLINE,"QA_ORIGINAL_WINDOW_CHANGED")
 require(prior.get("max_applications")==MAX_APPLICATIONS and integer(prior.get("application_count")) and prior["application_count"]<=MAX_APPLICATIONS,"QA_GLOBAL_APPLICATION_CEILING")
 require(integer(prior.get("success_count")) and integer(prior.get("failure_count")) and prior["success_count"]+prior["failure_count"]<=prior["application_count"],"QA_PRIOR_COUNTERS")
 for name in ("report_source_sha256","reconciliation_source_sha256"):receipt(snapshot.get(name))
 recon=copy.deepcopy(snapshot.get("reconciliation"));require(isinstance(recon,dict) and isinstance(recon.get("calls"),list),"QA_RECONCILIATION_REQUIRED")
 require(recon.get("d1_mutations")==0 and recon.get("payload_or_result_content_read") is False,"QA_RECONCILIATION_READ_ONLY")
 calls=[];requests=set();receipts=set();call_ids=set()
 for row in recon["calls"]:
  rid=safe_id(row.get("request_id"),"HARA-QA-LINUX-RO-");cid=safe_id(row.get("call_id"),"HARA-CALL-")
  require(rid not in requests and cid not in call_ids,"QA_HISTORICAL_ID_DUPLICATE");requests.add(rid);call_ids.add(cid)
  r=row.get("receipt_sha256")
  if r is not None:
   receipt(r);require(r not in receipts,"QA_HISTORICAL_RECEIPT_DUPLICATE");receipts.add(r)
  require(row.get("function_id")=="device.info" and row.get("risk_class")=="READ_ONLY","QA_HISTORICAL_TOOL_SCOPE")
  calls.append({k:row.get(k) for k in ("request_id","call_id","state","created_at_utc","completed_at_utc","usage_mode","usage_units","receipt_sha256","error_code","result_state","function_id","risk_class","process_exit_code")})
 require(len(calls)<=prior["application_count"],"QA_HISTORY_EXCEEDS_RESERVED_COUNTER")
 unknown=prior["application_count"]-len(calls)
 pending=[x["request_id"] for x in calls if x["state"] not in TERMINAL]
 ready=snapshot.get("old_observer_stopped_confirmed") is True and unknown==0 and not pending
 base=witness(snapshot.get("native_handoff_witness"),now)
 handoff=None
 if current_witness is not None:
  fresh=witness(current_witness,now);require(same_native(base,fresh),"QA_NATIVE_HANDOFF_IDENTITY_CHANGED");handoff=fresh
 history=copy.deepcopy(prior.get("historical_report",prior))
 if prior.get("schema")==REPORT_SCHEMA:
  require(prior["application_count"]==history["application_count"]+len(prior.get("ledger",[])),"QA_PHASE_APPLICATION_COUNTER_ROLLBACK")
 pilot=copy.deepcopy(history.get("pilot_result"))
 require(pilot and pilot.get("state")=="PASS" and pilot.get("calls")==20 and pilot.get("success")==20,"QA_ORIGINAL_PILOT_REQUIRED")
 phase={"phase_id":len(prior.get("phases",[]))+1,"resumed_at_utc":stamp(now),"starting_application_count":prior["application_count"],"application_count":0,"success_count":0,"failure_count":0,"cloud_quota_units_verified":0,"local_budget_units_verified":0,"state":"PREPARED"}
 report={k:copy.deepcopy(prior.get(k)) for k in ("success_count","failure_count","failures_by_code","receipt_count","receipt_chain_sha256","receipt_sample_first","receipt_sample_last","last_observed_at_utc")}
 report.update(schema=REPORT_SCHEMA,state="PREPARED",device_id=DEVICE,environment="DEV",started_at_utc=START,deadline_at_utc=DEADLINE,max_applications=MAX_APPLICATIONS,application_count=prior["application_count"],
  historical_report=history,historical_failure_count=history["failure_count"],historical_failures_by_code=copy.deepcopy(history["failures_by_code"]),historical_pilot_result=pilot,
  resume_ready=ready,baseline_unidentified_application_reservations=unknown,historical_pending_request_ids=pending,
  historical_uniqueness_verified=unknown==0 and len(receipts)==len(calls),
  reconciliation_calls=calls,ledger=copy.deepcopy(prior.get("ledger",[])),phases=copy.deepcopy(prior.get("phases",[]))+[phase],
  native_handoff_witness=base,native_handoff_after_witness=handoff,handoff_same_agent_session=handoff is not None,
  coverage_gaps=copy.deepcopy(prior.get("coverage_gaps",[]))+[{"from_utc":snapshot.get("old_observer_stopped_at_utc") or prior.get("last_observed_at_utc") or START,"to_utc":stamp(now),"reason":"OBSERVER_REPLACEMENT_AND_METADATA_RECONCILIATION","basis":"CONFIRMED_OBSERVER_STOP" if snapshot.get("old_observer_stopped_at_utc") else "LAST_PROBE_PROXY_STOP_TIME_NOT_PROVIDED","unobserved_interval_is_success":False}],
  sampled_coverage_intervals=copy.deepcopy(prior.get("sampled_coverage_intervals",[]))+[{"last_probe_at_utc":prior.get("last_observed_at_utc") or START,"resume_at_utc":stamp(now),"not_an_observer_outage_measurement":True}],
  report_source_sha256=snapshot["report_source_sha256"],reconciliation_source_sha256=snapshot["reconciliation_source_sha256"],
  content_retained=False,credentials_retained=False,human_ASK_inputs_generated=False,signed_agent_modified=False,holder_or_session_restarted=False,
  accounting_scope="CLOUD_QUOTA_OR_LOCAL_BUDGET_UNIT1_SEPARATE_PROOFS",historical_failures_rewritten=False)
 if snapshot.get("old_observer_stopped_at_utc"):
  require(dt(START)<=dt(snapshot["old_observer_stopped_at_utc"])<=now,"QA_OBSERVER_STOP_TIMESTAMP")
 report["holder_started_at_utc"]=history.get("holder_started_at_utc")
 report["authoritative_historical_receipt_count"]=len(receipts)
 report["receipt_count_basis"]="LEGACY_OBSERVER_COUNTER_PLUS_NEW_PHASE_CAPTURES"
 require(len(report["ledger"])<=prior["application_count"],"QA_LEDGER_COUNTER_MISMATCH")
 known={x["request_id"] for x in report["ledger"]}
 require(len(known)==len(report["ledger"]),"QA_PRIOR_LEDGER_DUPLICATE")
 return report,requests|known,receipts

class Observer:
 def __init__(self,snapshot,clock,save,current_witness=None):
  self.clock=clock;self.save=save;self.report,self.requests,self.receipts=build_report(snapshot,clock.utcnow(),current_witness)
 def remaining_state(self):
  if self.clock.utcnow()>=dt(DEADLINE):return "DEADLINE_ELAPSED_PENDING_NATIVE_REVIEW"
  if self.report["application_count"]>=MAX_APPLICATIONS:return "BUDGET_EXHAUSTED_PENDING_REVIEW"
  return None
 def reserve(self,request_id):
  require(self.report["resume_ready"] and self.report["handoff_same_agent_session"],"QA_HANDOFF_RECONCILIATION_REQUIRED")
  require(self.remaining_state() is None,"QA_NO_APPLICATION_BUDGET_OR_WINDOW")
  safe_id(request_id,"HARA-QA-LINUX-RO-");require(request_id not in self.requests,"QA_REQUEST_ID_DUPLICATE")
  self.requests.add(request_id);self.report["application_count"]+=1;self.report["phases"][-1]["application_count"]+=1
  record={"request_id":request_id,"call_id":None,"reserved_at_utc":stamp(self.clock.utcnow()),"state":"RESERVED_BEFORE_POST","usage_mode":None,"usage_units":None,"receipt_sha256":None,"terminal_confirmed":False,"metrics_accounted":False}
  self.report["ledger"].append(record);self.save(self.report)
  return record
 def account(self,record,error):
  if record["metrics_accounted"]:return False
  record["metrics_accounted"]=True;record["error_code"]=error;phase=self.report["phases"][-1]
  if error:
   self.report["failure_count"]+=1;phase["failure_count"]+=1
   codes=self.report["failures_by_code"];codes[error]=codes.get(error,0)+1
  else:
   self.report["success_count"]+=1;phase["success_count"]+=1
   mode=record["usage_mode"];phase["cloud_quota_units_verified" if mode=="CLOUD_QUOTA" else "local_budget_units_verified"]+=1
  if record.get("receipt_sha256") and record["receipt_sha256"] not in self.receipts:
   r=record["receipt_sha256"];self.receipts.add(r);self.report["receipt_count"]+=1
   if self.report["receipt_sample_first"] is None:self.report["receipt_sample_first"]=r
   self.report["receipt_sample_last"]=r
   self.report["receipt_chain_sha256"]=hashlib.sha256(((self.report["receipt_chain_sha256"] or "")+r).encode()).hexdigest()
  self.report["last_observed_at_utc"]=stamp(self.clock.utcnow());self.save(self.report);return True
 def apply(self,request_id,request,local_commit):
  record=self.reserve(request_id)
  body={"tool_id":"hara.device.info","device_id":DEVICE,"request_id":request_id,"payload":{}}
  try:http,call=request("enqueue",body)
  except Exception:
   record["state"]="ENQUEUE_RESULT_UNKNOWN_PENDING_RECONCILIATION";self.account(record,"QA_ENQUEUE_RESULT_UNKNOWN");return record
  cid=call.get("call_id")
  record["enqueue_http"]=http
  if not cid:
   record["state"]="ENQUEUE_HTTP_RESULT_PENDING_RECONCILIATION";record["enqueue_http"]=http;self.account(record,"QA_ENQUEUE_REJECTED_OR_UNKNOWN");return record
  record["call_id"]=safe_id(cid,"HARA-CALL-")
  mode=call.get("usage_mode");units=call.get("usage_units")
  record["usage_mode"]=mode if mode in ("CLOUD_QUOTA","LOCAL_BUDGET") else "UNRECOGNIZED_MODE"
  record["usage_units"]=units if type(units) in (int,float,bool) else None
  record["usage_units_type"]=type(units).__name__;metadata_error=usage_error(mode,units)
  record["state"]="ENQUEUED_PENDING";self.save(self.report)
  end=min(self.clock.monotonic()+40,self.clock.monotonic()+max(0,(dt(DEADLINE)-self.clock.utcnow()).total_seconds()))
  result={};polls=0
  while self.clock.monotonic()<end:
   polls+=1
   try:status,result=request("status",{"call_id":record["call_id"]})
   except Exception:status=0;result={}
   record["last_status_http"]=status
   if status==200 and result.get("state") in TERMINAL:break
   self.clock.sleep(.5)
  record["poll_attempts"]=polls
  if not (record.get("last_status_http")==200 and result.get("state") in TERMINAL):
   record["state"]="TIMEOUT_PENDING_RECONCILIATION";self.account(record,"QA_CALL_STATUS_TIMEOUT_PENDING");return record
  record["state"]=result["state"];record["terminal_confirmed"]=True;record["completed_at_utc"]=stamp(self.clock.utcnow())
  error=None
  try:
   require(result.get("device_id")==DEVICE,"QA_RESULT_IDENTITY_MISMATCH")
   if result.get("call_id") is not None:require(result["call_id"]==record["call_id"],"QA_RESULT_CALL_ID_MISMATCH")
   if result.get("request_id") is not None:require(result["request_id"]==request_id,"QA_RESULT_REQUEST_ID_MISMATCH")
   proof=result.get("result") or {};r=proof.get("result") or {};h=proof.get("bridge_receipt_sha256")
   if h is not None:record["receipt_sha256"]=receipt(h)
   require(result["state"]=="COMPLETED" and not result.get("error_code"),"QA_RESULT_NOT_COMPLETED")
   require(proof.get("state")=="PASS" and proof.get("mutation_performed") is False and r.get("risk_class")=="READ_ONLY" and r.get("function_id")=="device.info" and type(r.get("process_exit_code")) is int and r["process_exit_code"]==0,"QA_RESULT_OPERATION_INVALID")
   require(record["receipt_sha256"] and record["receipt_sha256"] not in self.receipts,"QA_RECEIPT_DUPLICATE_OR_MISSING")
   record["operation_verified"]=True
   require(http in (200,201),"QA_ENQUEUE_HTTP_UNEXPECTED")
   require(metadata_error is None,metadata_error or "QA_USAGE_METADATA_INVALID")
   if mode=="LOCAL_BUDGET":
    require(callable(local_commit),"QA_LOCAL_COMMIT_CALLBACK_REQUIRED")
    record["local_commit_proof"]=committed(local_commit(request_id),request_id)
   record["accounting_verified"]=True
  except Exception as failure:error=safe_code(str(failure))
  self.account(record,error);return record
