#!/usr/bin/env python3
"""Finite public-file staging and captured PowerShell driver for the existing QA VM.

Native execution is root-only on physical Sentinela B. No credentials, Agent
configuration, installer/network calls or arbitrary scripts/arguments are accepted.
Keep polling through this driver: QGA consumes completed guest-exec status.
"""
import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

UUID = '154e2853-3d1d-4d23-a43d-706f76ad7939'
NAME = 'hara-review-win11-restoretest-20261024'
PREP = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027')
CODE = PREP / 'code/windows-0356'
NATIVE = PREP / 'windows-native-0356-20261027'
STATE = NATIVE / 'qga-public-driver-activeqa'
WIN = r'C:\ProgramData\HARA-QA\native-0356-activeqa-20261027'
SOURCE = WIN + r'\source'
RESULTS = WIN + r'\results'
POWERSHELL = r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
BOOTSTRAP = 'bootstrap_windows_commanderqa_native_components.ps1'
# Bootstrap/runner pins are frozen by the Windows fixture owner before native use.
PINS = {
    'agent-windows-0.3.56.ps1': (PREP / 'install-0356-private/assets/agent/windows.ps1', 172687,
                   'a44e2f7c7ce75cf2cff0e60886fce60bd999b9e4cea22e5baa24619d9ee27620'),
    'test_commercial_056_windows_job_native.ps1': (CODE / 'test_commercial_056_windows_job_native.ps1', 6037,
                   'e4210dc8346456d928ecbf645a963a6e8710aeca4f30a69d643e7c3c9c56f710'),
    'test_windows_commanderqa_user_context_native.ps1': (CODE / 'test_windows_commanderqa_user_context_native.ps1', 11390,
                   '4a7a9c42b198caba5143ccd7928b2b8d7b03696126e3f6374a0f540bd9e03cfd'),
    'run_windows_commanderqa_native_components.ps1': (CODE / 'run_windows_commanderqa_native_components.ps1', 10241,
                   '912ba13f77ca5e72128af1c1f79e8fec7e0b92454f0a82dd1d01e9ca53f65cb6'),
    BOOTSTRAP: (CODE / BOOTSTRAP, 10075,
                   'fa8f5b6eba9e187404077f6ea9f00701a843d5aaaa6adb97b1ec6393c5678885'),
}


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def need(value, code):
    if not value:
        raise RuntimeError(code)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_dir(path):
    path.mkdir(mode=0o700, exist_ok=True)
    meta = path.lstat()
    need(stat.S_ISDIR(meta.st_mode) and not path.is_symlink() and
         meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o700,
         'PRIVATE_NATIVE_DIRECTORY_UNSAFE')


def put(path, value):
    data = (json.dumps(value, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    fsync_dir(path.parent)


def load(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        meta = os.fstat(fd)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and
             stat.S_IMODE(meta.st_mode) == 0o600 and meta.st_nlink == 1 and
             meta.st_size <= 8 * 1024 * 1024, 'NATIVE_STATE_FILE_UNSAFE')
        with os.fdopen(fd, 'r', closefd=False) as src:
            return json.load(src)
    finally:
        os.close(fd)


def read_pinned(path, size, expected):
    need(len(expected) == 64 and all(c in '0123456789abcdef' for c in expected)
         and 0 < size <= 1024 * 1024, 'PUBLIC_SOURCE_PIN_NOT_FROZEN')
    for parent in (path.parent, *path.parent.parents):
        meta = parent.lstat()
        need(stat.S_ISDIR(meta.st_mode) and not parent.is_symlink() and
             meta.st_uid == 0 and not meta.st_mode & 0o022, 'PUBLIC_SOURCE_PARENT_UNSAFE')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and
             not before.st_mode & 0o022 and before.st_nlink == 1 and before.st_size == size,
             'PUBLIC_SOURCE_METADATA')
        data = b''
        while len(data) <= size:
            chunk = os.read(fd, min(65536, size + 1 - len(data)))
            if not chunk:
                break
            data += chunk
        after = os.fstat(fd)
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'PUBLIC_SOURCE_CHANGED')
        need(len(data) == size and digest(data) == expected, 'PUBLIC_SOURCE_PIN_MISMATCH')
        return data
    finally:
        os.close(fd)


def public_bundle():
    files = {name: read_pinned(*pin) for name, pin in PINS.items()}
    manifest = {'schema': 'hara.commander.qa-public-stage.v1', 'version': '0.3.56',
                'account': 'CommanderQA', 'windows_root': WIN,
                'files': [{'name': name, 'size': len(data), 'sha256': digest(data)}
                          for name, data in sorted(files.items())]}
    files['public-manifest.json'] = (json.dumps(manifest, sort_keys=True, separators=(',', ':')) + '\n').encode()
    transfer = [{'name': name, 'size': len(data), 'sha256': digest(data)}
                for name, data in sorted(files.items())]
    return files, manifest, transfer


PS_COMMON = r'''
$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
if([Security.Principal.WindowsIdentity]::GetCurrent().User.Value -ne 'S-1-5-18'){throw 'SYSTEM_CONTEXT_REQUIRED'}
$root='C:\ProgramData\HARA-QA\native-0356-activeqa-20261027'
$source=Join-Path $root 'source';$results=Join-Path $root 'results'
$qa=Get-LocalUser -Name 'CommanderQA' -ErrorAction Stop
$qaSid=$qa.SID.Value
if(-not $qa.Enabled){throw 'QA_ACCOUNT_DISABLED'}
$admins=Get-LocalGroup -SID 'S-1-5-32-544'
if(@(Get-LocalGroupMember -Group $admins | Where-Object {$_.SID.Value -eq $qaSid}).Count -ne 0){throw 'QA_MUST_BE_STANDARD'}
function Assert-NoReparse([string]$Path){
 $p=$Path
 while($p){
  $item=Get-Item -LiteralPath $p -Force -ErrorAction Stop
  if($item.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_COMPONENT_REFUSED'}
  $next=[IO.Path]::GetDirectoryName($p.TrimEnd('\'))
  if(-not $next -or $next -eq $p){break};$p=$next
 }
}
function Exact-Acl([string]$Path,[bool]$Directory,[bool]$QaFull){
 $acl=if($Directory){New-Object Security.AccessControl.DirectorySecurity}else{New-Object Security.AccessControl.FileSecurity}
 $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))
 $acl.SetAccessRuleProtection($true,$false)
 $inherit=if($Directory){[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'}else{[Security.AccessControl.InheritanceFlags]::None}
 foreach($sid in @('S-1-5-18','S-1-5-32-544',$qaSid)){
  $rights=if($sid -eq $qaSid -and -not $QaFull){[Security.AccessControl.FileSystemRights]::ReadAndExecute}else{[Security.AccessControl.FileSystemRights]::FullControl}
  $rule=New-Object Security.AccessControl.FileSystemAccessRule((New-Object Security.Principal.SecurityIdentifier($sid)),$rights,$inherit,[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AccessControlType]::Allow)
  [void]$acl.AddAccessRule($rule)
 }
 Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
 Assert-ExactAcl $Path $Directory $QaFull
}
function Assert-ExactAcl([string]$Path,[bool]$Directory,[bool]$QaFull){
 Assert-NoReparse $Path
 $acl=Get-Acl -LiteralPath $Path -ErrorAction Stop
 if($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -ne 'S-1-5-18' -or -not $acl.AreAccessRulesProtected){throw 'PROTECTED_SYSTEM_OWNER_REQUIRED'}
 $rules=@($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))
 if($rules.Count -ne 3){throw 'ACL_RULE_COUNT'}
 $seen=@{};$inherit=if($Directory){3}else{0}
 foreach($r in $rules){
  $sid=$r.IdentityReference.Value
  if(@('S-1-5-18','S-1-5-32-544',$qaSid) -notcontains $sid -or $seen.ContainsKey($sid)){throw 'ACL_PRINCIPAL'}
  $expected=if($sid -eq $qaSid -and -not $QaFull){0x1200a9}else{0x1f01ff}
  if($r.AccessControlType -ne 'Allow' -or $r.IsInherited -or [int64]$r.FileSystemRights -ne $expected -or [int]$r.InheritanceFlags -ne $inherit -or [int]$r.PropagationFlags -ne 0){throw 'ACL_RIGHTS'}
  $seen[$sid]=$true
 }
}
function New-Directory([string]$Path,[bool]$QaFull){
 if(Test-Path -LiteralPath $Path){throw 'CREATE_ONLY_DIRECTORY_EXISTS'}
 Assert-NoReparse ([IO.Path]::GetDirectoryName($Path))
 [void][IO.Directory]::CreateDirectory($Path)
 Exact-Acl $Path $true $QaFull
}
$transfer=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__TRANSFER__')) | ConvertFrom-Json
'''

PS_PREPARE = r'''
Assert-NoReparse 'C:\ProgramData'
$parent='C:\ProgramData\HARA-QA'
if(-not (Test-Path -LiteralPath $parent)){New-Directory $parent $false}
else {
 Assert-NoReparse $parent
 $acl=Get-Acl -LiteralPath $parent
 if(@('S-1-5-18','S-1-5-32-544') -notcontains $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value){throw 'PARENT_ADMIN_OWNER_REQUIRED'}
 foreach($r in @($acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier]))){
  if($r.AccessControlType -eq 'Allow' -and @('S-1-5-18','S-1-5-32-544') -notcontains $r.IdentityReference.Value -and ([int64]$r.FileSystemRights -band 0x500d0156)){throw 'PARENT_UNTRUSTED_WRITE'}
 }
}
New-Directory $root $false
New-Directory $source $false
New-Directory $results $true
$created=@()
foreach($f in $transfer){
 if($f.name -notmatch '^[a-zA-Z0-9_.-]+$'){throw 'SOURCE_LEAF_INVALID'}
 $path=Join-Path $source ([string]$f.name)
 $stream=New-Object IO.FileStream($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
 $stream.Dispose()
 Exact-Acl $path $false $false
 $created+=@{name=$f.name;size=0}
}
[ordered]@{state='PASS_PUBLIC_STAGE_PREPARED';account='CommanderQA';source=$source;results=$results;files=$created;installed=$false;paired=$false}|ConvertTo-Json -Depth 6 -Compress
'''

PS_VERIFY = r'''
Assert-ExactAcl $root $true $false
Assert-ExactAcl $source $true $false
Assert-ExactAcl $results $true $true
$actual=@(Get-ChildItem -LiteralPath $source -Force | ForEach-Object {$_.Name})
if(@(Compare-Object $actual @($transfer|ForEach-Object{$_.name})).Count -ne 0){throw 'SOURCE_FILE_SET_CHANGED'}
$checked=@()
foreach($f in $transfer){
 $path=Join-Path $source ([string]$f.name)
 Assert-ExactAcl $path $false $false
 $item=Get-Item -LiteralPath $path -Force
 if($item.PSIsContainer -or $item.Length -ne [long]$f.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$f.sha256){throw 'STAGED_SOURCE_PIN_MISMATCH'}
 $parseCount=0;$ids=@()
 if($f.name.EndsWith('.ps1')){
  $tokens=$null;$errors=$null
  [Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)|Out-Null
  $parseCount=@($errors).Count;$ids=@($errors|ForEach-Object{$_.ErrorId})
 }
 $checked+=@{name=$f.name;sha256=$f.sha256;size=$item.Length;parser_error_count=$parseCount;parser_error_ids=$ids;acl='PASS'}
}
if(@($checked|Where-Object{$_.parser_error_count -ne 0}).Count -ne 0){
 [ordered]@{state='HOLD_PUBLIC_SOURCE_PARSE';files=$checked}|ConvertTo-Json -Depth 8 -Compress
 exit 7
}
[ordered]@{state='PASS_PUBLIC_STAGE_VERIFIED';account='CommanderQA';files=$checked;installed=$false;paired=$false}|ConvertTo-Json -Depth 8 -Compress
'''

PS_READBACK = r'''
Assert-ExactAcl $root $true $false
Assert-ExactAcl $source $true $false
Assert-ExactAcl $results $true $true
$console=(Get-CimInstance Win32_ComputerSystem).UserName
$file=Join-Path $root 'bootstrap-result.json'
$closeout=$null
if(Test-Path -LiteralPath $file){
 Assert-NoReparse $file
 $owner=(Get-Acl -LiteralPath $file).GetOwner([Security.Principal.SecurityIdentifier]).Value
 if(@('S-1-5-18','S-1-5-32-544') -notcontains $owner){throw 'BOOTSTRAP_RESULT_OWNER'}
 if((Get-Item -LiteralPath $file).Length -gt 1048576){throw 'BOOTSTRAP_RESULT_TOO_LARGE'}
 $closeout=Get-Content -Raw -LiteralPath $file|ConvertFrom-Json
}
[ordered]@{state='PASS_READBACK_ONLY_NOT_ACCEPTANCE';console_user=$console;bootstrap_closeout=$closeout;source_acl='PASS';results_acl='PASS'}|ConvertTo-Json -Depth 16 -Compress
'''


class Driver:
    def __init__(self, qga, base=STATE):
        self.qga = qga
        self.base = base
        private_dir(self.base)

    def operation(self, label):
        need(label in ('stage-prepare', 'stage-verify', 'bootstrap', 'readback'), 'OPERATION_DENIED')
        path = self.base / label
        private_dir(path)
        return path

    def decode(self, folder, status):
        # complete.json is already durable before this method may decode anything.
        need((folder / 'complete.json').exists(), 'COMPLETION_NOT_PERSISTED')
        stdout = base64.b64decode(status.get('out-data', ''), validate=True)
        stderr = base64.b64decode(status.get('err-data', ''), validate=True)
        need(len(stdout) <= 2 * 1024 * 1024 and len(stderr) <= 2 * 1024 * 1024, 'CAPTURE_TOO_LARGE')
        text = stdout.decode('utf-8-sig', 'replace')
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        report = {'guest_pid': load(folder / 'launch.json')['guest_pid'],
                  'exited': True, 'exit_code': status.get('exitcode'),
                  'signal': status.get('signal'),
                  'out_truncated': bool(status.get('out-truncated', False)),
                  'err_truncated': bool(status.get('err-truncated', False)),
                  'stdout_sha256': digest(stdout), 'stdout_bytes': len(stdout),
                  'stderr_sha256': digest(stderr), 'stderr_bytes': len(stderr),
                  'result': parsed,
                  'state': 'COMPLETED_CAPTURED' if parsed is not None else 'HOLD_CAPTURE_PARSE'}
        if not (folder / 'decoded.json').exists():
            put(folder / 'decoded.json', report)
        return report

    def poll(self, label, wait_seconds=45):
        folder = self.operation(label)
        if (folder / 'complete.json').exists():
            return self.decode(folder, load(folder / 'complete.json')['status'])
        need((folder / 'launch.json').exists(), 'NO_DURABLE_GUEST_PID_NO_RELAUNCH')
        launch = load(folder / 'launch.json')
        need(launch['domain_uuid'] == UUID and launch['operation'] == label, 'PID_BINDING_MISMATCH')
        pid = launch['guest_pid']
        need(type(pid) is int and pid > 0, 'GUEST_PID_INVALID')
        deadline = time.monotonic() + wait_seconds
        while True:
            status = self.qga('guest-exec-status', {'pid': pid})
            if status.get('exited') is True:
                # QGA has consumed this completed response. Save before decode/checks.
                put(folder / 'complete.json', {'guest_pid': pid, 'captured_at_utc': stamp(), 'status': status})
                return self.decode(folder, status)
            if time.monotonic() >= deadline:
                return {'state': 'PENDING_KNOWN_GUEST_PID', 'guest_pid': pid,
                        'operation': label, 'exited': False, 'retry_launch_permitted': False}
            time.sleep(min(.5, max(0, deadline - time.monotonic())))

    def run_ps(self, label, script, wait_seconds=45):
        folder = self.operation(label)
        source_hash = digest(script.encode())
        if (folder / 'intent.json').exists():
            previous = load(folder / 'intent.json')
            need(previous['script_sha256'] == source_hash, 'SCRIPT_CHANGED_DURING_OPERATION')
            return self.poll(label, wait_seconds)
        put(folder / 'intent.json', {'operation': label, 'domain_uuid': UUID,
                                     'script_sha256': source_hash, 'created_at_utc': stamp()})
        result = self.qga('guest-exec', {
            'path': POWERSHELL,
            'arg': ['-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand',
                    base64.b64encode(script.encode('utf-16le')).decode()],
            'capture-output': True,
        })
        pid = result.get('pid')
        need(type(pid) is int and pid > 0, 'GUEST_LAUNCH_PID_INVALID')
        put(folder / 'launch.json', {'operation': label, 'domain_uuid': UUID,
                                     'guest_pid': pid, 'script_sha256': source_hash,
                                     'launched_at_utc': stamp()})
        if wait_seconds == 0:
            return {'state': 'PENDING_KNOWN_GUEST_PID', 'guest_pid': pid,
                    'operation': label, 'exited': False, 'retry_launch_permitted': False}
        return self.poll(label, wait_seconds)

    def transfer(self, name, data):
        need(name in {*PINS, 'public-manifest.json'}, 'TRANSFER_NAME_DENIED')
        folder = self.base / 'transfers'
        private_dir(folder)
        intent = folder / (name + '.intent.json')
        complete = folder / (name + '.complete.json')
        expected = {'name': name, 'sha256': digest(data), 'bytes': len(data)}
        if complete.exists():
            prior = load(complete)
            need(all(prior[k] == v for k, v in expected.items()) and prior['closed'] is True,
                 'TRANSFER_PRIOR_MISMATCH')
            return prior
        need(not intent.exists(), 'PARTIAL_TRANSFER_REQUIRES_READBACK_NO_REPLAY')
        put(intent, dict(expected, created_at_utc=stamp()))
        handle = self.qga('guest-file-open', {'path': SOURCE + '\\' + name, 'mode': 'r+'})
        need(type(handle) is int and handle >= 0, 'FILE_HANDLE_INVALID')
        put(folder / (name + '.handle.json'), {'handle': handle, 'name': name, 'domain_uuid': UUID})
        offset = 0
        try:
            while offset < len(data):
                chunk = data[offset:offset + 16384]
                result = self.qga('guest-file-write', {'handle': handle,
                                 'buf-b64': base64.b64encode(chunk).decode()})
                count = result.get('count')
                need(type(count) is int and 0 < count <= len(chunk), 'FILE_WRITE_COUNT_INVALID')
                offset += count
            self.qga('guest-file-flush', {'handle': handle})
        finally:
            self.qga('guest-file-close', {'handle': handle})
        report = dict(expected, bytes_confirmed_written=offset, closed=True, finished_at_utc=stamp())
        put(complete, report)
        return report


def check_capture(report, expected_state):
    need(report.get('exited') is True, 'GUEST_OPERATION_PENDING_USE_SAME_DRIVER')
    need(report.get('exit_code') == 0 and not report.get('out_truncated') and
         not report.get('err_truncated') and isinstance(report.get('result'), dict),
         'GUEST_OPERATION_EXIT_CAPTURE_OR_PARSE')
    need(report['result'].get('state') == expected_state, 'GUEST_OPERATION_RESULT_STATE')


def ps_script(tail, transfer):
    encoded = base64.b64encode(json.dumps(transfer, separators=(',', ':')).encode()).decode()
    return PS_COMMON.replace('__TRANSFER__', encoded) + tail


def console_report(action, report):
    """Keep Commander stdout bounded; full captures remain in protected files."""
    operation = {'stage': 'stage-verify', 'bootstrap': 'bootstrap',
                 'poll': 'bootstrap', 'readback': 'readback'}[action]
    result = report.get('result') or report.get('guest_result') or {}
    value = {'action': action, 'state': report.get('state'),
             'guest_pid': report.get('guest_pid'), 'exited': report.get('exited'),
             'exit_code': report.get('exit_code'), 'result_state': result.get('state'),
             'capture_directory': str(STATE / operation),
             'full_capture_file': str(STATE / operation / 'complete.json'),
             'decoded_file': str(STATE / operation / 'decoded.json'),
             'retry_launch_permitted': False}
    if isinstance(result.get('bootstrap_closeout'), dict):
        value['bootstrap_closeout_state'] = result['bootstrap_closeout'].get('state')
    if 'files' in report:
        value['public_files_verified'] = len(report['files'])
        value['manifest_sha256'] = report.get('manifest_sha256')
    return value


def stage(driver, files, manifest, transfer):
    caps = driver.qga('guest-info', {})
    available = {x['name'] for x in caps.get('supported_commands', []) if x.get('enabled')}
    need({'guest-file-open', 'guest-file-write', 'guest-file-flush', 'guest-file-close',
          'guest-exec', 'guest-exec-status'} <= available, 'REQUIRED_QGA_CAPABILITY_UNAVAILABLE')
    prepared = driver.run_ps('stage-prepare', ps_script(PS_PREPARE, transfer))
    check_capture(prepared, 'PASS_PUBLIC_STAGE_PREPARED')
    for name, data in sorted(files.items()):
        driver.transfer(name, data)
    verified = driver.run_ps('stage-verify', ps_script(PS_VERIFY, transfer))
    check_capture(verified, 'PASS_PUBLIC_STAGE_VERIFIED')
    return {'state': 'PASS_PUBLIC_STAGE_VERIFIED', 'files': transfer,
            'manifest_sha256': digest(files['public-manifest.json']),
            'guest_result': verified['result'], 'installed': False, 'paired': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('stage', 'bootstrap', 'poll', 'readback'))
    args = parser.parse_args()
    need(os.geteuid() == 0, 'NATIVE_ROOT_REQUIRED')
    private_dir(NATIVE)
    private_dir(STATE)
    lock = os.open(STATE / 'driver.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        meta = os.fstat(lock)
        need(stat.S_ISREG(meta.st_mode) and meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o600,
             'DRIVER_LOCK_UNSAFE')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sys.path.insert(0, '/usr/lib/python3/dist-packages')
        import libvirt
        import libvirt_qemu
        conn = libvirt.open('qemu:///system')
        try:
            try:
                domain = conn.lookupByUUIDString(UUID)
            except libvirt.libvirtError as exc:
                if exc.get_error_code() == libvirt.VIR_ERR_NO_DOMAIN:
                    raise RuntimeError('EXACT_ACTIVE_WINDOWS_QA_VM_NOT_FOUND') from None
                raise
            need(domain.name() == NAME and domain.UUIDString() == UUID and domain.isActive(),
                 'EXACT_ACTIVE_WINDOWS_QA_VM_REQUIRED')
            def qga(execute, arguments):
                result = json.loads(libvirt_qemu.qemuAgentCommand(domain,
                    json.dumps({'execute': execute, 'arguments': arguments}), 5, 0))
                need('return' in result and 'error' not in result, 'QGA_PROTOCOL_ERROR')
                return result['return']
            driver = Driver(qga)
            if args.action == 'poll':
                report = driver.poll('bootstrap')
            else:
                files, manifest, transfer = public_bundle()
                if args.action == 'stage':
                    report = stage(driver, files, manifest, transfer)
                elif args.action == 'bootstrap':
                    checked = driver.poll('stage-verify', wait_seconds=0)
                    check_capture(checked, 'PASS_PUBLIC_STAGE_VERIFIED')
                    bootstrap_code = "$ProgressPreference='SilentlyContinue'\n[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)\n" + files[BOOTSTRAP].decode('utf-8-sig')
                    report = driver.run_ps('bootstrap', bootstrap_code, wait_seconds=0)
                else:
                    terminal = driver.poll('bootstrap', wait_seconds=0)
                    need(terminal.get('exited') is True, 'BOOTSTRAP_STILL_PENDING_READBACK_NOT_LAUNCHED')
                    report = driver.run_ps('readback', ps_script(PS_READBACK, transfer))
            print(json.dumps(console_report(args.action, report)))
            return 7 if (report.get('exited') is True and report.get('exit_code') != 0) or str(report.get('state', '')).startswith('HOLD') else 0
        finally:
            conn.close()
    finally:
        os.close(lock)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        message = str(exc)
        code = message if message and len(message) < 120 and all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ_0123456789' for c in message) else 'DRIVER_OPERATION_FAILED'
        print(json.dumps({'state': 'HOLD', 'code': code, 'error_type': type(exc).__name__,
                          'automatic_relaunch_or_replay': False, 'native_state': str(STATE)}))
        raise SystemExit(7)
