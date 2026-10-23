# Extract only the guard AST. Never dot-source or invoke an installer.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot '../release-candidates/public-installer-floor-source-20261023/install/windows.ps1'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $source),[ref]$tokens,[ref]$errors)
if ($errors.Count -ne 0) { throw 'WINDOWS_INSTALLER_PARSE_FAILED' }
$guard=@($ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Assert-AgentVersionFloor'},$true))
if ($guard.Count -ne 1) { throw 'WINDOWS_VERSION_GUARD_NOT_UNIQUE' }
Invoke-Expression $guard[0].Extent.Text
$temp=Join-Path ([IO.Path]::GetTempPath()) ('hara-installer-guard-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp | Out-Null
$Agent=Join-Path $temp 'synthetic-agent.ps1'
$cases=@(
  @{Offer='0.3.55';Existing=$null;Error=$null},
  @{Offer='0.3.56';Existing='$AgentVersion = "0.3.55"';Error=$null},
  @{Offer='0.3.55';Existing='$AgentVersion = "0.3.55"';Error=$null},
  @{Offer='0.3.54';Existing=$null;Error='BELOW_WINDOWS_FLOOR'},
  @{Offer='0.3.55';Existing='$AgentVersion = "0.3.56"';Error='DOWNGRADE_REFUSED'},
  @{Offer='0.3.55';Existing='unknown';Error='INSTALLED_VERSION_UNKNOWN'},
  @{Offer='0.3.055';Existing=$null;Error='INVALID_SEMVER'},
  @{Offer='0.3.55-rc';Existing=$null;Error='INVALID_SEMVER'},
  @{Offer='0.3.55';Existing='$AgentVersion = "0.03.55"';Error='INSTALLED_VERSION_UNKNOWN'},
  @{Offer='0.3.55';Existing=('$AgentVersion = "0.3.54"'+"`n"+'$AgentVersion = "0.3.55"');Error='INSTALLED_VERSION_UNKNOWN'}
)
try {
  foreach($case in $cases) {
    Remove-Item -LiteralPath $Agent -Force -ErrorAction SilentlyContinue
    if($null -ne $case.Existing){[IO.File]::WriteAllText($Agent,$case.Existing)}
    $before=if(Test-Path $Agent){(Get-FileHash $Agent -Algorithm SHA256).Hash}else{$null}
    $failure=$null
    try{Assert-AgentVersionFloor -IncomingVersion $case.Offer}catch{$failure=$_.Exception.Message}
    if($case.Error){if(-not $failure -or -not $failure.Contains($case.Error)){throw ('GUARD_EXPECTED_'+$case.Error)}}
    elseif($failure){throw ('UNEXPECTED_GUARD_ERROR_'+$failure)}
    if($before -and (Get-FileHash $Agent -Algorithm SHA256).Hash -ne $before){throw 'INSTALLED_BYTES_CHANGED'}
  }
  Remove-Item -LiteralPath $Agent -Force -ErrorAction SilentlyContinue
  New-Item -ItemType Directory -Path $Agent | Out-Null
  $failure=$null
  try{Assert-AgentVersionFloor -IncomingVersion '0.3.55'}catch{$failure=$_.Exception.Message}
  if(-not $failure -or -not $failure.Contains('AGENT_INSTALLED_PATH_UNTRUSTED')){throw 'DIRECTORY_NOT_REFUSED'}
  Write-Output 'WINDOWS_NATIVE_PARSE_AND_GUARDS=PASS_11_CASES'
}finally{Remove-Item -LiteralPath $temp -Recurse -Force}
