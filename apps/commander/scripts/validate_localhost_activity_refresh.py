#!/usr/bin/env python3
from __future__ import annotations

import json
import runpy
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
AGENT = APP / "public" / "agent" / "linux.py"
PORTAL = (APP / "public" / "app.js").read_text(encoding="utf-8")
HEADERS = (APP / "public" / "_headers").read_text(encoding="utf-8")

def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_LOCALHOST_ACTIVITY_{code}=FAIL")
    print(f"COMMANDER_LOCALHOST_ACTIVITY_{code}=PASS")

source = AGENT.read_text(encoding="utf-8")
need('LOCAL_PORTAL_HOST = "127.0.0.1"' in source, "LOOPBACK_BIND")
need('"32145"' in source and "ThreadingHTTPServer" in source, "BOUNDED_SERVER")
need("0.0.0.0" not in source, "NO_WILDCARD_BIND")
need('parsed.path=="/v1/activity"' in source, "ACTIVITY_ROUTE")
need("local_activity_snapshot(window,limit=limit,include_events=True)" in source, "SQLITE_SOURCE")
need("Access-Control-Allow-Private-Network" in source, "PRIVATE_NETWORK_HEADER")
need("LOCAL_ORIGIN_DENIED" in source, "ORIGIN_FAIL_CLOSED")
need("HARA_DEVICE_TOKEN" not in source[source.index("class _LocalPortalHandler"):source.index("def append_console_event")], "TOKEN_NOT_EXPOSED")

need('const LOCAL_ACTIVITY_ORIGIN = "http://127.0.0.1:32145"' in PORTAL, "PORTAL_LOOPBACK_ORIGIN")
need("sessionAuthenticated" in PORTAL[PORTAL.index("async function loadUsageActivity"):PORTAL.index("async function loadServiceHealth")], "AUTHENTICATED_ONLY")
need('credentials:"omit"' in PORTAL, "LOCAL_CREDENTIALS_OMIT")
need('name:"loopback-network"' in PORTAL and 'state === "granted"' in PORTAL and 'state === "denied"' in PORTAL, "BROWSER_PERMISSION_GATE")
need('targetAddressSpace:"loopback"' in PORTAL, "TARGET_ADDRESS_SPACE")
need("explicitUserRefresh" in PORTAL and "Boolean(trigger)" in PORTAL, "PROMPT_ONLY_ON_USER_REFRESH")
need('credentials:"same-origin"' in PORTAL[PORTAL.index("async function loadUsageActivity"):PORTAL.index("async function loadServiceHealth")], "CLOUD_AUTH_PRESERVED")
need("handlePortalAuthFailure(response" in PORTAL, "CLOUD_AUTHORITY_PRESERVED")
need("mergeLocalActivityDetail" in PORTAL, "HYBRID_MERGE")
need("LOCAL_ACTIVITY_TIMEOUT_MS = 900" in PORTAL, "LOCAL_TIMEOUT")
need("activityCache.set" in PORTAL, "PORTAL_CACHE")
need("connect-src 'self' http://127.0.0.1:32145" in HEADERS, "CSP_EXACT_LOOPBACK")
need("upgrade-insecure-requests" not in HEADERS, "CSP_NO_HTTP_UPGRADE")

# Dynamic server proof on an ephemeral port with an isolated local DB.
ns = runpy.run_path(str(AGENT))
with tempfile.TemporaryDirectory(prefix="hara-localhost-activity-") as td:
    root = Path(td)
    globals_map = ns["start_local_portal_server"].__globals__
    globals_map["DATA_DIR"] = root
    globals_map["OPERATIONS_DB_FILE"] = root / "operations.sqlite3"
    globals_map["CONSOLE_EVENTS_FILE"] = root / "console-events.jsonl"
    globals_map["LOCAL_PORTAL_PORT"] = 0

    config = {
        "HARA_COMMANDER_URL": "https://commander.haralabs.com.br",
        "HARA_DEVICE_ID": "HARA-LOCALHOST-VALIDATOR",
    }
    server = ns["start_local_portal_server"](config)
    need(server is not None, "DYNAMIC_SERVER_START")
    try:
        port = int(server.server_address[1])
        base = f"http://127.0.0.1:{port}"

        req = urllib.request.Request(
            base + "/v1/activity?window=7d&limit=5",
            headers={"Origin": "https://commander.haralabs.com.br"},
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            allow_origin = response.headers.get("Access-Control-Allow-Origin")
            pna = response.headers.get("Access-Control-Allow-Private-Network")
        need(payload.get("schema") == "hara.commander-local-activity.v2", "DYNAMIC_SCHEMA")
        need(payload.get("source") == "LOCAL_SQLITE" and payload.get("local_direct") is True, "DYNAMIC_LOCAL_SOURCE")
        need(payload.get("device_id") == "HARA-LOCALHOST-VALIDATOR", "DYNAMIC_DEVICE_BINDING")
        need(allow_origin == "https://commander.haralabs.com.br", "DYNAMIC_CORS")
        need(pna == "true", "DYNAMIC_PNA")

        bad = urllib.request.Request(
            base + "/v1/activity",
            headers={"Origin": "https://evil.example"},
        )
        try:
            urllib.request.urlopen(bad, timeout=3)
        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8"))
            need(exc.code == 403 and body.get("code") == "LOCAL_ORIGIN_DENIED", "DYNAMIC_BAD_ORIGIN_DENIED")
        else:
            raise SystemExit("COMMANDER_LOCALHOST_ACTIVITY_DYNAMIC_BAD_ORIGIN_DENIED=FAIL")

        rendered = json.dumps(payload, sort_keys=True).lower()
        for forbidden in ("hara_device_token", "encrypted_device_token", "authorization", "payload_json", "result_json"):
            need(forbidden not in rendered, "DYNAMIC_SECRET_CONTENT_ABSENT_" + forbidden.upper())
    finally:
        server.shutdown()
        server.server_close()

print("COMMANDER_LOCALHOST_ACTIVITY_REFRESH=PASS")
