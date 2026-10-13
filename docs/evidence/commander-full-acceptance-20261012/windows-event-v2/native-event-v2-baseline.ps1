param([string]$Stage)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$env:LOCALAPPDATA=Join-Path $Stage 'profile'
New-Item -ItemType Directory -Path (Join-Path $env:LOCALAPPDATA 'HARA Commander') -Force|Out-Null
Copy-Item -LiteralPath (Join-Path $Stage 'stable_windows.ps1') -Destination (Join-Path $env:LOCALAPPDATA 'HARA Commander\hara-commander-agent.ps1') -Force
$checks=New-Object Collections.Generic.List[object]
function Check([string]$CheckLabel,[scriptblock]$Test){
 try{& $Test; $checks.Add([ordered]@{name=$CheckLabel;passed=$true})}
 catch{$checks.Add([ordered]@{name=$CheckLabel;passed=$false;error=[string]$_.Exception.Message})}
}
foreach($name in @('event_v2_windows_transport.ps1','event_v2_windows_agent.ps1','windows_agent_rc.ps1','install_windows_rc.ps1','stable_windows.ps1')){
 Check ('parser_'+$name) {
  $tok=$null;$err=$null
  [Management.Automation.Language.Parser]::ParseFile((Join-Path $Stage $name),[ref]$tok,[ref]$err)|Out-Null
  if($err.Count){throw ('PARSE_ERRORS_'+$err.Count+':'+(($err|Select-Object -First 4|ForEach-Object {('line'+$_.Extent.StartLineNumber+':'+$_.Message)}) -join '|'))}
 }
}
foreach($name in @('event_v2_windows_transport.ps1','event_v2_windows_agent.ps1')){
 Check ('selftest_'+$name) {
  $p=Start-Process -FilePath "$PSHOME\powershell.exe" -ArgumentList ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+(Join-Path $Stage $name)+'" -SelfTest') -Wait -PassThru -RedirectStandardOutput (Join-Path $Stage ($name+'.out')) -RedirectStandardError (Join-Path $Stage ($name+'.err'))
  if($p.ExitCode-ne 0){throw ('SELFTEST_EXIT_'+$p.ExitCode+':'+(Get-Content -Raw -LiteralPath (Join-Path $Stage ($name+'.err'))))}
 }
}
$src=Get-Content -Raw -LiteralPath (Join-Path $Stage 'event_v2_windows_agent.ps1')
$src=$src.Replace('$Here = Split-Path -Parent $MyInvocation.MyCommand.Path',('$Here = '+[char]39+$Stage+[char]39))
$at=$src.LastIndexOf('if ($AgentSelfTestRequested)')
if($at-lt 0){throw 'ADAPTER_IMPORT_BOUNDARY_ABSENT'}
. ([scriptblock]::Create($src.Substring(0,$at)))
Check 'stable_functions_exported' {
 foreach($name in @('Get-PlainText','Get-SafeErrorCode','Get-Catalog','Invoke-LocalFunction','Get-Utf8Sha256','Send-Json','Complete-Call')){
  if(-not (Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)){throw ('IMPORTED_FUNCTION_MISSING:'+ $name)}
 }
}
Check 'native_framework_reconnect_rng' {
 foreach($i in 0..31){$d=Get-ReconnectDelaySeconds $i;if($d-lt 0-or$d-gt 15){throw 'JITTER_RANGE'}}
}
$result=[ordered]@{schema='hara.commander.windows.event-v2-native-baseline.v1';utc=[DateTime]::UtcNow.ToString('o');powershell=$PSVersionTable.PSVersion.ToString();clr=[Environment]::Version.ToString();runtime_fixture_root=$Stage;founder_runtime_mutated=$false;cloud_connections_attempted=$false;passed=@($checks|Where-Object passed).Count;failed=@($checks|Where-Object {-not $_.passed}).Count;checks=$checks}
$result|ConvertTo-Json -Depth 10 -Compress
