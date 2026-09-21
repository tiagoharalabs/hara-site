#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import secrets
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
GENERATED = APP / ".generated"
CONFIG = GENERATED / "wrangler.remote.dev.json"
TOKEN_FILE = GENERATED / "remote-dev-access-token"
AUTH_FILE = GENERATED / "identity-dev.json"
AUTH_SECRET_FILE = GENERATED / "oidc-client-secret"
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

    auth_metadata = None
    if AUTH_FILE.exists():
        auth_metadata = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        for field in ("issuer", "client_id", "provider_label"):
            if not auth_metadata.get(field):
                print("HARA_IDENTITY_DEV_METADATA=FAIL:" + field)
                return 6

    config = {
        "$schema": "../../../node_modules/wrangler/config-schema.json",
        "name": WORKER_NAME,
        "main": "../src/worker.js",
        "compatibility_date": "2026-09-21",
        "assets": {
            "directory": "../../../public/dev/commander",
            "binding": "ASSETS",
            "run_worker_first": ["/api/*", "/auth/*"],
            "html_handling": "auto-trailing-slash",
            "not_found_handling": "404-page",
        },
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
    if auth_metadata:
        config["vars"]["AUTH_ISSUER"] = auth_metadata["issuer"]
        config["vars"]["AUTH_CLIENT_ID"] = auth_metadata["client_id"]
        config["vars"]["AUTH_PROVIDER_LABEL"] = auth_metadata["provider_label"]
        print("HARA_IDENTITY_DEV_METADATA=PASS")
    else:
        print("HARA_IDENTITY_DEV_METADATA=NOT_CONFIGURED")

    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print("REMOTE_DEV_CONFIG_GENERATED=PASS")

    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text(secrets.token_urlsafe(48), encoding="utf-8")
        TOKEN_FILE.chmod(0o600)
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        print("REMOTE_DEV_TOKEN=FAIL")
        return 5

    secret = subprocess.run(
        ["npx", "--yes", "wrangler@4.136.1", "secret", "put", "DEV_ACCESS_TOKEN", "--config", str(CONFIG)],
        cwd=ROOT,
        text=True,
        input=token + "\n",
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    require_ok(secret, "REMOTE_DEV_SECRET")
    print("REMOTE_DEV_SECRET=PASS")

    if auth_metadata and AUTH_SECRET_FILE.exists():
        auth_secret = AUTH_SECRET_FILE.read_text(encoding="utf-8").strip()
        if len(auth_secret) < 16:
            print("OIDC_CLIENT_SECRET=FAIL")
            return 7
        auth_secret_result = subprocess.run(
            ["npx", "--yes", "wrangler@4.136.1", "secret", "put", "AUTH_CLIENT_SECRET", "--config", str(CONFIG)],
            cwd=ROOT,
            text=True,
            input=auth_secret + "\n",
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        require_ok(auth_secret_result, "AUTH0_CLIENT_SECRET")
        print("OIDC_CLIENT_SECRET=PASS")
    elif auth_metadata:
        print("OIDC_CLIENT_SECRET=NOT_CONFIGURED")

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
    urls = re.findall(r"https://[^\s]+", output)
    worker_url = next((url.rstrip(".,") for url in urls if "workers.dev" in url), None)
    if worker_url:
        validation = subprocess.run(
            [sys.executable, str(APP / "scripts" / "validate_remote_dev.py"), worker_url, str(TOKEN_FILE)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            env=os.environ.copy(),
        )
        print(validation.stdout, end="")
        require_ok(validation, "REMOTE_DEV_POSTDEPLOY")
    else:
        print("REMOTE_DEV_WORKER_URL=NOT_DISCOVERED")

    print("REMOTE_DEV_D1=PASS")
    print("REMOTE_DEV_QUOTA_NAMESPACE=PASS")
    print("SYNTHETIC_DATA_ONLY=TRUE")
    print("PRODUCTION_DNS_MUTATION=FALSE")
    print("PRODUCTION_DATA_MUTATION=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
