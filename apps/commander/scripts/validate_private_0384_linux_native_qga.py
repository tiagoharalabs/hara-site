#!/usr/bin/env python3
"""Read-only native Ubuntu VM QA readback; no installation, enrollment or service changes."""
import base64
import json
import subprocess
import time

DOMAIN = "hara-commander-linux-qa0384-20261116"
EXPECTED_PRE = "a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733"
EXPECTED_INSTALLER = "e9a203ae3fdda1d6cc55e857bc0cf471a1e5d738a0b9ccab9526aef692b03476"
VM_CHECKS = [
    "HARA_QA_QGA_SERVICE_ACTIVE",
    "HARA_QA_SIGNED_AND_BASELINE_SHA_PASS",
    "HARA_QA_0383_USER_SERVICE_START_PASS",
    "HARA_QA_0383_USER_SERVICE_STOP_PASS",
    "HARA_QA_0384_NATIVE_USER_SERVICE_START_PASS",
    "HARA_QA_0383_NATIVE_USER_SERVICE_ROLLBACK_PASS",
    "HARA_QA_MANUAL_SERVICE_NOT_ENABLED_PASS",
    "HARA_QA_LINUX_V4_END",
]

def run(argv, timeout=10):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if proc.returncode:
        raise RuntimeError("HOST_READONLY_COMMAND_FAILED:" + str(argv[0]))
    return proc.stdout

def qga(payload):
    out = run(["virsh", "-c", "qemu:///system", "qemu-agent-command",
               DOMAIN, "--timeout", "4", json.dumps(payload)], timeout=8)
    response = json.loads(out)
    if "error" in response:
        raise RuntimeError("QGA_READONLY_REQUEST_FAILED")
    return response["return"]

def read_guest():
    command = r'''set -Eeuo pipefail
LOG=/var/log/hara-commander-0384-linux-e2e-v4.log
test -f "$LOG"
for MARK in HARA_QA_QGA_SERVICE_ACTIVE HARA_QA_SIGNED_AND_BASELINE_SHA_PASS HARA_QA_0383_USER_SERVICE_START_PASS HARA_QA_0383_USER_SERVICE_STOP_PASS HARA_QA_0384_NATIVE_USER_SERVICE_START_PASS HARA_QA_0383_NATIVE_USER_SERVICE_ROLLBACK_PASS HARA_QA_MANUAL_SERVICE_NOT_ENABLED_PASS HARA_QA_LINUX_V4_END;do
  grep -Fxq "$MARK" "$LOG"
done
systemctl is-active --quiet qemu-guest-agent.service
test -x /usr/sbin/qemu-ga
test "$(cat /home/haraqa/qa0384/offline-update-check.rc)" = 5
grep -Fxq DEVICE_NOT_ENROLLED /home/haraqa/qa0384/offline-update-check.log
test ! -e /home/haraqa/.config/hara-commander/device.env
test ! -e /home/haraqa/.local/share/hara-commander/hara-commander-agent
test "$(sha256sum /home/haraqa/qa0384/installer.sh | cut -d' ' -f1)" = e9a203ae3fdda1d6cc55e857bc0cf471a1e5d738a0b9ccab9526aef692b03476
test "$(sha256sum /home/haraqa/qa0384/agent.py | cut -d' ' -f1)" = a0784dc783b1675773f7ab05a21f07d01f48fd3f8b97906971ef90eb7018c733
QA_UID="$(id -u haraqa)"
show="$(runuser -u haraqa -- env HOME=/home/haraqa XDG_RUNTIME_DIR="/run/user/$QA_UID" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$QA_UID/bus" systemctl --user show hara-qa0384.service -p LoadState -p ActiveState -p UnitFileState)"
grep -Fxq LoadState=loaded <<< "$show"
grep -Fxq ActiveState=inactive <<< "$show"
grep -Fxq UnitFileState=disabled <<< "$show"
echo HARA_LINUX_NATIVE_0384_SERVICE_AND_OFFLINE_INSTALLER_READBACK_PASS'''
    pid = int(qga({"execute": "guest-exec", "arguments": {
        "path": "/usr/bin/bash", "arg": ["-lc", command], "capture-output": True}})["pid"])
    for _ in range(28):
        try:
            row = qga({"execute": "guest-exec-status", "arguments": {"pid": pid}})
        except (RuntimeError, subprocess.TimeoutExpired):
            time.sleep(.25)
            continue
        if row.get("exited"):
            raw = base64.b64decode(row.get("out-data", "")).decode(errors="replace").strip()
            if row.get("exitcode") != 0 or raw != "HARA_LINUX_NATIVE_0384_SERVICE_AND_OFFLINE_INSTALLER_READBACK_PASS":
                raise RuntimeError("GUEST_PROOF_FAILED_RC_" + str(row.get("exitcode")))
            return raw
        time.sleep(.25)
    raise RuntimeError("GUEST_PROOF_INCOMPLETE")

def main():
    info = run(["virsh", "-c", "qemu:///system", "dominfo", DOMAIN])
    if "Persistent:     no" not in info or "Autostart:      disable" not in info:
        raise RuntimeError("QA_DOMAIN_NOT_TRANSIENT")
    interfaces = run(["virsh", "-c", "qemu:///system", "domiflist", DOMAIN])
    if len(interfaces.strip().splitlines()) != 2:
        raise RuntimeError("QA_NETWORK_INTERFACE_PRESENT")
    disks = run(["virsh", "-c", "qemu:///system", "domblklist", DOMAIN])
    if "linux-qa0384-overlay.qcow2" not in disks or "qa-cloudinit-linux-e2e-v4.iso" not in disks:
        raise RuntimeError("QA_COW_OR_SEED_NOT_BOUND")
    qga({"execute": "guest-ping"})
    osinfo = qga({"execute": "guest-get-osinfo"})
    if osinfo.get("id") != "ubuntu" or not str(osinfo.get("version-id", "")).startswith("24.04"):
        raise RuntimeError("QA_GUEST_OS_DIFFERENT")
    actual = read_guest()
    print(json.dumps({
        "state": "LINUX_NATIVE_0384_USER_SERVICE_AND_INSTALLER_NEGATIVE_PASS",
        "guest": DOMAIN, "os": osinfo.get("pretty-name"),
        "checks": VM_CHECKS, "checks_passed": len(VM_CHECKS),
        "readback": actual,
        "official_installer_executed": True,
        "official_installer_unenrolled_exit": 5,
        "device_enrolled": False, "manual_user_service_only": True,
        "guest_network_interfaces": 0, "base_image_modified": False,
        "native_identity_pairing_tested": False,
        "production_modified": False
    }, sort_keys=True))

if __name__ == "__main__":
    main()
