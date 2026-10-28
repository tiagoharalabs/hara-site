[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$NativeReceiptPath)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$crOldBundle='ZnVuY3Rpb24gU3RhcnQtV2luZG93c1JlbGF5Q2hpbGQoJFN0YXRlLCRDZmcsW3N0cmluZ10kUm9sZSxbZG91YmxlXSROb3cpIHsKICAkc2VlZHM9aWYoJFJvbGUgLWNlcSAnZXhlY3V0b3InKXtAKCRTdGF0ZS5hYmFuZG9uZWQuVmFsdWVzKX1lbHNle0AoKX0KICAkd2FrZU5hbWU9aWYoJFN0YXRlLmV2ZW50VjJXYWtlKXtbc3RyaW5nXSRTdGF0ZS5ldmVudFYyV2FrZS5uYW1lfWVsc2V7JG51bGx9CiAgJHByb2Nlc3M9U3RhcnQtV2luZG93c1JlbGF5UHJvY2VzcyAkUm9sZSAkQ2ZnICRzZWVkcyAkU3RhdGUuYWdlbnRQYXRoICR3YWtlTmFtZQogICRTdGF0ZS5jaGlsZHJlblskUm9sZV09QHtwcm9jZXNzPSRwcm9jZXNzO2RlYWRsaW5lPSROb3crMzUuMDtyZWFkeT0kZmFsc2U7bmV0d29ya0JhY2tvZmY9JGZhbHNlO2NhbGw9JG51bGw7ZmVuY2VkPSRmYWxzZX0KfQoKZnVuY3Rpb24gU3RhcnQtV2luZG93c1JlbGF5UHJvY2Vzcyhbc3RyaW5nXSRSb2xlLCRDZmcsJEFiYW5kb25lZCxbc3RyaW5nXSRBZ2VudFBhdGgsW3N0cmluZ10kV2FrZU5hbWU9JG51bGwpIHsKICBJbml0aWFsaXplLVdpbmRvd3NSZWxheVByb2Nlc3NUeXBlCiAgJG5vbmNlPVtndWlkXTo6TmV3R3VpZCgpLlRvU3RyaW5nKCdOJykrW2d1aWRdOjpOZXdHdWlkKCkuVG9TdHJpbmcoJ04nKQogICRoYW5kc2hha2U9QHtzY2hlbWE9J2hhcmEuY29tbWFuZGVyLnJlbGF5LXdvcmtlci1oYW5kc2hha2UudjEnO25vbmNlPSRub25jZTthYmFuZG9uZWQ9QCgkQWJhbmRvbmVkKTtldmVudF92Ml93YWtlX25hbWU9JFdha2VOYW1lfSB8IENvbnZlcnRUby1Kc29uIC1EZXB0aCA2IC1Db21wcmVzcwogICRwYXJlbnRTdGFydD0oR2V0LVByb2Nlc3MgLUlkICRQSUQpLlN0YXJ0VGltZS5Ub1VuaXZlcnNhbFRpbWUoKS5Ub1N0cmluZygnbycpCiAgcmV0dXJuIE5ldy1PYmplY3QgSGFyYVJlbGF5UHJvY2VzcyAtQXJndW1lbnRMaXN0IChKb2luLVBhdGggJFBTSE9NRSAncG93ZXJzaGVsbC5leGUnKSwoW0lPLlBhdGhdOjpHZXRGdWxsUGF0aCgkQWdlbnRQYXRoKSksJFJvbGUsKFtzdHJpbmddJFBJRCksJHBhcmVudFN0YXJ0LChHZXQtRW5yb2xsbWVudENvbnRleHQgJENmZyksJG5vbmNlLCRoYW5kc2hha2UKfQoKZnVuY3Rpb24gUmVzdG9yZS1XaW5kb3dzUmVsYXlDbGFpbXMoJENsYWltcykgewogIGZvcmVhY2goJGNsYWltIGluIEAoJENsYWltcykpewogICAgaWYoW3N0cmluZ10kY2xhaW0uZmluZ2VycHJpbnQgLWNub3RtYXRjaCAnXlswLTlhLWZdezY0fSQnIC1vciAtbm90ICRjbGFpbS5jYWxsX2lkIC1vciAtbm90ICRjbGFpbS5yZXF1ZXN0X2lkIC1vciAoW3N0cmluZ10kY2xhaW0uY2FsbF9pZCkuTGVuZ3RoIC1ndCAxODAgLW9yIChbc3RyaW5nXSRjbGFpbS5yZXF1ZXN0X2lkKS5MZW5ndGggLWd0IDE4MCl7dGhyb3cgJ0NBTExfUkVDT1ZFUllfQklORElOR19JTlZBTElEJ30KICAgIEludm9rZS1XaXRoV2luZG93c1JlbGF5TG9jayB7CiAgICAgIEluaXRpYWxpemUtV2luZG93c1JlbGF5U3RvcmUKICAgICAgJHJvdz1AKEludm9rZS1Mb2NhbERiUXVlcnkgJ1NFTEVDVCBjYWxsX2lkLGZpbmdlcnByaW50IEZST00gd2luZG93c19yZWxheV9jYWxscyBXSEVSRSByZXF1ZXN0X2lkPT8nIEAoW3N0cmluZ10kY2xhaW0ucmVxdWVzdF9pZCkpCiAgICAgIGlmKCRyb3cuQ291bnQpewogICAgICAgIGlmKFtzdHJpbmddJHJvd1swXS5jYWxsX2lkIC1jbmUgW3N0cmluZ10kY2xhaW0uY2FsbF9pZCAtb3IgW3N0cmluZ10kcm93WzBdLmZpbmdlcnByaW50IC1jbmUgW3N0cmluZ10kY2xhaW0uZmluZ2VycHJpbnQpe3Rocm93ICdDQUxMX0lERU1QT1RFTkNZX0NPTkZMSUNUJ30KICAgICAgfSBlbHNlIHsKICAgICAgICBJbnZva2UtTG9jYWxEYkV4ZWMgJ0lOU0VSVCBJTlRPIHdpbmRvd3NfcmVsYXlfY2FsbHMocmVxdWVzdF9pZCxjYWxsX2lkLGZpbmdlcnByaW50LHBoYXNlLHVwZGF0ZWRfYXRfdXRjKSBWQUxVRVMoPyw/LD8sPyw/KScgQChbc3RyaW5nXSRjbGFpbS5yZXF1ZXN0X2lkLFtzdHJpbmddJGNsYWltLmNhbGxfaWQsW3N0cmluZ10kY2xhaW0uZmluZ2VycHJpbnQsJ1BSRVBBUklORycsW0RhdGVUaW1lXTo6VXRjTm93LlRvU3RyaW5nKCdvJykpCiAgICAgIH0KICAgIH0KICB9Cn0K'
$crOldBundleSha='eb9264fccbefc9f6358833d81f284605374ad867e1ce9ff2ff299707cd4fd37a'
$crNewBundle='ZnVuY3Rpb24gU3RhcnQtV2luZG93c1JlbGF5Q2hpbGQoJFN0YXRlLCRDZmcsW3N0cmluZ10kUm9sZSxbZG91YmxlXSROb3cpIHsKICAjIEFuIGVtcHR5IGlmLW91dHB1dCBiZWNvbWVzIG51bGwgYXQgdGhlIG5leHQgZnVuY3Rpb24gYm91bmRhcnkuCiAgIyBLZWVwIGFuIGFjdHVhbCBhcnJheSBzbyB0aGUgaGFuZHNoYWtlIGNhcnJpZXMgW10gaW5zdGVhZCBvZiBbbnVsbF0uCiAgW29iamVjdFtdXSRzZWVkcz1AKCkKICBpZigkUm9sZSAtY2VxICdleGVjdXRvcicpeyRzZWVkcz1AKCRTdGF0ZS5hYmFuZG9uZWQuVmFsdWVzKX0KICAkd2FrZU5hbWU9aWYoJFN0YXRlLmV2ZW50VjJXYWtlKXtbc3RyaW5nXSRTdGF0ZS5ldmVudFYyV2FrZS5uYW1lfWVsc2V7JG51bGx9CiAgJHByb2Nlc3M9U3RhcnQtV2luZG93c1JlbGF5UHJvY2VzcyAkUm9sZSAkQ2ZnICRzZWVkcyAkU3RhdGUuYWdlbnRQYXRoICR3YWtlTmFtZQogICRTdGF0ZS5jaGlsZHJlblskUm9sZV09QHtwcm9jZXNzPSRwcm9jZXNzO2RlYWRsaW5lPSROb3crMzUuMDtyZWFkeT0kZmFsc2U7bmV0d29ya0JhY2tvZmY9JGZhbHNlO2NhbGw9JG51bGw7ZmVuY2VkPSRmYWxzZX0KfQoKZnVuY3Rpb24gU3RhcnQtV2luZG93c1JlbGF5UHJvY2Vzcyhbc3RyaW5nXSRSb2xlLCRDZmcsJEFiYW5kb25lZCxbc3RyaW5nXSRBZ2VudFBhdGgsW3N0cmluZ10kV2FrZU5hbWU9JG51bGwpIHsKICBJbml0aWFsaXplLVdpbmRvd3NSZWxheVByb2Nlc3NUeXBlCiAgJG5vbmNlPVtndWlkXTo6TmV3R3VpZCgpLlRvU3RyaW5nKCdOJykrW2d1aWRdOjpOZXdHdWlkKCkuVG9TdHJpbmcoJ04nKQogICRoYW5kc2hha2U9QHtzY2hlbWE9J2hhcmEuY29tbWFuZGVyLnJlbGF5LXdvcmtlci1oYW5kc2hha2UudjEnO25vbmNlPSRub25jZTthYmFuZG9uZWQ9QCgkQWJhbmRvbmVkKTtldmVudF92Ml93YWtlX25hbWU9JFdha2VOYW1lfSB8IENvbnZlcnRUby1Kc29uIC1EZXB0aCA2IC1Db21wcmVzcwogICRwYXJlbnRTdGFydD0oR2V0LVByb2Nlc3MgLUlkICRQSUQpLlN0YXJ0VGltZS5Ub1VuaXZlcnNhbFRpbWUoKS5Ub1N0cmluZygnbycpCiAgcmV0dXJuIE5ldy1PYmplY3QgSGFyYVJlbGF5UHJvY2VzcyAtQXJndW1lbnRMaXN0IChKb2luLVBhdGggJFBTSE9NRSAncG93ZXJzaGVsbC5leGUnKSwoW0lPLlBhdGhdOjpHZXRGdWxsUGF0aCgkQWdlbnRQYXRoKSksJFJvbGUsKFtzdHJpbmddJFBJRCksJHBhcmVudFN0YXJ0LChHZXQtRW5yb2xsbWVudENvbnRleHQgJENmZyksJG5vbmNlLCRoYW5kc2hha2UKfQoKZnVuY3Rpb24gUmVzdG9yZS1XaW5kb3dzUmVsYXlDbGFpbXMoJENsYWltcykgewogIGZvcmVhY2goJGNsYWltIGluIEAoJENsYWltcykpewogICAgaWYoW3N0cmluZ10kY2xhaW0uZmluZ2VycHJpbnQgLWNub3RtYXRjaCAnXlswLTlhLWZdezY0fSQnIC1vciAtbm90ICRjbGFpbS5jYWxsX2lkIC1vciAtbm90ICRjbGFpbS5yZXF1ZXN0X2lkIC1vciAoW3N0cmluZ10kY2xhaW0uY2FsbF9pZCkuTGVuZ3RoIC1ndCAxODAgLW9yIChbc3RyaW5nXSRjbGFpbS5yZXF1ZXN0X2lkKS5MZW5ndGggLWd0IDE4MCl7dGhyb3cgJ0NBTExfUkVDT1ZFUllfQklORElOR19JTlZBTElEJ30KICAgIEludm9rZS1XaXRoV2luZG93c1JlbGF5TG9jayB7CiAgICAgIEluaXRpYWxpemUtV2luZG93c1JlbGF5U3RvcmUKICAgICAgJHJvdz1AKEludm9rZS1Mb2NhbERiUXVlcnkgJ1NFTEVDVCBjYWxsX2lkLGZpbmdlcnByaW50IEZST00gd2luZG93c19yZWxheV9jYWxscyBXSEVSRSByZXF1ZXN0X2lkPT8nIEAoW3N0cmluZ10kY2xhaW0ucmVxdWVzdF9pZCkpCiAgICAgIGlmKCRyb3cuQ291bnQpewogICAgICAgIGlmKFtzdHJpbmddJHJvd1swXS5jYWxsX2lkIC1jbmUgW3N0cmluZ10kY2xhaW0uY2FsbF9pZCAtb3IgW3N0cmluZ10kcm93WzBdLmZpbmdlcnByaW50IC1jbmUgW3N0cmluZ10kY2xhaW0uZmluZ2VycHJpbnQpe3Rocm93ICdDQUxMX0lERU1QT1RFTkNZX0NPTkZMSUNUJ30KICAgICAgfSBlbHNlIHsKICAgICAgICBJbnZva2UtTG9jYWxEYkV4ZWMgJ0lOU0VSVCBJTlRPIHdpbmRvd3NfcmVsYXlfY2FsbHMocmVxdWVzdF9pZCxjYWxsX2lkLGZpbmdlcnByaW50LHBoYXNlLHVwZGF0ZWRfYXRfdXRjKSBWQUxVRVMoPyw/LD8sPyw/KScgQChbc3RyaW5nXSRjbGFpbS5yZXF1ZXN0X2lkLFtzdHJpbmddJGNsYWltLmNhbGxfaWQsW3N0cmluZ10kY2xhaW0uZmluZ2VycHJpbnQsJ1BSRVBBUklORycsW0RhdGVUaW1lXTo6VXRjTm93LlRvU3RyaW5nKCdvJykpCiAgICAgIH0KICAgIH0KICB9Cn0K'
$crNewBundleSha='a03cdca1beeb5408f51e2b058cb2ccc6cfe0a3d6c7ce8c6726d6265b76656a7a'
$crReceiptAdmitted=$false
$crReport=[ordered]@{schema='hara.commander.windows-empty-claims-regression.v1';state='HOLD';started_utc=[DateTime]::UtcNow.ToString('o');native_powershell_binding_and_json=$true;process_constructor_mocked=$true;database_mocked=$true;network_calls=0;product_files_changed=$false;cases=@()}
function Need-CR([bool]$Condition,[string]$Code){if(-not $Condition){throw $Code}}
function Import-CR([string]$Encoded,[string]$Sha){
  $raw=[Convert]::FromBase64String($Encoded)
  $alg=[Security.Cryptography.SHA256]::Create()
  try{$actual=([BitConverter]::ToString($alg.ComputeHash($raw))).Replace('-','').ToLowerInvariant()}finally{$alg.Dispose()}
  Need-CR ($actual -ceq $Sha) 'REGRESSION_FUNCTION_BUNDLE_HASH_MISMATCH'
  $text=[Text.Encoding]::UTF8.GetString($raw);$tokens=$null;$errors=$null
  $ast=[Management.Automation.Language.Parser]::ParseInput($text,[ref]$tokens,[ref]$errors)
  Need-CR ($errors.Count -eq 0 -and $ast.EndBlock.Statements.Count -eq 3) 'REGRESSION_FUNCTION_BUNDLE_PARSE_FAILED'
  foreach($node in $ast.EndBlock.Statements){
    Need-CR ($node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -cin @('Start-WindowsRelayChild','Start-WindowsRelayProcess','Restore-WindowsRelayClaims')) 'REGRESSION_FUNCTION_BUNDLE_SCOPE_INVALID'
    $definition=[regex]::Replace($node.Extent.Text,('^function\s+'+[regex]::Escape($node.Name)+'(?=[(\s])'),('function script:'+$node.Name))
    . ([scriptblock]::Create($definition))
  }
}
function Initialize-WindowsRelayProcessType {}
function Get-EnrollmentContext($Cfg){return ('a'*64)}
function Invoke-WithWindowsRelayLock([scriptblock]$Action){$script:crLocks++;& $Action}
function Initialize-WindowsRelayStore {}
function Invoke-LocalDbQuery([string]$Sql,[object[]]$Values){return @()}
function Invoke-LocalDbExec([string]$Sql,[object[]]$Values){$script:crWrites++}
function New-CRClaim([string]$Id){return [pscustomobject]@{request_id=('request-'+$Id);call_id=('call-'+$Id);fingerprint=('b'*64)}}
function Produce-CR([string]$Role,[hashtable]$Abandoned){
  $state=@{agentPath='C:\HARA-QA-SYNTHETIC\agent.ps1';abandoned=$Abandoned;children=@{}}
  $cfg=[pscustomobject]@{base_url='https://example.invalid';device_id='QA-SYNTHETIC'}
  Start-WindowsRelayChild $state $cfg $Role 1.0
  Need-CR ($state.children.ContainsKey($Role)) 'PRODUCER_DID_NOT_RETURN_STUB_CHILD'
  $raw=[string]$state.children[$Role].process.Handshake
  return [pscustomobject]@{Raw=$raw;Value=($raw|ConvertFrom-Json)}
}
function Rejected-CR($Claims){
  $script:crLocks=0;$script:crWrites=0;$code=$null
  try{Restore-WindowsRelayClaims $Claims}catch{$code=[string]$_.Exception.Message}
  Need-CR ($code -ceq 'CALL_RECOVERY_BINDING_INVALID' -and $script:crLocks -eq 0 -and $script:crWrites -eq 0) 'MALFORMED_CLAIM_NOT_REJECTED_BEFORE_DATABASE'
}
function Case-CR([string]$Name){$crReport.cases+=@(@{name=$Name;state='PASS'})}
try{
  Need-CR ([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ceq 'S-1-5-21-1207901905-1500652706-889822281-1005' -and $env:USERPROFILE -ceq 'C:\Users\CommanderQA') 'EXPECTED_QA_IDENTITY_REQUIRED'
  $principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
  Need-CR (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) -and $PSVersionTable.PSVersion.Major -eq 5 -and $PSVersionTable.PSVersion.Minor -eq 1) 'LIMITED_NATIVE_POWERSHELL_51_REQUIRED'
  $NativeReceiptPath=[IO.Path]::GetFullPath($NativeReceiptPath)
  Need-CR ([IO.Path]::GetDirectoryName($NativeReceiptPath) -ieq 'C:\ProgramData\HARA-QA\windows-install-0356-20261028\results' -and [IO.Path]::GetFileName($NativeReceiptPath) -cmatch '^[A-Za-z0-9_.-]+\.json$' -and -not(Test-Path -LiteralPath $NativeReceiptPath)) 'REGRESSION_RECEIPT_PATH_REFUSED'
  $crReceiptAdmitted=$true
  Need-CR (-not('HaraRelayProcess' -as [type])) 'UNEXPECTED_EXISTING_PROCESS_TYPE'
  Add-Type -Language CSharp -TypeDefinition @'
public sealed class HaraRelayProcess {
  public readonly string Handshake;
  public HaraRelayProcess(string shell,string script,string role,string parentPid,string parentStart,string context,string nonce,string handshake) {Handshake=handshake;}
}
'@
  Import-CR $crOldBundle $crOldBundleSha
  $legacy=Produce-CR 'executor' @{}
  Need-CR ($legacy.Raw -cmatch '"abandoned":\[null\]' -and @($legacy.Value.abandoned).Count -eq 1) 'LEGACY_PARAMETER_BOUNDARY_BUG_NOT_REPRODUCED'
  Rejected-CR $legacy.Value.abandoned
  Case-CR 'legacy_empty_executor_becomes_null_claim_and_is_rejected'

  Import-CR $crNewBundle $crNewBundleSha
  foreach($role in @('executor','heartbeat','alerts')){
    $result=Produce-CR $role @{}
    Need-CR ($result.Raw -cmatch '"abandoned":\[\]' -and @($result.Value.abandoned).Count -eq 0) 'EMPTY_CLAIMS_ARRAY_NOT_PRESERVED'
    $script:crLocks=0;$script:crWrites=0
    Restore-WindowsRelayClaims $result.Value.abandoned
    Need-CR ($script:crLocks -eq 0 -and $script:crWrites -eq 0) 'EMPTY_CLAIMS_TOUCHED_DATABASE'
    Case-CR ('candidate_empty_'+$role+'_preserves_empty_array')
  }
  foreach($count in @(1,2)){
    $claims=@{}
    for($i=1;$i -le $count;$i++){$claims[[string]$i]=New-CRClaim ([string]$i)}
    $result=Produce-CR 'executor' $claims
    Need-CR (@($result.Value.abandoned).Count -eq $count) 'REAL_CLAIM_COUNT_CHANGED'
    foreach($wanted in $claims.Values){
      $found=@($result.Value.abandoned|Where-Object {$_.request_id -ceq $wanted.request_id})
      Need-CR ($found.Count -eq 1 -and $found[0].call_id -ceq $wanted.call_id -and $found[0].fingerprint -ceq $wanted.fingerprint) 'REAL_CLAIM_BINDING_CHANGED'
    }
    $script:crLocks=0;$script:crWrites=0
    Restore-WindowsRelayClaims $result.Value.abandoned
    Need-CR ($script:crLocks -eq $count -and $script:crWrites -eq $count) 'VALID_CLAIM_RESTORE_PATH_CHANGED'
    Case-CR ('candidate_preserves_'+$count+'_real_claims')
  }
  $result=Produce-CR 'executor' @{invalid=$null}
  Need-CR ($result.Raw -cmatch '"abandoned":\[null\]' -and @($result.Value.abandoned).Count -eq 1) 'MALFORMED_NULL_CLAIM_WAS_SILENTLY_DROPPED'
  Rejected-CR $result.Value.abandoned
  Case-CR 'candidate_preserves_and_rejects_malformed_null_claim'
  $badFingerprint=New-CRClaim 'bad-fingerprint';$badFingerprint.fingerprint='bad'
  Rejected-CR @($badFingerprint);Case-CR 'invalid_fingerprint_still_rejected'
  $missingId=New-CRClaim 'missing-id';$missingId.call_id=''
  Rejected-CR @($missingId);Case-CR 'missing_call_id_still_rejected'
  $oversized=New-CRClaim 'oversized';$oversized.request_id='x'*181
  Rejected-CR @($oversized);Case-CR 'oversized_request_id_still_rejected'
  Need-CR ($crReport.cases.Count -eq 10) 'REGRESSION_CASE_COUNT_UNEXPECTED'
  $crReport.state='PASS_NATIVE_EMPTY_CLAIMS_REGRESSION';$crReport.passed=$crReport.cases.Count
}catch{
  $message=[string]$_.Exception.Message
  $crReport.error_code=if($message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){$message}else{'EMPTY_CLAIMS_REGRESSION_FAILED'}
  $crReport.error_type=$_.Exception.GetType().Name
}finally{
  $crReport.finished_utc=[DateTime]::UtcNow.ToString('o')
  $crJson=$crReport|ConvertTo-Json -Depth 8 -Compress
  if($crReceiptAdmitted){
    $bytes=[Text.Encoding]::UTF8.GetBytes($crJson)
    $file=New-Object IO.FileStream($NativeReceiptPath,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::Read)
    try{$file.Write($bytes,0,$bytes.Length);$file.Flush($true)}finally{$file.Dispose()}
  }
}
$crJson
if($crReport.state -ceq 'PASS_NATIVE_EMPTY_CLAIMS_REGRESSION'){exit 0}
exit 2
