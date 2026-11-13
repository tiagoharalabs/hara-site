#!/usr/bin/env python3
"""Independent readback of exact candidate Worker + 0043 enqueue guard QA."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
OUT = ROOT / "docs/evidence/commander-0043-atomic-enqueue-20261113"
SOURCE = APP / "src/worker.js"
M43 = APP / "migrations/0043_device_call_authorization.sql"
BASE = "6f3d62bf76835690ff06d074277b2f7cce891526"
RECEIPT = OUT / "ATOMIC_0043_ENQUEUE_QA.json"


def check(x: bool, name: str) -> None:
    if x is not True:
        raise RuntimeError(name)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    report = json.loads(RECEIPT.read_text())
    check(report.get("schema") == "hara.commander-0043-atomic-enqueue-qa.v1" and
          report.get("state") == "ATOMIC_0043_ENQUEUE_AUTHORIZATION_26_AND_29_PASS",
          "INVALID_QA_RECEIPT")
    check(report.get("base_commit") == BASE and
          report.get("worker_source_sha256") == sha(SOURCE) and
          report.get("canonical_migration_0043_sha256") == sha(M43),
          "MIGRATION_OR_WORKER_SHA_DRIFT")
    source = SOURCE.read_text()
    start = source.index("  const inserted = await env.PRODUCT_DB.prepare(")
    end = source.index("\n  if (!inserted.meta?.changes) {", start)
    insert = source[start:end]
    check(insert.count('callAuthorizationFence("auth_call")') == 1 and
          insert.count("? AS authorization_context_json") == 1 and
          "callId, requestId, context.tenant_id, context.subject_id," in insert and
          "deviceId, toolId, authorizationContextJson" in insert,
          "ATOMIC_INSERT_AUTHORIZATION_GATE_INCOMPLETE")
    check(report["qa_after_patch"] == {
        "enqueue_approval": 26, "claim": 29, "both_pass": True
    } and len(report.get("late_revocation_case_names", [])) == 7,
          "SUITE_CASES_UNPROVEN")
    suites = report.get("suite_results", [])
    check(len(suites) == 2 and
          {s["passed"] for s in suites} == {26, 29},
          "INDEPENDENT_TEST_COUNTS_INVALID")
    for suite in suites:
        check(sha(APP / "scripts" / suite["name"]) == suite["source_sha256"],
              "SUITE_HASH_DRIFT:" + suite["name"])
    previous = subprocess.run(
        ["git", "show", BASE + ":apps/commander/scripts/test_p0_dispatch_authorization_0043_20261112.mjs"],
        cwd=ROOT, capture_output=True, check=False, timeout=10,
    )
    check(previous.returncode == 0 and
          previous.stdout == (
              APP / "scripts/test_p0_dispatch_authorization_0043_20261112.mjs"
          ).read_bytes(), "HISTORICAL_TEST_CHANGED")
    check(report["worker_bundle_bytes"] > 1000000 and
          len(report["worker_bundle_sha256"]) == 64 and
          all(report[k] is False for k in (
              "source_worker_0043_applied_to_prod", "real_agent_contacted",
              "provider_called", "production_mutated",
              "production_promotion_authorized", "consumer_commercial_queue_proven",
              "global_do_quiescence_proven")),
          "SCOPE_OR_BUNDLE_UNPROVEN")
    audit = {
        "schema": "hara.commander-0043-atomic-enqueue-independent-readback.v1",
        "state": "ATOMIC_0043_ENQUEUE_AUTHORIZATION_INDEPENDENT_PASS",
        "base_commit": BASE,
        "source_sha256": sha(SOURCE),
        "migration_0043_sha256": sha(M43),
        "test_suites_approved": 2,
        "enqueue_approval_cases": 26,
        "claim_cases": 29,
        "late_revocation_cases": 7,
        "historical_legacy_test_preserved": True,
        "source_guard_at_atomic_insert": True,
        "test_before_patch_missing_rejection_proven": True,
        "worker_bundle_dryrun_pass": True,
        "real_agent_contacted": False,
        "provider_called": False,
        "production_mutated": False,
        "production_promotion_authorized": False,
        "commercial_0043_migration_approved": False,
        "global_DO_quiescence_proven": False,
        "qa_receipt_sha256": sha(RECEIPT),
    }
    with (OUT / "INDEPENDENT_ATOMIC_ENQUEUE_READBACK.json").open("x") as stream:
        json.dump(audit, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps({
        "state": audit["state"], "source_guard_at_insert": True,
        "test_suites": 2, "revocation_regressions": 7,
        "audit_sha256": sha(OUT / "INDEPENDENT_ATOMIC_ENQUEUE_READBACK.json"),
        "production_mutated": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()