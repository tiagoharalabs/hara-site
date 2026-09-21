#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
GENERATED = APP / ".generated"
CONFIG = GENERATED / "wrangler.remote.dev.json"
DB_NAME = "hara-commander-product-dev"
WORKER_NAME = "hara-commander-dev-v2"


def run(*args: str, capture: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["npx", "--yes", "wrangler@4.136.1", *args]
    return subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        capture_output=capture,
        check=False,
        env=os.environ.copy(),
    )


def require_ok(result: subprocess.CompletedProcess[str], code: str) -> str:
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        print(f"{code}=FAIL")
        if detail:
            print(detail)
        raise SystemExit(result.returncode or 1)
    return result.stdout


def main() -> int:
    who = run("whoami")
    if who.returncode != 0 or "not logged in" in (who.stdout + who.stderr).lower():
        print("CLOUDFLARE_AUTH=REQUIRED")
        print("REMOTE_DEV_MUTATION=FALSE")
        return 2

    print("CLOUDFLARE_AUTH=PASS")

    listing = run("d1", "list", "--json")
    raw = require_ok(listing, "REMOTE_DEV_D1_LIST")
    databases = json.loads(raw or "[]")
    database = next((item for item in databases if item.get("name") == DB_NAME), None)

    if database is None:
        created = run("d1", "create", DB_NAME)
        require_ok(created, "REMOTE_DEV_D1_CREATE")
        listing = run("d1", "list", "--json")
        databases = json.loads(require_ok(listing, "REMOTE_DEV_D1_RELIST") or "[]")
        database = next((item for item in databases if item.get("name") == DB_NAME), None)
        if database is None:
            print("REMOTE_DEV_D1_DISCOVERY=FAIL")
            return 3
        print("REMOTE_DEV_D1_CREATED=TRUE")
    else:
        print("REMOTE_DEV_D1_CREATED=FALSE")

    database_id = database.get("uuid") or database.get("id")
    if not database_id:
        print("REMOTE_DEV_D1_ID=FAIL")
        return 4

    GENERATED.mkdir(parents=True, exist_ok=True)
    config = {
        "$schema": "../../../node_modules/wrangler/config-schema.json",
        "name": WORKER_NAME,
        "main": "../src/worker.js",
        "compatibility_date": "2026-09-21",
        "vars": {
            "ENVIRONMENT": "DEV",
            "STORAGE_MODE": "REMOTE_DEV",
            "MCP_BASE_URL": "https://mcp.haralabs.com.br/mcp",
        },
        "d1_databases": [{
            "binding": "PRODUCT_DB",
            "database_name": DB_NAME,
            "database_id": database_id,
            "migrations_dir": "../migrations",
        }],
        "durable_objects": {
            "bindings": [{
                "name": "TENANT_QUOTA",
                "class_name": "TenantQuota",
            }]
        },
        "migrations": [{
            "tag": "v1",
            "new_sqlite_classes": ["TenantQuota"],
        }],
    }
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("REMOTE_DEV_CONFIG_GENERATED=PASS")

    migrations = run(
        "d1", "migrations", "apply", DB_NAME,
        "--remote",
        "--config", str(CONFIG),
    )
    require_ok(migrations, "REMOTE_DEV_D1_MIGRATIONS")
    print("REMOTE_DEV_D1_MIGRATIONS=PASS")

    seed = run(
        "d1", "execute", DB_NAME,
        "--remote",
        "--config", str(CONFIG),
        "--file", str(APP / "seed" / "dev.sql"),
    )
    require_ok(seed, "REMOTE_DEV_D1_SEED")
    print("REMOTE_DEV_SYNTHETIC_SEED=PASS")

    deploy = run(
        "deploy",
        "--config", str(CONFIG),
        "--strict",
    )
    output = require_ok(deploy, "REMOTE_DEV_WORKER_DEPLOY")
    print("REMOTE_DEV_WORKER_DEPLOY=PASS")
    for line in output.splitlines():
        if "workers.dev" in line or "https://" in line:
            print("REMOTE_DEV_DEPLOY_OUTPUT=" + line.strip())

    print("REMOTE_DEV_D1=PASS")
    print("REMOTE_DEV_QUOTA_NAMESPACE=PASS")
    print("SYNTHETIC_DATA_ONLY=TRUE")
    print("PRODUCTION_DNS_MUTATION=FALSE")
    print("PRODUCTION_DATA_MUTATION=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
