# The production function above is extracted unchanged. These mocks replace
# network and Agent self-test; this script never invokes install/enroll.
function Get-MockSha([byte[]]$Bytes) {
  $sha=[Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant() }
  finally { $sha.Dispose() }
}
function Get-AgentReleaseMetadata { return $script:MockMeta }
function Assert-AgentSelfTest([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'MOCK_AGENT_MISSING' }
}
function Invoke-WebRequest {
  param([string]$Uri,[string]$OutFile,[switch]$UseBasicParsing,[int]$TimeoutSec,[int]$MaximumRedirection)
  $relative=@($script:MockAssets.Keys | Where-Object { $Uri.EndsWith('/'+$_) })
  if ($relative.Count -ne 1) { throw 'MOCK_UNKNOWN_ASSET' }
  [IO.File]::WriteAllBytes($OutFile,[byte[]]$script:MockAssets[$relative[0]])
}
function Set-MockMeta {
  $rows=@()
  foreach($relative in $script:MockAssets.Keys) {
    $raw=[byte[]]$script:MockAssets[$relative]
    $rows+=,[pscustomobject]@{path=$relative;sha256=(Get-MockSha $raw);bytes=$raw.Length}
  }
  $script:MockMeta=[pscustomobject]@{
    Version='0.3.43';Sha256=($rows | Where-Object {$_.path -eq 'agent/windows.ps1'} | Select-Object -First 1).sha256
    Manifest=[pscustomobject]@{schema='hara.commander-agent-release.v1';files=$rows}
  }
}

$script:MockAssets=@{
  'agent/linux.py'=[Text.Encoding]::UTF8.GetBytes('AGENT_VERSION = "0.3.43"')
  'agent/windows.ps1'=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.43"')
  'install/linux.sh'=[Text.Encoding]::UTF8.GetBytes('#!/bin/sh')
  'install/windows.ps1'=[IO.File]::ReadAllBytes($PSCommandPath)
}
Set-MockMeta
$valid=Get-VerifiedReleaseBeforeEnrollment
if ($valid.Version -ne '0.3.43' -or -not (Test-Path -LiteralPath $valid.Agent)) { throw 'R11_VALID_PRE_ENROLL_FAILED' }
Remove-Item -LiteralPath $valid.Stage -Recurse -Force
Write-Output 'WINDOWS_R11_VALID_BUNDLE_BEFORE_ENROLL=PASS'

$script:MockAssets['agent/linux.py']=[Text.Encoding]::UTF8.GetBytes('tampered')
$blocked=$false
try { Get-VerifiedReleaseBeforeEnrollment | Out-Null }
catch { $blocked=([string]$_.Exception.Message -eq 'RELEASE_ASSET_DIGEST_MISMATCH:agent/linux.py') }
if (-not $blocked) { throw 'R11_LINUX_ASSET_TAMPER_ACCEPTED' }
Write-Output 'WINDOWS_R11_LINUX_ASSET_TAMPER=DENIED'

$script:MockAssets['agent/linux.py']=[Text.Encoding]::UTF8.GetBytes('AGENT_VERSION = "0.3.43"')
$script:MockAssets['agent/windows.ps1']=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.44"')
Set-MockMeta
$blocked=$false
try { Get-VerifiedReleaseBeforeEnrollment | Out-Null }
catch { $blocked=([string]$_.Exception.Message -eq 'AGENT_VERSION_MANIFEST_MISMATCH') }
if (-not $blocked) { throw 'R11_AGENT_VERSION_TAMPER_ACCEPTED' }
Write-Output 'WINDOWS_R11_AGENT_VERSION_MISMATCH=DENIED'

$signature=[pscustomobject]@{schema='hara.commander-release-signature.v1';alg='RS256';kid='commander-release-v1'}
$blocked=$false
try { Assert-ReleaseManifestSignature ([byte[]](1,2,3)) $signature }
catch { $blocked=([string]$_.Exception.Message -eq 'RELEASE_SIGNATURE_KID_MISMATCH') }
if (-not $blocked) { throw 'R11_SIGNATURE_KID_MISMATCH_ACCEPTED' }
Write-Output 'WINDOWS_R11_SIGNATURE_KID_MISMATCH=DENIED'

Write-Output 'WINDOWS_R11_NO_INSTALL_OR_ENROLL=PASS'
