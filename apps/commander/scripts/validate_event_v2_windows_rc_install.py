#!/usr/bin/env python3
"""Fail-closed source guard for Windows Event V2 RC installer."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INSTALLER = ROOT / "apps/commander/candidate/install_windows_rc.ps1"
RC = ROOT / "apps/commander/candidate/windows_agent_rc.ps1"
ADAPTER = ROOT / "apps/commander/experimental/event_v2_windows_agent.ps1"
TRANSPORT = ROOT / "apps/commander/experimental/event_v2_windows_transport.ps1"
PUBLIC_INSTALLER = ROOT / "apps/commander/public/install/windows.ps1"
PUBLIC_AGENT = ROOT / "apps/commander/public/agent/windows.ps1"
MANIFEST = ROOT / "apps/commander/public/release/agent-manifest.json"


def main() -> int:
    installer = INSTALLER.read_text(encoding="utf-8")
    rc = RC.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    transport = TRANSPORT.read_text(encoding="utf-8")
    public_installer = PUBLIC_INSTALLER.read_text(encoding="utf-8")
    public_agent = PUBLIC_AGENT.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")

    required = (
        'ValidateSet("check","install","activate-event-v2","rollback","status")',
        '$StableTaskName = "HARA Commander Agent"',
        '$RcTaskName = "HARA Commander Agent RC"',
        '$StableConfig = Join-Path $StableRoot "device.json"',
        'Assert-ExistingIdentity',
        'COMMANDER_WINDOWS_RC_REUSES_EXISTING_IDENTITY=TRUE',
        'COMMANDER_WINDOWS_RC_AUTO_START=FALSE',
        'COMMANDER_WINDOWS_RC_DUAL_AGENT=DENY',
        'COMMANDER_WINDOWS_RC_ROLLBACK=SOURCE_READY',
        'Stop-TaskSafe $StableTaskName',
        'Start-TaskRequired $RcTaskName',
        'Wait-EventConnection',
        'Rollback-ToStable',
        'WINDOWS_RC_EVENT_V2_ACTIVATION_FAILED_ROLLED_BACK',
        'COMMANDER_WINDOWS_RC_DEVICE_REPAIRING=FALSE',
        'COMMANDER_WINDOWS_RC_TOKEN_EXPOSED=FALSE',
    )
    for marker in required:
        assert marker in installer, marker

    required_sources = (
        'candidate\\windows_agent_rc.ps1',
        'experimental\\event_v2_windows_agent.ps1',
        'experimental\\event_v2_windows_transport.ps1',
    )
    for marker in required_sources:
        assert marker in installer, marker

    forbidden = (
        "/api/device/enroll",
        "pairing_token",
        "device_token =",
        "Remove-Item -LiteralPath $StableRoot",
        "Unregister-ScheduledTask -TaskName $StableTaskName",
        'Register-ScheduledTask -TaskName $StableTaskName',
        "CUSTOMER_CONTENT_COLLECTION=TRUE",
        "HARA_SERVICES",
    )
    for marker in forbidden:
        assert marker not in installer, marker

    # The RC remains opt-in and the public release remains V1.
    assert 'if ([string]::IsNullOrWhiteSpace($Transport)) { $Transport = "POLL_V1" }' in rc
    assert '$OperationalAuthority = "HARA_COMMANDER"' in adapter
    assert '[System.Net.WebSockets.ClientWebSocket]::new()' in transport
    assert "HARA_DEVICE_TRANSPORT_MODE" not in public_installer
    assert "HARA_DEVICE_TRANSPORT_MODE" not in public_agent
    assert "install_windows_rc.ps1" not in manifest
    assert "event_v2_windows_agent.ps1" not in manifest

    print("COMMANDER_WINDOWS_EVENT_V2_RC_INSTALLER=PASS")
    print("COMMANDER_WINDOWS_RC_REUSES_EXISTING_IDENTITY=TRUE")
    print("COMMANDER_WINDOWS_RC_REENROLLMENT=FALSE")
    print("COMMANDER_WINDOWS_RC_AUTO_START=FALSE")
    print("COMMANDER_WINDOWS_RC_DUAL_AGENT=DENY")
    print("COMMANDER_WINDOWS_RC_ROLLBACK=SOURCE_READY")
    print("COMMANDER_WINDOWS_PUBLIC_V1_MUTATION=FALSE")
    print("COMMANDER_WINDOWS_RUNTIME_PROVEN=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
