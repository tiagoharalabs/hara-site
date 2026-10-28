param([string]$Candidate=(Join-Path $PSScriptRoot 'windows.source-only-candidate.ps1'))
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
if($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'NATIVE_WINDOWS_POWERSHELL_51_REQUIRED'}
# Negative-path source regression only. Uses an ephemeral fixture signing key,
# fake download functions and a prompt sentinel. It never authenticates, pairs,
# registers a task or writes a product configuration.
$source=[IO.File]::ReadAllText($Candidate)
$tokens=$null;$errors=$null
$ast=[Management.Automation.Language.Parser]::ParseInput($source,[ref]$tokens,[ref]$errors)
if($errors.Count){throw 'CANDIDATE_SYNTAX_INVALID'}
foreach($fn in $ast.FindAll({param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst]},$false)){
  . ([scriptblock]::Create($fn.Extent.Text))
}
$tailAt=$source.IndexOf('if ($Action -ne "install")')
if($tailAt -lt 0){throw 'INSTALL_TAIL_MISSING'}
$installBody=[scriptblock]::Create($source.Substring($tailAt))
$fixtureRoot=Join-Path $env:TEMP ('hara-pairing-preflight-regression-'+[guid]::NewGuid().ToString('N'))
[void][IO.Directory]::CreateDirectory($fixtureRoot)
$oldTemp=$env:TEMP;$oldRelease=$env:HARA_COMMANDER_RELEASE_URL
$rsa=[Security.Cryptography.RSA]::Create();$rsa.KeySize=2048
function Fixture-B64([byte[]]$Value){[Convert]::ToBase64String($Value).TrimEnd('=').Replace('+','-').Replace('/','_')}
function Fixture-Sha([byte[]]$Value){$h=[Security.Cryptography.SHA256]::Create();try{[BitConverter]::ToString($h.ComputeHash($Value)).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function Read-Host {param([string]$Prompt,[switch]$AsSecureString) $script:PromptCount++;throw 'FIXTURE_PAIRING_PROMPT_REACHED'}
function Invoke-WebRequest {
  param([string]$Uri,[string]$OutFile,[switch]$UseBasicParsing,[int]$TimeoutSec,[int]$MaximumRedirection)
  if($Uri.EndsWith('/release/agent-manifest.sig.json')){$bytes=$script:FixtureSignature}
  elseif($Uri.EndsWith('/release/agent-manifest.json')){$bytes=$script:FixtureManifest}
  elseif($Uri.EndsWith('/agent/windows.ps1')){if($script:FixtureDownloadFailure){throw 'FIXTURE_DOWNLOAD_FAILURE'};$bytes=$script:FixturePayload}
  else{throw 'UNEXPECTED_FIXTURE_DOWNLOAD_URI'}
  [IO.File]::WriteAllBytes($OutFile,$bytes)
}
function Invoke-RestMethod {
  param([string]$Uri,[string]$Method,[string]$ContentType,$Headers,$Body,[int]$TimeoutSec,[int]$MaximumRedirection)
  if($Uri.EndsWith('/api/health')){return @{ok=$true;service='hara-commander'}}
  if($Uri.EndsWith('/api/device/enroll')){$script:EnrollmentCount++}
  throw 'UNEXPECTED_FIXTURE_API_CALL'
}
$results=@()
try{
  $env:TEMP=$fixtureRoot;$BaseUrl='https://commander.fixture.invalid'
  $env:HARA_COMMANDER_RELEASE_URL=$BaseUrl+'/releases/0.3.56'
  $Root=Join-Path $fixtureRoot 'product-must-remain-absent';$Agent=Join-Path $Root 'hara-commander-agent.ps1';$Config=Join-Path $Root 'device.json'
  $TaskName='HARA Commander Agent';$Action='install'
  $ReleaseSigningKid='commander-release-v2';$pub=$rsa.ExportParameters($false)
  $ReleaseSigningN=Fixture-B64 $pub.Modulus;$ReleaseSigningE=Fixture-B64 $pub.Exponent
  $good=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.56"'+"`n# A`nexit 0`n")
  $cases=@(
    @{name='same_size_hash_mismatch';expected='AGENT_SHA256_MISMATCH';prompts=0},
    @{name='size_mismatch';expected='AGENT_SIZE_MISMATCH';prompts=0},
    @{name='invalid_signature';expected='AGENT_RELEASE_SIGNATURE_INVALID';prompts=0},
    @{name='syntax_failure';expected='AGENT_INSTALL_SYNTAX_INVALID';prompts=0},
    @{name='self_test_failure';expected='AGENT_SELF_TEST_FAILED';prompts=0},
    @{name='payload_version_mismatch';expected='AGENT_VERSION_MANIFEST_MISMATCH';prompts=0},
    @{name='download_failure';expected='FIXTURE_DOWNLOAD_FAILURE';prompts=0},
    @{name='valid_payload_reaches_prompt';expected='FIXTURE_PAIRING_PROMPT_REACHED';prompts=1},
    @{name='valid_preflight_report';expected='';prompts=0}
  )
  foreach($case in $cases){
    $script:PromptCount=0;$script:EnrollmentCount=0;$script:FixtureDownloadFailure=$false
    [byte[]]$signedPayload=$good.Clone();[byte[]]$script:FixturePayload=$good.Clone()
    switch($case.name){
      'same_size_hash_mismatch' {$script:FixturePayload=[Text.Encoding]::UTF8.GetBytes([Text.Encoding]::UTF8.GetString($good).Replace('# A','# B'))}
      'size_mismatch' {$script:FixturePayload=[byte[]]($good+10)}
      'syntax_failure' {$signedPayload=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.56"'+"`nif (`n");$script:FixturePayload=$signedPayload}
      'self_test_failure' {$signedPayload=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.56"'+"`nexit 37`n");$script:FixturePayload=$signedPayload}
      'payload_version_mismatch' {$signedPayload=[Text.Encoding]::UTF8.GetBytes('$AgentVersion = "0.3.55"'+"`nexit 0`n");$script:FixturePayload=$signedPayload}
      'download_failure' {$script:FixtureDownloadFailure=$true}
    }
    $files=@();foreach($path in @('agent/linux.py','agent/windows.ps1','install/linux.sh','install/windows.ps1')){
      $files+=@{path=$path;sha256=$(if($path -eq 'agent/windows.ps1'){Fixture-Sha $signedPayload}else{'a'*64});bytes=$(if($path -eq 'agent/windows.ps1'){$signedPayload.Length}else{1})}
    }
    $manifest=@{schema='hara.commander-agent-release.v1';product='H.A.R.A. Commander';channel='stable';agent_version='0.3.56';files=$files}
    $script:FixtureManifest=[Text.Encoding]::UTF8.GetBytes(($manifest|ConvertTo-Json -Depth 5 -Compress))
    $sig=$rsa.SignData($script:FixtureManifest,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
    if($case.name -eq 'invalid_signature'){$sig[0]=$sig[0] -bxor 1}
    $signature=@{schema='hara.commander-release-signature.v1';alg='RS256';kid=$ReleaseSigningKid;manifest_sha256=(Fixture-Sha $script:FixtureManifest);signature=(Fixture-B64 $sig)}
    $script:FixtureSignature=[Text.Encoding]::UTF8.GetBytes(($signature|ConvertTo-Json -Compress))
    $actual='';$report=$null
    try{if($case.name -eq 'valid_preflight_report'){$report=Invoke-Preflight|ConvertFrom-Json}else{& $installBody|Out-Null}}catch{$actual=$_.Exception.Message}
    $leftovers=@(Get-ChildItem -LiteralPath $fixtureRoot -Filter 'hara-commander-*' -File)
    $pass=($actual -ceq $case.expected -and $script:PromptCount -eq $case.prompts -and $script:EnrollmentCount -eq 0 -and $leftovers.Count -eq 0 -and -not (Test-Path -LiteralPath $Root))
    if($case.name -eq 'valid_preflight_report'){$pass=$pass -and [bool]$report.agent_payload -and [bool]$report.agent_payload_syntax -and [bool]$report.agent_payload_self_test}
    $results+=[ordered]@{case=$case.name;pass=$pass;actual=$actual;prompt_calls=$script:PromptCount;enrollment_calls=$script:EnrollmentCount;leftover_files=$leftovers.Count}
  }
  $failed=@($results|Where-Object {-not $_.pass})
  [ordered]@{schema='hara.commander.source-pairing-preflight-regression.v1';state=$(if($failed.Count){'FAIL'}else{'PASS'});fixture_only=$true;real_enrollment=$false;native_installed_product_test=$false;results=$results}|ConvertTo-Json -Depth 5
  if($failed.Count){throw 'SOURCE_PREFLIGHT_REGRESSION_FAILED'}
}finally{
  $env:TEMP=$oldTemp;$env:HARA_COMMANDER_RELEASE_URL=$oldRelease;$rsa.Dispose()
  if(Test-Path -LiteralPath $fixtureRoot){Remove-Item -LiteralPath $fixtureRoot -Recurse -Force -ErrorAction Stop}
}
