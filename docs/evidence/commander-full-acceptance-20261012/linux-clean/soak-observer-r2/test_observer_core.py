#!/usr/bin/env python3
"""Synthetic contract fixtures only: no network, SSH, Agent, holder or live-observer effects."""
import copy,hashlib,importlib.util,json,subprocess,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sp=importlib.util.spec_from_file_location("core_fixture",Path(__file__).with_name("observer_core.py"))
m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
NOW=datetime(2026,10,13,5,0,tzinfo=timezone.utc)
def sha(x):return hashlib.sha256(str(x).encode()).hexdigest()
def rid(i):return "HARA-QA-LINUX-RO-"+f"{i:024x}"
def native(now=NOW):
 return {"device_id":m.DEVICE,"agent_version":"0.3.53","agent_sha256":m.AGENT53,"agent_pid":1111,"agent_start_marker":"12345","agent_started_at_utc":"2026-10-13T01:50:08Z","operator_pid":2222,"operator_start_marker":"12344","approval_mode":"ASK_EVERY_ACTION","observed_at_utc":m.stamp(now)}
def snapshot(count=31,export_count=None,now=NOW):
 export_count=count if export_count is None else export_count
 prior={"schema":"hara.commander-linux-real-cloud-soak.v1","device_id":m.DEVICE,"environment":"DEV","started_at_utc":m.START,"deadline_at_utc":m.DEADLINE,"holder_started_at_utc":"2026-10-13T01:50:08Z","max_applications":200,"application_count":count,"success_count":max(0,count-3),"failure_count":min(3,count),"failures_by_code":{"QA_QUOTA_CALL_METADATA_INVALID":min(3,count)},"receipt_count":max(0,count-3),"receipt_chain_sha256":sha("old-chain"),"receipt_sample_first":sha(0),"receipt_sample_last":sha(max(0,count-4)),"last_observed_at_utc":"2026-10-13T04:00:00Z","pilot_result":{"state":"PASS","calls":20,"success":20,"elapsed_seconds":1201}}
 rows=[{"request_id":rid(i),"call_id":"HARA-CALL-"+f"{i:032x}","state":"COMPLETED","created_at_utc":m.START,"completed_at_utc":m.START,"usage_mode":"CLOUD_QUOTA","usage_units":1,"receipt_sha256":sha(i),"error_code":None,"result_state":"PASS","function_id":"device.info","risk_class":"READ_ONLY","process_exit_code":0} for i in range(export_count)]
 return {"schema":m.RESUME_SCHEMA,"report":prior,"reconciliation":{"d1_mutations":0,"payload_or_result_content_read":False,"calls":rows},"native_handoff_witness":native(now),"old_observer_stopped_confirmed":True,"report_source_sha256":sha("report"),"reconciliation_source_sha256":sha("recon")}
class Clock:
 def __init__(self,now=NOW):self.now=now;self.seconds=0
 def utcnow(self):return self.now+timedelta(seconds=self.seconds)
 def monotonic(self):return self.seconds
 def sleep(self,s):self.seconds+=s
class Router:
 def __init__(self,mode="CLOUD_QUOTA",units=1,state="COMPLETED",receipt=None):self.mode=mode;self.units=units;self.state=state;self.calls=[];self.hash=receipt or sha("new")
 def __call__(self,kind,body):
  self.calls.append((kind,copy.deepcopy(body)))
  if kind=="enqueue":return 201,{"call_id":"HARA-CALL-new","usage_mode":self.mode,"usage_units":self.units}
  return 200,{"state":self.state,"device_id":m.DEVICE,"result":{"state":"PASS","mutation_performed":False,"bridge_receipt_sha256":self.hash,"result":{"risk_class":"READ_ONLY","function_id":"device.info","process_exit_code":0}}}
def local(request_id,**change):
 return {"device_id":m.DEVICE,"request_id":request_id,"budget_id":"HARA-BUDGET-fixture","state":"COMMITTED","units":1,"sqlite_open_mode":"ro","query_only":True,**change}
class Contracts(unittest.TestCase):
 def observer(self,s=None,clock=None,save=None):
  clock=clock or Clock();s=s or snapshot(now=clock.utcnow());return m.Observer(s,clock,save or (lambda value:None),native(clock.utcnow()))
 def test_both_legitimate_usage_modes(self):
  for mode in ("CLOUD_QUOTA","LOCAL_BUDGET"):
   with self.subTest(mode=mode):
    ob=self.observer();r=ob.apply(rid(900),Router(mode),lambda x:local(x))
    self.assertTrue(r["accounting_verified"]);self.assertTrue(r["operation_verified"])
    p=ob.report["phases"][-1];self.assertEqual(p["success_count"],1)
    self.assertEqual(p["cloud_quota_units_verified"],int(mode=="CLOUD_QUOTA"));self.assertEqual(p["local_budget_units_verified"],int(mode=="LOCAL_BUDGET"))
 def test_invalid_units_always_poll_and_capture_receipt(self):
  for units in (True,False,1.0,"1",0,2,None):
   with self.subTest(units=units):
    router=Router(units=units);ob=self.observer();r=ob.apply(rid(901),router,lambda x:local(x))
    self.assertEqual([x[0] for x in router.calls],["enqueue","status"])
    self.assertTrue(r["terminal_confirmed"]);self.assertTrue(r["operation_verified"])
    self.assertEqual(r["receipt_sha256"],sha("new"));self.assertEqual(r["error_code"],"QA_USAGE_METADATA_INVALID")
    self.assertEqual(ob.report["phases"][-1]["success_count"],0)
 def test_invalid_mode_always_polls(self):
  ob=self.observer();router=Router("OTHER");r=ob.apply(rid(902),router,None)
  self.assertEqual(len(router.calls),2);self.assertEqual(r["error_code"],"QA_USAGE_METADATA_INVALID")
 def test_local_commit_required_and_identity_checked(self):
  proofs=[None,lambda x:local(x,state="RESERVED"),lambda x:local(x,units=2),lambda x:local(x,units=True),lambda x:local("wrong"),lambda x:local(x,device_id="wrong"),lambda x:local(x,sqlite_open_mode="rw"),lambda x:local(x,query_only=False)]
  for callback in proofs:
   with self.subTest(callback=callback):
    ob=self.observer();r=ob.apply(rid(903),Router("LOCAL_BUDGET"),callback)
    self.assertTrue(r["operation_verified"]);self.assertFalse(r.get("accounting_verified",False))
    self.assertEqual(ob.report["phases"][-1]["local_budget_units_verified"],0)
 def test_local_callback_after_terminal(self):
  calls=[];router=Router("LOCAL_BUDGET")
  def callback(x):
   self.assertEqual(router.calls[-1][0],"status");calls.append(x);return local(x)
  ob=self.observer();ob.apply(rid(904),router,callback);self.assertEqual(calls,[rid(904)])
 def test_old_false_fails_and_pilot_remain_immutable(self):
  s=snapshot();before=copy.deepcopy(s);ob=self.observer(s);ob.apply(rid(905),Router(),None)
  self.assertEqual(s,before);self.assertEqual(ob.report["historical_failure_count"],3)
  self.assertEqual(ob.report["historical_failures_by_code"],{"QA_QUOTA_CALL_METADATA_INVALID":3})
  self.assertEqual(ob.report["historical_pilot_result"],before["report"]["pilot_result"])
  self.assertEqual(ob.report["application_count"],32);self.assertEqual(ob.report["failure_count"],3)
 def test_original_times_and_explicit_gap(self):
  ob=self.observer()
  self.assertEqual(ob.report["started_at_utc"],m.START);self.assertEqual(ob.report["deadline_at_utc"],m.DEADLINE)
  self.assertFalse(ob.report["coverage_gaps"][-1]["unobserved_interval_is_success"])
  self.assertEqual(ob.report["phases"][-1]["resumed_at_utc"],m.stamp(NOW))
 def test_window_extension_rejected(self):
  for key,value in (("started_at_utc","2026-10-13T05:00:00Z"),("deadline_at_utc","2026-10-15T01:49:23Z"),("max_applications",201)):
   s=snapshot();s["report"][key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):self.observer(s)
 def test_incomplete_export_preserves_debt_blocks_enqueue(self):
  ob=self.observer(snapshot(31,30));self.assertEqual(ob.report["application_count"],31)
  self.assertEqual(ob.report["baseline_unidentified_application_reservations"],1);self.assertFalse(ob.report["historical_uniqueness_verified"])
  with self.assertRaises(RuntimeError):ob.apply(rid(906),Router(),None)
 def test_nonterminal_history_blocks_enqueue(self):
  s=snapshot();s["reconciliation"]["calls"][-1]["state"]="RUNNING";ob=self.observer(s)
  self.assertFalse(ob.report["resume_ready"])
  with self.assertRaises(RuntimeError):ob.reserve(rid(907))
 def test_old_observer_not_stopped_blocks_enqueue(self):
  s=snapshot();s["old_observer_stopped_confirmed"]=False;ob=self.observer(s)
  with self.assertRaises(RuntimeError):ob.reserve(rid(908))
 def test_199_then_200_budget_no_more_post(self):
  ob=self.observer(snapshot(199));router=Router();ob.apply(rid(909),router,None)
  self.assertEqual(ob.report["application_count"],200);self.assertEqual(ob.remaining_state(),"BUDGET_EXHAUSTED_PENDING_REVIEW")
  with self.assertRaises(RuntimeError):ob.apply(rid(910),router,None)
  self.assertEqual(len(router.calls),2)
 def test_resume_at_200_never_enqueues(self):
  ob=self.observer(snapshot(200));router=Router()
  with self.assertRaises(RuntimeError):ob.apply(rid(911),router,None)
  self.assertEqual(router.calls,[])
 def test_deadline_elapsed_never_enqueues(self):
  now=m.dt(m.DEADLINE)+timedelta(seconds=1);clock=Clock(now);ob=self.observer(snapshot(now=now),clock);router=Router()
  self.assertEqual(ob.remaining_state(),"DEADLINE_ELAPSED_PENDING_NATIVE_REVIEW")
  with self.assertRaises(RuntimeError):ob.apply(rid(912),router,None)
  self.assertEqual(router.calls,[])
 def test_native_identity_handoff_and_freshness(self):
  for key,value in (("agent_pid",3333),("operator_pid",3333),("agent_start_marker","different"),("operator_start_marker","9999"),("agent_sha256","0"*64),("approval_mode","SESSION_TRUSTED"),("observed_at_utc","2026-10-13T04:00:00Z")):
   s=snapshot();s["native_handoff_witness"][key]=value
   with self.subTest(key=key),self.assertRaises(RuntimeError):self.observer(s)
 def test_missing_witness_rejected(self):
  s=snapshot();s["native_handoff_witness"]=None
  with self.assertRaises(RuntimeError):self.observer(s)
 def test_journal_persisted_before_post(self):
  saves=[];ob=self.observer(save=lambda r:saves.append(copy.deepcopy(r)));router=Router()
  def request(kind,body):
   if kind=="enqueue":
    self.assertEqual(saves[-1]["application_count"],32);self.assertEqual(saves[-1]["ledger"][-1]["state"],"RESERVED_BEFORE_POST")
   return router(kind,body)
  ob.apply(rid(913),request,None)
 def test_crash_after_reservation_keeps_counter_and_never_posts(self):
  saved=[];router=Router()
  def crash(r):saved.append(copy.deepcopy(r));raise RuntimeError("SIMULATED_POWER_LOSS")
  ob=self.observer(save=crash)
  with self.assertRaises(RuntimeError):ob.apply(rid(914),router,None)
  self.assertEqual(router.calls,[]);self.assertEqual(saved[-1]["application_count"],32)
  s=snapshot();s["report"]=saved[-1];resumed=self.observer(s)
  self.assertEqual(resumed.report["application_count"],32);self.assertEqual(resumed.report["baseline_unidentified_application_reservations"],1)
  with self.assertRaises(RuntimeError):resumed.reserve(rid(914))
 def test_unknown_enqueue_keeps_request_and_budget(self):
  ob=self.observer()
  def timeout(kind,body):raise TimeoutError("FIXTURE_TIMEOUT")
  r=ob.apply(rid(915),timeout,None)
  self.assertEqual(r["state"],"ENQUEUE_RESULT_UNKNOWN_PENDING_RECONCILIATION");self.assertFalse(r["terminal_confirmed"])
  self.assertEqual(ob.report["application_count"],32);self.assertEqual(r["request_id"],rid(915))
 def test_status_timeout_marker_not_fake_terminal(self):
  ob=self.observer();router=Router(state="RUNNING");r=ob.apply(rid(916),router,None)
  self.assertEqual(r["state"],"TIMEOUT_PENDING_RECONCILIATION");self.assertFalse(r["terminal_confirmed"]);self.assertGreater(r["poll_attempts"],1)
  self.assertEqual(ob.report["application_count"],32)
 def test_historical_request_and_receipt_duplicates_rejected(self):
  for key in ("request_id","receipt_sha256"):
   s=snapshot();s["reconciliation"]["calls"][1][key]=s["reconciliation"]["calls"][0][key]
   with self.subTest(key=key),self.assertRaises(RuntimeError):self.observer(s)
 def test_new_duplicate_request_never_allocates(self):
  ob=self.observer();router=Router()
  with self.assertRaises(RuntimeError):ob.apply(rid(0),router,None)
  self.assertEqual(ob.report["application_count"],31);self.assertEqual(router.calls,[])
 def test_duplicate_receipt_not_success(self):
  ob=self.observer();r=ob.apply(rid(917),Router(receipt=sha(0)),None)
  self.assertEqual(r["error_code"],"QA_RECEIPT_DUPLICATE_OR_MISSING");self.assertEqual(ob.report["phases"][-1]["success_count"],0)
 def test_known_call_id_with_unexpected_http_still_polls(self):
  ob=self.observer();router=Router()
  def unusual(kind,body):
   http,packet=router(kind,body)
   return (500,packet) if kind=="enqueue" else (http,packet)
  r=ob.apply(rid(919),unusual,None)
  self.assertEqual([x[0] for x in router.calls],["enqueue","status"])
  self.assertTrue(r["terminal_confirmed"]);self.assertTrue(r["operation_verified"])
  self.assertEqual(r["receipt_sha256"],sha("new"));self.assertEqual(r["error_code"],"QA_ENQUEUE_HTTP_UNEXPECTED")
 def test_cli_adapter_accepts_exact_one_debit_row(self):
  spec=importlib.util.spec_from_file_location("cli_unit",Path(__file__).with_name("linux_cloud_soak_resume.py"))
  cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
  cli.probe=lambda *args:{"state":"PASS_LOCAL_COMMITTED1","local_commit_confirmed":True,"debit_metadata":[local(rid(920))]}
  proof=m.committed(cli.local_commit(rid(920)),rid(920));self.assertEqual(proof["units"],1)
  for bad in ([],[local(rid(920)),local(rid(920))],local(rid(920))):
   cli.probe=lambda *args:{"state":"PASS_LOCAL_COMMITTED1","local_commit_confirmed":True,"debit_metadata":bad}
   with self.subTest(bad=bad),self.assertRaises(RuntimeError):cli.local_commit(rid(920))
 def test_sequential_replay_199_200_refused_before_second_enqueue(self):
  s=snapshot(199);ob=self.observer(s);router=Router();ob.apply(rid(921),router,None)
  checkpoint=copy.deepcopy(ob.report);checkpoint_sha=sha(json.dumps(checkpoint,sort_keys=True)+"\n")
  with self.assertRaises(RuntimeError):m.checkpoint_guard(s,checkpoint,checkpoint_sha)
  self.assertEqual(len(router.calls),2);self.assertEqual(checkpoint["application_count"],200)
 def test_checkpoint_requires_exact_latest_source_even_equal_counter(self):
  s=snapshot();ob=self.observer(s);checkpoint=copy.deepcopy(ob.report);checkpoint_sha=sha("durable-latest")
  with self.assertRaises(RuntimeError):m.checkpoint_guard(s,checkpoint,checkpoint_sha)
  s["report"]=checkpoint;s["report_source_sha256"]=checkpoint_sha
  m.checkpoint_guard(s,checkpoint,checkpoint_sha)
 def test_v2_counter_cannot_drop_ledger_application(self):
  s=snapshot();ob=self.observer(s);ob.apply(rid(922),Router(),None);s["report"]=copy.deepcopy(ob.report);s["report"]["application_count"]-=1
  with self.assertRaises(RuntimeError):self.observer(s)
 def test_confirmed_stop_gap_separate_from_sampling_interval(self):
  s=snapshot();s["old_observer_stopped_at_utc"]="2026-10-13T04:59:30Z";ob=self.observer(s)
  self.assertEqual(ob.report["coverage_gaps"][-1]["from_utc"],s["old_observer_stopped_at_utc"])
  self.assertEqual(ob.report["coverage_gaps"][-1]["basis"],"CONFIRMED_OBSERVER_STOP")
  self.assertEqual(ob.report["sampled_coverage_intervals"][-1]["last_probe_at_utc"],s["report"]["last_observed_at_utc"])
 def test_cli_alternate_reports_cannot_replay_199_snapshot(self):
  # Actual isolated filesystem and sequential Python processes; API/witness are synthetic.
  with tempfile.TemporaryDirectory(prefix="observer-unit-",dir=str(Path(__file__).parent)) as tmp:
   root=Path(tmp);own=root/"own";own.mkdir()
   lock=root/"apps/commander/.generated/full-acceptance-20261012/linux-cloud-probe.lock";lock.parent.mkdir(parents=True);lock.write_text("")
   api=root/"apps/commander/scripts/commander_remote_customer_dev_acceptance.py";api.parent.mkdir(parents=True)
   api.write_text("import json,hashlib\nfrom pathlib import Path\nROOT=Path("+repr(str(root))+")\nclass fixtures:\n @staticmethod\n def read_private(p):return json.loads(p.read_text())\ndef request(data,method,path,body,internal=False,cookie=False):\n p=ROOT/'enqueue-count.json'\n if path.endswith('/calls'):\n  n=json.loads(p.read_text()) if p.exists() else 0;p.write_text(json.dumps(n+1));return 201,{'call_id':'HARA-CALL-fixture','usage_mode':'CLOUD_QUOTA','usage_units':1}\n return 200,{'state':'COMPLETED','device_id':"+repr(m.DEVICE)+",'result':{'state':'PASS','mutation_performed':False,'bridge_receipt_sha256':hashlib.sha256(b'fixture-receipt').hexdigest(),'result':{'risk_class':'READ_ONLY','function_id':'device.info','process_exit_code':0}}}\n")
   snap=own/"snapshot.json";snap.write_text(json.dumps(snapshot(199)));snap.chmod(0o600)
   fixture=own/"fixture.json";fixture.write_text(json.dumps({"environment":"DEV","dev_origin":"https://hara-commander-dev-v2.tiago-sartori.workers.dev","tenant_id":"HARA-ACCEPT-T-unit","issuer":"unit","external_subject":"unit"}));fixture.chmod(0o600)
   driver=root/"driver.py"
   driver.write_text("import importlib.util,json,sys\nfrom datetime import datetime,timedelta,timezone\nfrom pathlib import Path\nsp=importlib.util.spec_from_file_location('cli_fixture',"+repr(str(Path(__file__).with_name("linux_cloud_soak_resume.py")))+");c=importlib.util.module_from_spec(sp);sp.loader.exec_module(c)\nc.ROOT=Path("+repr(str(root))+");c.OWN=c.ROOT/'own';c.CHECKPOINT=c.OWN/'application-budget-checkpoint.json'\nclass Clock:\n def __init__(self):self.s=0\n def utcnow(self):return datetime(2026,10,13,5,0,tzinfo=timezone.utc)+timedelta(seconds=self.s)\n def monotonic(self):return self.s\n def sleep(self,s):self.s+=s\nc.Clock=Clock\nc.native_witness=lambda:json.loads((c.OWN/'snapshot.json').read_text())['native_handoff_witness']\nsys.argv=['cli','--run','--one-application','--resume-snapshot',str(c.OWN/'snapshot.json'),'--fixture',str(c.OWN/'fixture.json'),'--report',str(c.OWN/sys.argv[1])]\ntry:raise SystemExit(c.main())\nexcept RuntimeError as e:print(str(e));raise SystemExit(2)\n")
   first=subprocess.run(["/usr/bin/python3","-I","-B",str(driver),"report-A.json"],capture_output=True,text=True,timeout=10)
   self.assertEqual(first.returncode,0,first.stdout+first.stderr)
   cp=own/"application-budget-checkpoint.json";before=cp.read_bytes()
   self.assertEqual(json.loads(before)["application_count"],200)
   second=subprocess.run(["/usr/bin/python3","-I","-B",str(driver),"report-B.json"],capture_output=True,text=True,timeout=10)
   self.assertEqual(second.returncode,2,second.stdout+second.stderr)
   self.assertIn("QA_SNAPSHOT_APPLICATION_ROLLBACK",second.stdout)
   self.assertEqual(json.loads((root/"enqueue-count.json").read_text()),1)
   self.assertEqual(cp.read_bytes(),before);self.assertFalse((own/"report-B.json").exists())
 def test_terminal_accounting_is_idempotent(self):
  ob=self.observer();r=ob.apply(rid(918),Router(),None);before=copy.deepcopy(ob.report)
  self.assertFalse(ob.account(r,None));self.assertEqual(ob.report,before)
if __name__=="__main__":
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Contracts);r=unittest.TextTestRunner(verbosity=1).run(suite)
 print(json.dumps({"state":"PASS" if r.wasSuccessful() else "FAIL","tests":r.testsRun,"failures":len(r.failures),"errors":len(r.errors),"scope":"UNIT_SYNTHETIC_FIXTURES_NO_EXTERNAL_REQUESTS_OR_SSH","guest_operations":0,"live_observer_changes":0}))
 raise SystemExit(0 if r.wasSuccessful() else 1)
