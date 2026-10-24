#!/usr/bin/env python3
"""Fail-closed validation for the Linux Event V2 release-candidate installer."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "apps/commander/candidate/install_linux_rc.sh"
PUBLIC_INSTALLER = ROOT / "apps/commander/public/install/linux.sh"
PUBLIC_MANIFEST = ROOT / "apps/commander/public/release/agent-manifest.json"


def main() -> int:
    source = INSTALLER.read_text(encoding="utf-8")
    public_installer = PUBLIC_INSTALLER.read_text(encoding="utf-8")
    manifest = PUBLIC_MANIFEST.read_text(encoding="utf-8")

    required = (
        "COMMANDER_AGENT_RC_AUTO_START=FALSE",
        "COMMANDER_AGENT_RC_DEVICE_REPAIRING=FALSE",
        "COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE",
        "activate-event-v2",
        "rollback_to_stable",
        "Conflicts=hara-commander-agent.service",
        "HARA_DEVICE_TRANSPORT_MODE",
        "systemctl --user stop \"$STABLE_SERVICE\"",
        "systemctl --user start \"$RC_SERVICE\"",
        "systemctl --user start \"$STABLE_SERVICE\"",
        "RC_EVENT_V2_PROCESS_ATTESTATION_FAILED_ROLLED_BACK",
        "RC_EVENT_V2_CONNECTION_ATTESTATION_FAILED_ROLLED_BACK",
        "RC_DUAL_AGENT_DENIED_ROLLED_BACK",
        "RC_INSTALL_WHILE_ACTIVE_DENIED",
        'Environment="XDG_CONFIG_HOME=$CONFIG_HOME"',
        'Environment="XDG_DATA_HOME=$DATA_HOME"',
        'attest_active "$RC_SERVICE"',
        'attest_event_v2_connection "$previous_event_status"',
        "RC_EVENT_V2_CONNECTION_ATTESTATION_FAILED_ROLLED_BACK",
        "COMMANDER_AGENT_RC_EVENT_V2_CONNECTION_ATTESTATION=PASS",
    )
    for marker in required:
        assert marker in source, f"missing marker: {marker}"

    forbidden = (
        "/api/device/enroll",
        "PAIRING_TOKEN",
        "device_token\":",
        "rm -rf",
        "curl ",
        "wget ",
    )
    for marker in forbidden:
        assert marker not in source, f"forbidden surface: {marker}"

    # The candidate must reuse the existing config rather than create/rewrite it.
    assert 'DEVICE_CONFIG="$COMMANDER_CONFIG_DIR/device.env"' in source
    assert 'secure_regular_file "$DEVICE_CONFIG"' in source
    assert '> "$DEVICE_CONFIG"' not in source
    assert '>"$DEVICE_CONFIG"' not in source

    # Stable public release remains untouched by transport selection.
    assert "HARA_DEVICE_TRANSPORT_MODE" not in public_installer
    assert "candidate/" not in manifest

    proc = subprocess.run(
        ["bash", str(INSTALLER), "check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        raise AssertionError(proc.stderr or proc.stdout or "RC_INSTALLER_CHECK_FAILED")
    output = proc.stdout
    for marker in (
        "COMMANDER_AGENT_RC_INSTALLER_SOURCE=PASS",
        "COMMANDER_AGENT_RC_DEFAULT_TRANSPORT=POLL_V1",
        "COMMANDER_AGENT_RC_AUTO_START=FALSE",
        "COMMANDER_AGENT_RC_REPAIRING=ABSENT",
        "COMMANDER_AGENT_RC_DUAL_AGENT=DENY",
        "COMMANDER_AGENT_RC_ROLLBACK=SOURCE_READY",
        "COMMANDER_AGENT_RC_DEVICE_TOKEN_EXPOSED=FALSE",
    ):
        assert marker in output

    print("COMMANDER_EVENT_V2_LINUX_RC_INSTALLER=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_REPAIRING=ABSENT")
    print("COMMANDER_EVENT_V2_LINUX_RC_DEFAULT=POLL_V1")
    print("COMMANDER_EVENT_V2_LINUX_RC_AUTO_START=FALSE")
    print("COMMANDER_EVENT_V2_LINUX_RC_DUAL_AGENT=DENY")
    print("COMMANDER_EVENT_V2_LINUX_RC_ROLLBACK=SOURCE_READY")
    print("COMMANDER_EVENT_V2_LINUX_RC_XDG_ISOLATION=PASS")
    print("COMMANDER_EVENT_V2_LINUX_RC_ACTIVE_REINSTALL=DENY")
    print("COMMANDER_EVENT_V2_LINUX_RC_CONNECTION_ATTESTATION=SOURCE_READY")
    print("COMMANDER_STABLE_PUBLIC_INSTALLER_MUTATION=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
