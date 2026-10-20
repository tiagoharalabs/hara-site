# This footer runs against functions extracted from the unsigned candidate.
# The installed Agent remains active and unchanged.
$script:CompletedWindowsRuns=@{}
$script:ManagedWindowsSessions=@{}
$script:WindowsRunRetentionSeconds=3600
$script:WindowsRunMaxRetained=8
$CallPollHotSeconds=2
$CallPollIdleSeconds=10
$script:ApprovalChecks=0
function Assert-StarterMutationAuthorized($Cfg,$Call) { $script:ApprovalChecks++ }
function Need([bool]$Condition,[string]$Code) { if(-not $Condition){throw $Code} }

$qaRoot='C:\Users\Public\Documents\HARA_COMMANDER_QA_20261020_WIN11'
Need (Test-Path -LiteralPath $qaRoot -PathType Container) 'R10_QA_ROOT_MISSING'
$fixture=Join-Path $qaRoot ('codex-r10-candidate-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $fixture -ErrorAction Stop | Out-Null
try {
  foreach($name in @('alpha','beta','gamma','delta','epsilon','zeta','eta','theta')) {
    [IO.File]::WriteAllText((Join-Path $fixture ($name+'-probe.txt')),
      "João 漢字 ☕`nline2`nline3`nline4`nline5`nline6`nline7`nline8",(New-Object Text.UTF8Encoding($false)))
  }
  $page0=Get-WindowsDirectory $fixture 1 3 0
  $page1=Get-WindowsDirectory $fixture 1 3 3
  $page100=Get-WindowsDirectory $fixture 1 3 100
  Need ($page0.count -eq 3 -and $page0.next_offset -eq 3) 'R10_LIST_PAGE0_FAILED'
  Need ($page1.count -eq 3 -and $page1.entries[0].name -ne $page0.entries[0].name) 'R10_LIST_PAGE1_REPEATED'
  Need ($page100.count -eq 0 -and -not $page100.has_more) 'R10_LIST_OFFSET100_REPEATED'

  $first=Join-Path $fixture 'alpha-probe.txt'
  $many=Read-WindowsManyTextFiles @($first,(Join-Path $fixture 'missing.txt')) 0 3
  Need ($many.overall_status -eq 'PARTIAL' -and $many.successful_count -eq 1 -and $many.failed_count -eq 1) 'R10_READ_MANY_SUMMARY_FAILED'
  Need ($many.files[0].text.Contains('漢字') -and $many.files[0].next_offset -eq 3) 'R10_READ_MANY_PAGE_FAILED'
  $manyNext=Read-WindowsManyTextFiles @($first) 3 3
  Need ($manyNext.files[0].text.Contains('line4')) 'R10_READ_MANY_CONTINUATION_FAILED'
  $search=Search-WindowsFiles $fixture 'files' 'probe' 3 $false $true '' 3
  Need ($search.count -eq 3 -and $search.matches[0].path -ne $page0.entries[0].name -and $search.next_offset -eq 6) 'R10_SEARCH_OFFSET_FAILED'
  $content=Search-WindowsFiles $fixture 'content' '漢字' 2 $false $true '*.txt' 0
  Need ($content.count -eq 2 -and $content.has_more) 'R10_SEARCH_UNICODE_FAILED'

  $before=(Get-FileHash -LiteralPath $first -Algorithm SHA256).Hash.ToLowerInvariant()
  $denied=$false
  try { Edit-WindowsTextFile $null $null $first 'line2' 'edited' $false ('0'*64) | Out-Null }
  catch { $denied=$_.Exception.Message -eq 'FILE_PRECONDITION_FAILED' }
  Need $denied 'R10_EDIT_STALE_HASH_ACCEPTED'
  Need (((Get-FileHash -LiteralPath $first -Algorithm SHA256).Hash.ToLowerInvariant()) -eq $before) 'R10_EDIT_STALE_HASH_MUTATED'
  $edited=Edit-WindowsTextFile $null $null $first 'line2' 'edited' $false $before
  Need ($edited.changed -and $edited.replacements -eq 1 -and (Get-Content -Raw -LiteralPath $first).Contains('edited')) 'R10_EDIT_CORRECT_HASH_FAILED'

  $race=Join-Path $fixture 'race.txt'
  [IO.File]::WriteAllText($race,'base',(New-Object Text.UTF8Encoding($false)))
  $raceHash=(Get-FileHash -LiteralPath $race -Algorithm SHA256).Hash.ToLowerInvariant()
  $gate=Join-Path $fixture 'go.txt'
  $definitions='function Get-Utf8Sha256 {'+(Get-Command Get-Utf8Sha256).Definition+"}`n"+
    'function Edit-WindowsTextFile {'+(Get-Command Edit-WindowsTextFile).Definition+"}`n"+
    'function Assert-StarterMutationAuthorized($Cfg,$Call) {}'+"`n"
  $workerHeader=@'
param($path,$expected,$replacement,$gate)
'@
  $workerTail=@'
while (-not (Test-Path -LiteralPath $gate)) { Start-Sleep -Milliseconds 10 }
try { $result=Edit-WindowsTextFile $null $null $path 'base' $replacement $false $expected; if($result.changed){'PASS'}else{'NO_CHANGE'} }
catch { $_.Exception.Message }
'@
  $worker=[scriptblock]::Create($workerHeader+$definitions+$workerTail)
  $jobA=$null; $jobB=$null
  try {
    $jobA=Start-Job -ScriptBlock $worker -ArgumentList $race,$raceHash,'A',$gate
    $jobB=Start-Job -ScriptBlock $worker -ArgumentList $race,$raceHash,'B',$gate
    [IO.File]::WriteAllText($gate,'go')
    $finished=@(Wait-Job -Job @($jobA,$jobB) -Timeout 8)
    Need ($finished.Count -eq 2) 'R10_EDIT_RACE_TIMEOUT'
    $results=@((Receive-Job $jobA | Out-String).Trim(),(Receive-Job $jobB | Out-String).Trim())
    Need (@($results | Where-Object {$_ -eq 'PASS'}).Count -eq 1 -and
          @($results | Where-Object {$_ -eq 'FILE_PRECONDITION_FAILED'}).Count -eq 1) 'R10_EDIT_RACE_ACCEPTED_TWICE'
  } finally {
    foreach($job in @($jobA,$jobB)) { if($job){Stop-Job $job -ErrorAction SilentlyContinue;Remove-Job $job -Force -ErrorAction SilentlyContinue} }
  }

  $counter=Join-Path $fixture 'counter.txt'
  $command="Add-Content -LiteralPath '$counter' -Value once; 1..8 | ForEach-Object { Write-Output ('line'+`$_) }"
  $run=Invoke-WindowsOneShotProcess $null $null $command $fixture 5000 3
  Need ($run.exit_code -eq 0 -and $run.session_retained -and $run.next_offset -eq 3) 'R10_ONESHOT_NOT_RETAINED'
  Need ($script:CompletedWindowsRuns.ContainsKey($run.run_id)) 'R10_ONESHOT_MAP_MISSING_BEFORE_READ'
  Cleanup-WindowsCompletedRuns
  Need ($script:CompletedWindowsRuns.ContainsKey($run.run_id)) 'R10_ONESHOT_CLEANUP_EVICTED_FRESH_RESULT'
  $second=Read-WindowsManagedSession $run.run_id 3 3 0
  $third=Read-WindowsManagedSession $run.run_id 6 3 0
  Need ($second.text.Contains('line4') -and $third.text.Contains('line8') -and $third.next_offset -eq 8) 'R10_ONESHOT_PAGE_FAILED'
  Need (@(Get-Content -LiteralPath $counter).Count -eq 1) 'R10_ONESHOT_REEXECUTED'
  $failedCommand=Invoke-WindowsOneShotProcess $null $null 'Write-Output "ação_漢字_☕"; exit 7' $fixture 5000 20
  Need ($failedCommand.exit_code -eq 7 -and $failedCommand.text.Contains('ação_漢字_☕')) 'R10_ONESHOT_EXIT_OR_UNICODE_FAILED'
  Need ($script:ApprovalChecks -eq 4) 'R10_CONSENT_HOOK_COUNT_FAILED'
  Need ((Get-WindowsRelayPollSleep $true 1 $true) -eq 0 -and
        (Get-WindowsRelayPollSleep $true 4 $true) -eq 0 -and
        (Get-WindowsRelayPollSleep $true 8 $true) -eq 2 -and
        (Get-WindowsRelayPollSleep $false 0 $false) -eq 10) 'R10_RELAY_BURST_POLICY_FAILED'
  Write-Output 'WINDOWS_R10_CANDIDATE_LIST=PASS'
  Write-Output 'WINDOWS_R10_CANDIDATE_READ_MANY=PASS'
  Write-Output 'WINDOWS_R10_CANDIDATE_SEARCH=PASS'
  Write-Output 'WINDOWS_R10_CANDIDATE_EDIT_CAS=PASS'
  Write-Output 'WINDOWS_R10_CANDIDATE_EDIT_CROSS_PROCESS=PASS'
  Write-Output 'WINDOWS_R10_CANDIDATE_ONESHOT=PASS'
  Write-Output 'WINDOWS_R10_RELAY_BURST_POLICY=PASS'
  Write-Output ('WINDOWS_R10_FUNCTIONS_SHA256='+$CandidateFunctionsSha256)
} finally {
  if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction SilentlyContinue }
}
