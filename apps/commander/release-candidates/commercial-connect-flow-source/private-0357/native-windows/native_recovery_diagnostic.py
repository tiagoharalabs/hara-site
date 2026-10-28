"""Restore the verified original QA runtime after the observed failed update."""
import base64,hashlib,json,runpy,sys
from pathlib import Path
BASE=Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028')
p=BASE/'windows_install_native_driver_r6.py'
assert hashlib.sha256(p.read_bytes()).hexdigest()=='e1d3eea70edb079e6cc8492edd3544db254d262e98eab2211bb1abdadf1f1e04'
m=runpy.run_path(str(p))
import libvirt
d=libvirt.open('qemu:///system').lookupByUUIDString('154e2853-3d1d-4d23-a43d-706f76ad7939')
assert d.name()=='hara-review-win11-restoretest-20261024' and d.isActive()
m['ps'].__globals__['DOM']=d
TASK='HARA-QA057-Restore-Original-20261028'
OUT=r'C:\ProgramData\HARA-QA\windows-install-0356-20261028\results\upgrade-0357-original-recovery.json'
USER=r'''
$ErrorActionPreference='Stop'
$out='C:\ProgramData\HARA-QA\windows-install-0356-20261028\results\upgrade-0357-original-recovery.json'
$r=[ordered]@{state='HOLD';at_utc=[DateTime]::UtcNow.ToString('o');action='RESTORE_VERIFIED_ORIGINAL_RUNTIME'}
try{
 if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -cne 'S-1-5-21-1207901905-1500652706-889822281-1005'){throw 'QA_IDENTITY_REQUIRED'}
 $source='C:\Users\CommanderQA\Desktop\HARA Commander Conexao QA\Connect-Commander.ps1'
 if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne '2c2233afa8f9eba4544ca735198922dc9424657fe40108c30445339734fb04da'){throw 'CONTROLLER_PIN_MISMATCH'}
 . $source
 $context=New-CCContext 'https://commander.haralabs.com.br' '' 'PERSISTENT_TRUSTED'
 $guard=Enter-CCGuard $context
 $state=Get-CCInstalledState $context
 if($state.Version -cne '0.3.56' -or $state.AgentSha -cne 'a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620' -or $state.DeviceId -cne 'HARA-DEVICE-a544f7b1-3ee1-49f7-aa55-f559376d5d12'){throw 'EXPECTED_ORIGINAL_AGENT_AND_BINDING_REQUIRED'}
 if((Test-CCCredential $state) -cne 'VALID'){throw 'ORIGINAL_BINDING_AUTH_FAILED'}
 $before=Get-CCFileSha $context.ConfigPath
 $xml=Export-ScheduledTask -TaskName $context.TaskName -TaskPath '\'
 $r.task_before=[string](Get-CCTask $context).State
 $receipt=Get-Content -LiteralPath 'C:\ProgramData\HARA-QA\windows-install-0356-20261028\results\upgrade-0357-native.json' -Raw|ConvertFrom-Json
 $logs=[string]$receipt.private_log_directory
 if($logs -cnotmatch '^C:\\Users\\CommanderQA\\AppData\\Local\\Temp\\hara-commander-connect-[a-f0-9]{32}$'){throw 'PRIVATE_LOG_PATH_INVALID'}
 Assert-CCNoReparse $logs
 $r.diagnostic=@{}
 foreach($name in @('installer-update-stdout.private.bin','installer-update-stderr.private.bin')){
  $text=[IO.File]::ReadAllText((Join-Path $logs $name))
  $item=@{bytes=[Text.Encoding]::UTF8.GetByteCount($text);codes=@([regex]::Matches($text,'\b(?:AGENT|HARA|RELEASE|DEVICE)_[A-Z0-9_]{2,100}\b')|ForEach-Object{$_.Value}|Select-Object -Unique);markers=@([regex]::Matches($text,'(?m)^HARA_[A-Z0-9_]+=[A-Z0-9_]+\s*$')|ForEach-Object{$_.Value.Trim()});error_id=@([regex]::Matches($text,'FullyQualifiedErrorId\s*:\s*([A-Za-z0-9_.,]+)')|ForEach-Object{$_.Groups[1].Value});script_line=@([regex]::Matches($text,':(\d+) char:(\d+)')|ForEach-Object{$_.Value})}
  $r.diagnostic[$name]=$item
 }
 $r.heartbeat_utc=Ensure-CCRuntime $context $state
 $after=Get-CCInstalledState $context
 if((Get-CCFileSha $context.ConfigPath) -cne $before -or $after.AgentSha -cne $state.AgentSha -or (Export-ScheduledTask -TaskName $context.TaskName -TaskPath '\') -cne $xml){throw 'RECOVERY_PREIMAGE_CHANGED'}
 $r.agent_version=$after.Version;$r.config_preserved=$true;$r.agent_preserved=$true;$r.task_definition_preserved=$true
 $r.task_after=[string](Get-CCTask $context).State
 $r.current_user_policy=[string](Get-ExecutionPolicy -Scope CurrentUser)
 $r.authenticated_binding=((Test-CCCredential $after) -ceq 'VALID')
 if(-not $r.authenticated_binding -or $r.task_after -cne 'Running'){throw 'RECOVERY_RUNTIME_UNCONFIRMED'}
 $r.state='PASS_ORIGINAL_RUNTIME_RECOVERED'
}catch{
 $r.error_type=$_.Exception.GetType().FullName
 $r.error_code=if([string]$_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){[string]$_.Exception.Message}else{'RECOVERY_DIAGNOSTIC_FAILED'}
}finally{
 if($guard){$guard.ReleaseMutex();$guard.Dispose()}
 $r.finished_utc=[DateTime]::UtcNow.ToString('o')
 [IO.File]::WriteAllText($out,($r|ConvertTo-Json -Depth 8 -Compress),[Text.Encoding]::UTF8)
}
if($r.state -ceq 'PASS_ORIGINAL_RUNTIME_RECOVERED'){exit 0};exit 2
'''
action=sys.argv[1]
assert action in ('run','result')
if action=='run':
    source=r'C:\ProgramData\HARA-QA\windows-install-0356-20261028\config\upgrade-0357\Recover-OriginalRuntime.ps1'
    raw=USER.encode('utf-8');sha=hashlib.sha256(raw).hexdigest()
    marker=BASE/'connect-flow-20261028/private-0357/native-windows/recovery-source-transferred.json'
    if not marker.exists():
        handle=m['call']('guest-file-open',{'path':source,'mode':'w'})
        try:
            result=m['call']('guest-file-write',{'handle':handle,'buf-b64':base64.b64encode(raw).decode()})
            assert result['count']==len(raw)
            m['call']('guest-file-flush',{'handle':handle})
        finally:m['call']('guest-file-close',{'handle':handle})
        m['save'](marker,{'sha256':sha})
    code="$name='"+TASK+"'\n$out='"+OUT+"'\n$source='"+source+"'\n$sha='"+sha+"'\n"+r'''
if((Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) -or (Test-Path -LiteralPath $out)){throw 'RECOVERY_ALREADY_ATTEMPTED'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sha){throw 'RECOVERY_SOURCE_MISMATCH'}
$tokens=$null;$errors=$null
[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)|Out-Null
if($errors.Count){throw 'RECOVERY_SOURCE_PARSE_FAILED'}
$a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$source+'"')
$p=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $name
@{state='ORIGINAL_RUNTIME_RECOVERY_STARTED'}|ConvertTo-Json -Compress
'''
    answer=m['ps']('qa0357-original-recovery-start',m['COMMON']+code)
else:
    code="$name='"+TASK+"'\n$out='"+OUT+"'\n"+r'''
$task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if($task -and [string]$task.State -eq 'Running'){@{state='RECOVERY_RUNNING'}|ConvertTo-Json -Compress;exit 0}
if(-not(Test-Path -LiteralPath $out)){@{state='RECOVERY_RECEIPT_MISSING'}|ConvertTo-Json -Compress;exit 0}
$r=Get-Content -LiteralPath $out -Raw|ConvertFrom-Json
if($task){Unregister-ScheduledTask -TaskName $name -Confirm:$false}
$r|ConvertTo-Json -Depth 8 -Compress
'''
    i=0
    while (BASE/('qa0357-original-recovery-result-'+str(i)+'-decoded.json')).exists():
        prior=json.loads((BASE/('qa0357-original-recovery-result-'+str(i)+'-decoded.json')).read_text())
        if prior['exit']!=0 or json.loads(prior['stdout']).get('state')!='RECOVERY_RUNNING':break
        i+=1
    answer=m['ps']('qa0357-original-recovery-result-'+str(i),m['COMMON']+code)
print(json.dumps(answer))
