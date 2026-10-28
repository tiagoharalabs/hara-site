"""Stage, run and observe the one authorized Windows QA .57 update."""
import base64
import hashlib
import json
from pathlib import Path
import runpy
import sys

BASE = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028')
ROOT = BASE / 'connect-flow-20261028/private-0357'
original = BASE / 'windows_install_native_driver_r6.py'
assert hashlib.sha256(original.read_bytes()).hexdigest() == 'e1d3eea70edb079e6cc8492edd3544db254d262e98eab2211bb1abdadf1f1e04'
m = runpy.run_path(str(original))
import libvirt
connection = libvirt.open('qemu:///system')
domain = connection.lookupByUUIDString('154e2853-3d1d-4d23-a43d-706f76ad7939')
assert domain.name() == 'hara-review-win11-restoretest-20261024' and domain.isActive()
m['ps'].__globals__['DOM'] = domain
SOURCE_SHA = 'fa0f7c579a00b0b1fbd5c45452d2024fe685c6f7b1fffe78ab8f202d50fe0516'
FOLDER = r'C:\ProgramData\HARA-QA\windows-install-0356-20261028\config\upgrade-0357'
FILE = FOLDER + r'\Invoke-Private0357Upgrade.ps1'
RESULT = r'C:\ProgramData\HARA-QA\windows-install-0356-20261028\results\upgrade-0357-native.json'
TASK = 'HARA-QA057-Connect-Upgrade-20261028'

def ps(label, code):
    return m['ps'](label, m['COMMON'] + code)

action = sys.argv[1]
assert action in ('stage', 'run', 'result')
if action == 'stage':
    data = (ROOT/'native-windows/Invoke-Private0357Upgrade.ps1').read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA
    ps('qa0357-windows-folder', "$folder='"+FOLDER+"'\n"+r"""
if(Test-Path -LiteralPath $folder){throw 'PRIVATE_UPGRADE_FOLDER_EXISTS'}
[void][IO.Directory]::CreateDirectory($folder)
Exact-Acl $folder $true 'ReadAndExecute'
@{state='PRIVATE_UPGRADE_SOURCE_FOLDER_READY'}|ConvertTo-Json -Compress
""")
    marker = ROOT/'native-windows/source-transferred.json'
    if not marker.exists():
        handle = m['call']('guest-file-open', {'path':FILE,'mode':'w'})
        try:
            for start in range(0,len(data),16000):
                chunk = data[start:start+16000]
                written = m['call']('guest-file-write', {'handle':handle,'buf-b64':base64.b64encode(chunk).decode()})
                assert written['count'] == len(chunk)
            m['call']('guest-file-flush', {'handle':handle})
        finally:
            m['call']('guest-file-close', {'handle':handle})
        m['save'](marker, {'sha256':SOURCE_SHA})
    script = "$source='"+FILE+"'\n"
    script += """
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne '"""+SOURCE_SHA+"""'){throw 'PRIVATE_UPGRADE_SOURCE_HASH_MISMATCH'}
$tokens=$null;$errors=$null
[Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$errors)|Out-Null
if($errors.Count){throw 'PRIVATE_UPGRADE_SOURCE_PARSE_FAILED'}
@{state='PRIVATE_UPGRADE_SOURCE_NATIVE_PARSED';sha256='"""+SOURCE_SHA+"""';parser_errors=0;installer_executed=$false}|ConvertTo-Json -Compress
"""
    answer = ps('qa0357-windows-source-verify', script)
elif action == 'run':
    script = "$name='"+TASK+"'\n$source='"+FILE+"'\n$receipt='"+RESULT+"'\n"
    script += """
if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'PRIVATE_UPGRADE_TASK_EXISTS'}
if((Test-Path -LiteralPath $receipt) -or (Test-Path -LiteralPath ($receipt+'.progress.json'))){throw 'PRIVATE_UPGRADE_ALREADY_ATTEMPTED'}
if((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant() -cne '"""+SOURCE_SHA+"""'){throw 'PRIVATE_UPGRADE_SOURCE_HASH_MISMATCH'}
$arguments='-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -File "'+$source+'" -NativeReceiptPath "'+$receipt+'"'
$action=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument $arguments
$principal=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Settings $settings|Out-Null
Start-ScheduledTask -TaskName $name
@{state='PRIVATE_SIGNED_UPGRADE_STARTED';task=$name;receipt=$receipt;user_sid=$sid}|ConvertTo-Json -Compress
"""
    answer = ps('qa0357-windows-upgrade-start', script)
else:
    script = "$name='"+TASK+"'\n$receipt='"+RESULT+"'\n"
    script += r"""
$task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if($task -and [string]$task.State -eq 'Running'){
    $out=@{state='NATIVE_UPGRADE_RUNNING';task_state=[string]$task.State}
    if(Test-Path -LiteralPath ($receipt+'.progress.json')){$out.progress=Get-Content -Raw -LiteralPath ($receipt+'.progress.json')|ConvertFrom-Json}
    $out|ConvertTo-Json -Depth 8 -Compress
    exit 0
}
if(-not(Test-Path -LiteralPath $receipt)){
    $out=@{state='NATIVE_UPGRADE_RECEIPT_MISSING';task_present=[bool]$task}
    if($task){$out.task_last_result=(Get-ScheduledTaskInfo -TaskName $name).LastTaskResult}
    $out|ConvertTo-Json -Compress
    exit 0
}
$report=Get-Content -Raw -LiteralPath $receipt|ConvertFrom-Json
if($task){
    $report|Add-Member -NotePropertyName diagnostic_task_exit -NotePropertyValue (Get-ScheduledTaskInfo -TaskName $name).LastTaskResult
    Unregister-ScheduledTask -TaskName $name -Confirm:$false
}
$report|ConvertTo-Json -Depth 9 -Compress
"""
    index=0
    while True:
        label='qa0357-windows-upgrade-result-'+str(index)
        prior=BASE/(label+'-decoded.json')
        if not prior.exists():
            break
        value=json.loads(prior.read_text())
        if value['exit'] != 0 or json.loads(value['stdout']).get('state') != 'NATIVE_UPGRADE_RUNNING':
            break
        index+=1
    answer=ps(label,script)
print(json.dumps(answer))
