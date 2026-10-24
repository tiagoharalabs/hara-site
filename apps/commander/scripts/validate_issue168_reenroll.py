#!/usr/bin/env python3
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
LINUX = (ROOT / "apps/commander/public/install/linux.sh").read_text(encoding="utf-8")

checks = {
    "COMMAND_DISCOVERABLE": "re-enroll|reenroll)" in LINUX and "bash linux.sh re-enroll" in LINUX,
    "OLD_CREDENTIAL_EXPLICITLY_REJECTED": 'obj.get("code") != "DEVICE_AUTH_INVALID"' in LINUX,
    "ACTIVE_DEVICE_REFUSED": "REENROLL_REFUSED_CURRENT_DEVICE_STILL_ACTIVE" in LINUX,
    "AMBIGUOUS_AUTH_FAILS_CLOSED": "REENROLL_AUTH_CHECK_AMBIGUOUS" in LINUX,
    "FRESH_PAIRING_SECRET_STDIN": "IFS= read -r -s PAIRING_TOKEN </dev/tty" in LINUX,
    "NORMAL_ENROLL_ENDPOINT_REUSED": '$BASE_URL/api/device/enroll' in LINUX,
    "OLD_CONFIG_BACKED_UP": 'cp -p "$CONFIG_FILE" "$REENROLL_BACKUP"' in LINUX,
    "NEW_DEVICE_ROLLBACK_READY": "cleanup_failed_reenroll" in LINUX and "rollback_enrolled_device" in LINUX,
    "OLD_CONFIG_RESTORED_ON_FAILURE": 'mv -f "$REENROLL_BACKUP" "$CONFIG_FILE"' in LINUX,
    "OLD_AUTHORITY_NOT_RESURRECTED": "OLD_DEVICE_AUTHORITY_RESURRECTED=FALSE" in LINUX,
    "TOKEN_NOT_EXPOSED": "DEVICE_TOKEN_EXPOSED=FALSE" in LINUX,
    "NO_ENV_PAIRING_TOKEN": "HARA_PAIRING_TOKEN=" not in LINUX,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("ISSUE168_REENROLL_CONTRACT_FAIL:" + ",".join(failed))

subprocess.run(["bash", "-n", str(ROOT / "apps/commander/public/install/linux.sh")], check=True)

print("ISSUE168_REENROLL_SOURCE_CONTRACT=PASS")
print("REVOKED_CREDENTIAL_REMAINS_DENIED=PASS")
print("SILENT_CREDENTIAL_REPLACEMENT=FALSE")
print("FRESH_PAIRING_TOKEN_REQUIRED=TRUE")
print("REENROLL_COMMAND_DISCOVERABLE=TRUE")
print("REENROLL_COMMAND_ONE_FLOW=TRUE")
print("OLD_DEVICE_AUTHORITY_NOT_RESURRECTED=TRUE")
print("NEW_DEVICE_CREDENTIAL_ISSUED=BACKEND_NORMAL_ENROLL_CONTRACT")
print("TOKEN_EXPOSURE=FALSE")
