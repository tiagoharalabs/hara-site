[CmdletBinding()]
param([string]$BundleRoot='C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-051-rc-r1')
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$Fixture='C:\ProgramData\HaraLabs\CommanderWinLab\20261012\windows-clean-native-root-r1'
$Installer=Join-Path $BundleRoot 'install\windows.ps1'
$AgentFile=Join-Path $BundleRoot 'agent\windows.ps1'
$ExpectedInstaller='2f0dae1684fae5a5b4fb716e54ca3d314eedd814eef23238ffa41e479a4346c4'
$ExpectedAgent='4c563987986249d78c76258d062a4d360ffb88199539429ea97c2f346644656a'
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
 $prompt=Join-Path $sandbox 'secure-prompt.ps1'
 [IO.File]::WriteAllText($prompt,'$s=Read-Host "QA fixture" -AsSecureString;$b=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($s);try{[pscustomobject]@{chars=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($b).Length;secure=($s -is [Security.SecureString])}|ConvertTo-Json -Compress}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b)}',(New-Object Text.UTF8Encoding($false)))
 $start=New-Object Diagnostics.ProcessStartInfo
 $start.FileName=(Get-Command powershell.exe).Source;$start.Arguments='-NoLogo -NoProfile -ExecutionPolicy Bypass -File "'+$prompt+'"'
 $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
 $proc=New-Object Diagnostics.Process;$proc.StartInfo=$start;$null=$proc.Start()
 $proc.StandardInput.WriteLine('HARA-QA-SECURE-INPUT');$proc.StandardInput.Close()
 $finished=$proc.WaitForExit(5000)
 if(-not $finished){$proc.Kill();$proc.WaitForExit()}
 $promptOutput=$proc.StandardOutput.ReadToEnd();$promptError=$proc.StandardError.ReadToEnd();$promptWorks=($finished -and $proc.ExitCode -eq 0 -and $promptOutput -match '"chars":20' -and $promptOutput -match '"secure":true')
 [ordered]@{schema='hara.windows-clean-native-crypto.v1';state='PASS';checks=$Checks.Count;cases=$Checks;installer_sha256=$ExpectedInstaller;agent_sha256=$ExpectedAgent;secure_readhost_redirect_supported=$promptWorks;secure_readhost_fixture_timed_out=(-not $finished);real_powershell_version=$PSVersionTable.PSVersion.ToString();scope='REAL_SIGNED_CODE_NATIVE_FIXTURE_NOT_EXTERNAL_CLEAN_INSTALL';agent_transport_started=$false;founder_config_read=$false;main_task_modified=$false;secrets_printed=$false}|ConvertTo-Json -Depth 5 -Compress
}finally{
 [Environment]::SetEnvironmentVariable('LOCALAPPDATA',$saved,'Process')
 Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
}
