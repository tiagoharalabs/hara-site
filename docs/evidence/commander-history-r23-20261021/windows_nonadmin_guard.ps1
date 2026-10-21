$ErrorActionPreference="Stop"
function Clear-LocalActivityHistory {
  $who=[Security.Principal.WindowsIdentity]::GetCurrent()
  $admin=[Security.Principal.WindowsPrincipal]::new($who).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
  if(-not $admin){throw "HISTORY_CLEAR_SUPERUSER_REQUIRED"}
  if(-not [Environment]::UserInteractive -or [Console]::IsInputRedirected){
    throw "HISTORY_CLEAR_LOCAL_TTY_REQUIRED"
  }
  if(Get-OperatorSession){throw "HISTORY_CLEAR_ACTIVE_SESSION_DENIED"}
  $task=Get-ScheduledTask -TaskName $AgentTaskName -ErrorAction SilentlyContinue
  if($task -and [string]$task.State -eq "Running"){throw "HISTORY_CLEAR_AGENT_MUST_BE_STOPPED"}
  Write-Host "Limpeza local do historico (SQLite/JSONL); recibos preservados."
  Write-Host "Encerre antes o Commander na janela pessoal."
  $answer=Read-Host "Digite LIMPAR HISTORICO LOCAL para confirmar"
  if($answer -cne "LIMPAR HISTORICO LOCAL"){throw "HISTORY_CLEAR_CONFIRMATION_DENIED"}
  Clear-LocalHistoryData
}

try { Clear-LocalActivityHistory; throw "R23_UNEXPECTED_ADMIN_CLEAR_ALLOWED" } catch { if ([string]$_.Exception.Message -ne "HISTORY_CLEAR_SUPERUSER_REQUIRED") {throw}; Write-Output "R23_WINDOWS_NON_ADMIN_CLEAR_DENIED=PASS" }
