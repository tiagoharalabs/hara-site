#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
DEV_PATH = APP / "wrangler.dev.jsonc"
PROD_PATH = APP / "wrangler.jsonc"

dev = json.loads(DEV_PATH.read_text(encoding="utf-8"))
prod = json.loads(PROD_PATH.read_text(encoding="utf-8"))

def need(value, code):
    if not value:
        raise AssertionError(code)

need(dev["name"] == "hara-commander-dev-v2", "DEV_WORKER_NAME")
need(dev["main"] == "src/worker.js", "DEV_MAIN")
need(dev["compatibility_date"] == prod["compatibility_date"], "DEV_COMPAT_DATE")
need(dev.get("workers_dev") is True, "DEV_WORKERS_DEV_REQUIRED")
need(dev.get("preview_urls") is False, "DEV_PREVIEW_URLS_DISABLED")
need("routes" not in dev, "DEV_ROUTES_MUST_BE_ABSENT")

need(dev["assets"] == prod["assets"], "DEV_ASSET_CONTRACT_DRIFT")

vars_ = dev["vars"]
need(vars_["ENVIRONMENT"] == "DEV", "DEV_ENVIRONMENT")
need(vars_["STORAGE_MODE"] == "REMOTE_DEV", "DEV_STORAGE_MODE")
for key in (
    "MCP_BASE_URL",
    "MCP_ACCESS_ISSUER",
    "AUTH_ISSUER",
    "AUTH_CLIENT_ID",
    "AUTH_PROVIDER_LABEL",
    "AUTH_CLIENT_AUTH",
):
    need(vars_.get(key) == prod["vars"].get(key), f"DEV_SHARED_VAR_{key}")

d1 = dev["d1_databases"]
need(len(d1) == 1, "DEV_D1_COUNT")
d1 = d1[0]
need(d1["binding"] == "PRODUCT_DB", "DEV_D1_BINDING")
need(d1["database_name"] == "hara-commander-product-dev", "DEV_D1_NAME")
need(d1["database_id"] == "698afbb9-e4eb-4c4e-98f2-f5abe28219d3", "DEV_D1_ID")
need(d1["database_id"] != prod["d1_databases"][0]["database_id"], "DEV_D1_NOT_PROD")
need(d1["database_name"] != prod["d1_databases"][0]["database_name"], "DEV_D1_NAME_NOT_PROD")
need(d1["migrations_dir"] == "migrations", "DEV_D1_MIGRATIONS")

do_bindings = dev["durable_objects"]["bindings"]
need(do_bindings == [{"name": "TENANT_QUOTA", "class_name": "TenantQuota"}], "DEV_DO_BINDING")
need(dev["migrations"] == prod["migrations"], "DEV_DO_MIGRATION_CONTRACT")

raw = DEV_PATH.read_text(encoding="utf-8")
for secret in ("AUTH_CLIENT_SECRET", "DEV_ACCESS_TOKEN", "MCP_PRODUCT_TOKEN"):
    need(secret not in raw, f"DEV_SECRET_MUST_NOT_BE_CONFIGURED:{secret}")

for prod_marker in (
    "hara-commander-product-prod",
    "2c6473ff-9f65-4ee3-b9aa-a68996d47c46",
    "commander.haralabs.com.br",
    '"ENVIRONMENT": "PROD"',
    '"STORAGE_MODE": "REMOTE_PROD"',
):
    need(prod_marker not in raw, f"DEV_PROD_MARKER_PRESENT:{prod_marker}")

print("COMMANDER_DEV_CONFIG_NAME=PASS")
print("COMMANDER_DEV_CONFIG_ENVIRONMENT=DEV")
print("COMMANDER_DEV_CONFIG_STORAGE=REMOTE_DEV")
print("COMMANDER_DEV_CONFIG_D1=DEV_ONLY")
print("COMMANDER_DEV_CONFIG_ROUTES=ABSENT")
print("COMMANDER_DEV_CONFIG_SECRETS=EXTERNAL")
print("COMMANDER_DEV_CONFIG=PASS")
