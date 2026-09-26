#!/usr/bin/env python3
"""Fail-closed source guard for Windows Event V2 RC contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RC = ROOT / "apps/commander/candidate/windows_agent_rc.ps1"
DOC = ROOT / "docs/architecture/HARA_COMMANDER_EVENT_V2_WINDOWS_RC.md"
PUBLIC_INSTALLER = ROOT / "apps/commander/public/install/windows.ps1"
PUBLIC_AGENT = ROOT / "apps/commander/public/agent/windows.ps1"
MANIFEST = ROOT / "apps/commander/public/release/agent-manifest.json"
TRANSPORT = ROOT / "apps/commander/experimental/event_v2_windows_transport.ps1"
ADAPTER = ROOT / "apps/commander/experimental/event_v2_windows_agent.ps1"


def main() -> int:
    rc = RC.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")
    installer = PUBLIC_INSTALLER.read_text(encoding="utf-8")
    agent = PUBLIC_AGENT.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")
    transport = TRANSPORT.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")

    required_rc = (
        'ValidateSet("POLL_V1","EVENT_V2")',
        'if ([string]::IsNullOrWhiteSpace($Transport)) { $Transport = "POLL_V1" }',
        "COMMANDER_WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1",
        "COMMANDER_WINDOWS_RC_EVENT_V2=SOURCE_READY_UNPROVEN",
        "COMMANDER_WINDOWS_RC_SERVICES_PROXY=FALSE",
        "public\\agent\\windows.ps1",
        "experimental\\event_v2_windows_agent.ps1",
    )
    for marker in required_rc:
        assert marker in rc, marker

    required_doc = (
        "WINDOWS_PUBLIC_TRANSPORT=POLL_V1",
        "WINDOWS_EVENT_V2=SOURCE_ADAPTER_READY_UNPROVEN",
        "WINDOWS_PUBLIC_CUTOVER=DENY",
        "CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=FALSE",
        "WINDOWS_RC_REPAIRING=FALSE",
        "WINDOWS_EVENT_V2_TRANSPORT_SOURCE=READY_UNPROVEN",
        "WINDOWS_EVENT_V2_AGENT_ADAPTER_IMPLEMENTED=TRUE",
        "CROSS_PLATFORM_EVENT_V2_PARITY=FALSE",
        "System.Net.WebSockets.ClientWebSocket",
        "CALL_AVAILABLE is a wake hint only",
    )
    for marker in required_doc:
        assert marker in doc, marker

    required_transport = (
        "[System.Net.WebSockets.ClientWebSocket]::new()",
        'SetRequestHeader("Authorization", ("Bearer " + $DeviceToken))',
        "KeepAliveInterval = [TimeSpan]::FromSeconds($KeepAliveSeconds)",
        'if ($uri.Scheme -ne "https")',
        '$builder.Scheme = "wss"',
        "WINDOWS_EVENT_V2_FRAGMENTATION_DENIED",
        "WINDOWS_EVENT_V2_MESSAGE_TYPE_DENIED",
        "WINDOWS_EVENT_V2_EVENT_INVALID",
        "CONTENT_BEARING_WAKE=DENIED",
        "SOURCE_ONLY_USE_WINDOWS_EVENT_V2_AGENT",
        "param([switch]$SelfTest,[switch]$ImportOnly)",
        "if ($ImportOnly) { return }",
    )
    for marker in required_transport:
        assert marker in transport, marker

    forbidden_transport = (
        "Write-Host $DeviceToken",
        "Write-Output $DeviceToken",
        "CUSTOMER_CONTENT_COLLECTION=TRUE",
        "HARA_SERVICES",
        "/api/device/heartbeat",
        "Start-Sleep -Seconds 2",
    )
    for marker in forbidden_transport:
        assert marker not in transport, marker

    required_adapter = (
        "Import-StableAgentFunctions",
        "public\\agent\\windows.ps1",
        "experimental\\event_v2_windows_transport.ps1",
        "$OperationalAuthority = \"HARA_COMMANDER\"",
        "$TransportMode = \"EVENT_V2\"",
        "$MaxDrainCalls = 8",
        "$ReconnectBaseSeconds = 1",
        "$ReconnectMaxSeconds = 15",
        "$DurableLivenessSeconds = 21600",
        "Invoke-DurableDrain",
        "CALL_AVAILABLE",
        "Get-NextDurableCall",
        "/api/device/calls/next",
        "COMMANDER_WINDOWS_EVENT_V2_AGENT_ADAPTER=PASS",
        "COMMANDER_WINDOWS_EVENT_V2_SERVICES_PROXY=FALSE",
    )
    for marker in required_adapter:
        assert marker in adapter, marker

    forbidden_adapter = (
        "HARA_SERVICES",
        "/api/device/heartbeat",
        "Start-Sleep -Seconds 2",
        "CUSTOMER_CONTENT_COLLECTION=TRUE",
        "shell.run",
        "Write-Host $token",
        "Write-Output $token",
    )
    for marker in forbidden_adapter:
        assert marker not in adapter, marker

    # Public V1 surfaces remain unchanged by this source-only lane.
    assert "HARA_DEVICE_TRANSPORT_MODE" not in installer
    assert "HARA_DEVICE_TRANSPORT_MODE" not in agent
    assert "candidate/windows_agent_rc.ps1" not in manifest
    assert "event_v2_windows_agent.ps1" not in manifest

    forbidden = (
        "CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=TRUE",
        "WINDOWS_PUBLIC_CUTOVER=ALLOW",
        "CROSS_PLATFORM_EVENT_V2_PARITY=TRUE",
        "WINDOWS_RC_REPAIRING=TRUE",
    )
    combined = rc + "\n" + doc
    for marker in forbidden:
        assert marker not in combined, marker

    print("COMMANDER_WINDOWS_EVENT_V2_RC_CONTRACT=PASS")
    print("COMMANDER_WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1")
    print("COMMANDER_WINDOWS_EVENT_V2_SOURCE_ADAPTER=READY_UNPROVEN")
    print("COMMANDER_WINDOWS_PUBLIC_V1_MUTATION=FALSE")
    print("COMMANDER_WINDOWS_CROSS_PLATFORM_PARITY_CLAIM=FALSE")
    print("COMMANDER_WINDOWS_SERVICES_PROXY=FALSE")
    print("COMMANDER_WINDOWS_EVENT_V2_TRANSPORT_SOURCE=READY_UNPROVEN")
    print("COMMANDER_WINDOWS_EVENT_V2_AGENT_ADAPTER=SOURCE_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
