#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
MODULE = (APP / "src" / "security-rate-limit.mjs").read_text(encoding="utf-8")
STRICT = (APP / "src" / "security-rate-limit-do.mjs").read_text(encoding="utf-8")

EXPECTED = {
    "RATE_LIMIT_LOGIN": 30,
    "RATE_LIMIT_DEVICE_ENROLL_CLIENT": 60,
    "RATE_LIMIT_DEVICE_ENROLL_TOKEN": 10,
    "RATE_LIMIT_PORTAL_MUTATION": 60,
    "RATE_LIMIT_MCP_AUTH_FAILURE": 20,
}

def load_config(name):
    return json.loads((APP / name).read_text(encoding="utf-8"))

def binding_map(config):
    return {item["name"]: item for item in config.get("ratelimits", [])}

def do_binding_map(config):
    return {item["name"]: item for item in config.get("durable_objects", {}).get("bindings", [])}

def need(condition, label):
    if not condition:
        raise AssertionError(label)

prod = load_config("wrangler.jsonc")
dev = load_config("wrangler.dev.jsonc")
prod_bindings = binding_map(prod)
dev_bindings = binding_map(dev)

need(set(prod_bindings) == set(EXPECTED), "PROD_RATE_LIMIT_BINDINGS")
need(set(dev_bindings) == set(EXPECTED), "DEV_RATE_LIMIT_BINDINGS")
for name, limit in EXPECTED.items():
    for env_name, bindings in (("PROD", prod_bindings), ("DEV", dev_bindings)):
        binding = bindings[name]
        need(binding["simple"]["limit"] == limit, f"{env_name}_{name}_LIMIT")
        need(binding["simple"]["period"] == 60, f"{env_name}_{name}_PERIOD")
        need(str(binding["namespace_id"]).isdigit(), f"{env_name}_{name}_NAMESPACE")

prod_namespaces = {item["namespace_id"] for item in prod_bindings.values()}
dev_namespaces = {item["namespace_id"] for item in dev_bindings.values()}
need(prod_namespaces.isdisjoint(dev_namespaces), "DEV_PROD_RATE_LIMIT_NAMESPACE_ISOLATION")

for env_name, cfg in (("PROD", prod), ("DEV", dev)):
    strict_binding = do_binding_map(cfg).get("STRICT_RATE_LIMIT")
    need(strict_binding is not None, f"{env_name}_STRICT_DO_BINDING")
    need(strict_binding["class_name"] == "SecurityRateLimit", f"{env_name}_STRICT_DO_CLASS")
    migrations = cfg.get("migrations", [])
    need(any("SecurityRateLimit" in item.get("new_sqlite_classes", []) for item in migrations),
         f"{env_name}_STRICT_DO_MIGRATION")

need('import { SecurityRateLimit } from "./security-rate-limit-do.mjs";' in WORKER,
     "STRICT_DO_IMPORT")
need('export { DeviceChannel };' in WORKER, "DEVICE_CHANNEL_EXPORT_PRESERVED")
need('export { SecurityRateLimit };' in WORKER, "STRICT_DO_EXPORT")
need(WORKER.count("await enforceLayeredRateLimit(") == 6, "LAYERED_GUARD_COUNT")
need("env.STRICT_RATE_LIMIT" in WORKER, "STRICT_DO_ROUTE_BINDING")
need("enforceRateLimit(" not in WORKER, "NO_FAST_ONLY_WORKER_GUARD")

need('AUTH_RATE_LIMITED: 429' in WORKER, "AUTH_RATE_LIMIT_429")
need('DEVICE_ENROLL_RATE_LIMITED: 429' in WORKER, "ENROLL_RATE_LIMIT_429")
need('PORTAL_MUTATION_RATE_LIMITED: 429' in WORKER, "PORTAL_RATE_LIMIT_429")
need('MCP_AUTH_RATE_LIMITED: 429' in WORKER, "MCP_RATE_LIMIT_429")
need('STRICT_RATE_LIMIT_BINDING_MISSING: 503' in WORKER, "STRICT_BINDING_FAIL_CLOSED")
need('STRICT_RATE_LIMIT_CHECK_FAILED: 503' in WORKER, "STRICT_CHECK_FAIL_CLOSED")
need('response.headers.set("retry-after", "60")' in WORKER, "RETRY_AFTER")

need('crypto.subtle.digest("SHA-256"' in MODULE, "RATE_LIMIT_KEY_HASHING")
need('cf-connecting-ip' in MODULE, "CLIENT_IP_SOURCE")
need('x-forwarded-for' not in MODULE.lower(), "NO_SPOOFABLE_XFF_FALLBACK")
need('fixedWindowDecision' in MODULE, "FIXED_WINDOW_DECISION")
need('STRICT_RATE_LIMIT_BINDING_MISSING' in MODULE, "STRICT_MISSING_BINDING_FAIL_CLOSED")
need('STRICT_RATE_LIMIT_CHECK_FAILED' in MODULE, "STRICT_FAILURE_FAIL_CLOSED")

need('from "cloudflare:workers"' in STRICT, "STRICT_DO_BASE_IMPORT")
need('CREATE TABLE IF NOT EXISTS strict_rate_window' in STRICT, "STRICT_DO_SQL_TABLE")
need('SELECT window_start_ms, count FROM strict_rate_window' in STRICT, "STRICT_DO_READ")
need('ON CONFLICT(id) DO UPDATE SET' in STRICT, "STRICT_DO_ATOMIC_STATE")
need('fixedWindowDecision' in STRICT, "STRICT_DO_FIXED_WINDOW")

mcp = WORKER.split("async function requireMcpProductToken", 1)[1].split(
    "async function enforceLoginInitiationRateLimit", 1
)[0]
need(mcp.find("secretMatches") < mcp.find("RATE_LIMIT_MCP_AUTH_FAILURE"),
     "VALID_MCP_TOKEN_BEFORE_FAILURE_LIMIT")
need('rateLimitSecretKey("mcp-auth-failure-token", supplied)' in mcp,
     "MCP_SECRET_DIGEST_LIMIT")

need(prod["d1_databases"][0]["migrations_dir"] == "migrations", "PROD_D1_MIGRATIONS_DIR")
need(dev["d1_databases"][0]["migrations_dir"] == "migrations", "DEV_D1_MIGRATIONS_DIR")

print("COMMANDER_RATE_LIMIT_CONFIG=PASS")
print("COMMANDER_RATE_LIMIT_ROUTE_COVERAGE=PASS")
print("COMMANDER_RATE_LIMIT_KEY_PRIVACY=PASS")
print("COMMANDER_RATE_LIMIT_STRICT_DO_BINDING=PASS")
print("COMMANDER_RATE_LIMIT_FIXED_WINDOW_SOURCE=PASS")
print("COMMANDER_RATE_LIMIT_FAIL_CLOSED=PASS")
print("COMMANDER_RATE_LIMIT_NO_D1_MIGRATION=PASS")
