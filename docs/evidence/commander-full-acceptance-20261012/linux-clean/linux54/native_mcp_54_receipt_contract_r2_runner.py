#!/usr/bin/env python3
"""Installed public Linux54 MCP: explicit QA session, SHA writes and 20-line PTY."""
import argparse, hashlib, json, os, pty, re, select, shlex, subprocess, time
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
receipts = []
owner = None
client = None
policy_touched = False
tool_calls = 0
pass_tool_calls = 0
precondition_rejections = 0

def note(name, ok, extra=None):
    if not ok:
        raise AssertionError(name)
    checks.append({'check': name, 'state': 'PASS', **(extra or {})})

def policy(mode, expected):
    global policy_touched
    require(not S.exists(), 'QA_POLICY_CHANGE_BLOCKED_ACTIVE_SESSION')
    policy_touched = True
    rc, out = run_cli('approval-mode', mode)
    require(rc == 0, 'PUBLIC_APPROVAL_MODE_SET_NATIVE_EXIT')
    rc, get = run_cli('approval-mode')
    note('public-approval-mode-' + mode + '-set-and-get', rc == 0 and 'HARA_COMMANDER_APPROVAL_MODE=' + expected in get and (config()['HARA_COMMANDER_APPROVAL_MODE'] == expected))

class Client:

    def __init__(self):
        self.p = subprocess.Popen([str(WRAPPER), 'commander', 'mcp'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        os.set_blocking(self.p.stdout.fileno(), False)
        self.buffer = bytearray()
        self.next_id = 0
        try:
            self.call('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'HARA-LinuxQA-54', 'version': '1'}})
        except BaseException:
            self.close()
            raise

    def call(self, method, params):
        self.next_id += 1
        ident = self.next_id
        wire = (json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params}, ensure_ascii=False) + '\n').encode()
        self.p.stdin.write(wire)
        self.p.stdin.flush()
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if b'\n' in self.buffer:
                raw, _, rest = self.buffer.partition(b'\n')
                self.buffer = bytearray(rest)
                if not raw.strip():
                    continue
                response = json.loads(raw.decode('utf-8'))
                if 'id' not in response:
                    continue
                require(response.get('id') == ident and 'error' not in response, 'MCP_PROTOCOL_ERROR')
                return response['result']
            readable, _, _ = select.select([self.p.stdout.fileno()], [], [], min(0.5, max(0, deadline - time.monotonic())))
            if not readable:
                continue
            try:
                chunk = os.read(self.p.stdout.fileno(), 65536)
            except BlockingIOError:
                continue
            if not chunk:
                raise RuntimeError('PUBLIC_MCP_EOF')
            self.buffer.extend(chunk)
            if len(self.buffer) > 2 * 1024 * 1024:
                raise RuntimeError('PUBLIC_MCP_RESPONSE_TOO_LARGE')
        raise RuntimeError('PUBLIC_MCP_RESPONSE_TIMEOUT')

    def tool(self, name, args=None):
        global tool_calls, pass_tool_calls, precondition_rejections
        tool_calls += 1
        response = self.call('tools/call', {'name': name, 'arguments': args or {}})
        result = response.get('structuredContent')
        require(isinstance(result, dict), 'MCP_STRUCTURED_RESULT_MISSING')
        sha = result.get('bridge_receipt_sha256')
        if result.get('state') == 'PASS':
            require(isinstance(sha, str) and re.fullmatch('[0-9a-f]{64}', sha), 'MCP_RECEIPT_MISSING')
            receipts.append(sha)
            pass_tool_calls += 1
        else:
            blocker = result.get('blocker')
            require(isinstance(blocker, dict) and result.get('state') == 'CONFLICT' and blocker.get('code') == 'FILE_PRECONDITION_FAILED' and blocker.get('category') == 'FILE_PRECONDITION' and result.get('mutation_performed') is False and sha is None, 'MCP_UNEXPECTED_NONEXECUTION_RESULT')
            precondition_rejections += 1
        return result

    def close(self):
        if self.p.stdin and (not self.p.stdin.closed):
            try:
                self.p.stdin.close()
            except BrokenPipeError:
                pass
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.p.terminate()
            try:
                self.p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.p.kill()
                self.p.wait(timeout=5)

def data(result):
    note('MCP-operation-receipt-PASS', result.get('state') == 'PASS')
    return json.loads(result['result']['stdout'])
result = {'schema': 'hara.commander-linux-clean54-native-mcp.v1', 'backend': 'installed_public_product_MCP_LOCAL_STDIO_with_real_DEV_enrollment', 'systemctl_backend': 'real', 'cli_entrypoint': str(WRAPPER) + ' commander', 'human_ASK_response_generated': False, 'authorization': 'explicit_QA_SESSION_TRUSTED_until_own_CLI_close', 'managed_max_lines_contract': 'requested_20_initial_then_100_retained_numbered_lines', 'checks': checks, 'receipt_sha256': receipts}
try:
    source_guard()
    rc, out = run_cli('approval-mode')
    note('public-default-ASK-get', rc == 0 and 'HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION' in out)
    policy('session', 'SESSION_TRUSTED')
    pid, fd, session = start_console('SESSION_TRUSTED')
    owner = (pid, fd, session['owner_start_marker'])
    note('public-CLI-bounded-QA-session-identity', session.get('owner_pid') == pid and str(session.get('owner_start_marker')) == start_marker(pid), {'owner_pid': pid, 'owner_start_marker': session['owner_start_marker']})
    client = Client()
    folder = F / 'mcp-54'
    data(client.tool('create_directory', {'path': str(folder), 'parents': True}))
    path = folder / 'unicode.txt'
    first = 'Olá ação H.A.R.A. São Paulo — v54\n'
    second = 'Café açaí: execução confirmada.\n'
    sha1 = hashlib.sha256(first.encode()).hexdigest()
    sha2 = hashlib.sha256(second.encode()).hexdigest()
    write = client.tool('write_file', {'path': str(path), 'content': first, 'mode': 'rewrite'})
    data(write)
    note('session-authorization-source', write['result'].get('authorization_source') == 'LOCAL_OPERATOR_SESSION')
    read = data(client.tool('read_file', {'path': str(path), 'offset': 0, 'length': 30}))
    note('Unicode-write-read-exact', read.get('text') == first.rstrip('\n') and hashlib.sha256(path.read_bytes()).hexdigest() == sha1)
    data(client.tool('write_file', {'path': str(path), 'content': second, 'mode': 'rewrite', 'expected_sha256': sha1}))
    stale = client.tool('write_file', {'path': str(path), 'content': 'MUST_NOT_REPLACE\n', 'mode': 'rewrite', 'expected_sha256': sha1})
    note('stale-SHA-conflict-preserves-file', stale.get('state') == 'CONFLICT' and stale.get('blocker', {}).get('code') == 'FILE_PRECONDITION_FAILED' and stale.get('blocker', {}).get('category') == 'FILE_PRECONDITION' and stale.get('mutation_performed') is False and hashlib.sha256(path.read_bytes()).hexdigest() == sha2)
    bounded_code = "import sys;[print('QA-BOUND-%03d'%i,flush=True) for i in range(120)]"
    bounded = data(client.tool('start_process', {'command': 'python3 -u -c ' + shlex.quote(bounded_code), 'cwd': str(folder), 'interactive': False, 'timeout_ms': 3000, 'max_lines': 20}))
    note('bounded-run-line-cap-20', len(bounded.get('text', '').splitlines()) == 20 and bounded.get('total_lines') == 120 and (bounded.get('output_truncated') is True) and (bounded.get('exit_code') == 0) and (re.findall('QA-BOUND-([0-9]{3})', bounded.get('text', '')) == [f'{i:03}' for i in range(20)]))
    input_ = 'Café HARA açaí'
    input_sha = hashlib.sha256(input_.encode()).hexdigest()
    code = "import sys,hashlib;[print('QA-LINE-%03d'%i,flush=True) for i in range(120)];print('QA_READY',flush=True);v=sys.stdin.readline().rstrip('\\n');print('INPUT_SHA='+hashlib.sha256(v.encode()).hexdigest(),flush=True)"
    started = data(client.tool('start_process', {'command': 'python3 -u -c ' + shlex.quote(code), 'cwd': str(folder), 'interactive': True, 'timeout_ms': 1000, 'max_lines': 20}))
    sid = started['session_id']
    initial = started.get('text', '')
    chunks = [initial]
    note('managed-requested-initial-20-lines', len(initial.splitlines()) == 20 and re.findall('QA-LINE-([0-9]{3})', initial) == [f'{i:03}' for i in range(20)] and (started.get('next_offset') == 20))
    deferred = data(client.tool('read_process_output', {'session_id': sid, 'length': 100, 'timeout_ms': 1000}))
    chunks.append(deferred.get('text', ''))
    note('managed-retains-exactly-next-100-numbered-lines', re.findall('QA-LINE-([0-9]{3})', deferred.get('text', '')) == [f'{i:03}' for i in range(20, 120)], {'retained_numbered_line_count': 100})
    ready = 'QA_READY' in '\n'.join(chunks)
    for _ in range(10):
        if ready:
            break
        d = data(client.tool('read_process_output', {'session_id': sid, 'length': 100, 'timeout_ms': 1000}))
        chunks.append(d.get('text', ''))
        ready = 'QA_READY' in '\n'.join(chunks)
    note('interactive-PTY-ready-before-input', ready)
    echo = data(client.tool('interact_with_process', {'session_id': sid, 'input': input_ + '\n', 'timeout_ms': 1000}))
    chunks.append(echo.get('text', ''))
    exited = echo.get('state') == 'EXITED' and echo.get('exit_code') == 0
    for _ in range(15):
        if exited:
            break
        d = data(client.tool('read_process_output', {'session_id': sid, 'length': 100, 'timeout_ms': 1000}))
        chunks.append(d.get('text', ''))
        if d.get('state') == 'EXITED':
            exited = d.get('exit_code') == 0
            break
    text = '\n'.join(chunks)
    lines = re.findall('QA-LINE-([0-9]{3})', text)
    note('interactive-PTY-120-lines-complete-once', lines == [f'{i:03}' for i in range(120)] and exited, {'numbered_line_count': len(lines)})
    note('interactive-UTF8-input-roundtrip', 'INPUT_SHA=' + input_sha in text)
    note('all-PASS-MCP-operations-have-distinct-receipts', len(receipts) == pass_tool_calls and len(set(receipts)) == len(receipts) and tool_calls == pass_tool_calls + precondition_rejections and precondition_rejections == 1, {'PASS_tool_call_count': pass_tool_calls, 'preexecution_conflict_count': precondition_rejections})
    client.close()
    client = None
    close_console(owner)
    owner = None
    note('public-close-revokes-own-session', not S.exists() and (not active()))
    policy('ask', 'ASK_EVERY_ACTION')
    source_guard()
    result.update(state='PASS_NATIVE_LINUX_MCP_54', agent_version=a.expected_version, managed_initial_numbered_lines=20, managed_retained_numbered_lines=100, total_numbered_lines=120, tool_call_count=tool_calls, PASS_tool_call_count=pass_tool_calls, preexecution_conflict_count=precondition_rejections)
except Exception as error:
    result.update(state='FAIL_NATIVE_LINUX_MCP_54', error_type=type(error).__name__, error_code=str(error) if isinstance(error, AssertionError) else 'NATIVE_MCP_PHASE_FAILED')
finally:
    if client:
        try:
            client.close()
        except Exception:
            pass
    if owner:
        try:
            close_console(owner)
        except Exception:
            pass
    if policy_touched:
        try:
            if S.exists():
                result['active_session_preserved_without_policy_write'] = True
                raise RuntimeError('QA_POLICY_RESTORE_BLOCKED_ACTIVE_SESSION')
            rc, out = run_cli('approval-mode', 'ask')
            rc_get, get = run_cli('approval-mode')
            ok = rc == 0 and rc_get == 0 and (config()['HARA_COMMANDER_APPROVAL_MODE'] == 'ASK_EVERY_ACTION') and ('HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION' in get) and (not S.exists()) and (not active())
            result['qa_policy_restored_ASK_and_session_closed'] = ok
            if not ok:
                result['state'] = 'FAIL_NATIVE_LINUX_MCP_54_POLICY_RESTORE'
        except Exception:
            result['qa_policy_restored_ASK_and_session_closed'] = False
            result['state'] = 'FAIL_NATIVE_LINUX_MCP_54_POLICY_RESTORE'
print(json.dumps(result))
raise SystemExit(0 if result['state'].startswith('PASS') else 1)
