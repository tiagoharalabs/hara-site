# Isolated import-scope probe only; never runs the canary main body or Agent top level.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$HelperFile,[Parameter(Mandatory=$true)][string]$BundleRoot)
$ErrorActionPreference='Stop'
$helperSha=(Get-FileHash -LiteralPath $HelperFile -Algorithm SHA256).Hash.ToLowerInvariant()
if($helperSha -cne '71d617c2a665b0787612192bab0f5b0bfc11f401ee75a4c2d660ab01a4ea18fb'){throw 'IMPORT_PROBE_HELPER_HASH_INVALID'}
$source=Join-Path $BundleRoot 'agent\windows.ps1'
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'f54e5ff8c170e09a3dc795004af426851d111c89ae78408559886e0d693bf805'){throw 'IMPORT_PROBE_SOURCE48_HASH_INVALID'}
$tok=$null;$errs=$null;$ast=[Management.Automation.Language.Parser]::ParseFile($HelperFile,[ref]$tok,[ref]$errs)
if(@($errs).Count){throw 'IMPORT_PROBE_HELPER_PARSE_FAILED'}
$defs=@($ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq 'Import-ReviewedMarkerLock'},$true))
if($defs.Count -ne 1){throw 'IMPORT_PROBE_IMPORT_FUNCTION_MISSING'}
Set-Item -Path 'Function:script:Import-ReviewedMarkerLock' -Value ($defs[0].Body.GetScriptBlock())
$Root=Join-Path ([IO.Path]::GetTempPath()) ('hara-marker-import-synthetic-'+[guid]::NewGuid().ToString('N'))
$script:PendingApprovalPath=Join-Path $Root 'synthetic-pending-never-created.json'
# Import returns before we check the two functions; no function reads any live profile here.
Import-ReviewedMarkerLock
foreach($name in @('Get-Utf8Sha256','Invoke-WithLocalApprovalLock')){
 if(-not(Get-Command $name -CommandType Function -ErrorAction SilentlyContinue)){throw 'IMPORT_PROBE_FUNCTION_UNAVAILABLE_AFTER_RETURN'}
}
$aHash=Get-Utf8Sha256 'a'
if([string]$aHash -cne 'ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb'){throw 'IMPORT_PROBE_A_ARGUMENT_BINDING_FAILED'}
$knownHash=Get-Utf8Sha256 'SYNTHETIC'
if([string]$knownHash -cne '6ffbbe12c3d609cbd5297aa4418f8371ce1ee554ce8b6919fee54d90398d44db'){throw 'IMPORT_PROBE_NONEMPTY_ARGUMENT_BINDING_FAILED'}
$lockResult=@(Invoke-WithLocalApprovalLock {'SYNTHETIC_LOCK_OK'})
if($lockResult.Count -ne 1 -or [string]$lockResult[0] -cne 'SYNTHETIC_LOCK_OK'){throw 'IMPORT_PROBE_SCRIPTBLOCK_ARGUMENT_BINDING_FAILED'}
[ordered]@{state='PASS';helper_sha256=$helperSha;functions_available_after_import_return=$true;nonempty_hash_argument_bound=$true;lock_scriptblock_argument_bound=$true;synthetic_paths_only=$true;canary_main_executed=$false;agent_top_level_executed=$false;live_profile_touched=$false;task_apis_called=$false}|ConvertTo-Json -Compress
