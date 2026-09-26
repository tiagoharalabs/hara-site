#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
MODULE = (APP / "src" / "security-rate-limit.mjs").read_text(encoding="utf-8")

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

need('await enforceLoginInitiationRateLimit(request, env);' in WORKER, "LOGIN_GUARD")
need('await enforceDeviceEnrollClientRateLimit(request, env);' in WORKER, "ENROLL_CLIENT_GUARD")
need('await enforceDeviceEnrollTokenRateLimit(body, env);' in WORKER, "ENROLL_TOKEN_GUARD")
need(WORKER.count('await enforcePortalMutationRateLimit(env, session);') == 3,
     "PORTAL_MUTATION_GUARDS")
need('await requireMcpProductToken(request, env);' in WORKER, "MCP_ASYNC_GUARD")
need('"AUTH_RATE_LIMITED": 429' not in WORKER, "STATUS_MAP_OBJECT_SYNTAX_EXPECTED")
need('AUTH_RATE_LIMITED: 429' in WORKER, "AUTH_RATE_LIMIT_429")
need('DEVICE_ENROLL_RATE_LIMITED: 429' in WORKER, "ENROLL_RATE_LIMIT_429")
need('PORTAL_MUTATION_RATE_LIMITED: 429' in WORKER, "PORTAL_RATE_LIMIT_429")
need('MCP_AUTH_RATE_LIMITED: 429' in WORKER, "MCP_RATE_LIMIT_429")
need('response.headers.set("retry-after", "60")' in WORKER, "RETRY_AFTER")

need('crypto.subtle.digest("SHA-256"' in MODULE, "RATE_LIMIT_KEY_HASHING")
need('cf-connecting-ip' in MODULE, "CLIENT_IP_SOURCE")
need('x-forwarded-for' not in MODULE.lower(), "NO_SPOOFABLE_XFF_FALLBACK")
need('RATE_LIMIT_BINDING_MISSING' in MODULE, "MISSING_BINDING_FAIL_CLOSED")
need('RATE_LIMIT_CHECK_FAILED' in MODULE, "LIMITER_FAILURE_FAIL_CLOSED")

mcp = WORKER.split("async function requireMcpProductToken", 1)[1].split(
    "async function enforceLoginInitiationRateLimit", 1
)[0]
need(mcp.find("secretMatches") < mcp.find("RATE_LIMIT_MCP_AUTH_FAILURE"),
     "VALID_MCP_TOKEN_BEFORE_FAILURE_LIMIT")
need('rateLimitSecretKey("mcp-auth-failure-token", supplied)' in mcp,
     "MCP_SECRET_DIGEST_LIMIT")

need([m["tag"] for m in prod.get("migrations", [])] == ["v1"],
     "PROD_MIGRATIONS_UNCHANGED")
need([m["tag"] for m in dev.get("migrations", [])] == ["v1", "v2"],
     "DEV_MIGRATIONS_UNCHANGED")

print("COMMANDER_RATE_LIMIT_CONFIG=PASS")
print("COMMANDER_RATE_LIMIT_ROUTE_COVERAGE=PASS")
print("COMMANDER_RATE_LIMIT_KEY_PRIVACY=PASS")
print("COMMANDER_RATE_LIMIT_FAIL_CLOSED=PASS")
print("COMMANDER_RATE_LIMIT_NO_D1_MIGRATION=PASS")
