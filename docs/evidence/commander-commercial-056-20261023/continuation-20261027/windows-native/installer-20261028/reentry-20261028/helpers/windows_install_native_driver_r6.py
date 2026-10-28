#!/usr/bin/python3.10
"""Finite R6 launcher refresh and two independent native preflight cases."""
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
        if len(encoded) >= 30000:
            raise SystemExit('NATIVE_PS_ENCODED_ARGUMENT_TOO_LONG')
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
                print(json.dumps({'state': 'NATIVE_SCRIPT_FAILED', 'label': label, 'exit': decoded['exit'], 'stderr_utf8_bytes': len(err.encode('utf-8'))}))
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


BUNDLE_SHA = 'c0a0d59e4f6a2db3ee8d8942bf09b86d2085df09b5f79b713247157da9d23ee7'
OLD = {
    'Instalar-ou-verificar-Commander.ps1': 'b68b42fa4abdde397827d6898fe18a493274c84f9cf9aa566b5deab764c787e2',
    'Instalar-Commander.cmd': 'fe061c145472bd4757b5145c332fc23ee26fc40854f84662ecaead8596132b14',
    'Verificar-Commander.cmd': 'f6980ba567fad166cfba5356a151d8e4972d85a5231b28f795924c040f61ca97',
}
NEW = {
    'Instalar-ou-verificar-Commander.ps1': 'c0b384d05c7fa45b636bf73a18dd2f4f8e55e001578783162de632c4fab818a1',
    'Instalar-Commander.cmd': '6a4088282c6da3dc0cfd8da2704fbca1e03f52f14ed1baf6ab4e594fe962e6ad',
    'Verificar-Commander.cmd': 'a797a0da86ab2f0a6dd7b2e8dcb470d0897a1833eeb7a98ba21581fe5730a6ea',
}
INSTALLER_SHA = '2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401'

def hashes_ps(mapping, base='$desktop', code='R6_SOURCE_MISMATCH'):
    return ''.join("if((Get-FileHash -LiteralPath (Join-Path " + base + " '" + name + "') -Algorithm SHA256).Hash.ToLowerInvariant() -cne '" + digest + "'){throw '" + code + "'}\n" for name, digest in mapping.items())

def refresh():
    raw = (BASE / 'launcher-refresh-r6.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != BUNDLE_SHA:
        raise SystemExit('R6_BUNDLE_PIN_MISMATCH')
    bundle = json.loads(raw)
    if set(bundle) != set(NEW):
        raise SystemExit('R6_BUNDLE_FILESET_MISMATCH')
    decoded = {}
    for name, expected in NEW.items():
        item = bundle[name]
        data = base64.b64decode(item['data'], validate=True)
        if hashlib.sha256(data).hexdigest() != expected or item['sha256'] != expected:
            raise SystemExit('R6_BUNDLE_FILE_PIN_MISMATCH')
        if 'bytes' in item and len(data) != item['bytes']:
            raise SystemExit('R6_BUNDLE_FILE_SIZE_MISMATCH')
        decoded[name] = data
    backup = COMMON + r"""
$backup=Join-Path $root 'backup\r5-before-r6'
if(Test-Path -LiteralPath $backup){throw 'R5_BACKUP_ALREADY_EXISTS'}
foreach($p in @($desktop,$root,(Join-Path $root 'backup'))){if((Get-Item -LiteralPath $p).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_PATH'}}
$active=@(Get-CimInstance Win32_Process -Filter "Name='powershell.exe'"|Where-Object {$_.CommandLine -like '*Instalar-ou-verificar-Commander.ps1*' -or $_.CommandLine -like '*instalar-commander-0.3.56.ps1*'})
if($active.Count){throw 'QA_LAUNCHER_STILL_RUNNING'}
""" + hashes_ps(OLD, code='R5_PREIMAGE_CHANGED') + r"""
[void][IO.Directory]::CreateDirectory($backup);Exact-Acl $backup $true ''
$items=@()
"""
    for name, digest in OLD.items():
        backup += "$source=Join-Path $desktop '" + name + "';$target=Join-Path $backup '" + name + "'\n"
        backup += "if((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_SOURCE'}\n"
        backup += "$items+=@{name='" + name + "';sha256='" + digest + "';bytes=(Get-Item -LiteralPath $source).Length;sddl=(Get-Acl -LiteralPath $source).Sddl}\n"
        backup += "Copy-Item -LiteralPath $source -Destination $target -ErrorAction Stop;Exact-Acl $target $false ''\n"
    backup += hashes_ps(OLD, '$backup', 'R5_BACKUP_HASH_MISMATCH')
    backup += r"""
[IO.File]::WriteAllText((Join-Path $backup 'preimage.json'),(@{at_utc=[DateTime]::UtcNow.ToString('o');files=$items}|ConvertTo-Json -Depth 5),[Text.Encoding]::UTF8)
@{state='R5_BACKUP_VERIFIED';backup=$backup;files=$items}|ConvertTo-Json -Depth 6 -Compress
"""
    ps('refresh-r6-preimage-backup', backup)
    transfer = BASE / 'refresh-r6-transfer.json'
    if not transfer.exists():
        # Wrapper first: while its bytes change, both old CMD pins fail closed.
        for name, data in decoded.items():
            handle = call('guest-file-open', {'path': DESKTOP + '\\' + name, 'mode': 'w'})
            try:
                for start in range(0, len(data), 16000):
                    part = data[start:start + 16000]
                    wrote = call('guest-file-write', {'handle': handle, 'buf-b64': base64.b64encode(part).decode()})
                    if wrote['count'] != len(part):
                        raise RuntimeError('R6_TRANSFER_SHORT_WRITE')
                call('guest-file-flush', {'handle': handle})
            finally:
                call('guest-file-close', {'handle': handle})
        save(transfer, {'sha256': NEW, 'bundle_sha256': BUNDLE_SHA})
    verify = COMMON + "$backup=Join-Path $root 'backup\\r5-before-r6'\n" + hashes_ps(NEW) + hashes_ps(OLD, '$backup', 'R5_BACKUP_HASH_MISMATCH')
    verify += hashes_ps({'instalar-commander-0.3.56.ps1': INSTALLER_SHA}, code='SIGNED_INSTALLER_CHANGED')
    verify += r"""
$tok=$null;$err=$null
[Management.Automation.Language.Parser]::ParseFile((Join-Path $desktop 'Instalar-ou-verificar-Commander.ps1'),[ref]$tok,[ref]$err)|Out-Null
if($err.Count){throw 'R6_WRAPPER_PARSE_FAILED'}
@{state='R6_LAUNCHERS_VERIFIED';backup_verified=$true;signed_installer_unchanged=$true;parser_errors=0}|ConvertTo-Json -Compress
"""
    return ps('refresh-r6-verify', verify)

def case_names(case):
    if case not in ('expired', 'current'):
        raise SystemExit('EXPECTED_EXPIRED_OR_CURRENT')
    return 'preflight-r6-' + case, 'HARA-QA056-Preflight-R6-' + case.title() + '-20261028'

def launch_preflight(case):
    tag, task = case_names(case)
    user = r"""
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
$root='C:\ProgramData\HARA-QA\windows-install-0356-20261028';$res=Join-Path $root 'results'
$out=[ordered]@{started_utc=[DateTime]::UtcNow.ToString('o');state='HOLD';case='@CASE@'}
$child=$null
try{
 $id=[Security.Principal.WindowsIdentity]::GetCurrent()
 if($id.User.Value -cne 'S-1-5-21-1207901905-1500652706-889822281-1005' -or (Get-Process -Id $PID).SessionId -le 0){throw 'WRONG_QA_CONTEXT'}
 $out.config_sha256_before=(Get-FileHash -LiteralPath (Join-Path $root 'config\install-config.json') -Algorithm SHA256).Hash.ToLowerInvariant()
 $p=New-Object Diagnostics.ProcessStartInfo;$p.FileName=$env:ComSpec
 $p.Arguments='/d /c call "C:\Users\CommanderQA\Desktop\HARA Commander 0.3.56 QA\Verificar-Commander.cmd" <NUL'
 $p.UseShellExecute=$false;$p.CreateNoWindow=$true;$p.RedirectStandardOutput=$true;$p.RedirectStandardError=$true
 $child=[Diagnostics.Process]::Start($p);$readOut=$child.StandardOutput.ReadToEndAsync();$readErr=$child.StandardError.ReadToEndAsync();$clock=[Diagnostics.Stopwatch]::StartNew()
 while(-not $child.WaitForExit(300)){
  try{
   $latest=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander QA') -Directory -ErrorAction SilentlyContinue|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
   if($latest -and (Test-Path -LiteralPath (Join-Path $latest.FullName 'progress.json'))){
    $progress=Get-Content -Raw -LiteralPath (Join-Path $latest.FullName 'progress.json')|ConvertFrom-Json
    if([DateTimeOffset]::Parse($progress.started_utc) -ge [DateTimeOffset]::Parse($out.started_utc)){[IO.File]::WriteAllText((Join-Path $res '@TAG@-progress.json'),($progress|ConvertTo-Json -Depth 7),[Text.Encoding]::UTF8)}
   }
  }catch{}
  if($clock.Elapsed.TotalSeconds -gt 120){& "$env:SystemRoot\System32\taskkill.exe" /PID $child.Id /T /F|Out-Null;$out.timeout=$true;break}
 }
 if(-not $child.WaitForExit(5000)){throw 'PREFLIGHT_PROCESS_NOT_EXITED'}
 if(-not $readOut.Wait(5000) -or -not $readErr.Wait(5000)){throw 'PREFLIGHT_OUTPUT_TIMEOUT'}
 $stdout=$readOut.Result;$stderr=$readErr.Result
 [IO.File]::WriteAllText((Join-Path $res '@TAG@-console.txt'),$stdout,[Text.Encoding]::UTF8)
 $out.exit_code=$child.ExitCode;$out.stderr_bytes=[Text.Encoding]::UTF8.GetByteCount($stderr)
 $run=Get-ChildItem -LiteralPath (Join-Path $env:LOCALAPPDATA 'HARA Commander QA') -Directory|Sort-Object LastWriteTimeUtc -Descending|Select-Object -First 1
 $wr=Get-Content -Raw -LiteralPath (Join-Path $run.FullName 'result.json')|ConvertFrom-Json
 if([DateTimeOffset]::Parse($wr.started_utc) -lt [DateTimeOffset]::Parse($out.started_utc)){throw 'STALE_RESULT'}
 $out.config_sha256_after=(Get-FileHash -LiteralPath (Join-Path $root 'config\install-config.json') -Algorithm SHA256).Hash.ToLowerInvariant()
 if($out.config_sha256_after -cne $out.config_sha256_before){throw 'CONFIG_CHANGED_DURING_PREFLIGHT'}
 $out.wrapper=$wr
 $noProduct=(-not [bool]$wr.installed -and -not [bool]$wr.paired -and -not (Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json'))
 if('@CASE@' -eq 'expired'){
  $expected=($child.ExitCode -eq 2 -and $wr.state -ceq 'HOLD' -and $wr.error_code -ceq 'QA_RELEASE_WINDOW_EXPIRED' -and $wr.failure_stage -ceq 'QA_RELEASE_WINDOW' -and $wr.agent_payload_verified -eq $false -and -not $wr.PSObject.Properties['preflight_exit_code'] -and -not $wr.PSObject.Properties['qa_release_http_status'] -and $noProduct -and $wr.policy_restored -eq $true)
  $out.state=if($expected){'PASS_NATIVE_EXPIRED_GUARD'}else{'HOLD_NATIVE_EXPIRED_GUARD'}
 }else{
  $expected=($child.ExitCode -eq 0 -and $wr.state -ceq 'PASS_PREFLIGHT' -and $wr.agent_payload_verified -eq $true -and $wr.agent_payload_bytes -eq 172687 -and $wr.agent_payload_sha256 -ceq 'a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620' -and $wr.qa_release_reachable -eq $true -and $wr.agent_payload_cache_removed -eq $true -and $noProduct -and $wr.policy_restored -eq $true)
  $out.state=if($expected){'PASS_NATIVE_PREFLIGHT'}else{'HOLD_NATIVE_PREFLIGHT'}
 }
}catch{$out.error_type=$_.Exception.GetType().FullName;$out.error_code=if([string]$_.Exception.Message -cmatch '^[A-Z][A-Z0-9_]{0,100}$'){[string]$_.Exception.Message}else{'NATIVE_PREFLIGHT_FAILED'}}
finally{if($child){if(-not $child.HasExited){& "$env:SystemRoot\System32\taskkill.exe" /PID $child.Id /T /F|Out-Null};$child.Dispose()}}
$out.finished_utc=[DateTime]::UtcNow.ToString('o');[IO.File]::WriteAllText((Join-Path $res '@TAG@-result.json'),($out|ConvertTo-Json -Depth 9),[Text.Encoding]::UTF8)
if($out.state -in @('PASS_NATIVE_EXPIRED_GUARD','PASS_NATIVE_PREFLIGHT')){exit 0}else{exit 2}
""".replace('@CASE@', case).replace('@TAG@', tag)
    if any("'@" in line for line in user.splitlines()):
        raise SystemExit('USER_SCRIPT_HERE_STRING_DELIMITER_REFUSED')
    script = COMMON + hashes_ps(NEW) + hashes_ps({'instalar-commander-0.3.56.ps1': INSTALLER_SHA}, code='SIGNED_INSTALLER_CHANGED')
    script += r"""
if(Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue){throw 'PRODUCT_TASK_NOT_EMPTY'}
if(Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json'){throw 'QA_ALREADY_ENROLLED'}
$cfg=Get-Content -Raw -LiteralPath (Join-Path $root 'config\install-config.json')|ConvertFrom-Json
$deadline=[DateTimeOffset]::Parse([string]$cfg.qa_administrative_trust_until_utc)
"""
    if case == 'expired':
        script += "if($deadline -gt [DateTimeOffset]::UtcNow){throw 'EXPECTED_EXPIRED_WINDOW'}\n"
    else:
        script += "if($deadline -le [DateTimeOffset]::UtcNow.AddMinutes(3)){throw 'CURRENT_WINDOW_TOO_SHORT'}\n"
    script += "$name='" + task + "'\n$tag='" + tag + "'\n"
    script += r"""
if(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue){throw 'PREFLIGHT_TASK_EXISTS'}
foreach($suffix in @('-result.json','-progress.json','-console.txt')){if(Test-Path -LiteralPath (Join-Path $results ($tag+$suffix))){throw 'PREFLIGHT_OUTPUT_EXISTS'}}
"""
    script += "$qaPreflightUserScript=@'\n" + user + "\n'@\n"
    script += "$qaPreflightEncoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($qaPreflightUserScript))\n"
    script += "$a=New-ScheduledTaskAction -Execute (Join-Path $PSHOME 'powershell.exe') -Argument ('-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand '+$qaPreflightEncoded)\n"
    script += r"""
$p=New-ScheduledTaskPrincipal -UserId $sid -LogonType Interactive -RunLevel Limited
$s=New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $name -Action $a -Principal $p -Settings $s|Out-Null
Start-ScheduledTask -TaskName $name
@{state='PREFLIGHT_STARTED';task=$name;tag=$tag;config_sha256=(Get-FileHash -LiteralPath (Join-Path $root 'config\install-config.json') -Algorithm SHA256).Hash.ToLowerInvariant()}|ConvertTo-Json -Compress
"""
    return ps('native-' + tag + '-start', script)

def result(case):
    tag, task = case_names(case)
    script = COMMON + "$file=Join-Path $results '" + tag + "-result.json';$name='" + task + "'\n"
    script += "$progressFile=Join-Path $results '" + tag + "-progress.json'\n"
    script += r"""
$t=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if(-not (Test-Path -LiteralPath $file) -or ($t -and [string]$t.State -eq 'Running')){
 $progress=$null
 if(Test-Path -LiteralPath $progressFile){try{$progress=Get-Content -Raw -LiteralPath $progressFile|ConvertFrom-Json}catch{$progress=@{stage='CHECKPOINT_WRITE_IN_PROGRESS'}}}
 @{state='PREFLIGHT_RUNNING';task_state=[string]$t.State;progress=$progress}|ConvertTo-Json -Depth 7 -Compress;exit 0
}
$r=Get-Content -Raw -LiteralPath $file|ConvertFrom-Json
"""
    script += hashes_ps(NEW) + hashes_ps({'instalar-commander-0.3.56.ps1': INSTALLER_SHA}, code='SIGNED_INSTALLER_CHANGED')
    script += r"""
$old=Get-ScheduledTask -TaskName 'HARA Commander Agent' -ErrorAction SilentlyContinue
$hasConfig=Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\device.json'
$hasAgent=Test-Path 'C:\Users\CommanderQA\AppData\Local\HARA Commander\hara-commander-agent.ps1'
$independent=@{global_state=[string]$old.State;global_task_absent=(-not [bool]$old);product_config_present=$hasConfig;product_agent_present=$hasAgent;source_pins_verified=$true}
if($t){$ti=Get-ScheduledTaskInfo -TaskName $name;$independent.task_last_result=$ti.LastTaskResult}
$r|Add-Member -NotePropertyName independent -NotePropertyValue $independent
if($old -or $hasConfig -or $hasAgent){$r.state='HOLD_NATIVE_PRODUCT_STATE_CHANGED'}
"""
    if case == 'expired':
        script += r"""
if($r.state -eq 'PASS_NATIVE_EXPIRED_GUARD' -and ($r.wrapper.error_code -cne 'QA_RELEASE_WINDOW_EXPIRED' -or $r.wrapper.agent_payload_verified -ne $false -or $r.wrapper.installed -ne $false -or $r.wrapper.paired -ne $false -or $r.wrapper.PSObject.Properties['preflight_exit_code'])){$r.state='HOLD_NATIVE_EXPIRED_GUARD'}
"""
    script += r"""
if($t -and [string]$t.State -ne 'Running'){Unregister-ScheduledTask -TaskName $name -Confirm:$false}
$r|ConvertTo-Json -Depth 11 -Compress
"""
    index = 0
    while True:
        label = tag + '-result-' + str(index)
        prior = BASE / (label + '-decoded.json')
        if not prior.exists():
            break
        observed = json.loads(prior.read_text())
        if observed['exit'] != 0 or json.loads(observed['stdout']).get('state') != 'PREFLIGHT_RUNNING':
            break
        index += 1
    return ps(label, script)

def main():
    global DOM
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'sentinela-b':
        raise SystemExit('EXPECTED_NATIVE_B_ROOT')
    action = sys.argv[1] if len(sys.argv) == 2 else ''
    allowed = ('refresh', 'preflight-expired', 'result-expired', 'preflight-current', 'result-current')
    if action not in allowed:
        raise SystemExit('EXPECTED_REFRESH_OR_NAMED_PREFLIGHT_RESULT')
    connection = libvirt.open('qemu:///system')
    DOM = connection.lookupByUUIDString('154e2853-3d1d-4d23-a43d-706f76ad7939')
    if DOM.name() != 'hara-review-win11-restoretest-20261024' or not DOM.isActive():
        raise SystemExit('EXPECTED_ACTIVE_WINDOWS_DOMAIN')
    if action == 'refresh':
        answer = refresh()
    elif action.startswith('preflight-'):
        answer = launch_preflight(action.split('-', 1)[1])
    else:
        answer = result(action.split('-', 1)[1])
    print(json.dumps(answer))

if __name__ == '__main__':
    main()
