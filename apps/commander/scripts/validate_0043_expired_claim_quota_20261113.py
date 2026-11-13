#!/usr/bin/env python3
"""Fail-closed QA of expired claimed Cloud quota protection and 0043 regression.

The original Commander cleanup and original approval/claim sources are run
against isolated SQLite, then the full Worker is built ONLY via Wrangler dry-run.
No provider, Agent, customer, production migration or live billing action.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OUT=ROOT/"docs/evidence/commander-0043-expiry-quota-hold-20261113"
WORKER_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682"
PRE_WORKER_SHA="c9f4c48e553de133598982018a3fbc19f6fcf9165dfd9ddf1609620da61e8dbc"
M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
BASE="9fa0d7b9ac691e7efa884d361d7996c9c5dc8af0"
NODE="/tmp_hara/commander-node24/bin/node"
WRANGLER="/tmp_hara/commander-capability-suite-20261110/node_modules/wrangler/bin/wrangler.js"
DEPS=Path("/tmp_hara/commander-capability-suite-20261110/node_modules")
SCRIPTS=[
 ("expired_claim_cloud_quota","test_0043_expired_claim_quota_hold_20261113.mjs",8),
 ("enqueue_approval_0043","test_approval_async_queue_claim_0043_candidate_20261112.mjs",26),
 ("claim_authorization_0043","test_p0_dispatch_authorization_0043_undelivered_20261112.mjs",29),
]
MANDATORY=[
 "CLAIMED_CLOUD_QUOTA_EXPIRED_REQUIRES_HOLD_BEFORE_REDACTION",
 "FAILED_QUOTA_HOLD_MUST_NOT_SCRUB_UNCERTAIN_CLAIM",
 "EXPIRY_MAINTENANCE_MARKS_AND_HOLDS_CLAIMED_CLOUD_QUOTA",
 "METADATA_D1_WRITE_ERROR_PREVENTS_REDACTION",
 "REPEATED_MAINTENANCE_DOES_NOT_RELEASE_OR_DISPATCH",
]


def ensure(value:bool,label:str)->None:
    if value is not True:
        raise RuntimeError(label)


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main()->None:
    source=APP/"src/worker.js"
    migration=APP/"migrations/0043_device_call_authorization.sql"
    ensure(not OUT.exists(),"EVIDENCE_PATH_ALREADY_EXISTS_WRITE_ONCE")
    ensure(sha(source)==WORKER_SHA,"EXACT_WORKER_SOURCE_SHA_DRIFT")
    ensure(sha(migration)==M43_SHA,"CANONICAL_0043_MIGRATION_CHANGED")
    worker=source.read_text()
    ensure("const claimedCloudQuota = Boolean(row.claimed_at_utc)" in worker
           and "Number(row.approval_timeout_seconds)===900 || claimedCloudQuota" in worker
           and "await settleCallUsage(env,row,raw)" in worker,
           "EXPIRED_CLAIM_QUOTA_PROTECTION_GUARD_UNPROVEN")
    ensure(Path(NODE).is_file() and Path(WRANGLER).is_file()
           and DEPS.is_dir() and (DEPS/"zod").is_dir(),
           "EXISTING_QA_DEPENDENCIES_UNAVAILABLE")
    link=ROOT/"node_modules"
    ensure(not link.exists() and not link.is_symlink(),
           "PREEXISTING_DEPENDENCY_LINK_REFUSED")
    env={k:v for k,v in os.environ.items()
         if not k.upper().startswith(("CF_","CLOUDFLARE_"))
         and not k.upper().endswith(("TOKEN","SECRET","KEY"))}
    env.update({"PATH":"/tmp_hara/commander-node24/bin:"+env.get("PATH","/usr/bin:/bin"),
                "CI":"true","WRANGLER_SEND_METRICS":"false",
                "HTTP_PROXY":"http://127.0.0.1:9",
                "HTTPS_PROXY":"http://127.0.0.1:9","NO_PROXY":"*"})
    runs=[]
    link.symlink_to(DEPS,target_is_directory=True)
    try:
        for kind,name,count in SCRIPTS:
            test=APP/"scripts"/name
            parse=subprocess.run([NODE,"--check",str(test)],cwd=ROOT,
                 env=env,text=True,capture_output=True,timeout=12,check=False)
            ensure(parse.returncode==0,"TEST_SYNTAX_ERROR:"+name)
            proc=subprocess.run([NODE,str(test)],cwd=ROOT,
                 env=env,text=True,capture_output=True,timeout=35,check=False)
            ensure(proc.returncode==0,"TEST_FAILURE:"+name+":"+proc.stderr[-430:])
            last=[x for x in proc.stdout.splitlines() if x.startswith("{")]
            ensure(len(last)==1,"TEST_OUTPUT_NOT_SINGLE_JSON:"+name)
            result=json.loads(last[0])
            observed_source=result.get("worker_sha256",result.get("worker_source_sha256"))
            ensure(observed_source==WORKER_SHA,"TEST_SOURCE_DRIFT:"+name)
            if kind=="expired_claim_cloud_quota":
                ensure(result.get("state")=="EXPIRED_CLAIM_QUOTA_PROTECTION_QA_PASS"
                       and result.get("total_cases")==count
                       and result.get("real_worker_cleanup_source_exercised") is True
                       and result.get("real_settleCallUsage_exercised") is True
                       and result.get("synthetic_databases_closed")==count
                       and result.get("migration_0043_sha256")==M43_SHA
                       and all(x.get("state")=="PASS" for x in result.get("cases",[])),
                       "EXPIRED_QUOTA_CASE_MATRIX_INVALID")
                names={x["name"] for x in result["cases"]}
                ensure(set(MANDATORY).issubset(names),"CRITICAL_EXPIRY_REGRESSION_MISSING")
            elif kind=="enqueue_approval_0043":
                ensure(result.get("state")=="PASS" and result.get("tests")==count,
                       "ENQUEUE_APPROVAL_REGRESSION_FAILED")
            else:
                ensure(result.get("state")=="REAL_SOURCE_DISPATCH_AUTHORIZATION_QA_PASS"
                       and result.get("total_cases")==count
                       and result.get("sqlite_migration_21_to_22") is True
                       and all(x.get("state")=="PASS" for x in result.get("cases",[]))
                       and result.get("real_agent_dispatched") is False,
                       "0043_CLAIM_AND_SCRUB_REGRESSION_FAILED")
            runs.append({"name":name,"type":kind,"cases_passed":count,
                         "source_sha256":sha(test),
                         "stdout_sha256":hashlib.sha256(proc.stdout.encode()).hexdigest()})
        with tempfile.TemporaryDirectory(prefix="hara-0043-expiry-dryrun-",dir="/tmp_hara") as td:
            build=subprocess.run([NODE,WRANGLER,"deploy","--dry-run","--config",
                str(APP/"wrangler.dev.jsonc"),"--outdir",td],
                cwd=ROOT,env=env,text=True,capture_output=True,timeout=110,check=False)
            ensure(build.returncode==0,"WORKER_BUILD_DRYRUN_FAILED:"+build.stderr[-380:])
            bundle=Path(td)/"worker.js"
            ensure(bundle.is_file() and bundle.stat().st_size>1000000,
                   "COMPLETE_WORKER_BUNDLE_MISSING")
            bundle_digest=sha(bundle)
            bundle_bytes=bundle.stat().st_size
    finally:
        link.unlink()
    ensure(not link.exists(),"QA_DEPENDENCY_CLEANUP_UNPROVEN")
    receipt={
        "schema":"hara.commander-0043-expired-cloud-quota-local-qa.v1",
        "state":"EXPIRED_CLAIM_QUOTA_HOLD_8_PLUS_26_PLUS_29_PASS",
        "observed_at_utc":datetime.now(timezone.utc).isoformat(),
        "prechange_baseline_commit":BASE,
        "branch":"local/commander-0043-expiry-quota-hold-20261113",
        "worker_source_before_sha256":PRE_WORKER_SHA,
        "worker_source_after_sha256":WORKER_SHA,
        "migration_0043_original_sha256":M43_SHA,
        "new_expiry_cases":8,
        "enqueue_approval_cases":26,
        "claim_authorization_cases":29,
        "overlap_between_suites_not_assessed":True,
        "new_case_names":sorted(names),
        "test_runs":runs,
        "worker_dryrun_bundle_sha256":bundle_digest,
        "worker_dryrun_bundle_bytes":bundle_bytes,
        "before_patch_case":{
            "case":"CLAIMED_CLOUD_QUOTA_EXPIRED_REQUIRES_HOLD_BEFORE_REDACTION",
            "observed_hold_calls":0,"expected_hold_calls":1,
            "observed_state":"FAIL"
        },
        "claim_quota_hold_before_redaction":True,
        "hold_failure_no_false_redaction":True,
        "metadata_d1_failure_no_false_redaction":True,
        "no_automatic_quota_release_on_unknown_outcome":True,
        "claim_cleanup_idempotent_on_repeat":True,
        "real_quota_do_exercised":False,
        "quota_stub_synthetic":True,
        "cloudflare_called":False,
        "stripe_called":False,
        "agent_dispatched":False,
        "production_mutated":False,
        "production_migration_0043_applied":False,
        "hosted_qa_pass":False,
        "global_do_quiescence_proven":False,
        "commercial_ledger_recovery_approved":False,
        "production_promotion_authorized":False
    }
    OUT.mkdir(parents=True)
    dest=OUT/"EXPIRED_CLAIM_QUOTA_QA.json"
    with dest.open("x") as stream:
        json.dump(receipt,stream,ensure_ascii=False,sort_keys=True,indent=2)
        stream.write("\n")
    print(json.dumps({"state":receipt["state"],"cases":8,
        "enqueue_approval":26,"claim":29,"worker_sha256":WORKER_SHA,
        "bundle_sha256":bundle_digest,"receipt_sha256":sha(dest),
        "production_mutated":False,"hosted_qa_pass":False},sort_keys=True))


if __name__=="__main__":
    main()