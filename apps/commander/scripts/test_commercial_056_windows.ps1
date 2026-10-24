param([string]$AgentPath,[string]$InstallerPath)
$ErrorActionPreference='Stop'
if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
   $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){
 throw 'WINDOWS_POWERSHELL_51_REQUIRED'
}
$nativeOs=Get-CimInstance -ClassName Win32_OperatingSystem
if([int]$nativeOs.BuildNumber -lt 22000){throw 'WINDOWS_11_REQUIRED'}
$effectivePolicy=Get-ExecutionPolicy
if([string]$effectivePolicy -eq 'Bypass'){throw 'BYPASS_POLICY_REFUSED'}
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-commercial-056-native-'+[guid]::NewGuid().ToString('N'))
$priorLocal=$env:LOCALAPPDATA
$results=New-Object Collections.Generic.List[string]
function Check([bool]$ok,[string]$name){if(-not $ok){throw ('QA_FAILED_'+$name)};$results.Add($name)}
function Denied([scriptblock]$action,[string]$code){$seen=$false;try{& $action | Out-Null}catch{$seen=$_.Exception.Message.Contains($code)};Check $seen $code}
# No network or scheduled-task operation is permitted by this harness.
function Invoke-RestMethod {throw 'QA_NETWORK_FORBIDDEN'}
function Start-ScheduledTask {throw 'QA_TASK_START_FORBIDDEN'}
function Stop-ScheduledTask {throw 'QA_TASK_STOP_FORBIDDEN'}
try {
 New-Item -ItemType Directory -Path $qa | Out-Null
 $env:LOCALAPPDATA=$qa
 foreach($file in @($AgentPath,$InstallerPath)){
  $tokens=$null;$errors=$null
  [System.Management.Automation.Language.Parser]::ParseFile($file,[ref]$tokens,[ref]$errors) | Out-Null
  Check ($errors.Count -eq 0) ('PARSE_'+[IO.Path]::GetFileName($file))
 }
 $source=[IO.File]::ReadAllText($AgentPath)
 $cut=$source.IndexOf('if ($args -contains "--version")')
 Check ($cut -gt 0) 'ISOLATED_DECLARATIONS_BOUNDARY'
 # Only definitions/constant assignments before ALL dispatch/daemon code.
 . ([scriptblock]::Create($source.Substring(0,$cut)))
 Invoke-AgentSelfTest
 Check $true 'AGENT_SELF_TEST'
 $synthetic='qa-only-'+[guid]::NewGuid().ToString('N')
 $protected=ConvertFrom-SecureString (ConvertTo-SecureString $synthetic -AsPlainText -Force)
 Check ((Get-PlainText (ConvertTo-SecureString $protected)) -ceq $synthetic) 'NATIVE_DPAPI_ROUNDTRIP'
 $synthetic=$null;$protected=$null
 Check ($null -ne (Get-Command Get-ScheduledTask -ErrorAction Stop)) 'TASK_SCHEDULER_CMDLET_AVAILABLE_ONLY'
 $cfg=[pscustomobject]@{base_url='https://commander.invalid';device_id='device-a';tenant_id='tenant-a';architecture='test';encrypted_device_token='synthetic-protected-a';approval_mode='ASK_EVERY_ACTION'}
 New-Item -ItemType Directory -Path $Root -Force | Out-Null
 $cfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
 $context=Initialize-EnrollmentState $cfg
 $firstReceipts=$ReceiptDir
 Check ((Get-Acl (Split-Path $ReceiptDir)).AreAccessRulesProtected) 'ENROLLMENT_DIRECTORY_ACL_PROTECTED'
 foreach($field in @('device_id','tenant_id','encrypted_device_token','base_url')){
  $other=$cfg | Select-Object *
  $other.$field=if($field -eq 'base_url'){'https://other.invalid'}else{'other-context'}
  Check ((Get-EnrollmentContext $other) -cne $context) ('CONTEXT_'+$field)
 }
 foreach($url in @('http://commander.invalid','https://user:pass@commander.invalid','https://commander.invalid/path','https://commander.invalid/?q=x','https://commander.invalid/#fragment')){
  $bad=$cfg | Select-Object *;$bad.base_url=$url
  Denied {Get-EnrollmentContext $bad} 'COMMANDER_ORIGIN_INVALID'
 }
 $session=[ordered]@{schema='hara.commander-operator-session.v1';owner_pid=$PID;owner_started_at_utc=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o');started_at_utc=[DateTime]::UtcNow.ToString('o');enrollment_context=$context}
 $session | ConvertTo-Json -Compress | Set-Content -LiteralPath $SessionPath -Encoding UTF8
 Check ($null -ne (Get-OperatorSession)) 'BOUND_SESSION_ACTIVE'
 $other=$cfg | Select-Object *;$other.tenant_id='tenant-b'
 $other | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
 Check ($null -eq (Get-OperatorSession)) 'OTHER_TENANT_SESSION_DENIED'
 Denied {Invoke-Tool $cfg ([pscustomobject]@{tool_id='hara.health';payload=[pscustomobject]@{}})} 'ENROLLMENT_CHANGED_RESTART_REQUIRED'
 $cfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
 $session.Remove('enrollment_context')
 $session | ConvertTo-Json -Compress | Set-Content -LiteralPath $SessionPath -Encoding UTF8
 Check ($null -eq (Get-OperatorSession)) 'LEGACY_SESSION_NOT_AUTHORITY'
 foreach($field in @('device_id','tenant_id')){
  $call=[pscustomobject]@{tool_id='hara.files.write';payload=[pscustomobject]@{path=(Join-Path $qa 'must-not-write');content='x'}}
  $call | Add-Member -NotePropertyName $field -NotePropertyValue 'foreign'
  Denied {Invoke-Tool $cfg $call} 'CALL_ENROLLMENT_MISMATCH'
 }
 Check (-not (Test-Path (Join-Path $qa 'must-not-write'))) 'FOREIGN_CALL_NO_EFFECT'
 $call=[pscustomobject]@{tool_id='hara.ping';request_id='synthetic';payload=[pscustomobject]@{}}
 $receipt=New-Receipt $cfg $call 'PASS' @{}
 Check ((Get-Receipt $receipt $cfg).device_id -ceq 'device-a') 'BOUND_RECEIPT_READ'
 Denied {Get-Receipt $receipt $other} 'RECEIPT_ENROLLMENT_MISMATCH'
 # Native process.run envelope, with a synthetic enrollment and no network.
 $processCfg=$cfg | Select-Object *;$processCfg.approval_mode='PERSISTENT_TRUSTED'
 $processCfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
 foreach($expected in @(0,7)){
  $processCall=[pscustomobject]@{call_id=('qa-native-'+$expected);request_id=('qa-native-'+$expected);tool_id='hara.process.run';payload=[pscustomobject]@{command=('cmd.exe /d /c exit '+$expected);cwd=$qa;timeout_ms=5000;max_lines=20}}
  $response=Invoke-Tool $processCfg $processCall
  $inner=$response.result.stdout | ConvertFrom-Json
  Check ($inner.exit_code -eq $expected -and $response.result.process_exit_code -eq $expected) ('NATIVE_PROCESS_RUN_ENVELOPE_EXIT_'+$expected)
  Check (-not $inner.timed_out -and -not $inner.session_retained) ('NATIVE_PROCESS_RUN_REAPED_'+$expected)
 }
 $cfg | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
 Write-ConsoleEvent 'OLD_SYNTHETIC_EVENT' $null 'PASS'
 $historyBefore=[IO.File]::ReadAllBytes($ConsoleEvents)
 [long]$liveCursor=Get-ConsoleStreamCursor
 Check (@(Read-NewConsoleEvents ([ref]$liveCursor)).Count -eq 0) 'REOPENED_FEED_STARTS_AT_EOF'
 Write-ConsoleEvent 'NEW_SYNTHETIC_EVENT' $null 'PASS'
 $fresh=@(Read-NewConsoleEvents ([ref]$liveCursor))
 Check ($fresh.Count -eq 1 -and $fresh[0].event -ceq 'NEW_SYNTHETIC_EVENT') 'FEED_NEW_EVENT_ONCE'
 Check (@(Read-NewConsoleEvents ([ref]$liveCursor)).Count -eq 0) 'FEED_NO_DUPLICATE'
 $historyAfter=[IO.File]::ReadAllBytes($ConsoleEvents)
 Check ([Convert]::ToBase64String($historyBefore) -ceq [Convert]::ToBase64String($historyAfter,0,$historyBefore.Length)) 'FEED_PRESERVES_HISTORY_BYTES'
 $legacy=Join-Path $Root 'console-events.jsonl'
 [IO.File]::WriteAllText($legacy,'{"at_utc":"2026-10-23T00:00:00Z","event":"OLD","action_summary":"synthetic-private-do-not-display"}'+"`n")
 $legacyHash=(Get-FileHash $legacy -Algorithm SHA256).Hash
 $display=Show-LegacyOperatorHistory 50 6>&1 | Out-String
 Check ($display.Contains('OLD') -and -not $display.Contains('synthetic-private-do-not-display')) 'LEGACY_HISTORY_SANITIZED'
 $other.device_id='device-b'
 $other | ConvertTo-Json -Compress | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
 Initialize-EnrollmentState $other | Out-Null
 Check ($ReceiptDir -cne $firstReceipts) 'OTHER_ENROLLMENT_STORAGE_SEPARATE'
 Initialize-LocalActivityStore
 $rows=@(Invoke-LocalDbQuery 'SELECT event_id FROM activity_events')
 Check ($rows.Count -eq 0) 'NO_LEGACY_HISTORY_IMPORTED'
 Check ((Get-FileHash $legacy -Algorithm SHA256).Hash -ceq $legacyHash) 'LEGACY_HISTORY_PRESERVED'
 $legacyDb=Join-Path $Root 'operations.sqlite3'
 [HaraWinSqlite]::Execute($legacyDb,'CREATE TABLE activity_events(event_id integer,at_utc text,event text,state text,tool_id text,function_id text,request_id text,error_code text,receipt_sha256 text)',@())
 [HaraWinSqlite]::Execute($legacyDb,"INSERT INTO activity_events(event_id,at_utc,event) VALUES(1,'2026-10-23T00:00:00Z','SQL_OLD')",@())
 $legacyDbHash=(Get-FileHash $legacyDb -Algorithm SHA256).Hash
 $display=Show-LegacyOperatorHistory 50 6>&1 | Out-String
 Check ($display.Contains('SQL_OLD')) 'LEGACY_SQLITE_READ_ONLY_VIEW'
 Check ((Get-FileHash $legacyDb -Algorithm SHA256).Hash -ceq $legacyDbHash) 'LEGACY_SQLITE_PRESERVED'
 $writeDenied=$false
 try{[HaraWinSqlite]::QueryReadOnly($legacyDb,'DELETE FROM activity_events',@()) | Out-Null}catch{$writeDenied=$true}
 Check $writeDenied 'SQLITE_READ_ONLY_FLAG_ENFORCED'
 Denied {Send-Json 'http://commander.invalid/api/device/heartbeat' 'synthetic' @{}} 'COMMANDER_ORIGIN_INVALID'
 # Native installer guard only; never execute installer dispatch.
 $tokens=$null;$errors=$null
 $tree=[System.Management.Automation.Language.Parser]::ParseFile($InstallerPath,[ref]$tokens,[ref]$errors)
 $guard=@($tree.FindAll({param($n)$n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Assert-AgentVersionFloor'},$true))
 Check ($guard.Count -eq 1) 'INSTALLER_GUARD_UNIQUE'
 . ([scriptblock]::Create($guard[0].Extent.Text))
 $Agent=Join-Path $qa 'synthetic-installed.ps1'
 [IO.File]::WriteAllText($Agent,'$AgentVersion = "0.3.57"')
 Denied {Assert-AgentVersionFloor '0.3.56'} 'AGENT_DOWNGRADE_REFUSED'
 [IO.File]::WriteAllText($Agent,'$AgentVersion = "0.3.55"')
 Assert-AgentVersionFloor '0.3.56'
 Check $true 'INSTALLER_MONOTONIC_UPGRADE_ALLOWED'
 @{state='PASS_NATIVE_WINDOWS_NO_INSTALL_NO_PAIR';windows_build=[string]$nativeOs.BuildNumber;execution_policy=[string]$effectivePolicy;task_lifecycle_accepted=$false;reboot_accepted=$false;ps_version=$PSVersionTable.PSVersion.ToString();checks=$results.Count;cases=@($results);installed=$false;paired=$false;network_used=$false} | ConvertTo-Json -Depth 5
} finally {
 $env:LOCALAPPDATA=$priorLocal
 if(Test-Path $qa){Remove-Item -LiteralPath $qa -Recurse -Force}
}
