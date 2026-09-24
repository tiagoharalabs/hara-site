#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")

guard = WORKER.split(
    "function requirePortalMutationOrigin", 1
)[1].split("function cleanId", 1)[0]

assert 'request.headers.get("origin")' in guard
assert 'request.headers.get("sec-fetch-site")' in guard
assert 'origin !== expectedOrigin' in guard
assert 'fetchSite !== "same-origin"' in guard
assert 'throw new Error("PORTAL_ORIGIN_DENIED")' in guard
assert "PORTAL_ORIGIN_DENIED: 403" in WORKER

for route in (
    '"/auth/logout"',
    '"/api/portal/devices/pairing"',
    '"/api/portal/devices/revoke"',
    '"/api/portal/devices/select"',
):
    block = WORKER.split(f"url.pathname === {route}", 1)[1].split("}", 1)[0]
    assert "requirePortalMutationOrigin(request)" in block, f"ORIGIN_GUARD_MISSING:{route}"

for route in (
    '"/api/portal/session"',
    '"/api/portal/dashboard"',
    '"/api/portal/devices"',
):
    block = WORKER.split(f"url.pathname === {route}", 1)[1].split("}", 1)[0]
    assert "requirePortalMutationOrigin(request)" not in block, f"READ_ROUTE_GUARDED:{route}"

device_api = WORKER.split('url.pathname === "/api/device/enroll"', 1)[1]
assert "requirePortalMutationOrigin(request)" not in device_api.split(
    'url.pathname === "/api/internal/device/calls"', 1
)[0]

print("COMMANDER_PORTAL_MUTATION_ORIGIN_GUARD=PASS")
print("COMMANDER_PORTAL_CROSS_ORIGIN_MUTATION=DENIED_403")
print("COMMANDER_PORTAL_READ_ROUTES_ORIGIN_FREE=PASS")
print("COMMANDER_DEVICE_AGENT_API_ORIGIN_FREE=PASS")
