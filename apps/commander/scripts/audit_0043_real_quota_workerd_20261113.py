#!/usr/bin/env python3
"""Independent receipt/custody audit of original TenantQuota DO in workerd.

No network, no API, no migration to Cloudflare. Does not re-run the test.
"""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OUT=ROOT/"docs/evidence/commander-0043-real-quota-workerd-20261113"
RECEIPT=OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json"
PRECHANGE=OUT/"PRECHANGE_REAL_QUOTA_20261113.md"
WORKER_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682"
M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
BASE="15306dc6de16f80f09dcfc4c7939ed8f7f9f2586"
EXPECTED={
 "real TenantQuota reserves and starts a synthetic call",
 "real cleanup EXPIRED calls real DO hold before redaction",
 "real quota DO refuses premature automatic settlement of unknown effect",
 "repeating cleanup does not reexecute or release",
 "actual workerd restart preserves protected reservation",
}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def need(v,reason):
 if v is not True:raise RuntimeError(reason)
def main():
 need(PRECHANGE.is_file() and RECEIPT.is_file(),"PRECHANGE_OR_RESULT_MISSING")
 saved=json.loads(RECEIPT.read_text())
 need(saved["schema"]=="hara.commander-0043-real-quota-workerd-qa.v1" and
      saved["state"]=="REAL_TENANT_QUOTA_EXPIRED_CLAIM_HOLD_WORKERD_PASS",
      "RECEIPT_STATE_INVALID")
 need(saved["prechange_commit"]==BASE and
      saved["source_sha256"]==WORKER_SHA and
      saved["migration_0043_sha256"]==M43_SHA,
      "SOURCE_PIN_MISMATCH")
 need(sha(APP/"src/worker.js")==WORKER_SHA and
      sha(APP/"migrations/0043_device_call_authorization.sql")==M43_SHA,
      "SOURCE_DRIFT")
 need(saved["test_source_sha256"]==sha(APP/"scripts/test_0043_expiry_real_quota_workerd_20261113.mjs") and
      saved["bundle_bytes"]>1000000 and len(saved["real_worker_bundle_sha256"])==64,
      "TEST_OR_BUNDLE_DRIFT")
 r=saved["observed"]
 need(r["case_count"]==5 and len(r["cases"])==5 and
      {x["name"] for x in r["cases"]}==EXPECTED and
      all(x["state"]=="PASS" for x in r["cases"]),
      "EXPECTED_CASE_COVERAGE_INVALID")
 need(r["actual_tenantquota_worker_rpc"] is True and
      r["real_settleCallUsage"] is True and
      r["real_worker_cleanup"] is True and
      r["workerd_restart_preserved"] is True and
      r["protected_quota_units"]==1,
      "REAL_TENANT_QUOTA_GUARD_UNPROVEN")
 for key in ("provider_called","customer_data_used","agent_dispatched",
             "production_mutated","cloudflare_hosted_proven",
             "global_quiescence_proven","commercial_cutover_authorized"):
  need(r[key] is False,"QA_SCOPE_OVERCLAIM_"+key)
 need(saved["ephemeral_storage_deleted"] is True and
      saved["production_mutations"]==0 and
      saved["commercial_cutover_authorized"] is False,
      "QA_CUSTODY_OR_SCOPE_FAILED")
 git=subprocess.run(["git","show",BASE+":"+PRECHANGE.relative_to(ROOT).as_posix()],
        cwd=ROOT,capture_output=True,check=False,timeout=12)
 need(git.returncode==0 and git.stdout==PRECHANGE.read_bytes(),
      "PRECHANGE_WAS_MODIFIED_AFTER_COMMIT")
 audit={
   "schema":"hara.commander-0043-real-quota-workerd-independent-readback.v1",
   "state":"REAL_TENANT_QUOTA_EXPIRY_INDEPENDENT_PASS_HOSTED_HOLD",
   "prechange_commit":BASE,
   "source_sha256":WORKER_SHA,
   "migration_sha256":M43_SHA,
   "real_do_class":"TenantQuota",
   "five_cases_covered":True,
   "real_quota_rpc_exercised":True,
   "uncertain_reservation_survived_restart":True,
   "automatic_release_blocked":True,
   "global_quiescence_proven":False,
   "cloudflare_hosted_proven":False,
   "production_migration_performed":False,
   "production_mutations":0,
   "commercial_cutover_authorized":False,
   "original_qa_receipt_sha256":sha(RECEIPT),
   "test_source_sha256":saved["test_source_sha256"]
 }
 file=OUT/"INDEPENDENT_REAL_QUOTA_READBACK.json"
 with file.open("x") as stream:
  json.dump(audit,stream,ensure_ascii=False,sort_keys=True,indent=2);stream.write("\n")
 print(json.dumps({"state":audit["state"],"cases":5,
    "receipt_sha256":sha(file),"production_mutations":0},sort_keys=True))
if __name__=="__main__":main()