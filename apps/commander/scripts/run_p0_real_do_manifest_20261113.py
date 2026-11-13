#!/usr/bin/env python3
"""Build current real Commander DO Worker and test QA manifest in local workerd.

No Cloudflare calls, production deploy, migration, live code, or Agent effects.
Uses a bounded ephemeral build and write-once local QA evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
OUT = ROOT / "docs/evidence/commander-p0-real-do-manifest-20261113"
NODE = "/tmp_hara/commander-node24/bin/node"
WRANGLER = "/tmp_hara/commander-capability-suite-20261110/node_modules/wrangler/bin/wrangler.js"
DEPS = Path("/tmp_hara/commander-capability-suite-20261110/node_modules")
PINS = {
    "worker.js": "9d7b5f192509f482e1cd79362a567b8e832a19adf149705d4e5df731d0197260",
    "device-channel.mjs": "038025cdb9ca76fd992b828e2bdcbe623447014102f1d421469698d9380b6779",
    "security-rate-limit-do.mjs": "d2a610d7fa32c8687c057c1015658d550aa0d5a0ddf4358994c7c4da1ef7dd33",
}
M43_SHA = "7e4d484161461deec1e7235d4ed6f725bf1c32ecc7901ba1b0c9885ffb0f28d3"
TEST = APP / "scripts/test_p0_real_do_manifest_20261113.mjs"
GATE = APP / "qa/p0-manifest-runtime/manifest-gate.mjs"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def need(value: bool, code: str) -> None:
    if value is not True:
        raise RuntimeError(code)


def main() -> None:
    need(not OUT.exists(), "QA_RECEIPT_ALREADY_EXISTS")
    need(Path(NODE).is_file() and Path(WRANGLER).is_file() and
         (DEPS / "miniflare").is_dir() and (DEPS / "zod").is_dir(),
         "QA_RUNTIME_DEPENDENCY_MISSING")
    for name, pin in PINS.items():
        need(sha((APP / "src" / name).read_bytes()) == pin, "EXACT_SOURCE_DRIFT:" + name)
    need(sha((APP / "migrations/0043_device_call_authorization.sql").read_bytes())
         == M43_SHA, "MIGRATION_SOURCE_DRIFT")
    source_hashes = {"apps/commander/src/" + k: v for k, v in PINS.items()}
    for file in (TEST, GATE):
        source_hashes[file.relative_to(ROOT).as_posix()] = sha(file.read_bytes())
    environment = {k: v for k, v in os.environ.items()
                   if not k.upper().startswith(("CF_", "CLOUDFLARE_")) and
                   "API_KEY" not in k.upper() and "API_TOKEN" not in k.upper()}
    environment.update({
        "PATH": "/tmp_hara/commander-node24/bin:" + environment.get("PATH", "/usr/bin:/bin"),
        "CI": "true", "WRANGLER_SEND_METRICS": "false", "NO_PROXY": "*",
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
    })
    with tempfile.TemporaryDirectory(prefix="commander-do-manifest-", dir="/tmp_hara") as folder:
        tmp = Path(folder)
        shutil.copytree(APP / "src", tmp / "src")
        (tmp / "node_modules").symlink_to(DEPS, target_is_directory=True)
        for name, pin in PINS.items():
            need(sha((tmp / "src" / name).read_bytes()) == pin,
                 "COPIED_SOURCE_DIFFERENT:" + name)
        config = {
            "name": "hara-commander-p0-do-manifest-unpublished",
            "main": "src/worker.js", "compatibility_date": "2026-09-21",
            "workers_dev": False, "preview_urls": False,
            "durable_objects": {
                "bindings": [
                    {"name": "TENANT_QUOTA", "class_name": "TenantQuota"},
                    {"name": "DEVICE_CHANNEL", "class_name": "DeviceChannel"},
                    {"name": "STRICT_RATE_LIMIT", "class_name": "SecurityRateLimit"},
                ],
            },
            "migrations": [{"tag": "v1", "new_sqlite_classes": [
                "TenantQuota", "DeviceChannel", "SecurityRateLimit"]}],
            "vars": {
                "ENVIRONMENT": "DEV", "STORAGE_MODE": "ISOLATED_QA",
                "CUSTOMER_MCP_EDGE_ENABLED": "false",
                "DEVICE_EVENT_V2_ENABLED": "false",
                "STRIPE_CHECKOUT_ENABLED": "false",
            },
        }
        config_file = tmp / "wrangler.json"
        config_file.write_text(json.dumps(config, indent=2) + "\n")
        built = subprocess.run(
            [NODE, WRANGLER, "deploy", "--dry-run", "--config",
             str(config_file), "--outdir", str(tmp / "build")],
            cwd=tmp, env=environment, text=True, capture_output=True,
            timeout=110, check=False,
        )
        need(built.returncode == 0, "WORKER_BUNDLE_BUILD_FAILED:" + built.stderr[-280:])
        bundle = tmp / "build/worker.js"
        if not bundle.is_file():
            bundle = tmp / "build/entry.js"
        need(bundle.is_file() and bundle.stat().st_size > 100000,
             "EXACT_WORKER_BUNDLE_MISSING")
        (tmp / "build/package.json").write_text('{"type":"module"}\n')
        result = subprocess.run(
            [NODE, str(TEST), str(bundle), str(tmp / "storage")],
            cwd=tmp, env=environment, text=True, capture_output=True,
            timeout=100, check=False,
        )
        need(result.returncode == 0, "DO_MANIFEST_TEST_FAILED:" +
             result.stderr[:900] + result.stderr[-350:] + result.stdout[-350:])
        lines = [x for x in result.stdout.splitlines() if x.startswith("{")]
        need(len(lines) == 1, "MANIFEST_OUTPUT_NOT_SINGLE_JSON")
        observed = json.loads(lines[0])
        need(observed["state"] == "REAL_PRODUCT_DO_KNOWN_MANIFEST_WORKERD_PASS_GLOBAL_HOLD",
             "MANIFEST_QA_STATE_INVALID")
        need(observed["source_worker_sha256"] == PINS["worker.js"],
             "MANIFEST_WORKER_SHA_DRIFT")
        need(len(observed["cases"]) >= 10 and
             all(x["state"] == "PASS" for x in observed["cases"]),
             "DO_MANIFEST_CASES_INCOMPLETE")
        need(observed["commercial_cutover_authorized"] is False and
             observed["commercial_active_inventory_proven"] is False and
             observed["two_global_quiescence_windows_proven"] is False and
             observed["provider_called"] is False and
             observed["production_mutated"] is False and
             observed["unregistered_qa_actor_observed"] is True,
             "MANIFEST_GLOBAL_SCOPE_OVERCLAIM")
        need(observed["scoped_witness"]["unique_nonces"] == 8 and
             observed["scoped_witness"]["known_qa_instances"] == 4,
             "SCOPED_WITNESS_COUNT_INVALID")
        receipt = {
            "schema": "hara.commander-real-product-do-manifest-runtime-qa.v1",
            "state": "REAL_PRODUCT_DO_KNOWN_MANIFEST_WORKERD_PASS_GLOBAL_HOLD",
            "base_commit": "dcfe17937a314431a71c2634a0b8fed0ac61187d",
            "source_sha256": source_hashes,
            "worker_bundle_sha256": sha(bundle.read_bytes()),
            "worker_bundle_bytes": bundle.stat().st_size,
            "wrangler_config_sha256": sha(config_file.read_bytes()),
            "migration_0043_source_sha256": M43_SHA,
            "observed": observed,
            "temporary_storage_removed": True,
            "provider_called": False, "agent_contacted": False,
            "prod_migration_applied": False, "production_mutated": False,
            "global_quiescence_proven": False,
            "production_promotion_authorized": False,
        }
    OUT.mkdir(parents=True)
    destination = OUT / "REAL_DO_MANIFEST_WORKERD_QA.json"
    with destination.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({
        "state": receipt["state"],
        "case_count": len(observed["cases"]),
        "negative_rejected": next(
            x["negatives_rejected"] for x in observed["cases"]
            if x["name"] == "corrupted DO witnesses or actor rosters fail closed"),
        "manifest_instances": observed["scoped_witness"]["known_qa_instances"],
        "unregistered_effect_detected": observed["unregistered_qa_actor_observed"],
        "bundle_sha256": receipt["worker_bundle_sha256"],
        "receipt_sha256": sha(destination.read_bytes()),
        "temporary_storage_removed": True,
        "production_mutated": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()