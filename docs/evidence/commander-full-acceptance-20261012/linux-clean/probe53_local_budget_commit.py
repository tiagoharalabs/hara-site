#!/usr/bin/env python3
"""Query whitelisted COMMITTED1 metadata for one OWN read-only soak request."""
import argparse,json,re,shlex,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument("--request-id",required=True);p.add_argument("--budget-id");a=p.parse_args()
if not re.fullmatch("HARA-QA-LINUX-RO-[A-Za-z0-9-]{12,80}",a.request_id):raise RuntimeError("OWN_SOAK_REQUEST_ID_REQUIRED")
if a.budget_id and not re.fullmatch("HARA-BUDGET-[a-f0-9-]{36}",a.budget_id):raise RuntimeError("INVALID_OWN_BUDGET_ID")
args=json.dumps({"request_id":a.request_id,"budget_id":a.budget_id})
code="""import json,os,sqlite3,stat,sys
from pathlib import Path
q=Path('/home/commanderqa');device='HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889'
def require(ok,code):
 if not ok:raise RuntimeError(code)
require(os.getuid()==2000 and os.geteuid()==2000 and Path.home()==q and Path('/etc/hostname').read_text().strip()=='commander-linux-clean','OWN_QA53_PROFILE_GUARD')
p=q/'.local/share/hara-commander/operations.sqlite3'
require(not p.is_symlink() and p.is_file() and p.stat().st_uid==2000 and stat.S_IMODE(p.stat().st_mode)==0o600,'OWN_QA53_DB_GUARD')
a=json.loads(sys.argv[1]);conn=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=3);conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
rows=[dict(x) for x in conn.execute("SELECT d.request_id,d.budget_id,d.units,d.state,d.created_at_utc,d.updated_at_utc,b.device_id FROM local_budget_debits d JOIN local_budget_blocks b ON b.budget_id=d.budget_id WHERE d.request_id=? AND b.device_id=?",(a['request_id'],device))];conn.close()
valid=len(rows)==1 and rows[0]['state']=='COMMITTED' and type(rows[0]['units']) is int and rows[0]['units']==1 and (not a['budget_id'] or rows[0]['budget_id']==a['budget_id'])
print(json.dumps({'schema':'hara.commander-linux053-local-budget-commit-witness.v1','state':'PASS_LOCAL_COMMITTED1' if valid else 'PENDING_OR_INVALID_LOCAL_COMMIT','request_id':a['request_id'],'device_id':device,'local_commit_confirmed':valid,'debit_metadata':rows,'sqlite_open_mode':'ro','query_only':True,'secret_material_exposed':False,'agent_cli_or_session_modified':False}))
"""
ssh=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile=/tmp_hara/commander-linux-clean-20261012/known_hosts","-i","/tmp_hara/commander-linux-clean-20261012/qa_ed25519","commanderqa@192.168.122.180"]
cmd=shlex.join(["python3","-I","-B","-",args])
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(ssh+[cmd])],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
if r.returncode:raise RuntimeError("OWN_QA53_READ_ONLY_COMMIT_QUERY_FAILED")
report=json.loads(r.stdout);print(json.dumps(report))
raise SystemExit(0 if report['local_commit_confirmed'] else 2)
