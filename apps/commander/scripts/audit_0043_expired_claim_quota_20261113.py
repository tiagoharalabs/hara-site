#!/usr/bin/env python3
"""Independent audit: historical prepatch fails, current patch passes, scope HOLD.

Uses git source blobs and synthetic QA in a deleted temporary directory.
No Cloudflare API, DO provider, Agent, billing, PROD migration or deployment.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OUT=ROOT/"docs/evidence/commander-0043-expiry-quota-hold-20261113"
RECEIPT=OUT/"EXPIRED_CLAIM_QUOTA_QA.json"
BASE="9fa0d7b9ac691e7efa884d361d7996c9c5dc8af0"
PRE_SHA="c9f4c48e553de133598982018a3fbc19f6fcf9165dfd9ddf1609620da61e8dbc"
AFTER_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682"
M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
NODE="/tmp_hara/commander-node24/bin/node"
DEPS=Path("/tmp_hara/commander-capability-suite-20261110/node_modules")
TEST=APP/"scripts/test_0043_expired_claim_quota_hold_20261113.mjs"
FAILURE="claimed non-900 expired call was scrubbed without protecting uncertain Cloud quota"


def require(ok:bool,reason:str)->None:
    if ok is not True:
        raise RuntimeError(reason)


def sha(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()


def source_from_base(path:str)->bytes:
    result=subprocess.run(["git","show",BASE+":"+path],cwd=ROOT,
                          capture_output=True,check=False,timeout=15)
    require(result.returncode==0,"BASELINE_GIT_BLOB_UNAVAILABLE:"+path)
    return result.stdout


def main()->None:
    target=OUT/"INDEPENDENT_EXPIRY_QUOTA_READBACK.json"
    require(not target.exists(),"INDEPENDENT_RECEIPT_EXISTS")
    report=json.loads(RECEIPT.read_text())
    require(report["state"]=="EXPIRED_CLAIM_QUOTA_HOLD_8_PLUS_26_PLUS_29_PASS",
            "CURRENT_QA_RECEIPT_INVALID")
    require(report["worker_source_before_sha256"]==PRE_SHA
            and report["worker_source_after_sha256"]==AFTER_SHA
            and report["migration_0043_original_sha256"]==M43_SHA,
            "RECEIPT_SHA_PROVENANCE_INVALID")
    current=(APP/"src/worker.js").read_bytes()
    old=source_from_base("apps/commander/src/worker.js")
    require(sha(current)==AFTER_SHA and sha(old)==PRE_SHA,
            "SOURCE_BEFORE_AFTER_HASH_INVALID")
    migration=(APP/"migrations/0043_device_call_authorization.sql").read_bytes()
    require(sha(migration)==M43_SHA and
            source_from_base("apps/commander/migrations/0043_device_call_authorization.sql")==migration,
            "MIGRATION_0043_MODIFIED")
    patched=APP/"src/worker.js"
    worker=patched.read_text()
    start=worker.index("async function redactExpiredDeviceCallContent(env, cutoff) {")
    end=worker.index("\nasync function cleanupExpiredDeviceCalls(env)",start)
    selected=worker[start:end]
    require('Number(row.approval_timeout_seconds)===900 || claimedCloudQuota' in selected
            and 'await settleCallUsage(env,row,raw)' in selected,
            "UNCONDITIONAL_CLAIMED_CLOUD_QUOTA_FENCE_MISSING")
    old_segment=old.decode()[old.decode().index(
        "async function redactExpiredDeviceCallContent(env, cutoff) {"):]
    require('if (Number(row.approval_timeout_seconds)===900)' in old_segment,
            "BASELINE_EXPIRY_BRANCH_NOT_FOUND")

    require(TEST.is_file() and Path(NODE).is_file() and DEPS.is_dir(),
            "QA_TEST_DEPENDENCIES_MISSING")
    with tempfile.TemporaryDirectory(prefix="hara-expiry-independent-before-",dir="/tmp_hara") as tmp:
        tmp=Path(tmp)
        shutil.copytree(APP/"src",tmp/"src")
        (tmp/"src/worker.js").write_bytes(old)
        (tmp/"scripts").mkdir()
        source=TEST.read_text()
        require(source.count(AFTER_SHA)==1,"QA_WORKER_PIN_MISMATCH")
        (tmp/"scripts"/TEST.name).write_text(source.replace(AFTER_SHA,PRE_SHA))
        (tmp/"migrations").mkdir()
        (tmp/"migrations/0043_device_call_authorization.sql").write_bytes(migration)
        (tmp/"node_modules").symlink_to(DEPS,target_is_directory=True)
        env={k:v for k,v in os.environ.items()
             if not k.upper().startswith(("CF_","CLOUDFLARE_"))
             and not k.upper().endswith(("TOKEN","SECRET","KEY"))}
        env.update({"PATH":"/tmp_hara/commander-node24/bin:"+env.get("PATH","/usr/bin:/bin"),
                    "CI":"true","NO_PROXY":"*","HTTP_PROXY":"http://127.0.0.1:9",
                    "HTTPS_PROXY":"http://127.0.0.1:9"})
        result=subprocess.run([NODE,str(tmp/"scripts"/TEST.name)],cwd=tmp,
                              capture_output=True,text=True,env=env,
                              timeout=25,check=False)
        require(result.returncode!=0,"PREPATCH_UNEXPECTED_PASS")
        require(FAILURE in result.stderr and "0 !== 1" in result.stderr,
                "PREPATCH_FAILURE_CAUSE_UNPROVEN")
    require(report["new_expiry_cases"]==8 and
            report["enqueue_approval_cases"]==26 and
            report["claim_authorization_cases"]==29,
            "REGRESSION_SCOPE_INVALID")
    require(len(report["test_runs"])==3 and
            all(sha((APP/"scripts"/x["name"]).read_bytes())==x["source_sha256"]
                for x in report["test_runs"]),
            "REGRESSION_FILE_HASH_DRIFT")
    require(report["claim_quota_hold_before_redaction"] is True and
            report["hold_failure_no_false_redaction"] is True and
            report["metadata_d1_failure_no_false_redaction"] is True and
            report["claim_cleanup_idempotent_on_repeat"] is True,
            "QUOTA_HOLD_SAFETY_ACCEPTANCE_FAILED")
    require(all(report[key] is False for key in
                ["real_quota_do_exercised","cloudflare_called","stripe_called",
                 "agent_dispatched","production_mutated",
                 "production_migration_0043_applied","hosted_qa_pass",
                 "global_do_quiescence_proven",
                 "commercial_ledger_recovery_approved",
                 "production_promotion_authorized"]),
            "QA_SCOPE_OVERCLAIM")
    audit={
        "schema":"hara.commander-0043-expiry-quota-independent-readback.v1",
        "state":"EXPIRED_CLAIM_QUOTA_RECONCILIATION_INDEPENDENT_PASS_GLOBAL_HOLD",
        "audit_at_utc":datetime.now(timezone.utc).isoformat(),
        "prechange_baseline_commit":BASE,
        "prechange_source_sha256":PRE_SHA,
        "current_source_sha256":AFTER_SHA,
        "migration_0043_sha256":M43_SHA,
        "prepatch_independently_replayed":True,
        "prepatch_error":"CLAIMED_METERED_EXPIRED_ROW_REDACTED_WITHOUT_QUOTA_HOLD",
        "real_worker_cleanup_local_cases":8,
        "enqueue_approval_regression_cases":26,
        "claim_authorization_regression_cases":29,
        "worker_dryrun_bundle_sha256":report["worker_dryrun_bundle_sha256"],
        "quota_do_real_runtime_proven":False,
        "qa_hosted_runtime_proven":False,
        "live_do_active_manifest_proven":False,
        "two_global_quiescence_windows_proven":False,
        "commercial_consumer_0043_proven":False,
        "cloudflare_api_calls":0,
        "production_mutations":0,
        "production_promotion_authorized":False,
        "qa_receipt_sha256":sha(RECEIPT.read_bytes())
    }
    with target.open("x") as stream:
        json.dump(audit,stream,ensure_ascii=False,indent=2,sort_keys=True)
        stream.write("\n")
    print(json.dumps({"state":audit["state"],"before_patch_replay":"FAIL_AS_EXPECTED",
                      "current_local_qa":8,"enqueue_approval":26,"claim":29,
                      "audit_sha256":sha(target.read_bytes()),
                      "production_mutations":0},sort_keys=True))


if __name__=="__main__":
    main()