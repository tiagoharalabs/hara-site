#!/usr/bin/env python3
"""Audit corrected expiry QA Cron readback contract against actual HOLD evidence.

Never contacts Cloudflare, agents, or production; writes isolated QA receipts.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"docs/evidence/commander-expiry-cron-observer-fix-20261113"
SOURCE=ROOT/"apps/commander/scripts/expiry_cron_readback_contract_20261113.mjs"
TEST=ROOT/"apps/commander/scripts/test_expiry_cron_readback_contract_20261113.mjs"
HOSTED=Path("/srv/hara/repos/local-git-gateway/worktrees/hara-site/commander-0043-expiry-hosted-qa-20261113")
NATIVE=HOSTED/"docs/evidence/commander-0043-expiry-hosted-qa-20261113/NATIVE_CRON_HOSTED_READBACK.json"
CLOSED=HOSTED/"docs/evidence/commander-0043-expiry-hosted-qa-20261113/CRON_DISABLED.json"
ORIGINAL=HOSTED/"apps/commander/scripts/observe_0043_expiry_qa_20261113.py"
NODE="/tmp_hara/commander-node24/bin/node"
def sha(file):return hashlib.sha256(file.read_bytes()).hexdigest()
def require(cond,name):
 if cond is not True: raise RuntimeError(name)
def main():
 target=OUT/"INDEPENDENT_CRON_READBACK_QA.json"
 require(not target.exists(),"WRITE_ONCE_RECEIPT_PRESENT")
 require(SOURCE.is_file() and TEST.is_file() and ORIGINAL.is_file(),"ORIGINAL_HARNESS_UNAVAILABLE")
 orig=ORIGINAL.read_text()
 require('len(marker)==len("HARA_REDACTED_SHA256:")+64' in orig,
         "ORIGINAL_DIAGNOSTIC_DEFECT_NOT_OBSERVED")
 require(NATIVE.is_file() and CLOSED.is_file(),"HOSTED_QA_RECEIPTS_UNAVAILABLE")
 native=json.loads(NATIVE.read_text())
 closed=json.loads(CLOSED.read_text())
 require(native.get("state")=="QA_HOSTED_CRON_UNPROVEN" and
         native.get("receipts")==[] and
         native.get("qa_call",{}).get("state")=="EXECUTING",
         "HOSTED_PRIOR_HOLD_NOT_GROUNDED")
 require(closed.get("state")=="QA_NATIVE_CRON_DISABLED_PROVIDER_CONFIRMED"
         and closed.get("cron_schedules")==[],
         "HOSTED_CRON_CLOSURE_NOT_CONFIRMED")
 r=subprocess.run([NODE,str(TEST)],cwd=ROOT,text=True,capture_output=True,
                  timeout=18,check=False)
 require(r.returncode==0,"CONTRACT_REGRESSION_FAILED:"+r.stderr[-250:])
 result=json.loads(r.stdout.strip())
 require(result.get("state")=="EXACT_CRON_READBACK_BASE64URL_26_CASES_PASS"
         and result.get("cases")==26 and result.get("cloudflare_called") is False
         and result.get("production_mutated") is False,
         "CONTRACT_REGRESSION_SCOPE_INVALID")
 out={
  "schema":"hara.commander-expiry-cron-observer-correction.v1",
  "state":"QA_MARKER_CONTRACT_26_PASS_HOSTED_CRON_STILL_HOLD",
  "at_utc":datetime.now(timezone.utc).isoformat(),
  "prechange_base":"00438dbfbb21f901ca31ca857fdfc5286767d724",
  "prechange_document_exists":(OUT/"PRECHANGE_EXPIRY_CRON_READBACK_20261113.md").is_file(),
  "corrected_source_sha256":sha(SOURCE),
  "corrected_test_sha256":sha(TEST),
  "qa_test_cases_passed":26,
  "original_qa_observer_hex64_defect_confirmed":True,
  "correct_worker_marker_format":"SHA256_BASE64URL_UNPADDED_43",
  "previous_native_hosted_cron_receipts":0,
  "previous_native_hosted_cron_pass":False,
  "previous_qa_call_state":"EXECUTING",
  "previous_qa_cron_disabled":True,
  "old_hosted_receipt_sha256":sha(NATIVE),
  "old_cron_closure_receipt_sha256":sha(CLOSED),
  "cloudflare_provider_contacted":False,
  "production_mutated":False,
  "commercial_worker_changed":False,
  "hosted_cron_currently_pass":False,
  "global_ledger_recovery_proven":False,
  "commercial_cutover_authorized":False
 }
 require(out["prechange_document_exists"],"PRECHANGE_NOT_DOCUMENTED")
 with target.open("x") as file:
  json.dump(out,file,indent=2,sort_keys=True,ensure_ascii=False);file.write("\n")
 print(json.dumps({"state":out["state"],"cases":26,
   "native_receipts":0,"old_cron_disabled":True,
   "receipt_sha256":sha(target),"production_mutated":False},sort_keys=True))
if __name__=="__main__":main()