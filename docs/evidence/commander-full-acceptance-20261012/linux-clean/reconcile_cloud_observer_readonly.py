from pathlib import Path
from datetime import datetime,timezone
import importlib.util,json
root=Path("/tmp_hara/commander-win50-utf8-20261012")
spec=importlib.util.spec_from_file_location("wave29_fixtures",root/"apps/commander/scripts/full_acceptance_dev_fixtures.py")
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f);f.guard()
data=f.read_private(root/"apps/commander/.generated/full-acceptance-20261012/linux-install-20261012234227-4f4e7600.json")
assert data["environment"]=="DEV" and data["tenant_id"].startswith("HARA-ACCEPT-T-")
q=f.fresh.q;tenant=q(data["tenant_id"]);device=q("HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889")
rows=f.fresh.rows("SELECT call_id,request_id,state,created_at_utc,completed_at_utc,error_code,usage_mode,usage_units,usage_period_key,usage_budget_id,json_extract(call_result_metadata_json,'$.state') AS result_state,json_extract(call_result_metadata_json,'$.bridge_receipt_sha256') AS receipt_sha256,json_extract(call_result_metadata_json,'$.result.function_id') AS function_id,json_extract(call_result_metadata_json,'$.result.risk_class') AS risk_class,json_extract(call_result_metadata_json,'$.result.process_exit_code') AS process_exit_code FROM commander_device_calls WHERE tenant_id="+tenant+" AND device_id="+device+" AND request_id LIKE 'HARA-QA-LINUX-RO-%' AND created_at_utc>='2026-10-13T02:02:22Z' ORDER BY created_at_utc;")
terminal={"COMPLETED","FAILED","EXPIRED","CANCELLED"}
summary={"total":len(rows),"terminal":sum(r["state"] in terminal for r in rows),"completed":sum(r["state"]=="COMPLETED" for r in rows),"cloud_quota_units":sum(r["usage_units"] for r in rows if r["usage_mode"]=="CLOUD_QUOTA"),"local_budget_units":sum(r["usage_units"] for r in rows if r["usage_mode"]=="LOCAL_BUDGET"),"request_ids_unique":len({r["request_id"] for r in rows})==len(rows),"nonterminal":[{"call_id":r["call_id"],"request_id":r["request_id"],"state":r["state"]} for r in rows if r["state"] not in terminal]}
report={"schema":"hara.commander-linux-cloud-observer-readonly-reconciliation.v1","at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),"scope":"EXACT_OWN_DEV_FIXTURE_OBSERVER_PREFIX_SINCE_START","d1_reads":1,"d1_mutations":0,"payload_or_result_content_read":False,"summary":summary,"calls":rows}
path=root/"docs/evidence/commander-full-acceptance-20261012/linux-clean/soak-cloud-original-readonly-reconciliation.json"
path.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps({"at_utc":report["at_utc"],"summary":summary,"calls_after_wave28":[r for r in rows if r["created_at_utc"]>="2026-10-13T03:40:00Z"]},sort_keys=True))
