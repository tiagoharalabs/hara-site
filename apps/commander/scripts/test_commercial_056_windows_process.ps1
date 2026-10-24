param([string]$AgentPath=(Join-Path $PSScriptRoot '../release-candidates/commercial-0.3.56-source/agent/windows.ps1'))
$ErrorActionPreference='Stop'
$checks=New-Object Collections.Generic.List[string]
$qa=Join-Path ([IO.Path]::GetTempPath()) ('hara-056-process-'+[guid]::NewGuid().ToString('N'))
$native=[Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT
$pathKey=if($native){'Path'}else{'PATH'}
$priorPath=[Environment]::GetEnvironmentVariable($pathKey,'Process')
function Check([bool]$Value,[string]$Name) {
 if(-not $Value){throw ('QA_FAILED_'+$Name)}
 $checks.Add($Name)
}
function Run-Case([string]$Command,[int]$Expected,[string]$Name,[string]$Output='') {
 $session=New-Object HaraWindowsProcessSession -ArgumentList ([guid]::NewGuid().ToString('N')),$qa,$Command,$true
 try {
  Check ($session.Child.WaitForExit(10000)) ($Name+'_BOUNDED')
  $snapshot=$session.Snapshot(0,100,200)
  Check ($session.Child.ExitCode -eq $Expected) ($Name+'_EXIT_'+$Expected)
  if($Output){Check (([string]$snapshot.text).Contains($Output)) ($Name+'_OUTPUT')}
 } finally {
  if(-not $session.Child.HasExited){$session.Stop($true) | Out-Null;$session.Child.WaitForExit(1000) | Out-Null}
  $session.Dispose()
 }
}
try {
 New-Item -ItemType Directory -Path $qa | Out-Null
 $tokens=$null;$errors=$null
 $tree=[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $AgentPath),[ref]$tokens,[ref]$errors)
 Check ($errors.Count -eq 0) 'AGENT_PARSE'
 $definition=@($tree.FindAll({param($n)$n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Initialize-WindowsManagedProcessType'},$true))
 Check ($definition.Count -eq 1) 'PROCESS_DEFINITION_UNIQUE'
 . ([scriptblock]::Create($definition[0].Extent.Text))
 Initialize-WindowsManagedProcessType
 if(-not $native){
  # Run the exact candidate C# wrapper, using the portable runtime only on
  # non-Windows hosts. This is a regression check, not Windows 5.1 acceptance.
  New-Item -ItemType SymbolicLink -Path (Join-Path $qa 'powershell.exe') -Target (Join-Path $PSHOME 'pwsh') | Out-Null
  [Environment]::SetEnvironmentVariable($pathKey,($qa+[IO.Path]::PathSeparator+$priorPath),'Process')
 }
 $zero=if($native){'cmd.exe /d /c exit 0'}else{"/bin/sh -c 'exit 0'"}
 $seven=if($native){'cmd.exe /d /c exit 7'}else{"/bin/sh -c 'exit 7'"}
 Run-Case $zero 0 'NATIVE_ZERO'
 Run-Case $seven 7 'NATIVE_SEVEN'
 Run-Case ($seven+" # trailing comment") 7 'NATIVE_SEVEN_COMMENT'
 Run-Case 'exit 23' 23 'EXPLICIT_EXIT'
 Run-Case "throw 'synthetic failure'" 1 'TERMINATING_ERROR'
 Run-Case "Write-Error 'synthetic failure'" 1 'NONTERMINATING_ERROR'
 Run-Case ($seven+"; Write-Output 'finished'") 0 'LAST_SUCCESS_NO_STALE_EXIT' 'finished'
 $sample='Unicode: a'+[char]0xE7+[char]0xE3+'o '+[char]0x6F22+[char]0x5B57
 Run-Case ("Write-Output '"+$sample+"'") 0 'UNICODE' $sample
 @{state=if($native){'PASS_NATIVE_WINDOWS_PROCESS_NO_INSTALL'}else{'PASS_PORTABLE_PROCESS_NOT_WINDOWS_ACCEPTANCE'};checks=$checks.Count;cases=$checks.ToArray();ps_version=$PSVersionTable.PSVersion.ToString();windows_native=$native;installed=$false;paired=$false;network_used=$false} | ConvertTo-Json -Depth 5
} finally {
 [Environment]::SetEnvironmentVariable($pathKey,$priorPath,'Process')
 if(Test-Path -LiteralPath $qa){Remove-Item -LiteralPath $qa -Recurse -Force}
}
