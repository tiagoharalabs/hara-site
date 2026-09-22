#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "public/dev/commander"
LINUX = (PUBLIC / "install/linux.sh").read_text(encoding="utf-8")
WINDOWS = (PUBLIC / "install/windows.ps1").read_text(encoding="utf-8")
HTML = (PUBLIC / "index.html").read_text(encoding="utf-8")
JS = (PUBLIC / "app.js").read_text(encoding="utf-8")

def need(text: str, token: str, code: str) -> None:
    assert token in text, f"{code}:{token}"

for token in (
    'platform": "LINUX"',
    "/api/device/enroll",
    "/api/device/heartbeat",
    "systemctl --user enable --now",
    "chmod 600",
):
    need(LINUX, token, "LINUX_INSTALLER_MISSING")

assert "cloudflared" not in LINUX.lower(), "LINUX_INSTALLER_CLOUDFLARED_NOT_ALLOWED"
print("LINUX_DEVICE_INSTALLER_STATIC=PASS")

for token in (
    'platform="WINDOWS"',
    "/api/device/enroll",
    "/api/device/heartbeat",
    "ConvertFrom-SecureString",
    "New-ScheduledTaskTrigger -AtLogOn",
    "Register-ScheduledTask",
    "icacls.exe",
):
    need(WINDOWS, token, "WINDOWS_INSTALLER_MISSING")

assert "cloudflared" not in WINDOWS.lower(), "WINDOWS_INSTALLER_CLOUDFLARED_NOT_ALLOWED"
assert "encrypted_device_token" in WINDOWS, "WINDOWS_DPAPI_TOKEN_MISSING"
assert "DEVICE_TOKEN_EXPOSED=FALSE" in WINDOWS, "WINDOWS_TOKEN_HYGIENE_MARKER"
print("WINDOWS_DEVICE_INSTALLER_STATIC=PASS")

need(HTML, "/install/linux.sh", "PORTAL_LINUX_INSTALLER_LINK")
need(HTML, "/install/windows.ps1", "PORTAL_WINDOWS_INSTALLER_LINK")
need(HTML, "data-copy-windows", "PORTAL_WINDOWS_COPY")
need(JS, "Comando Windows copiado.", "PORTAL_WINDOWS_COPY_HANDLER")
print("PORTAL_DEVICE_INSTALLERS=PASS")
print("PER_DEVICE_CLOUDFLARED_DEPENDENCY=FALSE")
print("OUTBOUND_CALL_CHANNEL_IMPLEMENTED=FALSE")
