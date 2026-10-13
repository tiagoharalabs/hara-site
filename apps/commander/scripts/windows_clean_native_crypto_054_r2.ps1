[CmdletBinding()]
param([string]$BundleRoot='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1\private-054-rc-r2')
$ErrorActionPreference='Stop'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
$ProgressPreference='SilentlyContinue'
$Fixture='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
$Installer=Join-Path $BundleRoot 'install\windows.ps1'
$AgentFile=Join-Path $BundleRoot 'agent\windows.ps1'
$ExpectedInstaller='ea9f046bebf9ed85feefae05590ac915a75e9b491aefe1833d40bf316d414cc7'
$ExpectedAgent='fe61f177c51f6b6a01f31a3ea1b3d081173446e8f8cb33e680744c1fb808ae62'
$ExpectedManifest='e1c7c23de1b4313093e2d8c52be1ec52f6419f72d5ef59d675c7e5a279b1a13d'
if($PSVersionTable.PSEdition -ne 'Desktop' -or $PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1){throw 'QA_PS51_REQUIRED'}
$Checks=New-Object 'System.Collections.Generic.List[object]'
function Check([string]$Name,[bool]$Good){$Checks.Add([pscustomobject]@{name=$Name;pass=$Good});if(-not $Good){throw ('NATIVE_'+$Name.ToUpperInvariant()+'_FAILED')}}
function Reject-Signature([string]$Name,[byte[]]$Bytes,$Sig){$failed=$false;try{Assert-ReleaseManifestSignature $Bytes $Sig}catch{$failed=([string]$_.Exception.Message -ceq 'AGENT_RELEASE_SIGNATURE_INVALID')};Check $Name $failed}
Check 'installer_immutable' ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ExpectedInstaller)
Check 'agent_immutable' ((Get-FileHash -LiteralPath $AgentFile -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ExpectedAgent)
$tok=$null;$errors=$null;$Ast=[Management.Automation.Language.Parser]::ParseFile($Installer,[ref]$tok,[ref]$errors)
Check 'installer_parser' (@($errors).Count -eq 0)
foreach($name in @('ReleaseSigningKid','ReleaseSigningN','ReleaseSigningE')){
 $defs=@($Ast.EndBlock.Statements|Where-Object{$_ -is [Management.Automation.Language.AssignmentStatementAst] -and $_.Left.Extent.Text -ceq ('$'+$name)})
 Check ('key_'+$name+'_single') ($defs.Count -eq 1)
 Invoke-Expression $defs[0].Extent.Text
}
foreach($name in @('Convert-Base64UrlBytes','Assert-ReleaseManifestSignature','Assert-AgentSelfTest')){
 $defs=@($Ast.FindAll({param($n)$n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -ceq $name},$true))
 Check ('function_'+$name+'_single') ($defs.Count -eq 1)
 $re=New-Object Text.RegularExpressions.Regex('\Afunction\s+')
 Invoke-Expression ($re.Replace($defs[0].Extent.Text,'function script:',1))
}
$bytes=[IO.File]::ReadAllBytes((Join-Path $BundleRoot 'release\agent-manifest.json'))
Check 'manifest_immutable' ((Get-FileHash -LiteralPath (Join-Path $BundleRoot 'release\agent-manifest.json') -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $ExpectedManifest)
$sig=Get-Content -LiteralPath (Join-Path $BundleRoot 'release\agent-manifest.sig.json') -Raw|ConvertFrom-Json
Assert-ReleaseManifestSignature $bytes $sig;Check 'signed_manifest_positive' $true
$mutated=[byte[]]$bytes.Clone();$mutated[0]=$mutated[0] -bxor 1
Reject-Signature 'manifest_byte_tamper_rejected' $mutated $sig
$clone=$sig|ConvertTo-Json -Compress|ConvertFrom-Json;$clone.kid='invalid-key'
Reject-Signature 'wrong_key_id_rejected' $bytes $clone
$clone=$sig|ConvertTo-Json -Compress|ConvertFrom-Json;$clone.manifest_sha256=('0'*64)
Reject-Signature 'wrong_manifest_digest_rejected' $bytes $clone
$clone=$sig|ConvertTo-Json -Compress|ConvertFrom-Json;$clone.signature='AAAA'
Reject-Signature 'invalid_signature_rejected' $bytes $clone
$saved=[Environment]::GetEnvironmentVariable('LOCALAPPDATA','Process')
$sandbox=Join-Path $Fixture ('crypto-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $sandbox -ErrorAction Stop|Out-Null
try{
 [Environment]::SetEnvironmentVariable('LOCALAPPDATA',$sandbox,'Process')
 Assert-AgentSelfTest $AgentFile;Check 'actual_agent_selftest_isolated' $true
 Check 'no_device_enrollment' (-not(Test-Path -LiteralPath (Join-Path $sandbox 'HARA Commander\device.json')))
 [ordered]@{schema='hara.windows-clean-native-crypto.v2';state='PASS';checks=$Checks.Count;cases=$Checks;installer_sha256=$ExpectedInstaller;agent_sha256=$ExpectedAgent;manifest_sha256=$ExpectedManifest;real_powershell_version=$PSVersionTable.PSVersion.ToString();edition=$PSVersionTable.PSEdition;scope='REAL_SIGNED_CODE_NATIVE_FIXTURE_NOT_EXTERNAL_CLEAN_INSTALL';agent_transport_started=$false;founder_config_read=$false;main_task_modified=$false;secrets_printed=$false}|ConvertTo-Json -Depth 5 -Compress
}finally{
 [Environment]::SetEnvironmentVariable('LOCALAPPDATA',$saved,'Process')
 Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}
