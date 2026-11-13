#!/usr/bin/env python3
"""Compile original Worker locally, run original TenantQuota + cleanup in workerd.

Only ephemeral local paths are mutated. No Cloudflare token/provider is used.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
APP=ROOT/"apps/commander"
OUT=ROOT/"docs/evidence/commander-0043-real-quota-workerd-20261113"
WORKER_SHA="f14550bb603cb53f8d40df8ba7d96b998a8a4baf68d0eda2f5a8a197de4d4682"
M43_SHA="7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
NODE="/tmp_hara/commander-node24/bin/node"
WRANGLER="/tmp_hara/commander-capability-suite-20261110/node_modules/wrangler/bin/wrangler.js"
DEPS=Path("/tmp_hara/commander-capability-suite-20261110/node_modules")
TEST=APP/"scripts/test_0043_expiry_real_quota_workerd_20261113.mjs"


def need(ok:bool,reason:str)->None:
    if ok is not True:raise RuntimeError(reason)


def sha(file:Path)->str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def main()->None:
    need(not (OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json").exists(),"RECEIPT_ALREADY_EXISTS_WRITE_ONCE")
    need(sha(APP/"src/worker.js")==WORKER_SHA,"WORKER_SOURCE_PIN_DRIFT")
    need(sha(APP/"migrations/0043_device_call_authorization.sql")==M43_SHA,
         "MIGRATION_SOURCE_CHANGED")
    need(Path(NODE).is_file() and Path(WRANGLER).is_file()
         and (DEPS/"miniflare").is_dir() and (DEPS/"zod").is_dir(),
         "RUNTIME_DEPENDENCIES_UNAVAILABLE")
    env={k:v for k,v in os.environ.items()
         if not k.upper().startswith(("CF_","CLOUDFLARE_"))
         and not k.upper().endswith(("TOKEN","SECRET","KEY"))}
    env.update({"PATH":"/tmp_hara/commander-node24/bin:"+env.get("PATH","/usr/bin:/bin"),
       "CI":"true","WRANGLER_SEND_METRICS":"false",
       "HTTP_PROXY":"http://127.0.0.1:9","HTTPS_PROXY":"http://127.0.0.1:9","NO_PROXY":"*"})
    check=subprocess.run([NODE,"--check",str(TEST)],cwd=ROOT,
         env=env,text=True,capture_output=True,timeout=12,check=False)
    need(check.returncode==0,"QA_JAVASCRIPT_SYNTAX_INVALID:"+check.stderr[-350:])
    with tempfile.TemporaryDirectory(prefix="commander-real-quota-",dir="/tmp_hara") as tmp:
        tmp=Path(tmp)
        shutil.copytree(APP/"src",tmp/"src")
        (tmp/"node_modules").symlink_to(DEPS,target_is_directory=True)
        cfg={
         "name":"hara-p0-real-quota-local-workerd-unpublished",
         "main":"src/worker.js","compatibility_date":"2026-09-21",
         "workers_dev":False,"preview_urls":False,
         "durable_objects":{"bindings":[
           {"name":"TENANT_QUOTA","class_name":"TenantQuota"},
           {"name":"DEVICE_CHANNEL","class_name":"DeviceChannel"},
           {"name":"STRICT_RATE_LIMIT","class_name":"SecurityRateLimit"}]},
         "migrations":[{"tag":"v1","new_sqlite_classes":[
           "TenantQuota","DeviceChannel","SecurityRateLimit"]}],
         "vars":{"ENVIRONMENT":"DEV","STORAGE_MODE":"ISOLATED_QA",
                 "STRIPE_CHECKOUT_ENABLED":"false",
                 "CUSTOMER_MCP_EDGE_ENABLED":"false","DEVICE_EVENT_V2_ENABLED":"false"}}
        config=tmp/"wrangler.json";config.write_text(json.dumps(cfg,indent=2)+"\n")
        build=subprocess.run([NODE,WRANGLER,"deploy","--dry-run",
             "--config",str(config),"--outdir",str(tmp/"build")],
             cwd=tmp,env=env,capture_output=True,text=True,timeout=110,check=False)
        need(build.returncode==0,"WORKER_DRYRUN_FAILED:"+build.stderr[-480:])
        bundle=tmp/"build/worker.js"
        need(bundle.is_file() and bundle.stat().st_size>1000000,
             "WORKER_DRYRUN_BUNDLE_MISSING")
        (tmp/"build/package.json").write_text('{"type":"module"}\n')
        qa_link=ROOT/"node_modules"
        need(not qa_link.exists() and not qa_link.is_symlink(),
             "QA_DEPENDENCY_SYMLINK_PREEXISTS")
        qa_link.symlink_to(DEPS,target_is_directory=True)
        try:
            test=subprocess.run([NODE,str(TEST),str(bundle),str(tmp/"storage")],
                 cwd=tmp,env=env,capture_output=True,text=True,timeout=90,check=False)
        finally:
            qa_link.unlink()
        need(test.returncode==0,"REAL_QUOTA_WORKERD_TEST_FAILED:"+
             test.stderr[-1300:]+test.stdout[-500:])
        lines=[x for x in test.stdout.splitlines() if x.startswith("{")]
        need(len(lines)==1,"QA_RECEIPT_JSON_INVALID")
        observed=json.loads(lines[0])
        need(observed.get("state")=="REAL_TENANT_QUOTA_EXPIRED_CLAIM_HOLD_WORKERD_PASS"
             and observed.get("case_count")==5
             and all(c.get("state")=="PASS" for c in observed.get("cases",[])),
             "QA_CASES_INCOMPLETE")
        need(observed["worker_sha256"]==WORKER_SHA
             and observed["migration_0043_sha256"]==M43_SHA
             and observed["protected_quota_units"]==1
             and observed["actual_tenantquota_worker_rpc"] is True
             and observed["workerd_restart_preserved"] is True
             and observed["production_mutated"] is False
             and observed["cloudflare_hosted_proven"] is False,
             "QA_SCOPE_OR_QUOTA_INVALID")
        receipt={
          "schema":"hara.commander-0043-real-quota-workerd-qa.v1",
          "state":observed["state"],
          "prechange_commit":"15306dc6de16f80f09dcfc4c7939ed8f7f9f2586",
          "candidate_parent":"44e2d611fdd23cc605aa00ccb648aae9b1a2c133",
          "source_sha256":WORKER_SHA,
          "migration_0043_sha256":M43_SHA,
          "test_source_sha256":sha(TEST),
          "real_worker_bundle_sha256":sha(bundle),
          "bundle_bytes":bundle.stat().st_size,
          "observed":observed,
          "ephemeral_storage_deleted":True,
          "cloudflare_calls":0,"real_agent_dispatches":0,
          "production_mutations":0,"prod_0043_migration_applied":False,
          "global_quiescence_proven":False,
          "commercial_cutover_authorized":False}
    OUT.mkdir(parents=True,exist_ok=True)
    filename=OUT/"REAL_TENANT_QUOTA_WORKERD_QA.json"
    with filename.open("x") as out:
      json.dump(receipt,out,ensure_ascii=False,sort_keys=True,indent=2);out.write("\n")
    print(json.dumps({"state":receipt["state"],"cases_passed":5,
       "source_sha256":WORKER_SHA,
       "bundle_sha256":receipt["real_worker_bundle_sha256"],
       "receipt_sha256":sha(filename),
       "production_mutations":0},sort_keys=True))


if __name__=="__main__":main()