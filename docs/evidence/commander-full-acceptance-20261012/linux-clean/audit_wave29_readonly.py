from pathlib import Path
from datetime import datetime,timezone
import importlib.util,json,hashlib
root=Path("/tmp_hara/commander-win50-utf8-20261012")
p=root/"apps/commander/scripts/full_acceptance_dev_fixtures.py"
spec=importlib.util.spec_from_file_location("capacity_audit_fixtures",p)
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
f.guard()
fixture=root/"apps/commander/.generated/full-acceptance-20261012/linux-install-20261012234227-4f4e7600.json"
data=f.read_private(fixture)
assert data["environment"]=="DEV" and data["tenant_id"].startswith("HARA-ACCEPT-T-")
device="HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889"
q=f.fresh.q
ten=q(data["tenant_id"]);sub=q(data["subject_id"]);dev=q(device)
calls=f.fresh.rows("SELECT call_id, request_id, tenant_id, subject_id, device_id, tool_id, state, created_at_utc, expires_at_utc, claimed_at_utc, completed_at_utc, error_code, usage_mode, usage_units, usage_period_key, usage_budget_id FROM commander_device_calls WHERE tenant_id="+ten+" AND subject_id="+sub+" AND device_id="+dev+" AND created_at_utc>='2026-10-13T03:25:00Z' AND created_at_utc<'2026-10-13T03:50:00Z' ORDER BY created_at_utc;")
budgets=f.fresh.rows("SELECT budget_id, state, period_key, plan_code, allocation_sequence, units_allocated, units_issued, units_reported, issued_at_utc, last_reported_at_utc, expires_at_utc FROM commander_device_budget_blocks WHERE tenant_id="+ten+" AND device_id="+dev+" ORDER BY allocation_sequence DESC LIMIT 5;")
agent=f.fresh.rows("SELECT device_id, state, platform, agent_version, tunnel_mode, last_seen_at_utc, revoked_at_utc FROM commander_devices WHERE tenant_id="+ten+" AND device_id="+dev+";")
report=dict(schema="hara.commander-linux-dev54-wave29-readonly-audit.v1",at_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),scope="EXACT_OWN_DEV_FIXTURE_ONLY",d1_reads=3,d1_mutations=0,api_status_poll_performed=False,payload_or_result_content_read=False,customer_content_collected=False,device_id=device,calls=calls,budgets=budgets,device_metadata=agent,worker_source_sha256=hashlib.sha256((root/"apps/commander/src/worker.js").read_bytes()).hexdigest())
out=root/"docs/evidence/commander-full-acceptance-20261012/linux-clean/dev54-wave29-readonly-audit-r2.json"
out.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
print(json.dumps(report,sort_keys=True))
