#!/usr/bin/env python3
"""One real readonly observer gate through governed Nucleo->Services SSH."""
import json,subprocess
code="""import hashlib,json,subprocess
from pathlib import Path
E=Path('/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/linux-clean');O=E/'soak-observer-r2';CLI=O/'linux_cloud_soak_resume.py'
def require(ok,code):
 if not ok:raise RuntimeError(code)
require(hashlib.sha256(CLI.read_bytes()).hexdigest()=='163144a8d215113b1c7abe49b836073a1902b7d1cfcd30eebe67c678a5349878','REVIEWED_OBSERVER_CLI_PIN')
require(hashlib.sha256((O/'observer_core.py').read_bytes()).hexdigest()=='f1ddd05efe9fee6bb98f360ee798d8ca0484a656effac327b8e208c98124c1d2','REVIEWED_OBSERVER_CORE_PIN')
require(not Path('/proc/2730587').exists(),'ORIGINAL_OBSERVER_NOT_STOPPED')
stop=json.loads((O/'old-observer-stop.json').read_text());require(stop['old_observer_stopped_confirmed'] and stop['application_count']==38,'OWN_STOP_PROOF')
def run(args,timeout=100):
 p=subprocess.run(['/usr/bin/python3','-I','-B',*map(str,args)],capture_output=True,text=True,timeout=timeout)
 require(p.returncode==0,'OWN_OBSERVER_GATE_STEP_FAILED')
 return json.loads(p.stdout.strip())
w=run([E/'probe53_identity_witness.py','--label','observer-r2-first-gate-witness'],30)
b=run([CLI,'--make-snapshot','--prior-report',O/'original-final-status.json','--reconciliation',E/'soak-cloud-original-readonly-reconciliation.json','--witness-json',E/'observer-r2-first-gate-witness.json','--old-observer-stopped-confirmed','--old-observer-stopped-at-utc',stop['stopped_at_utc'],'--snapshot-output',O/'first-gate-snapshot.json'])
require(b['resume_ready'] is True and b['application_count']==38,'OWN_GATE_SNAPSHOT_NOT_READY')
f=Path('/tmp_hara/commander-win50-utf8-20261012/apps/commander/.generated/full-acceptance-20261012/linux-install-20261012234227-4f4e7600.json')
v=run([CLI,'--run','--one-application','--resume-snapshot',O/'first-gate-snapshot.json','--fixture',f,'--report',O/'first-gate-status.json'],100)
require(v['application_count']==39 and v['phase']['application_count']==1 and v['phase']['success_count']==1 and v['phase']['failure_count']==0 and v['phase']['local_budget_units_verified']==1 and v['historical_failure_count']==10,'OWN_OBSERVER_ACTUAL_GATE_FAILED')
out=O/'first-gate-summary.json';out.write_text(json.dumps(v,indent=2)+'\\n')
print(json.dumps({'state':'PASS_REAL_READONLY_OBSERVER_R2_GATE','application_count':39,'historical_failure_count':10,'new_phase_success_count':1,'local_COMMITTED1_verified':True,'evidence':str(out),'Agent_or_holder_restarted':False}))
"""
r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=7","services","python3 -I -B -"],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=130)
if r.returncode:raise RuntimeError("OWN_OBSERVER_GATE_PIPELINE_FAILED")
print(r.stdout.decode())
