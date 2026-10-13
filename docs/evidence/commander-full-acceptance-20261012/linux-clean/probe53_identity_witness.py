#!/usr/bin/env python3
"""Read-only witness of actual unchanged53 Agent and its CLI owner; no credentials."""
import argparse,json,re,shlex,subprocess
from pathlib import Path
E=Path("/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/linux-clean")
p=argparse.ArgumentParser();p.add_argument("--label",required=True);a=p.parse_args()
if not re.fullmatch("[a-z0-9-]{1,70}",a.label):raise RuntimeError("INVALID_OWN_WITNESS_LABEL")
code="""import hashlib,json,os,stat,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
q=Path('/home/commanderqa');d=q/'.local/share/hara-commander';c=q/'.config/hara-commander/device.env'
def require(ok,code):
 if not ok:raise RuntimeError(code)
require(os.getuid()==2000 and os.geteuid()==2000 and Path.home()==q and Path('/etc/hostname').read_text().strip()=='commander-linux-clean','QA53_PROFILE_GUARD')
def marker(pid):
 require(type(pid) is int and pid>1 and Path('/proc/'+str(pid)).stat().st_uid==2000,'QA53_PID_OWNER')
 raw=Path('/proc/'+str(pid)+'/stat').read_text();return raw[raw.rfind(')')+2:].split()[19]
v=dict(line.split('=',1) for line in c.read_text().splitlines() if '=' in line)
require(v['HARA_COMMANDER_URL']=='https://hara-commander-dev-v2.tiago-sartori.workers.dev' and v['HARA_DEVICE_ID']=='HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889' and v['HARA_COMMANDER_APPROVAL_MODE']=='ASK_EVERY_ACTION','QA53_BOUND_CONFIG_GUARD')
agent=d/'hara-commander-agent'
require(not agent.is_symlink() and agent.stat().st_uid==2000,'QA53_SOURCE_OWNER')
sha=hashlib.sha256(agent.read_bytes()).hexdigest();require(sha=='db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e','QA53_SOURCE_PIN')
env=dict(os.environ,HOME=str(q),XDG_RUNTIME_DIR='/run/user/2000',DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/2000/bus')
pid=int(subprocess.check_output(['systemctl','--user','show','hara-commander-agent.service','--property=MainPID','--value'],env=env,text=True,timeout=5).strip())
pm=marker(pid);cmd=Path('/proc/'+str(pid)+'/cmdline').read_bytes();require(str(agent).encode() in cmd,'QA53_AGENT_CMDLINE')
sessionfile=d/'operator-session.json';require(not sessionfile.is_symlink() and sessionfile.stat().st_uid==2000 and stat.S_IMODE(sessionfile.stat().st_mode)==0o600,'QA53_SESSION_OWNER')
s=json.loads(sessionfile.read_text());owner=s['owner_pid'];om=marker(owner)
require(str(s['owner_start_marker'])==om and s['approval_mode']=='ASK_EVERY_ACTION' and s.get('device_id')==v['HARA_DEVICE_ID'],'QA53_OPERATOR_BINDING')
started=s.get('started_at_epoch');require(type(started) is int and 0<=time.time()-started<43200,'QA53_OPERATOR_12H_TTL')
expiry=datetime.fromtimestamp(started+43200,timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
runtime=json.loads((d/'runtime-status.json').read_text());require(runtime['agent_version']=='0.3.53','QA53_RUNTIME_VERSION')
out={'schema':'hara.commander-linux053-soak-identity-witness.v1','state':'PASS_READ_ONLY','observed_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z'),'environment':'DEV','device_id':v['HARA_DEVICE_ID'],'agent_version':'0.3.53','agent_sha256':sha,'config_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'agent_pid':pid,'agent_start_marker':pm,'agent_started_at_utc':runtime.get('started_at_utc'),'operator_pid':owner,'operator_start_marker':om,'approval_mode':s['approval_mode'],'operator_started_at_epoch':started,'operator_started_at_utc':s.get('started_at_utc'),'operator_age_seconds':int(time.time()-started),'operator_max_seconds':43200,'operator_derived_expires_at_utc':expiry,'source_binding_valid':True,'secret_material_exposed':False,'agent_cli_or_session_modified':False}
print(json.dumps(out))
"""
ssh=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile=/tmp_hara/commander-linux-clean-20261012/known_hosts","-i","/tmp_hara/commander-linux-clean-20261012/qa_ed25519","commanderqa@192.168.122.180"]
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(ssh+["python3 -I -B -"])],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
if r.returncode:raise RuntimeError("QA53_READ_ONLY_WITNESS_FAILED")
report=json.loads(r.stdout);out=E/(a.label+".json");out.write_text(json.dumps(report,indent=2)+"\n");out.chmod(0o600)
print(json.dumps(report))
