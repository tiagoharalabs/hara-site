$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$env:LOCALAPPDATA=Join-Path $PSScriptRoot 'profile'
& (Join-Path $PSScriptRoot 'windows_agent_rc.ps1') -Transport EVENT_V2
exit $LASTEXITCODE
