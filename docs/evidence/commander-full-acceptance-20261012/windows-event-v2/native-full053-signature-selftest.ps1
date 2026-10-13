param([string]$BundleRoot)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$env:LOCALAPPDATA=Join-Path $BundleRoot 'native-selftest-profile'
function ShaBytes([byte[]]$Raw){$h=[Security.Cryptography.SHA256]::Create();try{return ([BitConverter]::ToString($h.ComputeHash($Raw))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
function Unb64([string]$Value){$s=$Value.Replace('-','+').Replace('_','/');$s=$s.PadRight($s.Length+((4-$s.Length%4)%4),'=');return [Convert]::FromBase64String($s)}
$manifestRaw=[IO.File]::ReadAllBytes((Join-Path $BundleRoot 'release\agent-manifest.json'))
$manifest=[Text.Encoding]::UTF8.GetString($manifestRaw)|ConvertFrom-Json
$signature=Get-Content -Raw -LiteralPath (Join-Path $BundleRoot 'release\agent-manifest.sig.json')|ConvertFrom-Json
$keyRaw=[IO.File]::ReadAllBytes((Join-Path $BundleRoot 'release\release-signing-public.jwk'))
$key=[Text.Encoding]::UTF8.GetString($keyRaw)|ConvertFrom-Json
if((ShaBytes $keyRaw)-ne'4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b'){throw 'PUBLIC_KEY_PIN'}
if($signature.alg-ne'RS256'-or$signature.kid-ne'commander-release-v2'-or$signature.manifest_sha256-ne(ShaBytes $manifestRaw)){throw 'SIGNATURE_ENVELOPE'}
$parameters=[Security.Cryptography.RSAParameters]::new()
$parameters.Modulus=Unb64 $key.n;$parameters.Exponent=Unb64 $key.e
$rsa=[Security.Cryptography.RSACryptoServiceProvider]::new();$rsa.PersistKeyInCsp=$false
try{
 $rsa.ImportParameters($parameters)
 if($rsa.KeySize-ne3072){throw 'RSA_KEY_SIZE'}
 if(-not$rsa.VerifyData($manifestRaw,'SHA256',(Unb64 $signature.signature))){throw 'SIGNATURE_INVALID'}
}finally{$rsa.Dispose()}
if($manifest.agent_version-ne'0.3.53'){throw 'MANIFEST_VERSION'}
foreach($row in $manifest.files){
 $path=Join-Path $BundleRoot ([string]$row.path).Replace('/','\')
 $raw=[IO.File]::ReadAllBytes($path)
 if($raw.Length-ne$row.bytes-or(ShaBytes $raw)-ne$row.sha256){throw 'MANIFEST_FILE_HASH'}
}
foreach($file in @('agent\windows.ps1','install\windows.ps1')){
 $tokens=$null;$errors=$null;[Management.Automation.Language.Parser]::ParseFile((Join-Path $BundleRoot $file),[ref]$tokens,[ref]$errors)|Out-Null
 if($errors.Count){throw 'WINDOWS_SOURCE_PARSE'}
}
$version=Select-String -LiteralPath (Join-Path $BundleRoot 'agent\windows.ps1') -Pattern '^\$AgentVersion = "0.3.53"$'
if(-not$version){throw 'WINDOWS_SOURCE_VERSION'}
$selfOut=Join-Path $BundleRoot 'self-test.stdout';$selfErr=Join-Path $BundleRoot 'self-test.stderr'
$p=Start-Process -FilePath "$PSHOME\powershell.exe" -ArgumentList ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+(Join-Path $BundleRoot 'agent\windows.ps1')+'" --self-test') -Wait -PassThru -RedirectStandardOutput $selfOut -RedirectStandardError $selfErr
if($p.ExitCode-ne0){throw 'NATIVE_AGENT_SELF_TEST_FAILED'}
$output=Get-Content -Raw -LiteralPath $selfOut
if($output-notmatch'COMMANDER_WINDOWS_AGENT_SELF_TEST=PASS'){throw 'NATIVE_AGENT_SELF_TEST_MARKER'}
[ordered]@{schema='hara.commander-full053-native-signature-and-selftest.v1';state='PASS';powershell=$PSVersionTable.PSVersion.ToString();clr=[Environment]::Version.ToString();manifest_sha256=(ShaBytes $manifestRaw);version='0.3.53';signature='RS256_RSA3072';four_files_authenticated=$true;windows_parser=$true;installer_parser=$true;windows_source_sha256=(Get-FileHash -LiteralPath (Join-Path $BundleRoot 'agent\windows.ps1')).Hash.ToLowerInvariant();windows_agent_self_test_exit=$p.ExitCode;windows_agent_self_test_marker=$true;live_profile_touched=$false;global_task_touched=$false;private_key_accessed=$false;signing_performed=$false;production_deployed=$false;utc=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Compress
