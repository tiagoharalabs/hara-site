$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-18'){throw 'SYSTEM_REQUIRED'}
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028';$folder='C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA';$desktop='C:\Users\CommanderQA\Desktop'
$sid='S-1-5-21-1207901905-1500652706-889822281-1005'
if((Get-CimInstance Win32_ComputerSystem).UserName -ine 'HARA_WIN11\CommanderQA'){throw 'COMMANDERQA_CONSOLE_REQUIRED'}
$ready=Get-Content -Raw -LiteralPath (Join-Path $root 'results\task-slot-ready.json')|ConvertFrom-Json
if($ready.state -cne 'INSTALL_TASK_SLOT_READY'){throw 'TASK_SLOT_READINESS_REQUIRED'}
$original=@{'LEIA-ME.txt'='edb9fea571be6f15df45a5d4fd47609fca178f8aa4d0070e4c2081e0a1406224';'RESULTADO-DOS-TESTES.txt'='24ff25570c1359f28509abde372b9bbf690e7a913d64e3d7abc135fda0c72be4'}
foreach($n in $original.Keys){$p=Join-Path $folder $n;if((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -cne $original[$n]){throw 'DESKTOP_DOCUMENT_PREIMAGE_CHANGED'};Copy-Item -LiteralPath $p -Destination (Join-Path (Join-Path $root 'backup') ($n+'.before-installer'))}
$readme=@'
HARA Commander 0.3.56 — Windows QA

Maquina fisica: Sentinela B.
VM: hara-review-win11-restoretest-20261024 (VM Win11 Sent B).
Usuario do Windows: HARA_WIN11\CommanderQA; a sessao atual ja esta aberta.
Conta HARA Identity para esta revisao: openai-reviewer@haralabs.com.br.

Os atalhos Instalar HARA Commander e Verificar HARA Commander estao na Area de Trabalho.
Instalar-Commander.cmd executa o instalador verdadeiro; um .ps1 aberto no editor nao instala o produto.

O preflight verdadeiro passou como CommanderQA, com rede, manifesto .56 e assinatura validados.
A tarefa antiga de sarti, que estava desativada, foi arquivada antes de liberar a instalacao para CommanderQA.
A instalacao e o pareamento ainda aguardam um codigo de pareamento valido da conta OpenAI Reviewer.
Esse codigo e gerado no portal Commander apos login. Nao digite a senha do Identity no campo Pairing token.
A senha antiga nao foi recuperada nem alterada. O Brave do Nucleo A mostrou uma entrada salva para essa conta.

Esta e a distribuicao interna temporaria de QA. O produto publico ainda nao foi liberado.
A janela atual de distribuicao termina aproximadamente em 28/10/2026 00:09, horario de Brasilia.
Se a janela terminar, retome a preparacao com a Valky antes de instalar.
'@
$result=@'
HARA Commander — resultado no Windows QA

27/10/2026 23:39 (Brasilia): PASS_NATIVE_PREFLIGHT, exit 0.
Executado pelo botao CMD, em PowerShell 5.1, como CommanderQA padrao e interativo.
Health do Commander, manifesto .56, assinatura e pre-requisitos de tarefas: PASS.
Politica CurrentUser restaurada para Undefined apos o preflight.
As tentativas anteriores ficaram retidas por confirmacao do certificado de QA e foram encerradas/recuperadas.
A verificacao aprovada usou confianca temporaria de QA provisionada administrativamente, com remocao automatica.

Os testes de componentes anteriores passaram: --version, --self-test, seis verificacoes de JobObject e treze de contexto do usuario.
Esses testes nao substituem instalacao, enrollment e ciclo de vida completos.

STATUS ATUAL: instalacao/pareamento pendentes do codigo legitimo da conta openai-reviewer@haralabs.com.br.
O produto ainda nao esta liberado para lancamento publico.
'@
[IO.File]::WriteAllText((Join-Path $folder 'LEIA-ME.txt'),$readme,[Text.Encoding]::UTF8)
[IO.File]::WriteAllText((Join-Path $folder 'RESULTADO-DOS-TESTES.txt'),$result,[Text.Encoding]::UTF8)
$shell=New-Object -ComObject WScript.Shell;$links=@()
foreach($entry in @(@('Instalar HARA Commander','Instalar-Commander.cmd'),@('Verificar HARA Commander','Verificar-Commander.cmd'))){
 $path=Join-Path $desktop ($entry[0]+'.lnk');if(Test-Path -LiteralPath $path){throw 'DESKTOP_SHORTCUT_EXISTS'}
 $link=$shell.CreateShortcut($path);$link.TargetPath=$env:ComSpec;$link.Arguments='/d /c call "'+(Join-Path $folder $entry[1])+'"';$link.WorkingDirectory=$folder;$link.WindowStyle=1;$link.IconLocation=(Join-Path $PSHOME 'powershell.exe')+',0';$link.Description=$entry[0];$link.Save()
 $check=$shell.CreateShortcut($path);if($check.TargetPath -ine $env:ComSpec -or $check.Arguments -cne $link.Arguments){throw 'SHORTCUT_READBACK_FAILED'}
 & icacls.exe $path /setowner ('*'+$sid)|Out-Null;if($LASTEXITCODE -ne 0){throw 'SHORTCUT_OWNER_FAILED'}
 $links+=@{name=$entry[0];target=$entry[1];sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}
}
$files=@(Get-ChildItem -LiteralPath $folder -File|Where-Object Name -ne 'SHA256SUMS.txt'|Sort-Object Name|ForEach-Object{@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
[IO.File]::WriteAllLines((Join-Path $folder 'SHA256SUMS.txt'),[string[]]@($files|ForEach-Object{$_.sha256+'  '+$_.name}),[Text.Encoding]::ASCII)
$cleanup=Get-ScheduledTask -TaskName 'HARA-QA056-TemporaryTLS-Cleanup-20261028'
$info=Get-ScheduledTaskInfo -TaskName $cleanup.TaskName
$policy=(Get-ItemProperty -LiteralPath ('Registry::HKEY_USERS\'+$sid+'\Software\Microsoft\PowerShell\1\ShellIds\Microsoft.PowerShell') -ErrorAction SilentlyContinue).ExecutionPolicy
[ordered]@{state='WINDOWS_DESKTOP_INSTALL_READY_AWAITING_IDENTITY';at_utc=[DateTime]::UtcNow.ToString('o');folder=$folder;shortcuts=$links;files=$files;preflight_console=[string](Get-Content -Raw -LiteralPath (Join-Path $root 'results\preflight-r4-console.txt'));current_user_policy=$(if($policy){[string]$policy}else{'Undefined'});product_task_absent=(-not (Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue));installed=(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\hara-commander-agent.ps1');paired=(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json');tls_cleanup_state=[string]$cleanup.State;tls_cleanup_principal=[string]$cleanup.Principal.UserId;tls_cleanup_next_run_utc=$info.NextRunTime.ToUniversalTime().ToString('o')}|ConvertTo-Json -Depth 7 -Compress
