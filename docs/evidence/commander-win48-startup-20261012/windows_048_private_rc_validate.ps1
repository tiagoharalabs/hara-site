# Private RC48 validation only. Never enrolls or starts an Agent transport.
[CmdletBinding()]
param([string]$BundleRoot='C:\ProgramData\HaraLabs\CommanderWinLab\20261012\private-048-rc',
      [switch]$FunctionsOnly,[switch]$SelfTest)
$ErrorActionPreference='Stop'
# Frozen manifest pin supplied after release signing; authority remains the pinned v2 key.
$Win48ManifestSha='5e65b1862c40bc9164609cdcd1401bb55e02e409b44f1b58bca15151e40de32c'
$Win48Kid='commander-release-v2'
$Win48N='p9ylK_Yf48aEfkps9ZVm6u5Uk3haKCF1ltQmZUrXHLqrbiXf4L-3OdqpYcv7VGktbXKVfccIR2-b8lfNPKT-OpemqcgkJ9Cb-gvjxdPxoLOWxTVasKr8ttUirM08LVzL7BF3Mwadl2SEQXSHC0ayH1Jtj3-57Z8XNZ4NvWuUswBhYrNtXpe8-a86HSy2r0pEMWZalqJE1mD1nGnODYWLpsLPkTX4rUBky5zBX11Rkf2_Op3jpo5nwWVPf2AEJSq-yogQQI3jopJRydnrDySxFpI7TgN1SAL1nEcNRkh-rOjchuqyHpQAN2DSDpQvrFDxANDLMhxrlwmE6MU4PAn46ICuKgyqAYULlVhYhjZpPUZpLHvwG3rjYbD022qYbBDdamJ79FWcoDxmr85mwiDQ4WDEn8cgF_5G2pmq6Wq3ss2O1cQJB_QgkID3uBeywonGs0ikoMtxmIvSi1HVGkBVC0Ay726K9wwpT_xhiwVT_OpAnNYgNdqWcc-cU7n-Zt43'
function Convert-Win48Base64Url([string]$Value){
 $text=$Value.Replace('-','+').Replace('_','/')
 if(($text.Length%4)-eq 2){$text+='=='}
 elseif(($text.Length%4)-eq 3){$text+='='}
 return [Convert]::FromBase64String($text)
}
function Get-Win48TextSha([string]$Text){
 $sha=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-','').ToLowerInvariant()}
 finally{$sha.Dispose()}
}
function Assert-Win48FrozenBundle([string]$Path){
 if($Win48ManifestSha -ceq ('0'*64)){throw 'WIN48_MANIFEST_PIN_REQUIRED'}
 $manifestPath=Join-Path $Path 'release\agent-manifest.json'
 $bytes=[IO.File]::ReadAllBytes($manifestPath)
 if((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Win48ManifestSha){throw 'WIN48_MANIFEST_NOT_FROZEN'}
 $sig=Get-Content -LiteralPath (Join-Path $Path 'release\agent-manifest.sig.json') -Raw|ConvertFrom-Json
 $jwk=Get-Content -LiteralPath (Join-Path $Path 'release\release-signing-public.jwk') -Raw|ConvertFrom-Json
 if([string]$sig.schema -cne 'hara.commander-release-signature.v1' -or [string]$sig.alg -cne 'RS256' -or [string]$sig.kid -cne $Win48Kid -or [string]$sig.manifest_sha256 -cne $Win48ManifestSha){throw 'WIN48_SIGNATURE_ENVELOPE_INVALID'}
 if([string]$jwk.kty -cne 'RSA' -or [string]$jwk.alg -cne 'RS256' -or [string]$jwk.kid -cne $Win48Kid -or [string]$jwk.n -cne $Win48N -or [string]$jwk.e -cne 'AQAB'){throw 'WIN48_PUBLIC_KEY_NOT_PINNED_V2'}
 $rsa=[Security.Cryptography.RSA]::Create()
 try{
  $params=New-Object Security.Cryptography.RSAParameters
  $params.Modulus=Convert-Win48Base64Url $Win48N
  $params.Exponent=Convert-Win48Base64Url 'AQAB'
  $rsa.ImportParameters($params)
  if(-not $rsa.VerifyData($bytes,(Convert-Win48Base64Url ([string]$sig.signature)),[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)){throw 'WIN48_RS256_SIGNATURE_INVALID'}
 }finally{$rsa.Dispose()}
 $manifest=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json
 if([string]$manifest.schema -cne 'hara.commander-agent-release.v1' -or [string]$manifest.product -cne 'H.A.R.A. Commander' -or [string]$manifest.agent_version -cne '0.3.48' -or [string]$manifest.channel -cne 'stable'){throw 'WIN48_MANIFEST_SCOPE_INVALID'}
 $expected=@('agent/linux.py','agent/windows.ps1','install/linux.sh','install/windows.ps1')
 if(@($manifest.files).Count -ne 4 -or @($manifest.files|Select-Object -ExpandProperty path -Unique).Count -ne 4){throw 'WIN48_FILESET_INVALID'}
 $rows=@()
 foreach($row in $manifest.files){
  $rel=[string]$row.path
  if($expected -cnotcontains $rel){throw 'WIN48_FILESET_INVALID'}
  $item=Get-Item -LiteralPath (Join-Path $Path $rel.Replace('/','\')) -ErrorAction Stop
  if($item.PSIsContainer -or ($item.Attributes-band [IO.FileAttributes]::ReparsePoint)){throw 'WIN48_FILE_NOT_REGULAR'}
  $sha=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  if($item.Length -ne [long]$row.bytes -or $sha -cne [string]$row.sha256){throw 'WIN48_FILE_DIGEST_INVALID'}
  $errorsCount=0
  if($rel -like '*.ps1'){
   $tok=$null;$errors=$null
   [Management.Automation.Language.Parser]::ParseFile($item.FullName,[ref]$tok,[ref]$errors)|Out-Null
   $errorsCount=@($errors).Count
   if($errorsCount){throw 'WIN48_PS51_PARSE_ERROR'}
  }
  $rows+=[pscustomobject]@{path=$rel;bytes=$item.Length;sha256=$sha;parse_errors=$errorsCount}
 }
 $index=Get-Content -LiteralPath (Join-Path $Path 'release\SHA256SUMS') -Raw
 $newline=[string][char]10
 $want=(@($manifest.files|ForEach-Object{[string]$_.sha256+'  '+[string]$_.path}) -join $newline)+$newline
 if($index -cne $want){throw 'WIN48_CHECKSUM_INDEX_INVALID'}
 return [pscustomobject]@{schema='hara.commander-win48-private-rc-windows-validation.v1';state='PASS';powershell_version=$PSVersionTable.PSVersion.ToString();manifest_sha256=$Win48ManifestSha;signature_algorithm='RS256_RSA3072';pinned_authority=$Win48Kid;files=$rows;installed_agent_modified=$false;agent_transport_started=$false}
}
function Invoke-Win48FixtureSelfTest([string]$Path){
 $sandbox=Join-Path ([IO.Path]::GetTempPath()) ('hara-win48-root-fixture-'+[guid]::NewGuid().ToString('N'))
 New-Item -ItemType Directory -Path $sandbox|Out-Null
 $original=[Environment]::GetEnvironmentVariable('LOCALAPPDATA','Process')
 try{
  [Environment]::SetEnvironmentVariable('LOCALAPPDATA',$sandbox,'Process')
  $lines=@(& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $Path 'agent\windows.ps1') --self-test 2>&1)
  if($LASTEXITCODE -ne 0 -or $lines -cnotcontains 'COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS'){throw 'WIN48_FIXTURE_SELFTEST_FAILED'}
  return [pscustomobject]@{state='PASS';marker='COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS';root_fixture_guaranteed=$true;agent_transport_started=$false;installed_agent_modified=$false}
 }finally{
  [Environment]::SetEnvironmentVariable('LOCALAPPDATA',$original,'Process')
  Remove-Item -LiteralPath $sandbox -Recurse -Force -ErrorAction SilentlyContinue
 }
}
if(-not $FunctionsOnly){
 $report=Assert-Win48FrozenBundle $BundleRoot
 if($SelfTest){$report|Add-Member NoteProperty self_test (Invoke-Win48FixtureSelfTest $BundleRoot)}
 $report|ConvertTo-Json -Depth 5 -Compress
}

