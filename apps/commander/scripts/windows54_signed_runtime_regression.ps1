param()
$ErrorActionPreference="Stop"
$Box="C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1"
if ((Get-CimInstance Win32_ComputerSystemProduct).UUID -ne "d35599c8-b9ea-45e5-9ae9-fa047e84b8ba") {throw "QA_UUID_MISMATCH"}
if ($PSVersionTable.PSEdition -ne "Desktop" -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) {throw "QA_PS51_REQUIRED"}
$Agent=Join-Path $Box "private-054-rc-r1\agent\windows.ps1"
$PatchSHA="fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62"
function Hash([string]$P){return (Get-FileHash -LiteralPath $P -Algorithm SHA256).Hash.ToLowerInvariant()}
if ((Hash $Agent) -ne $PatchSHA){throw "PATCH_SHA_MISMATCH"}
$Tokens=$null;$Errors=$null
$Ast=[System.Management.Automation.Language.Parser]::ParseFile($Agent,[ref]$Tokens,[ref]$Errors)
if ($Errors.Count -gt 0){throw "PATCH_PARSE_FAILED"}
foreach($Name in @("Set-RuntimeStatus","Try-SetRuntimeStatus")){
 $Fn=$Ast.FindAll({param($Node) $Node -is [System.Management.Automation.Language.FunctionDefinitionAst]},$true)|Where-Object Name -eq $Name
 if (@($Fn).Count -ne 1){throw "FIXTURE_AST_NOT_UNIQUE"}
 Invoke-Expression $Fn.Extent.Text
}
$Root=Join-Path $Box ("runtime-status-regression-"+[guid]::NewGuid().ToString("N"))
New-Item -Path $Root -ItemType Directory|Out-Null
$RuntimeStatus=Join-Path $Root "runtime-status.json"
$AgentVersion="0.3.54"
$Foreign=Join-Path $Box ("foreign-sentinel-"+[guid]::NewGuid().ToString("N")+".txt")
[IO.File]::WriteAllText($Foreign,"must-remain")
$ForeignHash=Hash $Foreign
$AclBefore=(Get-Acl -LiteralPath $Root).Sddl
$Results=New-Object System.Collections.Generic.List[object]
function Seed{
 Remove-Item -LiteralPath ($RuntimeStatus+".tmp") -Recurse -Force -ErrorAction SilentlyContinue
 [IO.File]::WriteAllText($RuntimeStatus,'{"schema_version":1,"agent_version":"0.3.54","started_at_utc":"A","last_successful_heartbeat_at_utc":"H0","last_runtime_error_code":"E0","last_runtime_error_at_utc":"T0","updated_at_utc":"U0"}')
}
function Values{
 $V=Get-Content -LiteralPath $RuntimeStatus -Raw|ConvertFrom-Json
 return @([string]$V.started_at_utc,[string]$V.last_successful_heartbeat_at_utc,[string]$V.last_runtime_error_code,[string]$V.last_runtime_error_at_utc)
}
function Check([string]$Name,[bool]$Ok){
 $Results.Add([pscustomobject]@{name=$Name;pass=$Ok})
 if(-not $Ok){throw ("REGRESSION_FAILED_"+$Name)}
}
function Equal([string[]]$Expected){$Actual=Values;return (($Actual -join "|") -ceq ($Expected -join "|"))}
try{
 foreach($Setter in @("Set-RuntimeStatus","Try-SetRuntimeStatus")){
  Seed
  & $Setter -HeartbeatAt "H1"|Out-Null
  Check ($Setter+"_heartbeat_preserves") (Equal @("A","H1","E0","T0"))
  & $Setter -ErrorCode "E1" -ErrorAt "T1"|Out-Null
  Check ($Setter+"_error_preserves") (Equal @("A","H1","E1","T1"))
  & $Setter -StartedAt "B"|Out-Null
  Check ($Setter+"_startup_preserves_history") (Equal @("B","H1","E1","T1"))
  & $Setter|Out-Null
  Check ($Setter+"_omitted_preserves_all") (Equal @("B","H1","E1","T1"))
  $Map=@{StartedAt=0;HeartbeatAt=1;ErrorCode=2;ErrorAt=3}
  foreach($Field in @("StartedAt","HeartbeatAt","ErrorCode","ErrorAt")){
   foreach($Clear in @("empty","null")){
    Seed
    $Arguments=@{};if($Clear -eq "null"){$Arguments[$Field]=$null}else{$Arguments[$Field]=""}
    & $Setter @Arguments|Out-Null
    $Expected=@("A","H0","E0","T0");$Expected[$Map[$Field]]=""
    Check ($Setter+"_"+$Field+"_"+$Clear+"_clears_only_field") (Equal $Expected)
   }
  }
 }
 Seed
 Try-SetRuntimeStatus -HeartbeatAt "H2" -ErrorCode "" -ErrorAt ""|Out-Null
 Check "heartbeat_success_explicit_clear" (Equal @("A","H2","",""))
 $Source=Get-Content -LiteralPath $Agent -Raw
 $Matches=[regex]::Matches($Source,'Try-SetRuntimeStatus -HeartbeatAt \([^\r\n]+ -ErrorCode "" -ErrorAt ""')
 Check "both_heartbeat_recovery_callsites" ($Matches.Count -eq 2)
 Remove-Item -LiteralPath $RuntimeStatus -Force
 $Ok=Try-SetRuntimeStatus -StartedAt "new"
 Check "missing_creates_parseable_leaf" ($Ok -and (Test-Path $RuntimeStatus -PathType Leaf) -and ((Values)[0] -ceq "new"))
 [IO.File]::WriteAllText($RuntimeStatus,"corrupt")
 $Ok=Try-SetRuntimeStatus -StartedAt "recovered"
 Check "corrupt_recovers_valid_leaf" ($Ok -and ((Values)[0] -ceq "recovered"))
 Seed;$Before=Hash $RuntimeStatus
 New-Item -Path ($RuntimeStatus+".tmp") -ItemType Directory|Out-Null
 $Ok=Try-SetRuntimeStatus -StartedAt "should-not-write"
 Check "temp_write_failure_preserves_previous" (-not $Ok -and (Hash $RuntimeStatus) -eq $Before)
 Remove-Item -LiteralPath ($RuntimeStatus+".tmp") -Recurse -Force
 Seed;$Before=Hash $RuntimeStatus
 $Locked=[IO.File]::Open($RuntimeStatus,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try{$Ok=Try-SetRuntimeStatus -StartedAt "should-not-replace"}finally{$Locked.Dispose()}
 Check "replace_failure_preserves_previous" (-not $Ok -and (Hash $RuntimeStatus) -eq $Before)
 Remove-Item -LiteralPath ($RuntimeStatus+".tmp") -Force -ErrorAction SilentlyContinue
 Check "fixture_directory_acl_unchanged" ((Get-Acl -LiteralPath $Root).Sddl -eq $AclBefore)
 Check "runtime_file_inherits_acl" (-not (Get-Acl -LiteralPath $RuntimeStatus).AreAccessRulesProtected)
 Check "foreign_sibling_unchanged" ((Hash $Foreign) -eq $ForeignHash)
 $TargetAsDir=Join-Path $Root "invalid-status-target"
 New-Item -Path $TargetAsDir -ItemType Directory|Out-Null
 $RuntimeStatus=$TargetAsDir
 $Returned=Try-SetRuntimeStatus -StartedAt "directory-target"
 $DirectoryAnomaly=($Returned -and -not (Test-Path -LiteralPath $RuntimeStatus -PathType Leaf))
 Check "existing_directory_behavior_recorded" $DirectoryAnomaly
 [pscustomobject]@{state="PASS";case_count=$Results.Count;cases=$Results;edition=$PSVersionTable.PSEdition;version=$PSVersionTable.PSVersion.ToString();source_sha256=$PatchSHA;scope="exact_AST_functions_unique_isolated_fixture";canonical_clear_value="empty_string";current_directory_target_limit_reproduced=$DirectoryAnomaly;atomic_durability_claimed=$false;installed_agent_modified=$false;primary_vm_modified=$false}|ConvertTo-Json -Depth 5 -Compress
}catch{
 [pscustomobject]@{state="FAIL";case_count=$Results.Count;cases=$Results;error_code=($_.Exception.Message -replace '[^A-Za-z0-9_:-]','');source_sha256=$PatchSHA}|ConvertTo-Json -Depth 5 -Compress
 exit 1
}finally{
 Remove-Item -LiteralPath $Root -Recurse -Force -ErrorAction SilentlyContinue
 Remove-Item -LiteralPath $Foreign -Force -ErrorAction SilentlyContinue
}
