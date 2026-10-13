param([string]$Stage)
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
try{
 $fx=Get-Content -Raw -LiteralPath (Join-Path $Stage 'pairing-fixture.json')|ConvertFrom-Json
 if([string]$fx.dev_origin-ne'https://hara-commander-dev-v2.tiago-sartori.workers.dev'){throw 'DEV_ORIGIN_REQUIRED'}
 $env:LOCALAPPDATA=Join-Path $Stage 'profile'
 $root=Join-Path $env:LOCALAPPDATA 'HARA Commander';New-Item -ItemType Directory -Path $root -Force|Out-Null
 if(Test-Path(Join-Path $root 'device.json')){throw 'FIXTURE_ALREADY_ENROLLED'}
 $versionLine=Select-String -LiteralPath (Join-Path $Stage 'stable_windows.ps1') -Pattern '^\$AgentVersion = "([^"]+)"$'
 $stableVersion=$versionLine.Matches[0].Groups[1].Value
 if($stableVersion-notmatch'^0[.]3[.][0-9]+$'){throw 'STABLE_SOURCE_VERSION_INVALID'}
 $payload=@{pairing_token=[string]$fx.pairing_token;device_name='QA-WINDOWS-EVENT-V2-20261012-ROOT';platform='WINDOWS';architecture='x64';agent_version=$stableVersion;approval_mode='SESSION_TRUSTED'}|ConvertTo-Json -Compress
 $body=[Text.Encoding]::UTF8.GetBytes($payload)
 $enroll=Invoke-RestMethod -Uri ($fx.dev_origin+'/api/device/enroll') -Method Post -ContentType 'application/json; charset=utf-8' -Headers @{Accept='application/json'} -Body $body -TimeoutSec 30 -MaximumRedirection 0
 if(-not$enroll.device_id-or-not$enroll.device_token){throw 'ENROLL_RESPONSE_INVALID'}
 $encrypted=ConvertTo-SecureString ([string]$enroll.device_token) -AsPlainText -Force|ConvertFrom-SecureString
 $cfg=@{base_url=[string]$fx.dev_origin;device_id=[string]$enroll.device_id;encrypted_device_token=$encrypted;architecture='x64';agent_version=$stableVersion;approval_mode='SESSION_TRUSTED'}
 $cfg|ConvertTo-Json -Compress|Set-Content -LiteralPath (Join-Path $root 'device.json') -Encoding UTF8
 Copy-Item -LiteralPath (Join-Path $Stage 'stable_windows.ps1') -Destination (Join-Path $root 'hara-commander-agent.ps1')
 [ordered]@{state='PASS';device_id=[string]$enroll.device_id;platform='WINDOWS';agent_source_version=$stableVersion;origin=[string]$fx.dev_origin;fixture_dpapi=$true;founder_identity_used=$false}|ConvertTo-Json -Compress
}catch{[ordered]@{state='FAILED';error_type=$_.Exception.GetType().Name;http_status=if($_.Exception.Response){[int]$_.Exception.Response.StatusCode}else{$null}}|ConvertTo-Json -Compress;exit 1}
finally{Remove-Item -LiteralPath (Join-Path $Stage 'pairing-fixture.json') -Force -ErrorAction SilentlyContinue}
