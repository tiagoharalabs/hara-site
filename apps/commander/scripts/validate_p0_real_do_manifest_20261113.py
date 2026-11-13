#!/usr/bin/env python3
"""Independent custody readback of the real 3-class DO manifest local QA.

Read-only relative to source and provider. Writes only new write-once QA report.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
OUT = ROOT / "docs/evidence/commander-p0-real-do-manifest-20261113"
RECEIPT = OUT / "REAL_DO_MANIFEST_WORKERD_QA.json"
SOURCE = "9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260"
M43 = "7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
SCOPED = "KNOWN_QA_DO_MANIFEST_TWO_OBSERVATIONS_PASS_GLOBAL_HOLD"
STATE = "REAL_PRODUCT_DO_KNOWN_MANIFEST_WORKERD_PASS_GLOBAL_HOLD"


def check(ok: bool, reason: str) -> None:
    if ok is not True:
        raise RuntimeError(reason)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    check(RECEIPT.is_file() and not RECEIPT.is_symlink(), "QA_RECEIPT_MISSING")
    record = json.loads(RECEIPT.read_text())
    check(record["schema"] == "hara.commander-real-product-do-manifest-runtime-qa.v1" and
          record["state"] == STATE, "QA_RESULT_SCHEMA_STATE_DRIFT")
    check(record.get("migration_0043_source_sha256") == M43, "M43_RECEIPT_DRIFT")
    check(sha(APP / "migrations/0043_device_call_authorization.sql") == M43,
          "M43_SOURCE_DRIFT")
    sources = record.get("source_sha256")
    check(isinstance(sources, dict) and len(sources) == 5 and
          sources.get("apps/commander/src/worker.js") == SOURCE, "SOURCE_MANIFEST_DRIFT")
    for key, digest in sources.items():
        f = ROOT / key
        check(f.is_file() and not f.is_symlink() and sha(f) == digest,
              "SOURCE_BLOB_MISMATCH:" + key)
    check(record.get("temporary_storage_removed") is True and
          record.get("provider_called") is False and
          record.get("agent_contacted") is False and
          record.get("prod_migration_applied") is False and
          record.get("production_mutated") is False and
          record.get("global_quiescence_proven") is False and
          record.get("production_promotion_authorized") is False,
          "QA_RECEIPT_SCOPE_INVALID")
    observed = record.get("observed")
    check(isinstance(observed, dict) and observed.get("state") == STATE and
          observed.get("source_worker_sha256") == SOURCE and
          observed.get("observer_scope") == "LOCAL_WORKERD_KNOWN_SYNTHETIC_MANIFEST_ONLY",
          "WORKERD_WITNESS_NOT_PINNED")
    cases = observed.get("cases")
    check(isinstance(cases, list) and len(cases) == 11 and
          len({row["name"] for row in cases}) == 11 and
          all(row["state"] == "PASS" for row in cases), "REAL_DO_CASE_MATRIX_INCOMPLETE")
    negative = next((x for x in cases if
                     x["name"] == "corrupted DO witnesses or actor rosters fail closed"),
                    None)
    check(isinstance(negative, dict) and negative.get("negatives_rejected") == 22,
          "NEGATIVE_ASSERTIONS_UNPROVEN")
    scoped = observed.get("scoped_witness")
    check(isinstance(scoped, dict) and scoped.get("state") == SCOPED and
          scoped.get("known_qa_instances") == 4 and
          scoped.get("samples") == 2 and scoped.get("unique_nonces") == 8 and
          scoped.get("quota_protected_units") == 2 and
          scoped.get("websocket_drained_in_known_channel") is True,
          "SCOPED_DO_WITNESS_INCOMPLETE")
    check(200 <= observed.get("time_gap_ms", -1) <= 30000 and
          observed.get("unregistered_qa_actor_observed") is True and
          observed.get("commercial_active_inventory_proven") is False and
          observed.get("two_global_quiescence_windows_proven") is False and
          observed.get("commercial_cutover_authorized") is False and
          observed.get("local_runtime_restart_proven") is True and
          observed.get("provider_called") is False and
          observed.get("production_mutated") is False,
          "GLOBAL_PROOF_OVERCLAIM_OR_RESTART_MISSING")
    check(scoped.get("unregistered_DO_instances_excluded") is True and
          scoped.get("global_two_quiescence_windows_proven") is False and
          scoped.get("commercial_cutover_authorized") is False,
          "SCOPED_GATE_OVERCLAIM")

    report = {
        "schema": "hara.commander-do-manifest-workerd-independent.v1",
        "state": "REAL_PRODUCT_DO_MANIFEST_11_AND_22_NEGATIVES_PASS_GLOBAL_HOLD",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "product_source_sha256": SOURCE,
        "migration_0043_source_sha256": M43,
        "three_real_classes_exercised": True,
        "four_known_qa_instances_exercised": True,
        "two_scoped_observations_with_distinct_nonces": True,
        "local_observation_gap_ms": observed["time_gap_ms"],
        "end_to_end_cases_passed": 11,
        "negative_mutations_rejected": 22,
        "protected_quota_units_survived_restart": 2,
        "unregistered_DO_mutation_possible": True,
        "all_live_instance_inventory_proven": False,
        "global_two_quiescence_windows_proven": False,
        "commercial_worker_0043_deployed": False,
        "commercial_migration_0043_authorized": False,
        "commercial_cutover_authorized": False,
        "rollback_to_legacy_worker_authorized": False,
        "filetools_activation_authorized": False,
        "cloudflare_calls": 0,
        "production_mutations": 0,
        "source_blob_sha256": sources,
        "worker_bundle_sha256": record["worker_bundle_sha256"],
        "qa_receipt_sha256": sha(RECEIPT),
    }
    filename = OUT / "INDEPENDENT_DO_MANIFEST_READBACK.json"
    with filename.open("x") as out:
        json.dump(report, out, indent=2, sort_keys=True)
        out.write("\n")
    print(json.dumps({
        "state": report["state"],
        "case_count": report["end_to_end_cases_passed"],
        "negatives_rejected": report["negative_mutations_rejected"],
        "known_qa_instances": 4, "production_promotion_authorized": False,
        "receipt_sha256": sha(filename),
    }, sort_keys=True))


if __name__ == "__main__":
    main()