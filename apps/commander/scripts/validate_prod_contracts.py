#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")

portal = WORKER.split(
    "async function dashboardForSubject", 1
)[1].split("async function grantsForPlan", 1)[0]

assert 'schema: "hara.commander-portal-dashboard.v1"' in portal
assert "portal-dashboard-dev.v1" not in portal
assert "DEVICE_PAIRING_CREATE_FAILED: 503" in WORKER

print("COMMANDER_PROD_PORTAL_SCHEMA=CANONICAL_V1")
print("COMMANDER_PROD_PORTAL_DEV_SCHEMA=ABSENT")
print("COMMANDER_PAIRING_CREATE_FAILURE_HTTP_503=PASS")
