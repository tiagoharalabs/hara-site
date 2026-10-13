#!/usr/bin/env python3
"""Run the immutable installer on the exclusive Linux QA guest with real systemd."""
import argparse, hashlib, json, os, pty, re, select, stat, subprocess, time
from pathlib import Path
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

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

class NoRedirect(HTTPRedirectHandler):

    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None
DEV_HTTP = build_opener(NoRedirect())
EXPECTED_INSTALLER = 'd2057adfff5c2b475d1520ae44f1ed76a7ec0ecc673f65cf08631d7a0083d0fa'
EXPECTED_AGENT = '6aecef8f8dd05bf8f2ab0c1b9c71308647892e70a0b34e2ccbe4322ad826df2e'
DEV = 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'
p = argparse.ArgumentParser()
p.add_argument('action', choices=['install', 're-enroll'])
p.add_argument('--fixture', type=Path, required=True)
p.add_argument('--installer', type=Path, required=True)
p.add_argument('--expected-installer-sha256', default=EXPECTED_INSTALLER)
p.add_argument('--expected-agent-sha256', default=EXPECTED_AGENT)
p.add_argument('--expected-version', choices=['0.3.53', '0.3.54'], default='0.3.54')
a = p.parse_args()
require(re.fullmatch('[0-9a-f]{64}', a.expected_installer_sha256) and re.fullmatch('[0-9a-f]{64}', a.expected_agent_sha256), 'QA_REQUIREMENT_FAILED')
EXPECTED_INSTALLER = a.expected_installer_sha256
EXPECTED_AGENT = a.expected_agent_sha256
require(os.getuid() == 2000 and Path('/etc/hostname').read_text().strip() == 'commander-linux-clean54' and (os.geteuid() == 2000) and (Path.home() == Path('/home/commanderqa')), 'QA_REQUIREMENT_FAILED')
normalize_qa_environment()
require(not a.fixture.is_symlink() and a.fixture.is_file() and (a.fixture.stat().st_uid == 2000) and (stat.S_IMODE(a.fixture.stat().st_mode) == 384), 'QA_REQUIREMENT_FAILED')
fixture = json.loads(a.fixture.read_text())
require(fixture['dev_origin'] == DEV and fixture['environment'] == 'DEV', 'QA_REQUIREMENT_FAILED')
require(not a.installer.is_symlink() and a.installer.is_file() and (a.installer.stat().st_uid == 2000) and (hashlib.sha256(a.installer.read_bytes()).hexdigest() == EXPECTED_INSTALLER), 'QA_REQUIREMENT_FAILED')
prior_values = {}
if a.action == 're-enroll':
    prior_config = Path.home() / '.config/hara-commander/device.env'
    prior_values = dict((line.split('=', 1) for line in prior_config.read_text().splitlines() if '=' in line))
    require(prior_values['HARA_COMMANDER_URL'] == DEV, 'QA_REQUIREMENT_FAILED')
token = fixture['pairing_token']
env = dict(os.environ, HARA_COMMANDER_URL=DEV)
env.pop('HARA_COMMANDER_APPROVAL_MODE', None)
pid, fd = pty.fork()
if pid == 0:
    try:
        os.execvpe('bash', ['bash', str(a.installer), a.action], env)
    except BaseException:
        os._exit(127)
buf = bytearray()
sent = False
status = None
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    readable, _, _ = select.select([fd], [], [], 0.1)
    if readable:
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            chunk = b''
        if chunk:
            buf.extend(chunk)
            if not sent and b'Pairing token:' in buf:
                os.write(fd, (token + '\n').encode())
                sent = True
    done, s = os.waitpid(pid, os.WNOHANG)
    if done:
        status = s
        break
if status is None:
    os.kill(pid, 9)
    _, status = os.waitpid(pid, 0)
os.set_blocking(fd, False)
drain_deadline = time.monotonic() + 3
while time.monotonic() < drain_deadline:
    readable, _, _ = select.select([fd], [], [], min(0.1, max(0, drain_deadline - time.monotonic())))
    if not readable:
        continue
    try:
        chunk = os.read(fd, 65536)
    except BlockingIOError:
        continue
    except OSError:
        break
    if not chunk:
        break
    buf.extend(chunk)
os.close(fd)
rc = os.waitstatus_to_exitcode(status)
config = Path.home() / '.config/hara-commander/device.env'
values = {}
if config.is_file():
    for line in config.read_text().splitlines():
        if '=' in line:
            k, v = line.split('=', 1)
            values[k] = v
out = buf.decode('utf-8', 'replace').replace(token, '[PAIRING_TOKEN_REDACTED]')
for key in ('HARA_DEVICE_TOKEN', 'HARA_OPERATOR_SESSION_TOKEN'):
    if values.get(key):
        out = out.replace(values[key], '[DEVICE_TOKEN_REDACTED]')
agent = Path.home() / '.local/share/hara-commander/hara-commander-agent'
result = {'schema': 'hara.commander-linux-clean54-native-installer.v1', 'action': a.action, 'state': 'PASS' if rc == 0 else 'FAIL', 'exit_code': rc, 'pairing_prompt_received': sent, 'approval_mode': values.get('HARA_COMMANDER_APPROVAL_MODE'), 'device_id': values.get('HARA_DEVICE_ID'), 'device_token_exposed': False, 'human_action_approval_generated': False, 'systemctl_backend': 'real', 'backend': 'remote_DEV_worker', 'installer_sha256': hashlib.sha256(a.installer.read_bytes()).hexdigest(), 'agent_sha256': hashlib.sha256(agent.read_bytes()).hexdigest() if agent.is_file() else None, 'expected_version': a.expected_version, 'output': out}
if rc == 0:
    require(sent, 'PAIRING_PROMPT_NOT_RECEIVED')
    require(result['agent_sha256'] == EXPECTED_AGENT, 'QA_REQUIREMENT_FAILED')
    require(subprocess.check_output(['python3', str(agent), '--version'], text=True, timeout=5).strip() == a.expected_version, 'QA_REQUIREMENT_FAILED')
    require(result['approval_mode'] == 'ASK_EVERY_ACTION', 'QA_REQUIREMENT_FAILED')
    require(values['HARA_COMMANDER_URL'] == DEV, 'QA_REQUIREMENT_FAILED')
    wrapper = Path.home() / '.local/bin/hara'
    expected_wrapper = {'0.3.53': 'c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953', '0.3.54': '19463b9d3c9f1c4072bb2017029ecc71da6a07c8dd7f61c4140e4f48c7fda8ae'}[a.expected_version]
    require(not wrapper.is_symlink() and hashlib.sha256(wrapper.read_bytes()).hexdigest() == expected_wrapper, 'QA_REQUIREMENT_FAILED')
    result['public_wrapper_sha256'] = expected_wrapper
    require(stat.S_IMODE(config.stat().st_mode) == 384, 'QA_REQUIREMENT_FAILED')
    if prior_values:
        require(values['HARA_DEVICE_ID'] != prior_values['HARA_DEVICE_ID'], 'QA_REQUIREMENT_FAILED')
        req = Request(DEV + '/api/device/heartbeat', data=json.dumps({'device_id': prior_values['HARA_DEVICE_ID'], 'platform': 'LINUX', 'architecture': 'x86_64', 'agent_version': a.expected_version}).encode(), method='POST', headers={'authorization': 'Bearer ' + prior_values['HARA_DEVICE_TOKEN'], 'content-type': 'application/json', 'user-agent': 'HARA-Commander-LinuxClean-DEV/1'})
        try:
            with DEV_HTTP.open(req, timeout=20) as response:
                old_status = response.status
        except HTTPError as error:
            old_status = error.code
        require(old_status in (401, 403), 'QA_REQUIREMENT_FAILED')
        result['old_authority_rejected'] = True
        result['old_credential_http_status'] = old_status
        result['prior_device_id'] = prior_values['HARA_DEVICE_ID']
print(json.dumps(result))
raise SystemExit(rc)
