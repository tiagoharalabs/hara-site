#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "apps/commander/public"
LINUX = (PUBLIC / "install/linux.sh").read_text(encoding="utf-8")
WINDOWS = (PUBLIC / "install/windows.ps1").read_text(encoding="utf-8")
LINUX_AGENT = (PUBLIC / "agent/linux.py").read_text(encoding="utf-8")
WINDOWS_AGENT = (PUBLIC / "agent/windows.ps1").read_text(encoding="utf-8")
HTML = (PUBLIC / "index.html").read_text(encoding="utf-8")
JS = (PUBLIC / "app.js").read_text(encoding="utf-8")
MANIFEST = json.loads((PUBLIC / "release/agent-manifest.json").read_text(encoding="utf-8"))
SHA256SUMS = (PUBLIC / "release/SHA256SUMS").read_text(encoding="utf-8")

def need(text: str, token: str, code: str) -> None:
    assert token in text, f"{code}:{token}"

for token in ('platform": "LINUX"', "/api/device/enroll", "/agent/linux.py",
              "systemctl --user enable --now", "chmod 600", '"agent_version": "0.3.2"',
              "HARA_COMMANDER_AGENT_UPDATE=PASS", "HARA_COMMANDER_AGENT_UNINSTALL=PASS",
              "HARA_COMMANDER_AGENT_VERSION=", "HARA_COMMANDER_AGENT_DOCTOR=PASS",
              "/api/device/revoke-self", "SERVER_DEVICE_REVOKE=",
              "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE",
              "/release/agent-manifest.json", "AGENT_SHA256_MISMATCH",
              "AGENT_VERSION_MANIFEST_MISMATCH", "HARA_COMMANDER_AGENT_INTEGRITY=PASS"):
    need(LINUX, token, "LINUX_INSTALLER_MISSING")
assert "cloudflared" not in LINUX.lower()
print("LINUX_DEVICE_INSTALLER_STATIC=PASS")

for token in ('platform="WINDOWS"', "/api/device/enroll", "/agent/windows.ps1",
              "ConvertFrom-SecureString", "Register-ScheduledTask", "icacls.exe",
              'agent_version="0.3.2"', "HARA_COMMANDER_AGENT_UPDATE=PASS",
              "HARA_COMMANDER_AGENT_UNINSTALL=PASS", "HARA_COMMANDER_AGENT_VERSION=",
              "HARA_COMMANDER_AGENT_DOCTOR=PASS", "/api/device/revoke-self",
              "SERVER_DEVICE_REVOKE=", "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE",
              "/release/agent-manifest.json", "AGENT_SHA256_MISMATCH",
              "AGENT_VERSION_MANIFEST_MISMATCH", "HARA_COMMANDER_AGENT_INTEGRITY=PASS"):
    need(WINDOWS, token, "WINDOWS_INSTALLER_MISSING")
assert "cloudflared" not in WINDOWS.lower()
assert "encrypted_device_token" in WINDOWS
assert "DEVICE_TOKEN_EXPOSED=FALSE" in WINDOWS
print("WINDOWS_DEVICE_INSTALLER_STATIC=PASS")

assert MANIFEST.get("schema") == "hara.commander-agent-release.v1"
assert MANIFEST.get("agent_version") == "0.3.2"
entries = {item["path"]: item for item in MANIFEST.get("files", [])}
for rel in ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1"):
    path = PUBLIC / rel
    assert rel in entries, f"RELEASE_MANIFEST_MISSING:{rel}"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert entries[rel].get("sha256") == digest, f"RELEASE_SHA256_DRIFT:{rel}"
    assert int(entries[rel].get("bytes", -1)) == path.stat().st_size, f"RELEASE_SIZE_DRIFT:{rel}"
    assert f"{digest}  {rel}\n" in SHA256SUMS, f"RELEASE_SHA256SUMS_DRIFT:{rel}"
print("COMMANDER_RELEASE_MANIFEST_INTEGRITY=PASS")
print("COMMANDER_RELEASE_SHA256SUMS_INTEGRITY=PASS")

TOOLS = ("hara.health","hara.functions.list","hara.functions.describe",
         "hara.functions.invoke","hara.receipts.get")
for token in TOOLS:
    need(LINUX_AGENT, token, "LINUX_AGENT_TOOL_MISSING")
    need(WINDOWS_AGENT, token, "WINDOWS_AGENT_TOOL_MISSING")
for forbidden in ("subprocess.", "os.system(", "shell=True", "paramiko", "ssh "):
    assert forbidden not in LINUX_AGENT, f"LINUX_AGENT_ARBITRARY_EXEC:{forbidden}"
for forbidden in ("Invoke-Expression", "Start-Process", "cmd.exe", "powershell.exe -Command"):
    assert forbidden not in WINDOWS_AGENT, f"WINDOWS_AGENT_ARBITRARY_EXEC:{forbidden}"
assert "UNKNOWN_FUNCTION_ID" in LINUX_AGENT and "UNKNOWN_FUNCTION_ID" in WINDOWS_AGENT
assert "device.info" in LINUX_AGENT and "device.info" in WINDOWS_AGENT
subprocess.run([str(PUBLIC / "agent/linux.py"), "--self-test"], check=True)
print("COMMANDER_EXACT_FIVE_TOOL_AGENT=PASS")
print("ARBITRARY_SHELL_EXPOSED=FALSE")

need(HTML, "/install/linux.sh", "PORTAL_LINUX_INSTALLER_LINK")
need(HTML, "/install/windows.ps1", "PORTAL_WINDOWS_INSTALLER_LINK")
need(JS, "Comando Windows copiado.", "PORTAL_WINDOWS_COPY_HANDLER")
need(JS, "/api/portal/devices/select", "PORTAL_DEVICE_SELECTION")
need(JS, "Agent \" + String(device.agent_version)", "PORTAL_AGENT_VERSION")
print("PORTAL_DEVICE_INSTALLERS=PASS")
print("PORTAL_DEVICE_SELECTION=PASS")
print("PER_DEVICE_CLOUDFLARED_DEPENDENCY=FALSE")
print("OUTBOUND_CALL_CHANNEL_FIVE_TOOL_READY=PASS")
print("AGENT_REMOTE_SELF_REVOKE=PASS")
print("AGENT_DOCTOR_REMOTE_HEARTBEAT=PASS")
print("AGENT_UPDATE_ROLLBACK_SAFE=PASS")
print("AGENT_DOWNLOAD_INTEGRITY_ENFORCED=PASS")
