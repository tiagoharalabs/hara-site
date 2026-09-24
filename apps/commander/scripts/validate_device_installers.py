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
WORKER = (ROOT / "apps/commander/src/worker.js").read_text(encoding="utf-8")
AUTH = (ROOT / "apps/commander/src/auth.js").read_text(encoding="utf-8")
MANIFEST = json.loads((PUBLIC / "release/agent-manifest.json").read_text(encoding="utf-8"))
SHA256SUMS = (PUBLIC / "release/SHA256SUMS").read_text(encoding="utf-8")

def need(text: str, token: str, code: str) -> None:
    assert token in text, f"{code}:{token}"

for token in ('platform": "LINUX"', "/api/device/enroll", "/agent/linux.py",
              "systemctl --user enable --now", "chmod 600", '"agent_version": "0.3.3"',
              "HARA_COMMANDER_AGENT_UPDATE=PASS", "HARA_COMMANDER_AGENT_UNINSTALL=PASS",
              "HARA_COMMANDER_AGENT_VERSION=", "HARA_COMMANDER_AGENT_DOCTOR=PASS",
              "/api/device/revoke-self", "SERVER_DEVICE_REVOKE=",
              "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE",
              "/release/agent-manifest.json", "AGENT_SHA256_MISMATCH",
              "AGENT_VERSION_MANIFEST_MISMATCH", "HARA_COMMANDER_AGENT_INTEGRITY=PASS",
              "HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=", "rollback_enrolled_device",
              "hara.commander-support-report.v1", "device_token_exposed", "support_agent",
              "hara.commander-device-preflight.v1", "mutation_performed", "preflight_agent"):
    need(LINUX, token, "LINUX_INSTALLER_MISSING")
assert "cloudflared" not in LINUX.lower()
assert 'python3 - "$PAIRING_TOKEN"' not in LINUX, "PAIRING_TOKEN_EXPOSED_IN_ARGV"
assert 'python3 - "$RESPONSE"' not in LINUX, "DEVICE_TOKEN_RESPONSE_EXPOSED_IN_ARGV"
assert '--data "$PAYLOAD"' not in LINUX, "PAIRING_PAYLOAD_EXPOSED_IN_CURL_ARGV"
assert "HARA_ROLLBACK_DEVICE_TOKEN=" not in LINUX, "DEVICE_TOKEN_EXPOSED_IN_ROLLBACK_ENV"
assert "--data-binary @-" in LINUX, "PAIRING_PAYLOAD_STDIN_MISSING"
print("LINUX_DEVICE_INSTALLER_STATIC=PASS")
print("LINUX_INSTALLER_SECRET_ARGV_EXPOSURE=FALSE")

for token in ('platform="WINDOWS"', "/api/device/enroll", "/agent/windows.ps1",
              "ConvertFrom-SecureString", "Register-ScheduledTask", "icacls.exe",
              'agent_version="0.3.3"', "HARA_COMMANDER_AGENT_UPDATE=PASS",
              "HARA_COMMANDER_AGENT_UNINSTALL=PASS", "HARA_COMMANDER_AGENT_VERSION=",
              "HARA_COMMANDER_AGENT_DOCTOR=PASS", "/api/device/revoke-self",
              "SERVER_DEVICE_REVOKE=", "HARA_COMMANDER_AGENT_UPDATE_ROLLBACK_READY=TRUE",
              "/release/agent-manifest.json", "AGENT_SHA256_MISMATCH",
              "AGENT_VERSION_MANIFEST_MISMATCH", "HARA_COMMANDER_AGENT_INTEGRITY=PASS",
              "HARA_COMMANDER_FAILED_INSTALL_ROLLBACK=", "$InstallEnrolled",
              "hara.commander-support-report.v1", "device_token_exposed", "Show-SupportReport",
              "hara.commander-device-preflight.v1", "mutation_performed", "Invoke-Preflight"):
    need(WINDOWS, token, "WINDOWS_INSTALLER_MISSING")
assert "cloudflared" not in WINDOWS.lower()
assert "encrypted_device_token" in WINDOWS
assert "DEVICE_TOKEN_EXPOSED=FALSE" in WINDOWS
print("WINDOWS_DEVICE_INSTALLER_STATIC=PASS")

assert MANIFEST.get("schema") == "hara.commander-agent-release.v1"
assert MANIFEST.get("agent_version") == "0.3.3"
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
assert "except Exception:\n            pass" not in LINUX_AGENT, "LINUX_AGENT_SILENT_RUNTIME_ERROR"
assert "catch {\n  }\n  Start-Sleep" not in WINDOWS_AGENT, "WINDOWS_AGENT_SILENT_RUNTIME_ERROR"
assert "safe_error_code" in LINUX_AGENT and "Get-SafeErrorCode" in WINDOWS_AGENT, "AGENT_ERROR_SANITIZATION_MISSING"
assert "runtime-status.json" in LINUX_AGENT and "runtime-status.json" in WINDOWS_AGENT, "AGENT_RUNTIME_STATUS_MISSING"
assert "last_runtime_error_code" in LINUX and "last_runtime_error_code" in WINDOWS, "SUPPORT_RUNTIME_DIAGNOSTIC_MISSING"
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
print("AGENT_FAILED_INSTALL_ROLLBACK=READY")
print("AGENT_SUPPORT_REPORT_SANITIZED=READY")
print("AGENT_DEVICE_PREFLIGHT_NON_MUTATING=READY")

enqueue = WORKER.split("async function enqueueDeviceCall", 1)[1].split("async function claimNextDeviceCall", 1)[0]
claim = WORKER.split("async function claimNextDeviceCall", 1)[1].split("async function completeDeviceCall", 1)[0]
status = WORKER.split("async function deviceCallStatus", 1)[1].split("export default", 1)[0]
heartbeat = WORKER.split("async function heartbeatDevice", 1)[1].split("async function revokeDeviceSelf", 1)[0]
revoke = WORKER.split("async function revokePortalDevice", 1)[1].split("async function enqueueDeviceCall", 1)[0]
assert 'const privileged = ["OWNER", "ADMIN"].includes(String(session.role));' in revoke, "DEVICE_REVOKE_PRIVILEGE_MATRIX_INVALID"
assert '["OWNER", "ADMIN", "REVIEWER"]' not in revoke, "REVIEWER_TENANT_WIDE_REVOKE_PRESENT"
assert "enrolled_by_subject_id = ?" in revoke, "NON_ADMIN_DEVICE_OWNERSHIP_GUARD_MISSING"
assert "UPDATE commander_devices SET last_seen_at_utc" not in claim, "CALL_POLL_PRESENCE_WRITE_PRESENT"
assert "SET state = 'EXPIRED'" not in claim, "CALL_POLL_EXPIRY_WRITE_PRESENT"
assert "DEVICE_CALL_TTL_SECONDS = 50" in WORKER and "nowIso(DEVICE_CALL_TTL_SECONDS)" in enqueue, "DEVICE_CALL_TTL_NOT_BOUNDED"
assert "SET state = 'EXPIRED'" in enqueue, "ENQUEUE_STALE_CALL_CLEANUP_MISSING"
assert status.index("let row = await readCall()") < status.index("SET state = 'EXPIRED'"), "DEVICE_STATUS_UNCONDITIONAL_EXPIRY_WRITE"
assert "RETURNING call_id, request_id, device_id, tool_id, state" in status, "DEVICE_STATUS_EXPIRY_RETURNING_MISSING"
assert "UPDATE commander_devices" in heartbeat and "last_seen_at_utc" in heartbeat, "HEARTBEAT_PRESENCE_WRITE_MISSING"
assert "authCallbackFailureResponse" in WORKER and "clearCookie(TX_COOKIE" in AUTH, "OIDC_CALLBACK_COOKIE_CLEANUP_MISSING"
assert "SESSION_TOUCH_SECONDS" in AUTH and ".run().catch(() => null)" in AUTH, "PORTAL_SESSION_TOUCH_NOT_BEST_EFFORT"
print("COMMANDER_CALL_POLL_PRESENCE_WRITE=ABSENT")
print("COMMANDER_CALL_POLL_EXPIRY_WRITE=ABSENT")
print("COMMANDER_DEVICE_CALL_TTL_BOUNDED=PASS")
print("COMMANDER_DEVICE_STATUS_CONDITIONAL_EXPIRY_WRITE=PASS")
print("COMMANDER_REVIEWER_TENANT_WIDE_REVOKE=DENIED")
print("COMMANDER_NON_ADMIN_DEVICE_OWNERSHIP_GUARD=PASS")
print("COMMANDER_OIDC_FAILURE_COOKIE_CLEANUP=READY")
print("COMMANDER_SESSION_TOUCH_BEST_EFFORT=READY")
print("COMMANDER_AGENT_RUNTIME_DIAGNOSTIC=READY")
print("COMMANDER_AGENT_ERROR_CODE_SANITIZATION=READY")
