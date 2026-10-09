#!/usr/bin/env python3
"""Offline regression for Linux tunnel manual/auto startup and portal installer UI."""
from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
AGENT = APP / "public/agent/linux.py"
LINUX_INSTALLER = (APP / "public/install/linux.sh").read_text(encoding="utf-8")
HTML = (APP / "public/index.html").read_text(encoding="utf-8")
JS = (APP / "public/app.js").read_text(encoding="utf-8")
SOURCE = AGENT.read_text(encoding="utf-8")

def need(condition, name):
    if not condition:
        raise AssertionError(f"COMMANDER_LINUX_TUNNEL_START_MODES_{name}=FAIL")
    print(f"COMMANDER_LINUX_TUNNEL_START_MODES_{name}=PASS")

need('data-tunnel-autostart' in HTML, "PORTAL_CHECKBOX_PRESENT")
need('data-tunnel-autostart-container' in HTML, "PORTAL_LINUX_ONLY_CHOICE")
need('data-copy-tunnel-start' in HTML and 'data-copy-tunnel-autostart' in HTML, "PORTAL_EXISTING_MACHINE_COMMANDS")
need('HARA_COMMANDER_TUNNEL_AUTOSTART=' in JS, "PORTAL_PROPAGATES_LINUX_INSTALL_CHOICE")
need('setInstallTunnelAutostart(event.target.checked)' in JS, "PORTAL_CHOICE_UPDATES_COMMAND")
need('hara-commander tunnel start' in HTML and 'hara-commander tunnel stop' in HTML, "PORTAL_MANUAL_STEPS")
need('HARA_COMMANDER_TUNNEL_AUTOSTART=$TUNNEL_AUTOSTART' in LINUX_INSTALLER, "INSTALLER_PERSISTS_CHOICE")
need('TUNNEL_AUTOSTART="$(resolve_tunnel_autostart)"' in LINUX_INSTALLER, "INSTALLER_VALIDATES_CHOICE")

# Exercise the Bash resolver in isolation. No enrollment, device token or network.
resolver = LINUX_INSTALLER.split("resolve_tunnel_autostart() {",1)[1].split("\n}\n",1)[0]
shell = "CONFIG_FILE=/does-not-exist; TUNNEL_AUTOSTART_RAW=\"$1\"; resolve_tunnel_autostart() {" + resolver + "\n}\nresolve_tunnel_autostart"
for value, expected in [("", "OFF"), ("OFF","OFF"), ("false","OFF"), ("0","OFF"),
                        ("ON","ON"), ("true","ON"), ("1","ON")]:
    result = subprocess.run(["bash","-c",shell,"--",value],text=True,capture_output=True,timeout=3)
    need(result.returncode==0 and result.stdout.strip()==expected, "INSTALLER_SHELL_"+(value or "DEFAULT").upper())
bad = subprocess.run(["bash","-c",shell,"--","INVALID"],text=True,capture_output=True,timeout=3)
need(bad.returncode==64 and "OPENAI_TUNNEL_AUTOSTART_INVALID" in bad.stderr, "INSTALLER_REJECTS_INVALID_CHOICE")

ns = {"__name__":"hara_tunnel_start_modes_test","__file__":str(AGENT)}
exec(compile(SOURCE,str(AGENT),"exec"),ns)

with tempfile.TemporaryDirectory(prefix="hara-tunnel-start-modes-") as directory:
    temp = Path(directory)
    cdir = temp / "config"
    data = temp / "data"
    device_dir = cdir / "hara-commander"
    device_dir.mkdir(parents=True)
    data.mkdir()
    cfg = device_dir / "device.env"
    cfg.write_text(
        "HARA_COMMANDER_URL=https://example.invalid\n"
        "HARA_DEVICE_ID=HARA-DEVICE-TEST\n"
        "HARA_DEVICE_TOKEN=NOT_A_CUSTOMER_TOKEN\n"
        "HARA_DEVICE_ARCH=x86_64\n"
        "HARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n"
        "HARA_COMMANDER_TRANSPORT_MODE=LOCAL_TUNNEL\n",
        encoding="utf-8",
    )
    cfg.chmod(0o600)
    ns["CONFIG_FILE"]=cfg
    ns["DATA_DIR"]=data
    ns["RECEIPT_DIR"]=data/"receipts"
    ns["CONSOLE_EVENTS_FILE"]=data/"console-events.jsonl"
    ns["OPERATIONS_DB_FILE"]=data/"operations.sqlite3"
    ns["TUNNEL_ENV_FILE"]=device_dir/"openai-tunnel.env"
    ns["TUNNEL_UNIT_FILE"]=cdir/"systemd/user/hara-commander-openai-tunnel.service"
    ns["TUNNEL_PROFILE_FILE"]=cdir/"tunnel-client/hara-commander.yaml"

    need(ns["tunnel_autostart_mode"]()=="OFF", "DEFAULT_IS_MANUAL")
    with contextlib.redirect_stdout(io.StringIO()):
        result=ns["tunnel_start"]()
    need(result==12 and not ns["TUNNEL_UNIT_FILE"].exists(), "NO_UNCONFIGURED_START")
    with contextlib.redirect_stdout(io.StringIO()):
        ns["set_tunnel_autostart"]("on")
    need(ns["tunnel_autostart_mode"]()=="ON" and not ns["TUNNEL_UNIT_FILE"].exists(), "AUTOSTART_PENDING_CONFIG_NOT_STARTED")

    fake_binary=data/"tunnel-client"
    fake_binary.write_text("#!/bin/sh\nexit 0\n",encoding="utf-8")
    fake_binary.chmod(0o700)
    ns["input"]=lambda _prompt="":"tunnel_0123456789abcdef0123456789abcdef"
    ns["getpass"].getpass=lambda _prompt="":"sk-runtime-TEST-0123456789abcdef0123456789abcdef"
    calls=[]
    def fake_run(argv,**kwargs):
        calls.append(list(argv))
        if len(argv)>1 and argv[1]=="init":
            profile=ns["TUNNEL_PROFILE_FILE"]
            profile.parent.mkdir(parents=True,exist_ok=True)
            profile.write_text('tunnel_id: "tunnel_0123456789abcdef0123456789abcdef"\n',encoding="utf-8")
            profile.chmod(0o600)
        return SimpleNamespace(returncode=0,stdout="",stderr="")
    # Deliberately only in this isolated script/test process, never on the actual hosts.
    ns["subprocess"].run=fake_run
    output=io.StringIO()
    with contextlib.redirect_stdout(output):
        rc=ns["configure_openai_tunnel"]()
    need(rc==0 and "HARA_COMMANDER_TUNNEL_AUTOSTART=PENDING_LOCAL_AUTHORIZATION" in output.getvalue(), "CONFIGURE_WAITS_FOR_LOCAL_LEASE")
    need(not any("enable" in c for c in calls), "NO_START_BEFORE_LEASE")
    need(not any(c[1:3]==["--user","restart"] for c in calls), "NO_AGENT_RESTART_BEFORE_AUTH")
    need(ns["TUNNEL_UNIT_FILE"].exists(), "SYSTEMD_UNIT_CREATED")
    need(stat.S_IMODE(ns["TUNNEL_ENV_FILE"].stat().st_mode)==0o600, "RUNTIME_KEY_PERMISSIONS")
    need(stat.S_IMODE(ns["TUNNEL_PROFILE_FILE"].stat().st_mode)==0o600, "TUNNEL_PROFILE_PRIVATE")
    need("sk-runtime-TEST" not in ns["TUNNEL_UNIT_FILE"].read_text(), "SYSTEMD_NO_CREDENTIALS")
    need("sk-runtime-TEST" not in str(calls), "ARGV_NO_CREDENTIALS")

    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["tunnel_start"]()
    need(rc==13 and not calls, "TUNNEL_START_MISSING_LEASE_DENIED")

    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["set_tunnel_autostart"]("on")
    need(rc==13 and not any("enable" in c for c in calls), "AUTOSTART_MISSING_LEASE_DENIED")

    # Once the six-hour signed local product lease is present, manual and
    # automatic start may proceed, but only after OpenAI doctor passes.
    ns["_tunnel_local_lease_active"]=lambda:True
    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["set_tunnel_autostart"]("off")
    need(rc==0 and ns["tunnel_autostart_mode"]()=="OFF", "EXISTING_MACHINE_AUTO_OFF")
    need(any(c[1:3]==["--user","disable"] for c in calls), "SYSTEMD_DISABLE")
    need(not any("stop" in c for c in calls), "DISABLE_DOES_NOT_KILL_ACTIVE_SESSION")

    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["tunnel_start"]()
    need(rc==0 and any(c[1:3]==["--user","start"] for c in calls), "MANUAL_START")
    need(not any("enable" in c for c in calls), "MANUAL_START_NO_ENABLE")
    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["tunnel_stop"]()
    need(rc==0 and any(c[1:3]==["--user","stop"] for c in calls), "MANUAL_STOP")
    need(ns["tunnel_autostart_mode"]()=="OFF", "MANUAL_STOP_PRESERVES_PREFERENCE")

    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["configure_openai_tunnel"]()
    need(rc==12 and not calls, "CONFIGURE_NEVER_OVERWRITES_EXISTING_KEY")

    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["set_tunnel_autostart"]("on")
    need(rc==0 and ns["tunnel_autostart_mode"]()=="ON", "EXISTING_MACHINE_AUTO_ON")
    need(any(c[1:4]==["--user","enable","--now"] for c in calls), "SYSTEMD_EXISTING_AUTO_ENABLE")

    # After successful manual reauthorization, configured auto mode can start.
    calls.clear()
    ns["getpass"].getpass=lambda _prompt="":"SIX_HOUR_AUTH_CODE"
    ns["refresh_product_lease"]=lambda *_a,**_k:{"product_lease":{"valid_until_utc":"2099-01-01T00:00:00Z"}}
    with contextlib.redirect_stdout(io.StringIO()):
        rc=ns["authorize_local_tunnel"]()
    need(rc==0 and any(c[1:4]==["--user","enable","--now"] for c in calls), "AUTHORIZATION_ACTIVATES_AUTO_TUNNEL")

    # OpenAI doctor failure cannot leave a runtime key or half-created profile.
    ns["TUNNEL_ENV_FILE"]=device_dir/"failed-setup/openai-tunnel.env"
    ns["TUNNEL_PROFILE_FILE"]=cdir/"failed-setup/hara-commander.yaml"
    ns["_openai_tunnel_doctor"]=lambda capture=False:(42,"unavailable")
    ns["getpass"].getpass=lambda _prompt="":"sk-runtime-TEST-0123456789abcdef0123456789abcdef"
    calls.clear()
    blocked=False
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            ns["configure_openai_tunnel"]()
        except RuntimeError as exc:
            blocked=str(exc)=="OPENAI_TUNNEL_DOCTOR_FAILED"
    need(blocked, "TUNNEL_DOCTOR_FAILURE_DENIED")
    need(not ns["TUNNEL_ENV_FILE"].exists() and not ns["TUNNEL_PROFILE_FILE"].exists(),
         "FAILED_SETUP_WIPES_KEY_AND_PROFILE")
    need(not any("enable" in c for c in calls), "FAILED_SETUP_NEVER_STARTS")

    # On/off cannot bypass the product lease; the actual MCP call is still gated.
    need("require_local_product_authority" in SOURCE, "PRODUCT_LEASE_GATE_RETAINED")
    need("PRODUCT_LEASE_REQUIRED" in SOURCE, "NO_LEASE_FAIL_CLOSED_RETAINED")

print("COMMANDER_LINUX_TUNNEL_START_MODES=PASS")
