#!/usr/bin/env python3
"""Read whitelisted local budget metadata from owned53 VM; never tokens or content."""
import json,shlex,subprocess
from pathlib import Path
E=Path("/tmp_hara/commander-win50-utf8-20261012/docs/evidence/commander-full-acceptance-20261012/linux-clean")
code="""import json,os,sqlite3,stat
from pathlib import Path
q=Path('/home/commanderqa')
if not(os.getuid()==2000 and os.geteuid()==2000 and Path.home()==q and Path('/etc/hostname').read_text().strip()=='commander-linux-clean'):raise RuntimeError('QA53_PROFILE_GUARD')
p=q/'.local/share/hara-commander/operations.sqlite3'
if p.is_symlink() or not p.is_file() or p.stat().st_uid!=2000 or stat.S_IMODE(p.stat().st_mode)!=0o600:raise RuntimeError('QA53_DB_GUARD')
conn=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=3)
conn.row_factory=sqlite3.Row;conn.execute('PRAGMA query_only=ON')
lease=[dict(x) for x in conn.execute("SELECT valid_until_utc,updated_at_utc,json_extract(lease_json,'$.usage_mode') AS usage_mode,json_extract(lease_json,'$.period_key') AS period_key,json_extract(lease_json,'$.plan_code') AS plan_code FROM product_lease")]
blocks=[dict(x) for x in conn.execute("SELECT b.budget_id,b.device_id,b.plan_code,b.meter_id,b.period_key,b.allocated_units,b.issued_at_utc,b.expires_at_utc,b.state,COALESCE(SUM(CASE WHEN d.state='COMMITTED' THEN d.units ELSE 0 END),0) AS committed_units,COALESCE(SUM(CASE WHEN d.state='RESERVED' THEN d.units ELSE 0 END),0) AS reserved_units FROM local_budget_blocks b LEFT JOIN local_budget_debits d ON d.budget_id=b.budget_id WHERE b.device_id=? GROUP BY b.budget_id ORDER BY b.issued_at_utc DESC LIMIT 4",('HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889',))]
debits=[dict(x) for x in conn.execute("SELECT request_id,budget_id,units,state,created_at_utc,updated_at_utc FROM local_budget_debits WHERE request_id=?",('HARA-QA-LINUX-RO-c686216c5b34c010edb21697',))]
conn.close()
print(json.dumps({'schema':'hara.commander-linux053-safe-local-budget-metadata.v1','state':'PASS_READ_ONLY','device_id':'HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889','sqlite_open_mode':'ro','query_only':True,'product_lease':lease,'local_budget_blocks':blocks,'wave29_debit':debits,'tokens_or_content_read_into_output':False,'agent_cli_or_session_modified':False}))
"""
ssh=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=7","-o","UserKnownHostsFile=/tmp_hara/commander-linux-clean-20261012/known_hosts","-i","/tmp_hara/commander-linux-clean-20261012/qa_ed25519","commanderqa@192.168.122.180"]
r=subprocess.run(["ssh","-o","BatchMode=yes","nucleo-a",shlex.join(ssh+["python3 -I -B -"])],input=code.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
if r.returncode:raise RuntimeError('READ_ONLY53_METADATA_TRANSPORT_FAILED')
report=json.loads(r.stdout);out=E/"soak-053-local-budget-wave29-metadata.json"
out.write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps(report))
