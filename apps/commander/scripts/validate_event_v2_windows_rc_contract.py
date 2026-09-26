#!/usr/bin/env python3
"""Fail-closed source guard for Windows Event V2 RC contract."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RC = ROOT / "apps/commander/candidate/windows_agent_rc.ps1"
DOC = ROOT / "docs/architecture/HARA_COMMANDER_EVENT_V2_WINDOWS_RC.md"
PUBLIC_INSTALLER = ROOT / "apps/commander/public/install/windows.ps1"
PUBLIC_AGENT = ROOT / "apps/commander/public/agent/windows.ps1"
MANIFEST = ROOT / "apps/commander/public/release/agent-manifest.json"


def main() -> int:
    rc = RC.read_text(encoding="utf-8")
    doc = DOC.read_text(encoding="utf-8")
    installer = PUBLIC_INSTALLER.read_text(encoding="utf-8")
    agent = PUBLIC_AGENT.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")

    required_rc = (
        'ValidateSet("POLL_V1","EVENT_V2")',
        'if ([string]::IsNullOrWhiteSpace($Transport)) { $Transport = "POLL_V1" }',
        "COMMANDER_WINDOWS_RC_DEFAULT_TRANSPORT=POLL_V1",
        "COMMANDER_WINDOWS_EVENT_V2_TRANSPORT_NOT_READY",
        "COMMANDER_WINDOWS_RC_SERVICES_PROXY=FALSE",
        "public\\agent\\windows.ps1",
        "experimental\\event_v2_windows_agent.ps1",
    )
    for marker in required_rc:
        assert marker in rc, marker

    required_doc = (
        "WINDOWS_PUBLIC_TRANSPORT=POLL_V1",
        "WINDOWS_EVENT_V2=SOURCE_CONTRACT_ONLY",
        "WINDOWS_PUBLIC_CUTOVER=DENY",
        "CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=FALSE",
        "WINDOWS_RC_REPAIRING=FALSE",
        "WINDOWS_EVENT_V2_TRANSPORT_IMPLEMENTED=FALSE",
        "CROSS_PLATFORM_EVENT_V2_PARITY=FALSE",
        "System.Net.WebSockets.ClientWebSocket",
        "CALL_AVAILABLE is a wake hint only",
    )
    for marker in required_doc:
        assert marker in doc, marker

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
    print("COMMANDER_WINDOWS_EVENT_V2_NOT_READY=FAIL_CLOSED")
    print("COMMANDER_WINDOWS_PUBLIC_V1_MUTATION=FALSE")
    print("COMMANDER_WINDOWS_CROSS_PLATFORM_PARITY_CLAIM=FALSE")
    print("COMMANDER_WINDOWS_SERVICES_PROXY=FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
