#!/usr/bin/env python3
"""Build exact product Worker dry-run and run 0043 expiry against real TenantQuota.

No external network, Cloudflare, Stripe, Agent or production mutation.
Write-once local QA receipt after independent full workerd/Miniflare validation.
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
TEST=APP/"scripts/test_0043_expired_claim_real_quota_20261113.mjs"
OUT=ROOT/"docs/evidence/commander-0043-realquota-workerd-20261113"
NODE="/tmp_hara/commander-node24/bin/node"
WRANGLER="/tmp_hara/commander-capability-suite-20261110/node_modules/wrangler/bin/wrangler.js"
DEPS=Path("/tmp_hara/commander-capability-suite-20261110/node_modules")
SOURCE_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682"
M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
EXPECTED_CASES=7


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(ok:bool,code:str)->None:
    if ok is not True:
        raise RuntimeError(code)


def main()->None:
    check(not OUT.exists(),"WRITE_ONCE_RECEIPT_EXISTS")
    check(sha(APP/"src/worker.js")==SOURCE_SHA,"WORKER_SHA_DRIFT")
    check(sha(APP/"migrations/0043_device_call_authorization.sql")==M43_SHA,
          "ORIGINAL_MIGRATION_SHA_DRIFT")
    check(Path(NODE).is_file() and Path(WRANGLER).is_file()
          and (DEPS/"zod").is_dir() and (DEPS/"miniflare").is_dir(),
          "LOCAL_QA_DEPENDENCIES_MISSING")
    env={k:v for k,v in os.environ.items()
         if not k.upper().startswith(("CF_","CLOUDFLARE_"))
         and not k.upper().endswith(("TOKEN","SECRET","KEY"))}
    env.update({
        "PATH":"/tmp_hara/commander-node24/bin:"+env.get("PATH","/usr/bin:/bin"),
        "CI":"true","WRANGLER_SEND_METRICS":"false",
        "HTTP_PROXY":"http://127.0.0.1:9",
        "HTTPS_PROXY":"http://127.0.0.1:9","NO_PROXY":"*"
    })
    with tempfile.TemporaryDirectory(prefix="commander-0043-realquota-",dir="/tmp_hara") as folder:
        tmp=Path(folder)
        shutil.copytree(APP/"src",tmp/"src")
        (tmp/"node_modules").symlink_to(DEPS,target_is_directory=True)
        check(sha(tmp/"src/worker.js")==SOURCE_SHA,"COPIED_WORKER_SOURCE_CHANGED")
        conf={
            "name":"hara-commander-qa-realquota-never-published",
            "main":"src/worker.js",
            "compatibility_date":"2026-09-21",
            "workers_dev":False,
            "preview_urls":False,
            "durable_objects":{"bindings":[
                {"name":"TENANT_QUOTA","class_name":"TenantQuota"},
                {"name":"DEVICE_CHANNEL","class_name":"DeviceChannel"},
                {"name":"STRICT_RATE_LIMIT","class_name":"SecurityRateLimit"}]},
            "migrations":[{"tag":"v1","new_sqlite_classes":[
                "TenantQuota","DeviceChannel","SecurityRateLimit"]}],
            "vars":{
                "ENVIRONMENT":"DEV","STORAGE_MODE":"ISOLATED_QA",
                "STRIPE_CHECKOUT_ENABLED":"false",
                "CUSTOMER_MCP_EDGE_ENABLED":"false",
                "DEVICE_EVENT_V2_ENABLED":"false"
            }
        }
        config=tmp/"wrangler.json"
        config.write_text(json.dumps(conf,indent=2)+"\n")
        build=subprocess.run(
            [NODE,WRANGLER,"deploy","--dry-run","--config",
             str(config),"--outdir",str(tmp/"build")],
            cwd=tmp,env=env,capture_output=True,text=True,timeout=110,check=False)
        check(build.returncode==0,"WORKER_BUNDLE_DRYRUN_FAILED:"+build.stderr[-650:])
        bundle=tmp/"build/worker.js"
        if not bundle.is_file():bundle=tmp/"build/entry.js"
        check(bundle.is_file() and bundle.stat().st_size>1000000,
              "EXACT_COMPLETE_WORKER_BUNDLE_MISSING")
        (tmp/"build/package.json").write_text('{"type":"module"}\n')
        parsed=subprocess.run([NODE,"--check",str(TEST)],cwd=tmp,env=env,
                              capture_output=True,text=True,timeout=12,check=False)
        check(parsed.returncode==0,"WORKERD_TEST_SYNTAX_FAILED")
        # Resolve the original source imports from existing local dependencies.
        # This is an ephemeral symlink, NOT an npm install or product mutation.
        original_link=ROOT/"node_modules"
        check(not original_link.exists() and not original_link.is_symlink(),
              "PREEXISTING_PRODUCT_DEPENDENCY_LINK_REFUSED")
        original_link.symlink_to(DEPS,target_is_directory=True)
        try:
            actual=subprocess.run(
                [NODE,str(TEST),str(bundle),str(tmp/"storage")],
                cwd=tmp,env=env,capture_output=True,text=True,timeout=105,check=False)
        finally:
            original_link.unlink()
        check(not original_link.exists(),"TEMP_LINK_CLEANUP_FAILED")
        check(actual.returncode==0,"WORKERD_REAL_QUOTA_TEST_FAILED:"+
              actual.stderr[-1300:]+actual.stdout[-500:])
        lines=[x for x in actual.stdout.splitlines() if x.startswith("{")]
        check(len(lines)==1,"WORKERD_RESULT_NOT_SINGLE_JSON")
        result=json.loads(lines[0])
        check(result.get("schema")=="hara.commander-0043-real-tenantquota-workerd.v1"
              and result.get("state")==
              "REAL_TENANT_QUOTA_EXPIRY_RECONCILIATION_WORKERD_PASS_GLOBAL_HOLD",
              "WORKERD_RESULT_STATE_INVALID")
        check(result.get("total_cases")==EXPECTED_CASES and
              len(result.get("cases",[]))==EXPECTED_CASES and
              all(x.get("state")=="PASS" for x in result["cases"]),
              "REAL_QUOTA_CASES_INCOMPLETE")
        check(result.get("worker_sha256")==SOURCE_SHA and
              result.get("migration_sha256")==M43_SHA,
              "REAL_QUOTA_SOURCE_SHA_UNPROVEN")
        check(all(result.get(x) is True for x in (
                "real_tenant_quota_rpc_exercised",
                "durable_object_persistence_after_restart",
                "migration_original_0043_exercised")) and
              all(result.get(x) is False for x in (
                "cloudflare_provider_called","real_agent_dispatched",
                "customer_data_used","production_mutated",
                "production_ledger_cutover_authorized")),
              "REAL_QUOTA_SCOPE_OVERCLAIM")
        bundle_sha,bundle_bytes=sha(bundle),bundle.stat().st_size
        config_sha=sha(config)

    record={
        "schema":"hara.commander-0043-expiry-realquota-workerd-qa.v1",
        "state":"0043_EXPIRY_REAL_TENANT_QUOTA_WORKERD_PASS_GLOBAL_HOLD",
        "date_utc":datetime.now(timezone.utc).isoformat(),
        "prechange_commit":"37429bdcafa3945acc72977023684c7087598e34",
        "base_worker_sha256":SOURCE_SHA,
        "migration_0043_sha256":M43_SHA,
        "test_source_sha256":sha(TEST),
        "runner_source_sha256":sha(Path(__file__)),
        "wrangler_config_sha256":config_sha,
        "worker_bundle_sha256":bundle_sha,
        "worker_bundle_bytes":bundle_bytes,
        "test_case_count":EXPECTED_CASES,
        "real_tenant_quota_rpc_exercised":True,
        "persisted_sqlite_do_after_workerd_restart":True,
        "temporary_isolated_storage_removed":True,
        "cases":result["cases"],
        "real_cloudflare_provider_called":False,
        "real_agent_dispatched":False,
        "production_mutated":False,
        "production_0043_migration_applied":False,
        "global_quiescence_proven":False,
        "commercial_cutover_authorized":False,
    }
    OUT.mkdir(parents=True)
    with (OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json").open("x") as file:
        json.dump(record,file,ensure_ascii=False,indent=2,sort_keys=True)
        file.write("\n")
    print(json.dumps({
        "state":record["state"],"cases":EXPECTED_CASES,
        "bundle_sha256":bundle_sha,
        "receipt_sha256":sha(OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json"),
        "production_mutated":False
    },sort_keys=True))


if __name__=="__main__":
    main()