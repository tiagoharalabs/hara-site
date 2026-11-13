#!/usr/bin/env python3
"""Reproduce and audit exact Commander 0043 atomic enqueue authorization fix.

Uses real Worker source, original 0043 migration and isolated SQLite.
Build dry-run only; no Cloudflare, Agent, Stripe, customer or deployment call.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
OUT = ROOT / "docs/evidence/commander-0043-atomic-enqueue-20261113"
WORKER_SHA = "c9f4c48e553de133598982018a3fbc19f6fcf9165dfd9ddf1609620da61e8dbc"
M43_SHA = "7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
NODE = "/tmp_hara/commander-node24/bin/node"
CLI = "/tmp_hara/commander-capability-suite-20261110/node_modules/wrangler/bin/wrangler.js"
DEPS = Path("/tmp_hara/commander-capability-suite-20261110/node_modules")
SUITES = (
    ("enqueue_and_async_approval", "test_approval_async_queue_claim_0043_candidate_20261112.mjs", 26),
    ("claim_fence_and_scrub", "test_p0_dispatch_authorization_0043_undelivered_20261112.mjs", 29),
)
EXPECTED_LATE = (
    "0043 final enqueue denies entitlement revoked during usage await",
    "0043 enqueuing after late identity binding revocation fails closed",
    "0043 enqueuing after late subject revocation fails closed",
    "0043 enqueuing after late plan revocation fails closed",
    "0043 enqueuing after late grant revocation fails closed",
    "0043 enqueuing after late expiry revocation fails closed",
    "0043 enqueuing after late OIDC issuer revocation fails closed",
)


def check(ok: bool, code: str) -> None:
    if ok is not True:
        raise RuntimeError(code)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    worker = APP / "src/worker.js"
    migration = APP / "migrations/0043_device_call_authorization.sql"
    check(not OUT.exists(), "RECEIPT_WRITE_ONCE_COLLISION")
    check(sha(worker) == WORKER_SHA, "WORKER_SOURCE_SHA_DRIFT")
    check(sha(migration) == M43_SHA, "CANONICAL_0043_DRIFT")
    source = worker.read_text()
    check('callAuthorizationFence("auth_call")' in source and
          "AND EXISTS (" in source and
          "callId, requestId, context.tenant_id, context.subject_id," in source,
          "ATOMIC_INSERT_AUTHORIZATION_GUARD_ABSENT")
    check(Path(NODE).is_file() and Path(CLI).is_file() and
          (DEPS / "zod").is_dir(), "QA_DEPS_MISSING")
    link = ROOT / "node_modules"
    check(not link.exists() and not link.is_symlink(), "PREEXISTING_NODE_MODULES_REFUSED")
    environment = {k: v for k, v in os.environ.items()
                   if not k.upper().startswith(("CLOUDFLARE_", "CF_"))
                   and not k.upper().endswith(("TOKEN", "SECRET", "KEY"))}
    environment.update({
        "PATH": "/tmp_hara/commander-node24/bin:" + environment.get("PATH", "/usr/bin:/bin"),
        "CI": "true", "WRANGLER_SEND_METRICS": "false",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "*",
    })
    results = []
    link.symlink_to(DEPS, target_is_directory=True)
    try:
        for kind, name, expected in SUITES:
            script = APP / "scripts" / name
            syntax = subprocess.run([NODE, "--check", str(script)],
                                    cwd=ROOT, env=environment,
                                    text=True, capture_output=True,
                                    timeout=12, check=False)
            check(syntax.returncode == 0, "NODE_PARSE_FAILED:" + name)
            run = subprocess.run([NODE, str(script)], cwd=ROOT,
                                 env=environment, text=True,
                                 capture_output=True, timeout=28, check=False)
            check(run.returncode == 0, "SUITE_FAILED:" + name + ":" + run.stderr[-450:])
            lines = [line for line in run.stdout.splitlines() if line.startswith("{")]
            check(len(lines) == 1, "SUITE_JSON_INVALID:" + name)
            value = json.loads(lines[0])
            check(value.get("worker_sha256", value.get("worker_source_sha256")) == WORKER_SHA,
                  "SUITE_SOURCE_MISMATCH:" + name)
            if kind == "enqueue_and_async_approval":
                check(value["state"] == "PASS" and value["tests"] == expected,
                      "ENQUEUE_SUITE_WRONG_CASE_COUNT")
                check(all(("PASS " + title) in run.stdout for title in EXPECTED_LATE),
                      "LATE_AUTHORIZATION_CASE_NOT_EXECUTED")
            else:
                check(value["state"] == "REAL_SOURCE_DISPATCH_AUTHORIZATION_QA_PASS" and
                      value["total_cases"] == expected and
                      all(case["state"] == "PASS" for case in value["cases"]),
                      "CLAIM_SUITE_NOT_ALL_PASS")
                check(value["sqlite_migration_21_to_22"] is True and
                      value["temporary_databases_closed"] == expected and
                      value["real_agent_dispatched"] is False and
                      value["production_mutated"] is False,
                      "CLAIM_SQL_OR_ISOLATION_DRIFT")
            results.append({
                "kind": kind, "name": name, "passed": expected,
                "source_sha256": sha(script),
                "stdout_sha256": hashlib.sha256(run.stdout.encode()).hexdigest(),
            })
        with tempfile.TemporaryDirectory(prefix="hara-0043-enqueue-dryrun-", dir="/tmp_hara") as temp:
            build = subprocess.run(
                [NODE, CLI, "deploy", "--dry-run", "--config",
                 str(APP / "wrangler.dev.jsonc"), "--outdir", temp],
                cwd=ROOT, env=environment, text=True,
                capture_output=True, timeout=110, check=False,
            )
            check(build.returncode == 0, "WORKER_DRYRUN_FAILED:" + build.stderr[-400:])
            bundle = Path(temp) / "worker.js"
            check(bundle.is_file() and bundle.stat().st_size > 1000000,
                  "WORKER_COMPLETE_BUNDLE_MISSING")
            bundle_sha, bundle_size = sha(bundle), bundle.stat().st_size
    finally:
        link.unlink()
    check(not link.exists(), "TEMP_DEPENDENCY_LINK_NOT_CLEANED")
    receipt = {
        "schema": "hara.commander-0043-atomic-enqueue-qa.v1",
        "state": "ATOMIC_0043_ENQUEUE_AUTHORIZATION_26_AND_29_PASS",
        "base_commit": "6f3d62bf76835690ff06d074277b2f7cce891526",
        "source_branch": "local/commander-0043-enqueue-auth-fence-20261113",
        "worker_source_sha256": WORKER_SHA,
        "canonical_migration_0043_sha256": M43_SHA,
        "source_guard": "callAuthorizationFence(auth_call) INSIDE_INSERT_OR_IGNORE",
        "late_revocation_regressions": len(EXPECTED_LATE),
        "late_revocation_case_names": list(EXPECTED_LATE),
        "suite_results": results,
        "worker_bundle_sha256": bundle_sha,
        "worker_bundle_bytes": bundle_size,
        "before_patch_observed": {
            "case": EXPECTED_LATE[0],
            "state": "MISSING_EXPECTED_REJECTION",
            "sql_row_insert_not_blocked": True,
        },
        "qa_after_patch": {"enqueue_approval": 26, "claim": 29, "both_pass": True},
        "source_worker_0043_applied_to_prod": False,
        "real_agent_contacted": False,
        "provider_called": False,
        "cloudflare_mutations": 0,
        "stripe_mutations": 0,
        "production_mutated": False,
        "production_promotion_authorized": False,
        "consumer_commercial_queue_proven": False,
        "global_do_quiescence_proven": False,
    }
    OUT.mkdir(parents=True)
    dest = OUT / "ATOMIC_0043_ENQUEUE_QA.json"
    with dest.open("x") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({
        "state": receipt["state"],
        "enqueue_cases": 26, "claim_cases": 29,
        "worker_sha256": WORKER_SHA,
        "bundle_sha256": bundle_sha,
        "receipt_sha256": sha(dest),
        "production_mutated": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()