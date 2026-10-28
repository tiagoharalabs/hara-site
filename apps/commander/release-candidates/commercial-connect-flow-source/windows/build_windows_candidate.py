#!/usr/bin/env python3
"""Generate an unsigned source candidate; never modify an existing release."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
SOURCE_ROOT = HERE.parent.parent
SOURCE_PATHS = (
    SOURCE_ROOT / "windows.ps1",
    SOURCE_ROOT / "commercial-0.3.56-source/install/windows.ps1",
)
ORIGINAL_SOURCE_SHA = "2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401"
BASE_SHA = "0d7eff7f92dd9f12a82b0bd74121cfc287fb953543cbbc665760f63e22b33b24"
CONTROLLER_SHA = "2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da"

PREFLIGHT_HELPER = r'''
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


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    source = next((path for path in SOURCE_PATHS if path.is_file()), None)
    if source is None:
        raise SystemExit("ORIGINAL_SOURCE_NOT_FOUND")
    original = source.read_bytes()
    if sha(original) != ORIGINAL_SOURCE_SHA:
        raise SystemExit("ORIGINAL_SOURCE_PREIMAGE_CHANGED")
    derived = original.decode("utf-8")
    patches = (
        ("\nfunction Get-DeviceToken {", PREFLIGHT_HELPER + "\nfunction Get-DeviceToken {"),
        ("  $release = Get-AgentReleaseMetadata\n  $scheduledTaskReady", "  $release = Get-AgentReleaseMetadata\n  Assert-InstallPayloadPreflight\n  $scheduledTaskReady"),
        ("    release_signature = $true\n    stable_agent_version", "    release_signature = $true\n    agent_payload = $true\n    agent_payload_syntax = $true\n    agent_payload_self_test = $true\n    stable_agent_version"),
        ('Assert-AgentVersionFloor -IncomingVersion ([string](Get-AgentReleaseMetadata).Version)\n\nWrite-Host "HARA Commander - Windows device pairing"', 'Assert-AgentVersionFloor -IncomingVersion ([string](Get-AgentReleaseMetadata).Version)\nAssert-InstallPayloadPreflight\n\nWrite-Host "HARA Commander - Windows device pairing"'),
    )
    for before, after in patches:
        if derived.count(before) != 1:
            raise SystemExit("PREFLIGHT_PATCH_ANCHOR_CHANGED")
        derived = derived.replace(before, after, 1)
    base_bytes = derived.encode("utf-8")
    if sha(base_bytes) != BASE_SHA:
        raise SystemExit("DERIVED_PREFLIGHT_SOURCE_CHANGED")
    controller_bytes = (HERE / "Connect-Commander.ps1").read_bytes()
    if sha(controller_bytes) != CONTROLLER_SHA:
        raise SystemExit("CONTROLLER_PREIMAGE_CHANGED")
    controller = controller_bytes.decode("utf-8")
    core_start = controller.index("$ErrorActionPreference='Stop'")
    core_end = controller.index("\nif($MyInvocation.InvocationName -ne '.'){")
    core = controller[core_start:core_end]
    helper = (HERE / "Preserved-Pairing.ps1").read_text(encoding="utf-8")
    dispatch = r'''
if ($Action -in @('connect','conectar')) {
  $connectGuard=$null;$connectExit=2
  try {
    $connectOrigin=if($env:HARA_COMMANDER_URL){[string]$env:HARA_COMMANDER_URL}else{''}
    $connectRelease=if($env:HARA_COMMANDER_RELEASE_URL){[string]$env:HARA_COMMANDER_RELEASE_URL}else{''}
    $connectContext=New-CCContext $connectOrigin $connectRelease $ApprovalMode
    $connectGuard=Enter-CCGuard $connectContext
    $connectResult=Invoke-CCConnect $connectContext
    if($connectResult.state -ceq 'CONNECTED'){
      Write-Host 'Commander conectado. O pareamento e a versao foram verificados.'
      $connectExit=0
    }elseif($connectResult.state -ceq 'CONNECTED_UPDATE_HOLD'){
      Write-Host 'Commander conectado. A atualizacao nao foi concluida; o pareamento foi preservado.' -ForegroundColor Yellow
      $connectExit=3
    }else{
      Write-Host 'Nao foi possivel concluir a conexao. Consulte o codigo de diagnostico abaixo.' -ForegroundColor Yellow
    }
    $connectResult|ConvertTo-Json -Depth 6
  }catch{
    [pscustomobject]@{state='HOLD';error_code=(Get-CCErrorCode $_);device_token_exposed=$false}|ConvertTo-Json
  }finally{if($connectGuard){$connectGuard.ReleaseMutex();$connectGuard.Dispose()}}
  exit $connectExit
}
if ($Action -in @('pair-existing','re-enroll')) {
  Invoke-PreservedPairing $Action
  exit 0
}
if ($Action -eq 'install' -and -not (Test-Path -LiteralPath $Config)) {
  if (Test-Path -LiteralPath $Agent) {
    Invoke-PreservedPairing 'pair-existing'
    exit 0
  }
  if ((Test-Path -LiteralPath $Root) -and @(Get-ChildItem -LiteralPath $Root -Force).Count -gt 0) {
    throw 'UNPAIRED_PATH_CONFLICT'
  }
}
'''
    base = base_bytes.decode("utf-8")
    if not base.startswith('param([string]$Action = "install")\n'):
        raise SystemExit("SOURCE_ENTRYPOINT_UNEXPECTED")
    base = base.replace('param([string]$Action = "install")', 'param([string]$Action = "connect")', 1)
    anchor = 'if ($Action -eq "preflight") { Invoke-Preflight; exit 0 }'
    if base.count(anchor) != 1:
        raise SystemExit("SOURCE_DISPATCH_ANCHOR_UNEXPECTED")
    embedded = (
        "\n# Embedded controller source SHA256: " + CONTROLLER_SHA + "\n"
        + core + "\n" + helper + "\n" + dispatch + "\n"
    )
    base = base.replace(anchor, embedded + anchor, 1)
    base = base.replace(
        "Usage: windows.ps1 -Action install|preflight|status|doctor|support|update|uninstall",
        "Usage: windows.ps1 -Action connect|install|pair-existing|re-enroll|preflight|status|doctor|support|update|uninstall",
        1,
    )
    output = (
        "# SOURCE CANDIDATE ONLY: unsigned; not deployed or published.\n"
        "# HARA_COMMANDER_PAIR_EXISTING=1\n"
        "# HARA_COMMANDER_REENROLL=1\n"
        "# HARA_COMMANDER_DEFAULT_CONNECT=1\n"
        + base
    ).encode("utf-8")
    target = HERE / "windows.source-only-candidate.ps1"
    target.write_bytes(output)
    report = {
        "schema": "hara.commander.windows-connect-source-candidate.v1",
        "state": "SOURCE_ONLY_NOT_DEPLOYED",
        "signature": "NOT_SIGNED",
        "native_tests": "NOT_RUN",
        "release_version_change_required_before_publication": True,
        "current_source_agent_version": "0.3.56",
        "original_source_sha256": ORIGINAL_SOURCE_SHA,
        "base_source_sha256": BASE_SHA,
        "embedded_controller_sha256": CONTROLLER_SHA,
        "preserved_pairing_helper_sha256": sha(helper.encode()),
        "candidate_sha256": sha(output),
        "candidate_bytes": len(output),
        "existing_signed_release_modified": False,
        "default_action": "connect",
        "preserved_pairing_actions": ["pair-existing", "re-enroll"],
    }
    (HERE / "source-candidate-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
