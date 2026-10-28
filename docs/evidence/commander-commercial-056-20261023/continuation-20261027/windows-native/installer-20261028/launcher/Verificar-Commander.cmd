@echo off
setlocal
title Verificar instalacao HARA Commander
set "HARA_QA_LAUNCHER_DIR=%~dp0"
echo Verificar instalacao HARA Commander
echo.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -Command ^
 "$ErrorActionPreference='Stop';$env:HARA_QA_WRAPPER_FINISHED='';$changed=$false;$old=$null;$code=2;" ^
 "try {$id=[Security.Principal.WindowsIdentity]::GetCurrent();if($id.User.Value -cne 'S-1-5-21-1207901905-1500652706-889822281-1005' -or $env:USERPROFILE -cne 'C:\Users\CommanderQA'){throw 'COMMANDERQA_REQUIRED'};" ^
 "$p=Join-Path $env:HARA_QA_LAUNCHER_DIR 'Instalar-ou-verificar-Commander.ps1';if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne 'b68b42fa4abdde397827d6898fe18a493274c84f9cf9aa566b5deab764c787e2'){throw 'LAUNCHER_HASH_MISMATCH'};" ^
 "$old=[string](Get-ExecutionPolicy -Scope CurrentUser);if(@('Undefined','Restricted','RemoteSigned') -cnotcontains $old -or [string](Get-ExecutionPolicy -Scope Process) -cne 'Undefined'){throw 'EXECUTION_POLICY_REVIEW_REQUIRED'};" ^
 "Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force;$changed=$true;if([string](Get-ExecutionPolicy) -cne 'RemoteSigned'){throw 'EFFECTIVE_POLICY_REFUSED'};" ^
 "& $p -Action 'preflight' -PriorExecutionPolicy $old;$code=$LASTEXITCODE}" ^
 "catch {$msg=[string]$_.Exception.Message;if($msg -cnotmatch '^[A-Z][A-Z0-9_]{0,100}$'){$msg='LAUNCHER_FAILED'};Write-Host ('Falha: '+$msg) -ForegroundColor Yellow;$code=2}" ^
 "finally {if($changed -and $env:HARA_QA_WRAPPER_FINISHED -ne '1'){try{Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy $old -Force}catch{Write-Host 'Falha ao restaurar a politica do usuario.' -ForegroundColor Yellow;$code=2}}};exit $code"
set "HARA_QA_EXIT=%ERRORLEVEL%"
echo.
if not "%HARA_QA_EXIT%"=="0" echo A operacao nao foi concluida. Veja o codigo e o resultado acima.
echo Pressione uma tecla para fechar esta janela.
pause >nul
exit /b %HARA_QA_EXIT%
