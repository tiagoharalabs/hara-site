#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = (ROOT / "src" / "auth.js").read_text()
OIDC = (ROOT / "src" / "oidc.js").read_text()
WORKER = (ROOT / "src" / "worker.js").read_text()
PROD = (ROOT / "wrangler.jsonc").read_text()
DEV = (ROOT / "wrangler.dev.jsonc").read_text()

assert "const SESSION_TOUCH_SECONDS = 30 * 60;" in AUTH
assert "export async function runAuthRetentionMaintenance(env)" in AUTH
begin = AUTH.split("export async function beginLogin", 1)[1].split("async function ensurePrimaryIdentityBinding", 1)[0]
assert "await cleanupExpiredOidcTransactions(env)" not in begin
assert "await cleanupTerminalPortalSessions(env)" not in begin

assert "const OIDC_PUBLIC_CACHE_TTL_MS = 5 * 60 * 1000;" in OIDC
assert "cacheGet(discoveryCache" in OIDC
assert "cacheGet(jwksCache" in OIDC
assert "forceRefresh: true" in OIDC
assert "OIDC_SIGNING_KEY_NOT_FOUND" in OIDC

assert "runAuthRetentionMaintenance" in WORKER
assert "async scheduled(_event, env, ctx)" in WORKER
assert "ctx.waitUntil(runAuthRetentionMaintenance(env));" in WORKER

for config in (PROD, DEV):
    assert '"triggers"' in config
    assert '"17 * * * *"' in config

print("COMMANDER_HUMAN_SCALE_V2_SOURCE=PASS")
