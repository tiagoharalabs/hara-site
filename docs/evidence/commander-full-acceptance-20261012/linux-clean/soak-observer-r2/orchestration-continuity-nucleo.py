#!/usr/bin/env python3
"""Resume own readonly observer under an independent bounded user unit."""
import json,subprocess
code="""import hashlib,json,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
R=Path('/tmp_hara/commander-win50-utf8-20261012');E=R/'docs/evidence/commander-full-acceptance-20261012/linux-clean';O=E/'soak-observer-r2';CLI=O/'linux_cloud_soak_resume.py';UNIT='hara-commander-linux-cloud-observer-r2-20261013'
def require(ok,code):
 if not ok:raise RuntimeError(code)
def run(args,timeout=60,env=None):
 p=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=timeout,env=env);require(p.returncode==0,'OWN_OBSERVER_CONTINUITY_STEP_FAILED');return p.stdout
require(hashlib.sha256(CLI.read_bytes()).hexdigest()=='163144a8d215113b1c7abe49b836073a1902b7d1cfcd30eebe67c678a5349878' and hashlib.sha256((O/'observer_core.py').read_bytes()).hexdigest()=='f1ddd05efe9fee6bb98f360ee798d8ca0484a656effac327b8e208c98124c1d2','REVIEWED_OBSERVER_PINS')
cp=O/'application-budget-checkpoint.json';c=json.loads(cp.read_text());require(c['application_count']==39 and c['phases'][-1]['success_count']==1 and c['historical_failure_count']==10,'OWN_LATEST_CHECKPOINT39_REQUIRED')
bins=sorted(Path('/home/sartorius/.nvm/versions/node').glob('v24*/bin'));require(bins,'PINNED_NODE24_REQUIRED');env=dict(os.environ,PATH=str(bins[-1])+':'+os.environ['PATH'])
run(['/usr/bin/python3','-I','-B','/tmp_hara/capacity-linux-observer-readonly-reconcile.py'],50,env)
a=json.loads((E/'soak-cloud-original-readonly-reconciliation.json').read_text());require(len(a['calls'])==39 and all(x['state']=='COMPLETED' for x in a['calls']),'OWN39_CALLS_TERMINAL')
run(['/usr/bin/python3','-I','-B',E/'probe53_identity_witness.py','--label','observer-r2-continuity-witness'],30)
snap=O/'continuity-snapshot.json'
v=json.loads(run(['/usr/bin/python3','-I','-B',CLI,'--make-snapshot','--prior-report',cp,'--reconciliation',E/'soak-cloud-original-readonly-reconciliation.json','--witness-json',E/'observer-r2-continuity-witness.json','--old-observer-stopped-confirmed','--old-observer-stopped-at-utc',c['phases'][-1].get('finished_at_utc',c.get('finished_at_utc')),'--snapshot-output',snap]))
require(v['resume_ready'] is True and v['application_count']==39,'CONTINUITY_SNAPSHOT_NOT_READY')
uid=os.getuid();runtime=Path('/run/user')/str(uid);bus=runtime/'bus';require(bus.is_socket() and bus.stat().st_uid==uid,'OWN_USER_BUS_REQUIRED')
env=dict(os.environ,XDG_RUNTIME_DIR=str(runtime),DBUS_SESSION_BUS_ADDRESS='unix:path='+str(bus))
show=subprocess.run(['systemctl','--user','show',UNIT+'.service','--property=LoadState','--value'],capture_output=True,text=True,timeout=8,env=env);require(show.stdout.strip() in ('','not-found'),'OWN_UNIT_ALREADY_EXISTS')
seconds=int((datetime.fromisoformat('2026-10-14T01:49:23+00:00')-datetime.now(timezone.utc)).total_seconds())+60;require(0<seconds<=86400,'OWN_UNIT_DURATION_GUARD')
fixture=R/'apps/commander/.generated/full-acceptance-20261012/linux-install-20261012234227-4f4e7600.json'
run(['systemd-run','--user','--unit='+UNIT,'--collect','--property=RuntimeMaxSec='+str(seconds),'--property=TimeoutStopSec=50','--property=Type=exec','/usr/bin/python3','-I','-B',CLI,'--run','--resume-snapshot',snap,'--fixture',fixture,'--report',O/'soak-cloud-r2-status.json'],20,env)
pid=int(run(['systemctl','--user','show',UNIT+'.service','--property=MainPID','--value'],10,env).strip());require(pid>1,'OWN_UNIT_MAINPID_REQUIRED')
raw=Path('/proc/'+str(pid)+'/stat').read_text();marker=raw[raw.rfind(')')+2:].split()[19]
value={'schema':'hara.commander-linux053-observer-r2-independent-unit-launch.v1','state':'STARTED_PENDING_NEXT_PROBE','started_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),'unit':UNIT+'.service','pid':pid,'process_start_marker':marker,'starting_application_count':39,'max_applications':200,'deadline_at_utc':'2026-10-14T01:49:23Z','Agent53_or_holder_restarted':False,'Services_agent_restarted':False,'unit_independent_of_Services_agent':True,'governed_transport':'HARA_Commander_DIRECT_Nucleo_to_known_SSHServices_to_own_DEV_VM','core_sha256':'f1ddd05efe9fee6bb98f360ee798d8ca0484a656effac327b8e208c98124c1d2','CLI_sha256':'163144a8d215113b1c7abe49b836073a1902b7d1cfcd30eebe67c678a5349878'}
out=O/'continuity-launch.json';out.write_text(json.dumps(value,indent=2)+'\\n');print(json.dumps(value))
"""
r=subprocess.run(["ssh","-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","ConnectTimeout=7","services","python3 -I -B -"],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
if r.returncode:raise RuntimeError("OWN_OBSERVER_CONTINUITY_LAUNCH_FAILED")
print(r.stdout.decode())
