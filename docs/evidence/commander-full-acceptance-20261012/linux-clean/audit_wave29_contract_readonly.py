from pathlib import Path
from datetime import datetime,timezone
import importlib.util,json,hashlib
root=Path("/tmp_hara/commander-win50-utf8-20261012")
spec=importlib.util.spec_from_file_location("wave29_audit_fixtures",root/"apps/commander/scripts/full_acceptance_dev_fixtures.py")
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);f.guard()
data=f.read_private(root/"apps/commander/.generated/full-acceptance-20261012/linux-install-20261012234227-4f4e7600.json")
assert data["environment"]=="DEV" and data["tenant_id"].startswith("HARA-ACCEPT-T-")
q=f.fresh.q;ten=q(data["tenant_id"]);dev=q("HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889")
call=q("HARA-CALL-3085f5a7-899d-4c73-8910-258fc7077b5c")
meta=f.fresh.rows("SELECT call_id,request_id,state,usage_mode,usage_units,usage_budget_id,json_extract(call_result_metadata_json,'$.state') AS result_state,json_extract(call_result_metadata_json,'$.mutation_performed') AS mutation_performed,json_extract(call_result_metadata_json,'$.bridge_receipt_sha256') AS receipt_sha256,json_extract(call_result_metadata_json,'$.result.function_id') AS function_id,json_extract(call_result_metadata_json,'$.result.risk_class') AS risk_class,json_extract(call_result_metadata_json,'$.result.process_exit_code') AS process_exit_code FROM commander_device_calls WHERE tenant_id="+ten+" AND device_id="+dev+" AND call_id="+call+";")
assert len(meta)==1
request=q(meta[0]["request_id"])
unique=f.fresh.rows("SELECT COUNT(*) AS call_rows,SUM(usage_units) AS issued_call_units FROM commander_device_calls WHERE tenant_id="+ten+" AND device_id="+dev+" AND request_id="+request+";")
baseline=f.fresh.rows("SELECT period_key,meter_id,legacy_consumed_units,source,state,established_at_utc,invalidated_at_utc,invalidation_reason FROM commander_tenant_budget_baselines WHERE tenant_id="+ten+";")
old=Path("/tmp_hara/commander-full-053-signed-stage-20261012-root-r3/apps/commander/src/worker.js").read_text()
new=(root/"apps/commander/src/worker.js").read_text()
def function(src,name,end):
 a=src.index(name);b=src.index(end,a+len(name));return src[a:b]
matches={}
for name,end in (("function localBudgetEligibleDevice","async function localBudgetAllocatedUnits"),("async function issueDeviceBudgetBlock","function signedLeaseRequired"),("async function deviceProductLease","async function")):
 try:
  one=function(old,name,end);two=function(new,name,end)
  matches[name]=dict(identical=one==two,old_sha256=hashlib.sha256(one.encode()).hexdigest(),new_sha256=hashlib.sha256(two.encode()).hexdigest())
 except ValueError:matches[name]={"comparison":"NOT_LOCATED"}
report=dict(schema="hara.commander-linux-wave29-contract-readonly-audit.v1",at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),exact_own_DEV_fixture=True,d1_reads=3,d1_mutations=0,raw_payload_or_result_read=False,whitelisted_result_metadata=meta,exact_request_call_counts=unique,own_budget_baselines=baseline,worker53_vs54_budget_functions=matches,DO_live_quota_counter_read=False,local_commit_evidence_pending=True,budget_issued_at_utc="2026-10-13T03:40:10.160Z",dev54_deploy_at_utc="2026-10-13T03:40:32Z",budget_predates_cutover=True)
path=root/"docs/evidence/commander-full-acceptance-20261012/linux-clean/dev54-wave29-contract-readonly-audit.json"
path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps(report,sort_keys=True))
