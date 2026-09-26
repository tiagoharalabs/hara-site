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
        '$ExpectedDevOrigin = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"',
        'WINDOWS_RC_DEV_ORIGIN_REQUIRED',
        'COMMANDER_WINDOWS_RC_EVENT_V2_ORIGIN=DEV_ONLY',
        'Disable-TaskSafe $RcTaskName',
        'Disable-TaskSafe $StableTaskName',
        'Enable-TaskRequired $RcTaskName',
        'Enable-TaskRequired $StableTaskName',
        'WINDOWS_RC_INSTALL_NOT_INERT',
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
    assert '$StableAgent = Join-Path $StableRoot "hara-commander-agent.ps1"' in rc
    assert '$EventV2Agent = Join-Path $Here "event_v2_windows_agent.ps1"' in rc
    assert '$OperationalAuthority = "HARA_COMMANDER"' in adapter
    assert '$ReconnectBaseSeconds = 10' in adapter
    activation = installer.split("function Activate-EventV2 {", 1)[1].split("function Show-Status {", 1)[0]
    transition_try = activation.index("try {")
    assert transition_try < activation.index("Stop-TaskSafe $StableTaskName")
    assert transition_try < activation.index("Disable-TaskSafe $StableTaskName")
    assert 'catch {\n    Rollback-ToStable' in activation

    assert '$StableAgent = Join-Path $StableRoot "hara-commander-agent.ps1"' in adapter
    assert '$TransportPath = Join-Path $Here "event_v2_windows_transport.ps1"' in adapter
    assert '[System.Net.WebSockets.ClientWebSocket]::new()' in transport
    assert "HARA_DEVICE_TRANSPORT_MODE" not in public_installer
    assert "HARA_DEVICE_TRANSPORT_MODE" not in public_agent
    assert "install_windows_rc.ps1" not in manifest
    assert "event_v2_windows_agent.ps1" not in manifest
    assert 'Join-Path $CommanderRoot "public\\agent\\windows.ps1"' not in rc
    assert 'Join-Path $CommanderRoot "experimental\\event_v2_windows_agent.ps1"' not in rc
    assert 'Join-Path $CommanderRoot "public\\agent\\windows.ps1"' not in adapter
    assert 'Join-Path $CommanderRoot "experimental\\event_v2_windows_transport.ps1"' not in adapter

    print("COMMANDER_WINDOWS_EVENT_V2_RC_INSTALLER=PASS")
    print("COMMANDER_WINDOWS_RC_REUSES_EXISTING_IDENTITY=TRUE")
    print("COMMANDER_WINDOWS_RC_REENROLLMENT=FALSE")
    print("COMMANDER_WINDOWS_RC_AUTO_START=FALSE")
    print("COMMANDER_WINDOWS_RC_INSTALL_INERT=TRUE")
    print("COMMANDER_WINDOWS_RC_INSTALLED_LAYOUT=PASS")
    print("COMMANDER_WINDOWS_RC_EVENT_V2_ORIGIN=DEV_ONLY")
    print("COMMANDER_WINDOWS_RC_DUAL_AGENT=DENY")
    print("COMMANDER_WINDOWS_RC_ROLLBACK=SOURCE_READY")
    print("COMMANDER_WINDOWS_PUBLIC_V1_MUTATION=FALSE")
    print("COMMANDER_WINDOWS_RUNTIME_PROVEN=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
