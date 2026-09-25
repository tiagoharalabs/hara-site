#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKER = (ROOT / "src" / "worker.js").read_text()
APP = (ROOT / "public" / "app.js").read_text()

assert '"/api/portal/bootstrap"' in WORKER
block = WORKER.split('if (url.pathname === "/api/portal/bootstrap"', 1)[1].split(
    'if (url.pathname === "/api/portal/dashboard"', 1
)[0]
assert block.count("resolvePortalSession(request, env)") == 1
assert "Promise.all([" in block
assert "dashboardForSubject(env, session.subject_id, session.tenant_id)" in block
assert "listDevices(env, session)" in block
assert '"hara.commander-portal-bootstrap.v1"' in block
assert "ENTITLEMENT_NOT_FOUND" in block

assert 'fetch("/api/portal/bootstrap"' in APP
assert "loadPortalBootstrap" in APP
assert "renderDevices(payload.device_state)" in APP
assert "skipNextWorkspaceLoad" in APP
assert "Bootstrap is an optimization only" in APP

for path in (
    "/api/portal/session",
    "/api/portal/dashboard",
    "/api/portal/devices",
):
    assert path in WORKER

print("COMMANDER_HUMAN_BOOTSTRAP_SINGLE_AUTH=PASS")
print("COMMANDER_HUMAN_BOOTSTRAP_FALLBACK=PASS")
