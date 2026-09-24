#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
CONFIG = APP / "wrangler.dev.jsonc"
DEV_ORIGIN = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
REQUIRED_SECRETS = {
    "AUTH_CLIENT_SECRET",
    "DEV_ACCESS_TOKEN",
    "MCP_PRODUCT_TOKEN",
}

def run(command):
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or "WRANGLER_READBACK_FAILED")
    return proc.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrangler-version", default="4.137.0")
    parser.add_argument("--expect-version", default="")
    parser.add_argument(
        "--allow-implicit-basic",
        action="store_true",
        help="accept missing AUTH_CLIENT_AUTH only as the historical BASIC fallback before config alignment",
    )
    args = parser.parse_args()
    wrangler = f"wrangler@{args.wrangler_version}"

    deployments = json.loads(run([
        "npx", "--yes", wrangler, "deployments", "list",
        "--json", "--config", str(CONFIG),
    ]))
    if not deployments:
        raise RuntimeError("DEV_DEPLOYMENTS_EMPTY")
    latest = deployments[-1]
    versions = latest.get("versions") or []
    if len(versions) != 1 or float(versions[0].get("percentage", 0)) != 100.0:
        raise RuntimeError("DEV_DEPLOYMENT_NOT_SINGLE_VERSION_100_PERCENT")
    current = str(versions[0].get("version_id") or "")
    if args.expect_version and current != args.expect_version:
        raise RuntimeError(f"DEV_VERSION_EXPECTED_{args.expect_version}_GOT_{current}")

    view = json.loads(run([
        "npx", "--yes", wrangler, "versions", "view", current,
        "--json", "--config", str(CONFIG),
    ]))
    bindings = view.get("resources", {}).get("bindings") or []
    by_name = {item.get("name"): item for item in bindings if item.get("name")}

    expected = json.loads(CONFIG.read_text(encoding="utf-8"))
    for key, value in expected["vars"].items():
        binding = by_name.get(key) or {}
        if (
            key == "AUTH_CLIENT_AUTH"
            and args.allow_implicit_basic
            and not binding
            and value == "BASIC"
        ):
            continue
        if binding.get("type") != "plain_text" or binding.get("text") != value:
            raise RuntimeError(f"DEV_VAR_DRIFT:{key}")

    product = by_name.get("PRODUCT_DB") or {}
    expected_d1 = expected["d1_databases"][0]
    if product.get("type") != "d1" or product.get("database_id") != expected_d1["database_id"]:
        raise RuntimeError("DEV_D1_BINDING_DRIFT")

    assets = by_name.get("ASSETS") or {}
    if assets.get("type") != "assets":
        raise RuntimeError("DEV_ASSETS_BINDING_DRIFT")

    quota = by_name.get("TENANT_QUOTA") or {}
    if quota.get("type") != "durable_object_namespace" or quota.get("class_name") != "TenantQuota":
        raise RuntimeError("DEV_QUOTA_BINDING_DRIFT")

    secret_names = {
        item.get("name")
        for item in bindings
        if item.get("type") == "secret_text"
    }
    if secret_names != REQUIRED_SECRETS:
        raise RuntimeError(
            "DEV_SECRET_BINDING_DRIFT:"
            + ",".join(sorted(secret_names))
        )

    req = Request(
        DEV_ORIGIN + "/api/health",
        headers={"User-Agent": "HARA-Commander-DEV-Readback/1"},
    )
    with urlopen(req, timeout=15) as response:
        health = json.loads(response.read())
    if health.get("ok") is not True:
        raise RuntimeError("DEV_HEALTH_NOT_OK")
    if health.get("environment") != "DEV":
        raise RuntimeError("DEV_HEALTH_ENVIRONMENT_DRIFT")
    if health.get("storage_mode") != "REMOTE_DEV":
        raise RuntimeError("DEV_HEALTH_STORAGE_DRIFT")

    rollback = None
    if len(deployments) >= 2:
        prior = deployments[-2].get("versions") or []
        if len(prior) == 1 and float(prior[0].get("percentage", 0)) == 100.0:
            rollback = str(prior[0].get("version_id") or "") or None

    print("COMMANDER_DEV_CONFIG_LIVE=PASS")
    print("COMMANDER_DEV_D1_LIVE=DEV_ONLY")
    print("COMMANDER_DEV_SECRETS_LIVE=PASS")
    print("COMMANDER_DEV_HEALTH=PASS")
    print(f"COMMANDER_DEV_WORKER_VERSION={current}")
    if rollback:
        print(f"COMMANDER_DEV_WORKER_ROLLBACK_VERSION={rollback}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMMANDER_DEV_CONFIG_LIVE=FAIL:{exc}")
        raise
