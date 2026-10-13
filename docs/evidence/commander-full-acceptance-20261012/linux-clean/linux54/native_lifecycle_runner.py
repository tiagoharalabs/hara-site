#!/usr/bin/env python3
"""Native signed Linux54 lifecycle through the installed public CLI."""
import argparse, hashlib, json, os, pty, re, select, stat, subprocess, time
from pathlib import Path

def require(condition, message='QA_REQUIREMENT_FAILED'):
    if not condition:
        raise RuntimeError(str(message))

def normalize_qa_environment():
    q = Path('/home/commanderqa')
    r = Path('/run/user/2000')
    bus = r / 'bus'
    require(os.getuid() == 2000 and os.geteuid() == 2000 and (Path.home() == q), 'QA_IDENTITY_HOME')
    require(Path('/etc/hostname').read_text().strip() == 'commander-linux-clean54', 'QA_HOSTNAME')
    require(not r.is_symlink() and r.is_dir() and (r.stat().st_uid == 2000) and (r.stat().st_mode & 511 == 448), 'QA_RUNTIME_OWNER')
    require(bus.is_socket() and bus.stat().st_uid == 2000, 'QA_DBUS_OWNER')
    os.environ.clear()
    os.environ.update({'HOME': str(q), 'USER': 'commanderqa', 'LOGNAME': 'commanderqa', 'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8', 'TERM': 'xterm', 'PYTHONUNBUFFERED': '1', 'XDG_CONFIG_HOME': str(q / '.config'), 'XDG_DATA_HOME': str(q / '.local/share'), 'XDG_RUNTIME_DIR': str(r), 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=' + str(bus), 'HARA_COMMANDER_URL': 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'})
DEV = 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'
PIN54 = '6aecef8f8dd05bf8f2ab0c1b9c71308647892e70a0b34e2ccbe4322ad826df2e'
INSTALL54 = 'd2057adfff5c2b475d1520ae44f1ed76a7ec0ecc673f65cf08631d7a0083d0fa'
Q = Path('/home/commanderqa')
F = Q / 'commander-qa'
D = Q / '.local/share/hara-commander'
A = D / 'hara-commander-agent'
C = Q / '.config/hara-commander/device.env'
S = D / 'operator-session.json'
WRAPPER = Q / '.local/bin/hara'
INSTALLER = F / 'linux.sh'
SERVICE = 'hara-commander-agent.service'
parser = argparse.ArgumentParser()
parser.add_argument('--expected-agent-sha256', default=PIN54)
parser.add_argument('--expected-installer-sha256', default=INSTALL54)
parser.add_argument('--expected-version', default='0.3.54', choices=['0.3.53', '0.3.54'])
a = parser.parse_args()
require(os.getuid() == 2000 and os.geteuid() == 2000 and (Path.home() == Q) and (Path('/etc/hostname').read_text().strip() == 'commander-linux-clean54'), 'QA_REQUIREMENT_FAILED')
normalize_qa_environment()
require(re.fullmatch('[0-9a-f]{64}', a.expected_agent_sha256) and re.fullmatch('[0-9a-f]{64}', a.expected_installer_sha256), 'QA_REQUIREMENT_FAILED')

def config():
    values = dict((line.split('=', 1) for line in C.read_text().splitlines() if '=' in line))
    require(values['HARA_COMMANDER_URL'] == DEV, 'QA_REQUIREMENT_FAILED')
    return values

def clean(text):
    for name in ('HARA_DEVICE_TOKEN', 'HARA_OPERATOR_SESSION_TOKEN'):
        value = config().get(name)
        if value:
            text = text.replace(value, '[REDACTED]')
    return text

def run_cli(*args, timeout=45):
    runtime_guard()
    p = subprocess.run([str(WRAPPER), 'commander', *args], capture_output=True, text=True, timeout=timeout)
    return (p.returncode, clean(p.stdout + p.stderr))

def ctl(*args):
    return subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, timeout=20)

def active():
    return ctl('is-active', '--quiet', SERVICE).returncode == 0

def enabled():
    return ctl('is-enabled', '--quiet', SERVICE).returncode == 0

def runtime_guard():
    require(not A.is_symlink() and A.stat().st_uid == 2000 and (hashlib.sha256(A.read_bytes()).hexdigest() == a.expected_agent_sha256), 'QA_REQUIREMENT_FAILED')
    require(subprocess.check_output(['python3', str(A), '--version'], text=True, timeout=5).strip() == a.expected_version, 'QA_REQUIREMENT_FAILED')
    require(not INSTALLER.is_symlink() and hashlib.sha256(INSTALLER.read_bytes()).hexdigest() == a.expected_installer_sha256, 'QA_REQUIREMENT_FAILED')
    expected = {'0.3.53': 'c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953', '0.3.54': '19463b9d3c9f1c4072bb2017029ecc71da6a07c8dd7f61c4140e4f48c7fda8ae'}[a.expected_version]
    require(not WRAPPER.is_symlink() and WRAPPER.stat().st_uid == 2000 and (hashlib.sha256(WRAPPER.read_bytes()).hexdigest() == expected), 'QA_REQUIREMENT_FAILED')
    require(config()['HARA_COMMANDER_URL'] == DEV, 'QA_REQUIREMENT_FAILED')
    require(not C.is_symlink() and C.stat().st_uid == 2000, 'QA_REQUIREMENT_FAILED')
    require(os.environ['XDG_CONFIG_HOME'] == str(Q / '.config') and os.environ['XDG_DATA_HOME'] == str(Q / '.local/share') and (os.environ['XDG_RUNTIME_DIR'] == '/run/user/2000') and (os.environ['DBUS_SESSION_BUS_ADDRESS'] == 'unix:path=/run/user/2000/bus') and (os.environ['HARA_COMMANDER_URL'] == DEV), 'QA_REQUIREMENT_FAILED')

def source_guard():
    runtime_guard()
    require(config()['HARA_COMMANDER_APPROVAL_MODE'] == 'ASK_EVERY_ACTION', 'QA_REQUIREMENT_FAILED')
    require(not S.exists(), 'QA_ALREADY_HAS_OPERATOR_SESSION')

def start_marker(pid):
    raw = Path(f'/proc/{pid}/stat').read_text()
    tail = raw[raw.rfind(')') + 2:].split()
    return tail[19]

def wait_console(pid, fd, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            done, status = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            return None
        if done:
            return os.waitstatus_to_exitcode(status)
        readable, _, _ = select.select([fd], [], [], 0.1)
        if readable:
            try:
                os.read(fd, 65536)
            except OSError:
                pass
    return 'RUNNING'

def reap_owned_console(owner):
    pid, fd, marker = owner
    try:
        state = wait_console(pid, fd, 0.2)
        if state == 'RUNNING':
            if start_marker(pid) != marker:
                raise RuntimeError('QA_CONSOLE_PID_IDENTITY_CHANGED')
            os.kill(pid, 15)
            state = wait_console(pid, fd, 5)
            if state == 'RUNNING':
                if start_marker(pid) != marker:
                    raise RuntimeError('QA_CONSOLE_PID_IDENTITY_CHANGED')
                os.kill(pid, 9)
                wait_console(pid, fd, 5)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass

def start_console(expected_mode):
    runtime_guard()
    require(not S.exists(), 'QA_ALREADY_HAS_OPERATOR_SESSION')
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(str(WRAPPER), [str(WRAPPER), 'commander', 'start'], os.environ.copy())
        except BaseException:
            os._exit(127)
    marker = None
    try:
        marker = start_marker(pid)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            readable, _, _ = select.select([fd], [], [], 0.1)
            if readable:
                try:
                    os.read(fd, 65536)
                except OSError:
                    pass
            done, status = os.waitpid(pid, os.WNOHANG)
            require(not done, 'PUBLIC_CLI_START_EXITED_BEFORE_SESSION')
            if S.is_file():
                session = json.loads(S.read_text())
                if session.get('owner_pid') == pid and str(session.get('owner_start_marker')) == marker and (session.get('approval_mode') == expected_mode) and active():
                    return (pid, fd, session)
        raise RuntimeError('PUBLIC_CLI_SESSION_IDENTITY_NOT_BOUND')
    except BaseException:
        try:
            if marker and S.is_file():
                current = json.loads(S.read_text())
                if current.get('owner_pid') == pid and str(current.get('owner_start_marker')) == marker:
                    run_cli('stop', timeout=30)
        finally:
            if marker:
                reap_owned_console((pid, fd, marker))
            else:
                try:
                    os.close(fd)
                except OSError:
                    pass
        raise

def close_console(owner):
    pid, fd, marker = owner
    try:
        runtime_guard()
        current = json.loads(S.read_text()) if S.is_file() else None
        require(current and current.get('owner_pid') == pid and (str(current.get('owner_start_marker')) == marker) and (start_marker(pid) == marker), 'QA_STOP_SESSION_IDENTITY_CHANGED')
        rc, out = run_cli('stop', timeout=30)
        require(rc == 0 and (not S.exists()) and (not active()), 'PUBLIC_CLI_STOP_FAILED')
        status = wait_console(pid, fd, 15)
        require(status == 0, 'PUBLIC_CLI_CONSOLE_NATIVE_EXIT')
    finally:
        reap_owned_console(owner)
checks = []
owner = None

def note(name, ok, extra=None):
    if not ok:
        raise AssertionError(name)
    checks.append({'check': name, 'state': 'PASS', **(extra or {})})

def mcp(name, args):
    p = subprocess.Popen([str(WRAPPER), 'commander', 'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    requests = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'HARA-LinuxQA-54-core', 'version': '1'}}}, {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': name, 'arguments': args}}]
    try:
        out, _ = p.communicate(''.join((json.dumps(x) + '\n' for x in requests)), timeout=40)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate(timeout=5)
        raise RuntimeError('PUBLIC_MCP_RESPONSE_TIMEOUT')
    require(p.returncode == 0, 'PUBLIC_MCP_NATIVE_EXIT')
    responses = [json.loads(x) for x in out.splitlines() if x.strip()]
    return next((x for x in responses if x.get('id') == 2))
result = {'schema': 'hara.commander-linux-clean54-native-lifecycle.v1', 'backend': 'remote_DEV_worker', 'systemctl_backend': 'real', 'cli_entrypoint': str(WRAPPER) + ' commander', 'checks': checks, 'human_action_approval_generated': False}
try:
    source_guard()
    values = config()
    note('installed-default-ASK', values['HARA_COMMANDER_APPROVAL_MODE'] == 'ASK_EVERY_ACTION')
    note('installed-source-version-and-wrapper-pins', True)
    note('installed-service-active-disabled', active() and (not enabled()))
    note('installed-no-operator-session', not S.exists())
    target = F / 'MUST_NOT_EXIST_NO_SESSION'
    require(not target.exists(), 'QA_REQUIREMENT_FAILED')
    reply = mcp('start_process', {'command': 'touch ' + str(target), 'cwd': str(Q), 'timeout_ms': 1000})
    code = None
    payload = reply.get('result', {})
    for item in payload.get('content', []):
        if item.get('type') == 'text':
            try:
                code = json.loads(item['text']).get('code') or code
            except (ValueError, TypeError):
                pass
    note('default-ASK-no-session-mutation-denied', payload.get('isError') is True and code == 'LOCAL_OPERATOR_SESSION_REQUIRED' and (not target.exists()), {'denial_code': code})
    rc, out = run_cli('stop', timeout=30)
    note('public-cli-stop-installed-service', rc == 0 and (not active()) and (not enabled()))
    p = subprocess.run(['bash', str(INSTALLER), 'update'], capture_output=True, text=True, timeout=150)
    out = clean(p.stdout + p.stderr)
    note('offline-signed-update-preserves-offline', p.returncode == 0 and 'UPDATE_SERVICE_WAS_ACTIVE=FALSE' in out and (not active()) and (not enabled()))
    note('offline-update-preserves-source', hashlib.sha256(A.read_bytes()).hexdigest() == a.expected_agent_sha256)
    pid, fd, session = start_console('ASK_EVERY_ACTION')
    owner = (pid, fd, session['owner_start_marker'])
    note('public-cli-start-binds-own-real-session', active() and (not enabled()), {'owner_pid': pid, 'owner_start_marker': session['owner_start_marker']})
    reply = mcp('get_device_info', {})
    payload = reply.get('result', {})
    info = payload.get('structuredContent', {})
    note('public-MCP-readonly-device-info', not payload.get('isError') and info.get('state') == 'PASS' and (re.fullmatch('[0-9a-f]{64}', str(info.get('bridge_receipt_sha256', ''))) is not None))
    before = json.loads((D / 'runtime-status.json').read_text()).get('started_at_utc')
    p = subprocess.run(['bash', str(INSTALLER), 'update'], capture_output=True, text=True, timeout=150)
    out = clean(p.stdout + p.stderr)
    after = json.loads((D / 'runtime-status.json').read_text()).get('started_at_utc')
    note('active-signed-update-startup-attestation', p.returncode == 0 and 'UPDATE_SERVICE_WAS_ACTIVE=TRUE' in out and ('STARTUP_ATTESTATION=PASS' in out) and active() and (before != after))
    note('active-update-preserves-source-policy', hashlib.sha256(A.read_bytes()).hexdigest() == a.expected_agent_sha256 and config()['HARA_COMMANDER_APPROVAL_MODE'] == 'ASK_EVERY_ACTION' and (not enabled()))
    close_console(owner)
    owner = None
    note('public-cli-stop-closes-own-session-and-service', not S.exists() and (not active()))
    result.update(state='PASS_NATIVE_LINUX54_LIFECYCLE_CORE', device_id=values['HARA_DEVICE_ID'], agent_version=a.expected_version, config_mode=oct(stat.S_IMODE(C.stat().st_mode)), agent_mode=oct(stat.S_IMODE(A.stat().st_mode)), manual_agent_boot=True)
except Exception as error:
    result.update(state='FAIL_NATIVE_LINUX54_LIFECYCLE_CORE', error_type=type(error).__name__, error_code=str(error) if isinstance(error, AssertionError) else 'NATIVE_PHASE_FAILED')
finally:
    if owner is not None:
        try:
            close_console(owner)
        except Exception:
            pass
print(json.dumps(result))
raise SystemExit(0 if result['state'].startswith('PASS') else 1)
