#!/usr/bin/env python3
"""Create an unsigned source-only proposal; never rewrite a signed artifact."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "windows.ps1"
SOURCE_SHA = "2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401"
HELPER = r'''
function Assert-InstallPayloadPreflight {
  # Verify actual signed Agent bytes before asking for or consuming a pairing
  # token. Installation still performs its independent post-enrollment check.
  $path=Join-Path $env:TEMP ("hara-commander-install-preflight-"+[guid]::NewGuid().ToString("N")+".ps1")
  $owned=$false
  try {
    $reservation=New-Object IO.FileStream($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $owned=$true
    $reservation.Dispose()
    Invoke-WebRequest -Uri "$(Get-ReleaseBaseUrl)/agent/windows.ps1" -OutFile $path -UseBasicParsing -TimeoutSec 30 -MaximumRedirection 0
    Assert-AgentIntegrity $path
    $tokens=$null; $errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors) | Out-Null
    if ($errors.Count -ne 0) { throw "AGENT_INSTALL_SYNTAX_INVALID" }
    Assert-AgentSelfTest $path
  } finally {
    if ($owned -and (Test-Path -LiteralPath $path)) {
      Remove-Item -LiteralPath $path -Force -ErrorAction Stop
      if (Test-Path -LiteralPath $path) { throw "AGENT_PREFLIGHT_CLEANUP_FAILED" }
    }
  }
  Write-Host "HARA_COMMANDER_INSTALL_PAYLOAD_PREFLIGHT=PASS"
}
'''


def once(text, before, after):
    assert text.count(before) == 1, f"Expected exactly one anchor: {before[:70]}"
    return text.replace(before, after, 1)


def build():
    raw = SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA, "Canonical source changed"
    before = raw.decode("utf-8")
    after = once(before, "\nfunction Get-DeviceToken {", HELPER + "\nfunction Get-DeviceToken {")
    after = once(after, "  $release = Get-AgentReleaseMetadata\n  $scheduledTaskReady", "  $release = Get-AgentReleaseMetadata\n  Assert-InstallPayloadPreflight\n  $scheduledTaskReady")
    after = once(after, "    release_signature = $true\n    stable_agent_version", "    release_signature = $true\n    agent_payload = $true\n    agent_payload_syntax = $true\n    agent_payload_self_test = $true\n    stable_agent_version")
    after = once(after, 'Assert-AgentVersionFloor -IncomingVersion ([string](Get-AgentReleaseMetadata).Version)\n\nWrite-Host "HARA Commander - Windows device pairing"', 'Assert-AgentVersionFloor -IncomingVersion ([string](Get-AgentReleaseMetadata).Version)\nAssert-InstallPayloadPreflight\n\nWrite-Host "HARA Commander - Windows device pairing"')
    # Preserve all enrollment, DPAPI, task setup, post-enrollment integrity and
    # rollback code byte-for-byte. This intentionally does not solve a later
    # asset change between preflight and the original second download.
    tail = 'Write-Host "HARA Commander - Windows device pairing"'
    assert before[before.index(tail):] == after[after.index(tail):]
    for name, next_name in [("Assert-ReleaseManifestSignature", "Assert-AgentVersionFloor"), ("Get-AgentReleaseMetadata", "Assert-AgentIntegrity"), ("Assert-AgentIntegrity", "Assert-AgentSelfTest")]:
        start = "function " + name
        end = "function " + next_name
        assert before[before.index(start):before.index(end)] == after[after.index(start):after.index(end)]
    candidate = HERE / "windows.source-only-candidate.ps1"
    candidate.write_text(after, encoding="utf-8", newline="")
    (HERE / "windows.source-only.patch").write_text("".join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True), fromfile="a/public/install/windows.ps1", tofile="b/public/install/windows.ps1")), encoding="utf-8")
    receipt = {
        "state": "SOURCE_ONLY_CANDIDATE_GENERATED",
        "canonical_source_sha256": SOURCE_SHA,
        "canonical_source_unchanged": hashlib.sha256(SOURCE.read_bytes()).hexdigest() == SOURCE_SHA,
        "candidate_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
        "candidate_bytes": candidate.stat().st_size,
        "enrollment_dpapi_task_rollback_tail_unchanged": True,
        "signature_manifest_integrity_functions_unchanged": True,
        "native_regression": "NOT_RUN",
        "signed_bundle_modified": False,
        "public_distribution_changed": False,
        "release_approved": False,
        "limit": "Detects mismatched payload before token prompt; original independent download after enrollment remains, so a later asset mutation can still require rollback.",
    }
    (HERE / "source-review.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    build()
