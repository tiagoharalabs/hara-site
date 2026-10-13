#!/usr/bin/env python3
"""Recover observer bookkeeping through authorized known SSH; never repeat SIGTERM."""
import json,shlex,subprocess
code="""from pathlib import Path
import hashlib,json,subprocess
E=Path('/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/linux-clean');O=E/'soak-observer-r2'
def require(ok,code):
 if not ok:raise RuntimeError(code)
require(not Path('/proc/2730587').exists(),'OLD_OBSERVER_STILL_PRESENT')
raw=(E/'soak-cloud-status.json').read_bytes();r=json.loads(raw);a=json.loads((E/'soak-cloud-original-readonly-reconciliation.json').read_text())
require(r['state']=='CANCELLED' and r['finished_at_utc']=='2026-10-13T05:13:14Z' and r['application_count']==38 and r['success_count']==28 and r['failure_count']==10,'ORIGINAL_CANCELLED38_GUARD')
require(len(a['calls'])==38 and all(x['state']=='COMPLETED' for x in a['calls']) and a['d1_mutations']==0,'OWN_TERMINAL_AUDIT_GUARD')
before=json.loads((E/'observer-r2-before-stop-witness.json').read_text())
p=subprocess.run(['/usr/bin/python3','-I','-B',str(E/'probe53_identity_witness.py'),'--label','observer-r2-after-stop-recovered-witness'],capture_output=True,timeout=25)
require(p.returncode==0,'NATIVE53_AFTER_WITNESS_FAILED')
after=json.loads(p.stdout)
fields=('device_id','agent_version','agent_sha256','config_sha256','agent_pid','agent_start_marker','agent_started_at_utc','operator_pid','operator_start_marker','approval_mode')
require(all(before[k]==after[k] for k in fields),'NATIVE53_IDENTITY_CHANGED')
f=O/'original-final-status.json';require(not f.exists(),'FROZEN_HISTORY_EXISTS');f.write_bytes(raw);f.chmod(0o600)
value={'schema':'hara.commander-linux053-owned-observer-stop.v1','state':'PASS_OWNED_OBSERVER_CANCELLED_RECONCILED','stopped_at_utc':r['finished_at_utc'],'old_observer_pid':2730587,'old_observer_start_marker':'85106700','old_observer_stopped_confirmed':True,'application_count':38,'historical_success_count':28,'historical_failure_count':10,'all_prior_calls_terminal':True,'frozen_report':str(f),'frozen_report_sha256':hashlib.sha256(raw).hexdigest(),'before_native_witness':before,'after_native_witness':after,'same_agent_and_operator_PIDs_markers':True,'agent_holder_or_session_modified':False,'bookkeeping_recovery_reason':'Normal SIGTERM handler wrote CANCELLED/final timestamp; initial stopguard rejected changed final bytes after successful cancellation. No repeated SIGTERM.'}
out=O/'old-observer-stop.json';out.write_text(json.dumps(value,indent=2)+'\\n');out.chmod(0o600)
print(json.dumps({'state':value['state'],'application_count':38,'historical_failure_count':10,'same_agent_session':True,'after_witness':str(E/'observer-r2-after-stop-recovered-witness.json'),'stopUTC':r['finished_at_utc']}))
"""
r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=7","services","python3 -I -B -"],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45)
if r.returncode:raise RuntimeError("OWN_BOOKKEEPING_RECOVERY_FAILED")
print(r.stdout.decode())
