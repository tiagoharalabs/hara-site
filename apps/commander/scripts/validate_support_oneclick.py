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
HTML = (APP / "public" / "index.html").read_text(encoding="utf-8")
HEADERS = (APP / "public" / "_headers").read_text(encoding="utf-8")
WORKER = (APP / "src" / "worker.js").read_text(encoding="utf-8")
AGENT_SOURCE = AGENT.read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SUPPORT_ONECLICK_{code}=FAIL")
    print(f"COMMANDER_SUPPORT_ONECLICK_{code}=PASS")


need("def build_support_report():" in AGENT_SOURCE, "AGENT_BUILDER")
need('parsed.path=="/v1/support"' in AGENT_SOURCE, "LOOPBACK_ROUTE")
need('self._json(200,build_support_report())' in AGENT_SOURCE, "LOOPBACK_SANITIZED_REPORT")
need('data-submit-local-support' in HTML, "PORTAL_BUTTON")
need('id="supportReportStatus"' in HTML, "PORTAL_STATUS")
need("function supportReportPrivacySafe" in PORTAL, "CLIENT_PRIVACY_GATE")
need("async function fetchLocalSupportReport" in PORTAL, "LOCAL_FETCH")
need('LOCAL_ACTIVITY_ORIGIN + "/v1/support"' in PORTAL, "LOCAL_ROUTE")
need('targetAddressSpace:"loopback"' in PORTAL, "LOOPBACK_ADDRESS_SPACE")
need('credentials:"omit"' in PORTAL, "LOCAL_CREDENTIALS_OMIT")
need('["OWNER","ADMIN"].includes' in PORTAL, "ADMIN_UI_GATE")
need('fetch("/api/portal/support-reports"' in PORTAL, "CLOUD_SUBMIT")
need('credentials:"same-origin"' in PORTAL, "CLOUD_SESSION_AUTH")
need('handlePortalAuthFailure(response' in PORTAL, "AUTHORITY_PRESERVED")
need("supportReportPrivacySafe(payload)" in PORTAL, "REPORT_PRIVACY_PRECHECK")
need('"SUPPORT_REPORT_PRIVACY_INVALID"' in WORKER, "SERVER_PRIVACY_RESANITIZE")
need("cleanSupportReportV2(body)" in WORKER, "SERVER_ALLOWLIST_SANITIZER")
need("connect-src 'self' http://127.0.0.1:32145" in HEADERS, "CSP_LOOPBACK_ONLY")

ns = runpy.run_path(str(AGENT))
with tempfile.TemporaryDirectory(prefix="hara-support-oneclick-") as td:
    root = Path(td)
    cfg_dir = root / "config" / "hara-commander"
    data_dir = root / "data" / "hara-commander"
    cfg_dir.mkdir(parents=True)
    data_dir.mkdir(parents=True)
    sentinel = "DO_NOT_EXPOSE_SUPPORT_ONECLICK_TOKEN"
    cfg_file = cfg_dir / "device.env"
    cfg_file.write_text(
        "HARA_COMMANDER_URL=https://commander.haralabs.com.br\n"
        "HARA_DEVICE_ID=HARA-ONECLICK-DEVICE\n"
        f"HARA_DEVICE_TOKEN={sentinel}\n"
        "HARA_DEVICE_ARCH=x86_64\n"
        "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n",
        encoding="utf-8",
    )

    globals_map = ns["start_local_portal_server"].__globals__
    globals_map["CONFIG_FILE"] = cfg_file
    globals_map["DATA_DIR"] = data_dir
    globals_map["OPERATIONS_DB_FILE"] = data_dir / "operations.sqlite3"
    globals_map["CONSOLE_EVENTS_FILE"] = data_dir / "console-events.jsonl"
    globals_map["STATUS_FILE"] = data_dir / "runtime-status.json"
    globals_map["SESSION_FILE"] = data_dir / "operator-session.json"
    globals_map["RECEIPT_DIR"] = data_dir / "receipts"
    globals_map["LOCAL_PORTAL_PORT"] = 0

    config = {
        "HARA_COMMANDER_URL": "https://commander.haralabs.com.br",
        "HARA_DEVICE_ID": "HARA-ONECLICK-DEVICE",
        "HARA_DEVICE_TOKEN": sentinel,
        "HARA_DEVICE_ARCH": "x86_64",
        "HARA_COMMANDER_APPROVAL_MODE": "PERSISTENT_TRUSTED",
    }
    server = ns["start_local_portal_server"](config)
    need(server is not None, "DYNAMIC_SERVER_START")
    try:
        port = int(server.server_address[1])
        url = f"http://127.0.0.1:{port}/v1/support"
        req = urllib.request.Request(
            url,
            headers={"Origin": "https://commander.haralabs.com.br"},
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw)
            allow_origin = response.headers.get("Access-Control-Allow-Origin")
            pna = response.headers.get("Access-Control-Allow-Private-Network")
        need(response.status == 200, "DYNAMIC_HTTP")
        need(payload.get("schema") == "hara.commander-support-report.v2", "DYNAMIC_SCHEMA")
        need(payload.get("device_id") == "HARA-ONECLICK-DEVICE", "DYNAMIC_DEVICE")
        privacy = payload.get("privacy") or {}
        need(all(privacy.get(key) is False for key in (
            "secret_material_exposed",
            "customer_content_included",
            "command_content_included",
            "payload_content_included",
            "result_content_included",
        )), "DYNAMIC_PRIVACY")
        need(sentinel not in raw, "DYNAMIC_TOKEN_ABSENT")
        need(allow_origin == "https://commander.haralabs.com.br", "DYNAMIC_CORS")
        need(pna == "true", "DYNAMIC_PNA")

        bad = urllib.request.Request(
            url,
            headers={"Origin": "https://evil.example"},
        )
        try:
            urllib.request.urlopen(bad, timeout=3)
        except urllib.error.HTTPError as exc:
            body = json.loads(exc.read().decode("utf-8"))
            need(exc.code == 403 and body.get("code") == "LOCAL_ORIGIN_DENIED", "DYNAMIC_EVIL_ORIGIN_DENIED")
        else:
            raise SystemExit("COMMANDER_SUPPORT_ONECLICK_DYNAMIC_EVIL_ORIGIN_DENIED=FAIL")
    finally:
        server.shutdown()
        server.server_close()

print("COMMANDER_SUPPORT_ONECLICK=PASS")
