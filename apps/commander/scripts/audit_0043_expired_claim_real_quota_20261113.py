#!/usr/bin/env python3
"""Independent second execution of original TenantQuota workerd QA and audit.

All effects are isolated to local temporary directories; never PRODUCTION.
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OUT=ROOT/"docs/evidence/commander-0043-realquota-workerd-20261113"
RECEIPT=OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json"
FINAL=OUT/"INDEPENDENT_REAL_QUOTA_READBACK.json"
BASE="37429bdcafa3945acc72977023684c7087598e34"
WORKER_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682"
M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
REQUIRED_CASES={
    "claimed_expired_quota_real_DO_hold_and_redact",
    "claimed_expired_async_profile_900_remains_protected",
    "real_quota_RPC_failure_prevents_scrub",
    "real_quota_subject_mismatch_fails_closed",
    "real_quota_hold_survives_D1_metadata_write_error",
    "real_quota_cleanup_EXECUTING_to_EXPIRED_preserves_hold",
    "real_quota_protected_reservation_survives_workerd_restart",
}


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(ok:bool,code:str)->None:
    if ok is not True:
        raise RuntimeError(code)


def verify(record:dict)->None:
    require(record.get("schema")=="hara.commander-0043-expiry-realquota-workerd-qa.v1"
            and record.get("state")=="0043_EXPIRY_REAL_TENANT_QUOTA_WORKERD_PASS_GLOBAL_HOLD",
            "REAL_QUOTA_RESULT_INVALID")
    require(record.get("prechange_commit")==BASE
            and record.get("base_worker_sha256")==WORKER_SHA
            and record.get("migration_0043_sha256")==M43_SHA,
            "PRECHANGE_WORKER_OR_M43_DRIFT")
    require(record.get("test_case_count")==7
            and len(record.get("cases",[]))==7
            and {x["name"] for x in record["cases"]}==REQUIRED_CASES
            and all(x.get("state")=="PASS" for x in record["cases"]),
            "REAL_QUOTA_CASES_INCOMPLETE")
    require(record.get("real_tenant_quota_rpc_exercised") is True
            and record.get("persisted_sqlite_do_after_workerd_restart") is True
            and record.get("temporary_isolated_storage_removed") is True,
            "REAL_TENANT_QUOTA_OR_RESTART_NOT_EXERCISED")
    require(all(record.get(k) is False for k in (
        "real_cloudflare_provider_called","real_agent_dispatched",
        "production_mutated","production_0043_migration_applied",
        "global_quiescence_proven","commercial_cutover_authorized")),
        "PROD_OR_SCOPE_OVERCLAIM")
    row={x["name"]:x for x in record["cases"]}
    require(row["claimed_expired_quota_real_DO_hold_and_redact"].get("held_units")==1
            and row["claimed_expired_quota_real_DO_hold_and_redact"].get("hold_before_redaction") is True
            and row["real_quota_RPC_failure_prevents_scrub"].get("failure_fail_closed") is True
            and row["real_quota_subject_mismatch_fails_closed"].get("binding_mismatch_denied") is True
            and row["real_quota_hold_survives_D1_metadata_write_error"].get("hold_persisted") is True
            and row["real_quota_cleanup_EXECUTING_to_EXPIRED_preserves_hold"].get("idempotent") is True
            and row["real_quota_protected_reservation_survives_workerd_restart"].get("hold_idempotent_after_restart") is True,
            "EXACT_REAL_QUOTA_SAFETY_ASSERTIONS_MISSING")


def main()->None:
    require(RECEIPT.is_file() and not FINAL.exists(),"QA_RECEIPT_MISSING_OR_AUDIT_ALREADY_EXISTS")
    require(sha(APP/"src/worker.js")==WORKER_SHA
            and sha(APP/"migrations/0043_device_call_authorization.sql")==M43_SHA,
            "CODE_OR_MIGRATION_CHANGED_AFTER_TEST")
    record=json.loads(RECEIPT.read_text())
    verify(record)
    runner=APP/"scripts/run_0043_expired_claim_real_quota_20261113.py"
    test=APP/"scripts/test_0043_expired_claim_real_quota_20261113.mjs"
    require(record["runner_source_sha256"]==sha(runner)
            and record["test_source_sha256"]==sha(test),
            "QA_HARNESS_HASH_DRIFT")
    require(record["worker_bundle_bytes"]>1000000 and
            len(record["worker_bundle_sha256"])==64,
            "WORKER_BUILD_UNPROVEN")
    spec=importlib.util.spec_from_file_location("audit_replay_real_quota",runner)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    require(mod.SOURCE_SHA==WORKER_SHA and mod.M43_SHA==M43_SHA,
            "AUDIT_REPLAY_SOURCE_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="hara-0043-audit-second-",dir="/tmp_hara") as folder:
        mod.OUT=Path(folder)/"separate_receipt"
        buffer=io.StringIO()
        with contextlib.redirect_stdout(buffer):
            mod.main()
        replay=json.loads((mod.OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json").read_text())
        verify(replay)
        require(replay["cases"]==record["cases"],
                "SECOND_REAL_QUOTA_RUN_RESULTS_DIFFER")
        require(replay["test_source_sha256"]==record["test_source_sha256"] and
                replay["runner_source_sha256"]==record["runner_source_sha256"],
                "SECOND_RUN_INPUTS_DIFFER")
        require(replay["worker_bundle_sha256"]==record["worker_bundle_sha256"],
                "SECOND_BUNDLE_SHA_DRIFT")
    output={
        "schema":"hara.commander-0043-expiry-realquota-independent-readback.v1",
        "state":"REAL_TENANT_QUOTA_EXPIRY_WORKERD_INDEPENDENT_REPLAY_PASS_GLOBAL_HOLD",
        "at_utc":datetime.now(timezone.utc).isoformat(),
        "prechange_commit":BASE,
        "worker_sha256":WORKER_SHA,
        "migration_0043_sha256":M43_SHA,
        "qa_receipt_sha256":sha(RECEIPT),
        "original_cases_passed":7,
        "independent_replay_cases_passed":7,
        "case_results_identical":True,
        "worker_bundle_sha_identical":True,
        "real_tenant_quota_used":True,
        "persistent_do_across_workerd_restart":True,
        "quota_release_on_uncertain_expiry":False,
        "synthetic_only_fault_injection":True,
        "cloudflare_provider_calls":0,
        "customer_or_agent_calls":0,
        "production_mutations":0,
        "qa_hosted_cloudflare_proven":False,
        "global_do_quiescence_proven":False,
        "commercial_ledger_recovery_proven":False,
        "production_promotion_authorized":False
    }
    with FINAL.open("x") as out:
        json.dump(output,out,ensure_ascii=False,sort_keys=True,indent=2)
        out.write("\n")
    print(json.dumps({
        "state":output["state"],
        "original_pass":7,"replay_pass":7,
        "audit_receipt_sha256":sha(FINAL),"production_mutations":0
    },sort_keys=True))


if __name__=="__main__":
    main()