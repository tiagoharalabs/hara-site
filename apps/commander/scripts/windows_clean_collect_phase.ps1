$ErrorActionPreference='Stop'
$Box='C:\ProgramData\HaraLabs\CommanderCleanQA\20261012-r1'
if(([string](Get-CimInstance Win32_ComputerSystemProduct).UUID).ToLowerInvariant() -cne 'd35599c8-b9ea-45e5-9ae9-fa047e84b8ba'){throw 'CLONE_UUID_REQUIRED'}
$Phase=[string](Get-Content -Raw -LiteralPath (Join-Path $Box 'phase-private.json')|ConvertFrom-Json).phase
if($Phase -notin @('install','inspect','start','stop','update-stopped','update-running','negative-signature','uninstall')){throw 'UNKNOWN_QA_PHASE'}
$Result=Join-Path $Box ('phase-'+$Phase+'.json')
if(Test-Path -LiteralPath $Result){Get-Content -LiteralPath $Result -Raw;exit 0}
$Task=Get-ScheduledTask -TaskName 'HARA Commander Clean QA Harness' -ErrorAction SilentlyContinue
$Info=if($Task){Get-ScheduledTaskInfo -TaskName $Task.TaskName}else{$null}
[ordered]@{state='QA_PHASE_RESULT_PENDING';phase=$Phase;task_state=if($Task){[string]$Task.State}else{$null};task_last_result=if($Info){$Info.LastTaskResult}else{$null};private_harness_error_present=(Test-Path -LiteralPath (Join-Path $Box ('harness-error-'+$Phase+'.private.txt')))}|ConvertTo-Json -Compress
