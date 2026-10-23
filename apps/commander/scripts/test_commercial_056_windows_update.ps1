param([string]$InstallerPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/install/windows.ps1'))
# Execute only the update AST with synthetic files and scheduler/network fakes.
# This also runs on portable PowerShell; it is not Windows runtime acceptance.
$ErrorActionPreference='Stop'
$tokens=$null;$errors=$null
$tree=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $InstallerPath),[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'INSTALLER_PARSE_FAILED'}
foreach($definition in $tree.FindAll({param($n)$n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)){
 . ([scriptblock]::Create($definition.Extent.Text))
}
$update=@($tree.EndBlock.Statements | Where-Object {$_.Extent.Text.StartsWith('if ($Action -eq "update")')})
if($update.Count -ne 1){throw 'UPDATE_DISPATCH_NOT_UNIQUE'}
$statements=$update[0].Clauses[0].Item2.Statements | Where-Object {$_ -isnot [System.Management.Automation.Language.ExitStatementAst]}
$body=[scriptblock]::Create(($statements | ForEach-Object {$_.Extent.Text}) -join "`n")
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-056-windows-update-'+[guid]::NewGuid().ToString('N'))
$checks=New-Object Collections.Generic.List[string]
$failures=New-Object Collections.Generic.List[string]
function Check([bool]$ok,[string]$name){if(-not $ok){throw $name}}
function Get-InstalledDevice {return [pscustomobject]@{base_url='https://commander.invalid'}}
function Get-RuntimeStartedAt {return ('synthetic-start-'+$script:starts)}
function Show-Status {}
function Assert-AgentSelfTest([string]$Path) {}
function Assert-AgentIntegrity([string]$Path) {Assert-AgentVersionFloor '0.3.56'}
function Get-ReleaseBaseUrl {return 'https://release.invalid/0.3.56'}
function Invoke-WebRequest {
 [CmdletBinding()]param($Uri,$OutFile,[switch]$UseBasicParsing,$TimeoutSec,$MaximumRedirection)
 [IO.File]::WriteAllText($OutFile,'$AgentVersion = "0.3.56"')
}
function Get-ScheduledTask {
 [CmdletBinding()]param($TaskName)
 return [pscustomobject]@{State=$(if($script:running){'Running'}else{'Ready'})}
}
function Stop-ScheduledTask {
 [CmdletBinding()]param($TaskName)
 $script:running=$false
}
function Start-ScheduledTask {
 [CmdletBinding()]param($TaskName)
 $script:starts++
 if($script:scenario -eq 'both-starts-fail' -or
    ($script:scenario -eq 'start-fails' -and $script:starts -eq 1)){throw 'SYNTHETIC_START_FAILED'}
 $script:running=$true
}
function Start-Sleep {param($Seconds)}
function Wait-AgentStartup([string]$ExpectedVersion,[string]$PreviousStarted,[int]$Seconds=10){
 if($ExpectedVersion -eq '0.3.55'){$script:rollbackChecks++}
 if($script:scenario -eq 'rollback-attestation-fails'){return $false}
 if($ExpectedVersion -eq '0.3.56' -and $script:scenario -eq 'startup-fails'){return $false}
 return $script:running -and ([IO.File]::ReadAllText($Agent).Contains($ExpectedVersion))
}
function Move-Item {
 [CmdletBinding()]param([string]$Path,[string]$Destination,[switch]$Force)
 if($script:scenario -eq 'swap-fails' -and $Path.EndsWith('.update.ps1')){throw 'SYNTHETIC_SWAP_FAILED'}
 Microsoft.PowerShell.Management\Move-Item -LiteralPath $Path -Destination $Destination -Force:$Force
}
try {
 New-Item -ItemType Directory -Path $qa | Out-Null
 $Agent=Join-Path $qa 'version-guard.ps1'
 foreach($case in @(
  @{Name='guard-upgrade';Offer='0.3.56';Old='0.3.55';Error=$null},
  @{Name='guard-equal';Offer='0.3.56';Old='0.3.56';Error=$null},
  @{Name='guard-downgrade';Offer='0.3.56';Old='0.3.57';Error='AGENT_DOWNGRADE_REFUSED'},
  @{Name='guard-floor';Offer='0.3.54';Old='0.3.55';Error='BELOW_WINDOWS_FLOOR'},
  @{Name='guard-semver';Offer='0.3.056';Old='0.3.55';Error='INVALID_SEMVER'},
  @{Name='guard-unknown';Offer='0.3.56';Old='UNKNOWN';Error='INSTALLED_VERSION_UNKNOWN'})){
  [IO.File]::WriteAllText($Agent,('$AgentVersion = "'+$case.Old+'"'))
  $seen=$null
  try {Assert-AgentVersionFloor $case.Offer} catch {$seen=$_.Exception.Message}
  if($case.Error){Check ($seen -and $seen.Contains($case.Error)) $case.Name}
  else{Check ($null -eq $seen) $case.Name}
  $checks.Add($case.Name)
 }
 # Exercise the actual installer verifier with historical public fixtures only.
 # Its successful cryptographic check grants no version/admission authority.
 foreach($name in @('ReleaseSigningKid','ReleaseSigningN','ReleaseSigningE')){
  $assignment=@($tree.EndBlock.Statements | Where-Object {$_ -is [System.Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq ('$'+$name)})
  Check ($assignment.Count -eq 1) 'TRUST_ANCHOR_NOT_UNIQUE'
  $literal=@($assignment[0].Right.FindAll({param($n)$n -is [System.Management.Automation.Language.StringConstantExpressionAst]},$true))
  Check ($literal.Count -eq 1 -and $assignment[0].Right.Extent.Text -ceq $literal[0].Extent.Text) 'TRUST_ANCHOR_NOT_LITERAL'
  Set-Variable -Name $name -Value $literal[0].Value
 }
 $fixture=Join-Path $PSScriptRoot '../../../scripts/fixtures/commercial_v2_043_signature'
 $manifest=[IO.File]::ReadAllBytes((Join-Path $fixture 'agent-manifest.json'))
 foreach($case in @('historical-crypto-only','missing-signature','tampered-manifest','wrong-kid')){
  $signature=Get-Content -Raw (Join-Path $fixture 'agent-manifest.sig.json') | ConvertFrom-Json
  $bytes=$manifest
  if($case -eq 'missing-signature'){$signature=$null}
  if($case -eq 'tampered-manifest'){$bytes=[byte[]]($manifest+32)}
  if($case -eq 'wrong-kid'){$signature.kid='NOT_ADMITTED'}
  $seen=$null
  try {Assert-ReleaseManifestSignature $bytes $signature} catch {$seen=$_.Exception.Message}
  Check (($null -eq $seen) -eq ($case -eq 'historical-crypto-only')) ('SIGNATURE_'+$case)
  $checks.Add('signature-'+$case)
 }
 foreach($case in @('active-success','stopped-success','start-fails','startup-fails','swap-fails','both-starts-fail','rollback-attestation-fails')){
  $script:scenario=$case;$script:starts=0;$script:rollbackChecks=0
  $script:running=$case -ne 'stopped-success'
  $Root=Join-Path $qa $case;New-Item -ItemType Directory -Path $Root | Out-Null
  $Agent=Join-Path $Root 'agent.ps1';$Config=Join-Path $Root 'device.json'
  $RuntimeStatus=Join-Path $Root 'runtime-status.json';$TaskName='SYNTHETIC_TASK_ONLY'
  [IO.File]::WriteAllText($Agent,'$AgentVersion = "0.3.55"')
  [IO.File]::WriteAllText($Config,'{"synthetic":true}')
  $before=[IO.File]::ReadAllBytes($Agent);$seen=$null
  $outputLines=New-Object Collections.Generic.List[string]
  try {& $body 6>&1 | ForEach-Object {$outputLines.Add([string]$_)}} catch {$seen=$_.Exception.Message}
  $output=$outputLines -join "`n"
  try {
   if($case.EndsWith('-success')){
    Check ($null -eq $seen) ('UNEXPECTED_FAILURE_'+$seen)
    Check ([IO.File]::ReadAllText($Agent).Contains('0.3.56')) 'UPGRADE_BYTES_NOT_INSTALLED'
    Check ($script:starts -eq $(if($case -eq 'active-success'){1}else{0})) 'MANUAL_STOP_NOT_PRESERVED'
   } else {
    Check ($null -ne $seen) 'FAILURE_WAS_NOT_PROPAGATED'
    Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Agent)) -ceq [Convert]::ToBase64String($before)) 'OLD_AGENT_NOT_RESTORED'
    Check (-not $output.Contains('HARA_COMMANDER_AGENT_UPDATE=PASS')) 'FALSE_UPDATE_PASS'
    if($case -in @('both-starts-fail','rollback-attestation-fails')){
     Check (-not $output.Contains('HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=PASS')) 'FALSE_ROLLBACK_PASS'
    } else {
     Check $script:running 'OLD_AGENT_NOT_RECOVERED'
     Check ($script:rollbackChecks -ge 1) 'ROLLBACK_STARTUP_NOT_ATTESTED'
    }
   }
   Check (Test-Path -LiteralPath ($Agent+'.rollback') -PathType Leaf) 'ROLLBACK_PREIMAGE_MISSING'
   Check ([Convert]::ToBase64String([IO.File]::ReadAllBytes($Agent+'.rollback')) -ceq [Convert]::ToBase64String($before)) 'ROLLBACK_PREIMAGE_CHANGED'
   $checks.Add($case)
  } catch {$failures.Add($case+':'+$_.Exception.Message)}
 }
 @{state=$(if($failures.Count){'FAIL'}else{'PASS_POWERSHELL_MOCKED_LIFECYCLE_ONLY'});
   checks=$checks.Count;passed=@($checks);failures=@($failures);installed=$false;network_used=$false;
   windows_runtime_acceptance=$false} | ConvertTo-Json -Depth 4
 if($failures.Count){exit 1}
} finally {
 if(Test-Path -LiteralPath $qa){Remove-Item -LiteralPath $qa -Recurse -Force}
}
