#!/usr/bin/python3.10
"""Finite QGA staging/launch for the existing CommanderQA Windows session."""
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, '/usr/lib/python3/dist-packages')
import libvirt
import libvirt_qemu

BASE = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028')
WIN = r'C:\ProgramData\HARA-QA\windows-install-0356-20261028'
DESKTOP = r'C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA'
PS = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'

def save(path, obj):
    data = (json.dumps(obj, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def call(name, args):
    r = json.loads(libvirt_qemu.qemuAgentCommand(DOM, json.dumps({'execute': name, 'arguments': args}), 5, 0))
    if 'error' in r:
        raise RuntimeError(json.dumps(r['error']))
    return r['return']

def ps(label, script):
    launch = BASE / (label + '-launch.json')
    completed = BASE / (label + '-complete.json')
    if not launch.exists():
        encoded = base64.b64encode(script.encode('utf-16-le')).decode()
        r = call('guest-exec', {'path': PS, 'arg': ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded], 'capture-output': True})
        save(launch, r)
    pid = json.loads(launch.read_text())['pid']
    for _ in range(6):
        if completed.exists():
            r = json.loads(completed.read_text())
        else:
            r = call('guest-exec-status', {'pid': pid})
            if r.get('exited'):
                save(completed, r)
        if r.get('exited'):
            out = base64.b64decode(r.get('out-data', '')).decode('utf-8', 'replace')
            err = base64.b64decode(r.get('err-data', '')).decode('utf-8', 'replace')
            decoded = {'exit': r.get('exitcode'), 'stdout': out, 'stderr': err}
            f = BASE / (label + '-decoded.json')
            if not f.exists():
                save(f, decoded)
            if decoded['exit'] != 0:
                print(json.dumps(decoded))
                raise SystemExit(2)
            return json.loads(out.strip())
        time.sleep(.15)
    print(json.dumps({'state': 'RUNNING', 'label': label, 'pid': pid}))
    raise SystemExit(0)

COMMON = r'''
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne 'S-1-5-18'){throw 'SYSTEM_REQUIRED'}
$qa=Get-LocalUser CommanderQA;$sid=$qa.SID.Value
if($sid -cne 'S-1-5-21-1207901905-1500652706-889822281-1005'){throw 'WRONG_QA_SID'}
$console=[string](Get-CimInstance Win32_ComputerSystem).UserName
if($console -ine 'HARA_WIN11\CommanderQA'){throw 'COMMANDERQA_CONSOLE_REQUIRED'}
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028'
$desktop='C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA'
$results=Join-Path $root 'results'
function Exact-Acl([string]$Path,[bool]$Directory,[string]$QaRights){
 $acl=if($Directory){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
 $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-18')));$acl.SetAccessRuleProtection($true,$false)
 $inherit=if($Directory){[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'}else{[Security.AccessControl.InheritanceFlags]::None}
 foreach($s in @('S-1-5-18','S-1-5-32-544',$sid)){
  if($s -eq $sid -and -not $QaRights){continue}
  $rights=if($s -eq $sid){$QaRights}else{'FullControl'}
  $rule=New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($s)),$rights,$inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
  [void]$acl.AddAccessRule($rule)
 };Set-Acl -LiteralPath $Path -AclObject $acl
}
function Hash-Text([string]$Text){$h=[Security.Cryptography.SHA256]::Create();try{[BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text))).Replace('-','').ToLowerInvariant()}finally{$h.Dispose()}}
'''

def stage():
    raw = (BASE / 'desktop-install-bundle.json').read_bytes()
    pin = (BASE / 'desktop-install-bundle.sha256').read_text().strip()
    assert hashlib.sha256(raw).hexdigest() == pin
    b = json.loads(raw)
    files = b['files']
    expected = []
    decoded = {}
    allowed = {'Instalar-Commander.cmd', 'Verificar-Commander.cmd', 'Instalar-ou-verificar-Commander.ps1', 'install-config.json', 'qa-release.der', 'ACESSO-IDENTITY.txt'}
    assert set(files) == allowed
    for name, item in files.items():
        data = base64.b64decode(item['data'], validate=True)
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']
        path = WIN + '\\config\\' + name if name in ('install-config.json', 'qa-release.der') else DESKTOP + '\\' + name
        expected.append({'name': name, 'path': path, 'bytes': len(data), 'sha256': item['sha256']})
        decoded[path] = data
    rows = base64.b64encode(json.dumps(expected).encode()).decode()
    prepare = COMMON + r'''
if(Test-Path -LiteralPath $root){throw 'INSTALL_STAGE_ALREADY_EXISTS'}
foreach($p in @('C:\ProgramData\HARA-QA',$desktop)){if((Get-Item -LiteralPath $p).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_PATH'}}
[void][IO.Directory]::CreateDirectory($root);Exact-Acl $root $true 'ReadAndExecute'
foreach($n in @('config','results','backup')){[void][IO.Directory]::CreateDirectory((Join-Path $root $n))}
Exact-Acl (Join-Path $root 'config') $true 'ReadAndExecute'
Exact-Acl $results $true 'FullControl';Exact-Acl (Join-Path $root 'backup') $true ''
$rows=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(''' + "'" + rows + "'" + r'''))|ConvertFrom-Json
foreach($r in $rows){if(Test-Path -LiteralPath $r.path){throw 'DESTINATION_EXISTS'};[void](New-Item -ItemType File -Path $r.path)}
[ordered]@{state='INSTALL_STAGE_READY';console=$console;root=$root;parent_owner=(Get-Acl 'C:\ProgramData\HARA-QA').Owner}|ConvertTo-Json -Compress
'''
    ps('install-stage-prepare', prepare)
    transfer = BASE / 'install-stage-transfer.json'
    if not transfer.exists():
        for path, data in decoded.items():
            handle = call('guest-file-open', {'path': path, 'mode': 'w'})
            try:
                for i in range(0, len(data), 16000):
                    chunk = data[i:i + 16000]
                    wrote = call('guest-file-write', {'handle': handle, 'buf-b64': base64.b64encode(chunk).decode()})
                    assert wrote['count'] == len(chunk)
                call('guest-file-flush', {'handle': handle})
            finally:
                call('guest-file-close', {'handle': handle})
        save(transfer, expected)
    verify = COMMON + r'''
$rows=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(''' + "'" + rows + "'" + r'''))|ConvertFrom-Json
foreach($r in $rows){$f=Get-Item -LiteralPath $r.path;if($f.Length -ne $r.bytes -or (Get-FileHash -LiteralPath $r.path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $r.sha256){throw 'STAGED_FILE_MISMATCH'}}
$parsed=@();foreach($name in @('Instalar-ou-verificar-Commander.ps1','instalar-commander-0.3.56.ps1')){$tokens=$null;$errors=$null;[Management.Automation.Language.Parser]::ParseFile((Join-Path $desktop $name),[ref]$tokens,[ref]$errors)|Out-Null;$parsed+=@{name=$name;errors=@($errors|ForEach-Object{$_.ErrorId})};if($errors.Count){throw 'PARSE_FAILED'}}
[ordered]@{state='INSTALL_LAUNCHERS_STAGED_AND_PARSED';files=$rows;parser=$parsed;installed=(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json')}|ConvertTo-Json -Depth 7 -Compress
'''
    return ps('install-stage-verify', verify)

def launch_preflight():
    user = r'''
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028';$res=Join-Path $root 'results'
$out=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');state='HOLD'}
try{
 $p=New-Object Diagnostics.ProcessStartInfo;$p.FileName=$env:ComSpec
 $p.Arguments='/d /c call "C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA\Verificar-Commander.cmd" <NUL'
 $p.UseShellExecute=$false;$p.CreateNoWindow=$true;$p.RedirectStandardOutput=$true;$p.RedirectStandardError=$true
 $child=[Diagnostics.Process]::Start($p);$readOut=$child.StandardOutput.ReadToEndAsync();$readErr=$child.StandardError.ReadToEndAsync();$clock=[Diagnostics.Stopwatch]::StartNew()
 while(-not $child.WaitForExit(300)){
  $latest=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander QA') -Directory -ErrorAction SilentlyContinue|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
  if($latest -and (Test-Path -LiteralPath (Join-Path $latest.FullName 'progress.json'))){$progress=Get-Content -Raw -LiteralPath (Join-Path $latest.FullName 'progress.json');[IO.File]::WriteAllText((Join-Path $res 'preflight-r5-progress.json'),$progress,[Text.Encoding]::UTF8)}
  if($clock.Elapsed.TotalSeconds -gt 90){& "$env:SystemRoot\System32\taskkill.exe" /PID $child.Id /T /F|Out-Null;$out.timeout=$true;break}
 }
 $child.WaitForExit();$stdout=$readOut.Result;$stderr=$readErr.Result
 [IO.File]::WriteAllText((Join-Path $res 'preflight-r5-console.txt'),$stdout,[Text.Encoding]::UTF8)
 $out.exit_code=$child.ExitCode;$out.stderr_bytes=$stderr.Length
 $run=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander QA') -Directory|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
 $wr=Get-Content -Raw -LiteralPath (Join-Path $run.FullName 'result.json')|ConvertFrom-Json
 if([DateTimeOffset]::Parse($wr.started_utc) -lt [DateTimeOffset]::Parse($out.started_utc)){throw 'STALE_RESULT'}
 $out.wrapper=$wr;$out.state=if($child.ExitCode -eq 0 -and $wr.state -eq 'PASS_PREFLIGHT' -and $wr.agent_payload_verified -eq $true){'PASS_NATIVE_PREFLIGHT'}else{'HOLD_NATIVE_PREFLIGHT'}
}catch{$out.error_type=$_.Exception.GetType().FullName;$out.error_code=if([string]$_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){[string]$_.Exception.Message}else{'NATIVE_PREFLIGHT_FAILED'}}
$out.finished_utc=[DateTime]::UtcNow.ToString('o');[IO.File]::WriteAllText((Join-Path $res 'preflight-r5-result.json'),($out|ConvertTo-Json -Depth 9),[Text.Encoding]::UTF8)
if($out.state -eq 'PASS_NATIVE_PREFLIGHT'){exit 0}else{exit 2}
'''
    encoded = base64.b64encode(user.encode('utf-16-le')).decode()
    script = COMMON + r'''
$name='HARA-QA056-Install-Preflight-R5-20261028'
if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'PREFLIGHT_TASK_EXISTS'}
$a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand ''' + "' + '" + encoded + "'" + r''')
$p=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $name
@{state='PREFLIGHT_STARTED';task=$name}|ConvertTo-Json -Compress
'''
    return ps('native-preflight-r5-start', script)

def refresh():
    bundle = json.loads((BASE / 'launcher-refresh-r5.json').read_text())
    old = {'Instalar-Commander.cmd': 'b70b1a6571844e6bed5edbddb2e47240ad7133a4ba1e881997872b0a36398dfc',
           'Verificar-Commander.cmd': 'b15e32fb04d4779f0e0d9ab4a3c9f663021ddd15c227e0bab7c10ac780dc993c',
           'Instalar-ou-verificar-Commander.ps1': '4e1c1aa8981a67b0dd8a1b14c6841875b940f4150c6dfcf017a6ed73d38ee72c'}
    assert set(bundle) == set(old)
    decoded = {}
    for name, item in bundle.items():
        data = base64.b64decode(item['data'], validate=True)
        assert hashlib.sha256(data).hexdigest() == item['sha256']
        decoded[name] = data
    checks = ''
    for name, digest in old.items():
        checks += "if((Get-FileHash -LiteralPath (Join-Path $desktop '" + name + "') -Algorithm SHA256).Hash.ToLowerInvariant() -cne '" + digest + "'){throw 'LAUNCHER_PREIMAGE_CHANGED'}\n"
    ps('refresh-r5-preimage', COMMON + checks + "@{state='R5_PREIMAGE_MATCHED'}|ConvertTo-Json -Compress")
    transfer = BASE / 'refresh-r5-transfer.json'
    if not transfer.exists():
        for name, data in decoded.items():
            handle = call('guest-file-open', {'path': DESKTOP + '\\' + name, 'mode': 'w'})
            try:
                r = call('guest-file-write', {'handle': handle, 'buf-b64': base64.b64encode(data).decode()})
                assert r['count'] == len(data)
                call('guest-file-flush', {'handle': handle})
            finally:
                call('guest-file-close', {'handle': handle})
        save(transfer, {'sha256': {n: x['sha256'] for n, x in bundle.items()}})
    checks = ''
    for name, item in bundle.items():
        checks += "if((Get-FileHash -LiteralPath (Join-Path $desktop '" + name + "') -Algorithm SHA256).Hash.ToLowerInvariant() -cne '" + item['sha256'] + "'){throw 'LAUNCHER_REFRESH_MISMATCH'}\n"
    checks += "$tok=$null;$err=$null;[Management.Automation.Language.Parser]::ParseFile((Join-Path $desktop 'Instalar-ou-verificar-Commander.ps1'),[ref]$tok,[ref]$err)|Out-Null;if($err.Count){throw 'WRAPPER_PARSE_FAILED'}\n"
    return ps('refresh-r5-verify', COMMON + checks + "@{state='R5_LAUNCHERS_VERIFIED'}|ConvertTo-Json -Compress")

def result():
    script = COMMON + r'''
$file=Join-Path $results 'preflight-r5-result.json';$name='HARA-QA056-Install-Preflight-R5-20261028'
$t=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if(-not (Test-Path -LiteralPath $file)){$pr=Join-Path $results 'preflight-r5-progress.json';$progress=$null;if(Test-Path -LiteralPath $pr){try{$progress=Get-Content -Raw -LiteralPath $pr|ConvertFrom-Json}catch{$progress=@{stage='CHECKPOINT_WRITE_IN_PROGRESS'}}};@{state='PREFLIGHT_RUNNING';task_state=[string]$t.State;progress=$progress}|ConvertTo-Json -Depth 6 -Compress;exit 0}
$r=Get-Content -Raw -LiteralPath $file|ConvertFrom-Json
if($t -and [string]$t.State -ne 'Running'){Unregister-ScheduledTask -TaskName $name -Confirm:$false}
$old=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
$r|Add-Member -NotePropertyName independent -NotePropertyValue (@{global_state=[string]$old.State;global_task_absent=(-not [bool]$old);product_config_present=(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json')})
$r|ConvertTo-Json -Depth 10 -Compress
'''
    index = 0
    while True:
        label = 'preflight-r5-result-' + str(index)
        prior = BASE / (label + '-decoded.json')
        if not prior.exists():
            break
        observed = json.loads(prior.read_text())
        if json.loads(observed['stdout']).get('state') != 'PREFLIGHT_RUNNING':
            break
        index += 1
    return ps(label, script)

def main():
    global DOM
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'sentinela-b':
        raise SystemExit('EXPECTED_NATIVE_B_ROOT')
    c = libvirt.open('qemu:///system')
    DOM = c.lookupByUUIDString('154e2853-3d1d-4d23-a43d-706f76ad7939')
    assert DOM.name() == 'hara-review-win11-restoretest-20261024' and DOM.isActive()
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    if action == 'stage':
        r = stage()
    elif action == 'preflight':
        r = launch_preflight()
    elif action == 'result':
        r = result()
    elif action == 'refresh':
        r = refresh()
    else:
        raise SystemExit('EXPECTED_STAGE_PREFLIGHT_RESULT')
    print(json.dumps(r))

if __name__ == '__main__':
    main()
