#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
AGENT = APP / "public" / "agent" / "linux.py"
LINUX_INSTALLER = (APP / "public" / "install" / "linux.sh").read_text(encoding="utf-8")
SOURCE = AGENT.read_text(encoding="utf-8")


def need(ok: bool, code: str) -> None:
    if not ok:
        raise SystemExit(f"COMMANDER_SUPPORT_V2_{code}=FAIL")
    print(f"COMMANDER_SUPPORT_V2_{code}=PASS")


need('"schema":"hara.commander-support-report.v2"' in SOURCE, "SCHEMA")
need('"activity_24h"' in SOURCE and '"slo"' in SOURCE, "SLO_SUMMARY")
need('"product_lease"' in SOURCE and '"local_budget"' in SOURCE, "PRODUCT_STATE")
need('"recent_receipt_sha256"' in SOURCE, "RECEIPT_HASHES")
need('"command_content_included":False' in SOURCE, "NO_COMMAND_CONTENT")
need('"payload_content_included":False' in SOURCE, "NO_PAYLOAD_CONTENT")
need('"result_content_included":False' in SOURCE, "NO_RESULT_CONTENT")
need('if python3 "$AGENT" support; then' in LINUX_INSTALLER, "INSTALLER_PREFERS_AGENT_V2")

with tempfile.TemporaryDirectory(prefix="hara-support-v2-") as td:
    root = Path(td)
    config_home = root / "config"
    data_home = root / "data"
    cfg_dir = config_home / "hara-commander"
    cfg_dir.mkdir(parents=True)
    data_home.mkdir()
    sentinel = "DO_NOT_EXPOSE_TEST_TOKEN_1234567890"
    (cfg_dir / "device.env").write_text(
        "HARA_COMMANDER_URL=https://commander.haralabs.com.br\n"
        "HARA_DEVICE_ID=HARA-SUPPORT-TEST\n"
        f"HARA_DEVICE_TOKEN={sentinel}\n"
        "HARA_DEVICE_ARCH=x86_64\n"
        "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n",
        encoding="utf-8",
    )
    os.chmod(cfg_dir / "device.env", 0o600)
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_home)
    env["XDG_DATA_HOME"] = str(data_home)
    proc = subprocess.run(
        ["python3", str(AGENT), "support"],
        cwd=ROOT, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=20, check=False,
    )
    need(proc.returncode == 0, "DYNAMIC_EXIT")
    payload = json.loads(proc.stdout.strip())
    rendered = json.dumps(payload, sort_keys=True)
    need(payload.get("schema") == "hara.commander-support-report.v2", "DYNAMIC_SCHEMA")
    need(payload.get("device_id") == "HARA-SUPPORT-TEST", "DYNAMIC_DEVICE")
    need((payload.get("activity_24h") or {}).get("slo", {}).get("status") == "INSUFFICIENT_DATA", "DYNAMIC_SLO")
    privacy = payload.get("privacy") or {}
    need(privacy.get("secret_material_exposed") is False, "DYNAMIC_SECRET_FLAG")
    need(privacy.get("customer_content_included") is False, "DYNAMIC_CONTENT_FLAG")
    need(sentinel not in rendered, "DYNAMIC_TOKEN_ABSENT")
    for forbidden in ("payload_json", "result_json", '"command":', "stdout", "stderr"):
        need(forbidden not in rendered.lower(), "DYNAMIC_FORBIDDEN_" + forbidden.upper().replace('"', "").replace(":", ""))

print("COMMANDER_SUPPORT_BUNDLE_V2=PASS")
