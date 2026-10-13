#!/usr/bin/env python3
"""Check real support, uninstall, remote revoke and local cleanup on the QA guest."""
import argparse, hashlib, json, os, re, subprocess
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
Q = Path('/home/commanderqa')
F = Q / 'commander-qa'
C = Q / '.config/hara-commander/device.env'
D = Q / '.local/share/hara-commander'
parser = argparse.ArgumentParser()
parser.add_argument('--expected-version', default='0.3.54', choices=['0.3.53', '0.3.54'])
parser.add_argument('--expected-agent-sha256', default='6aecef8f8dd05bf8f2ab0c1b9c71308647892e70a0b34e2ccbe4322ad826df2e')
parser.add_argument('--expected-installer-sha256', default='d2057adfff5c2b475d1520ae44f1ed76a7ec0ecc673f65cf08631d7a0083d0fa')
a = parser.parse_args()
require(os.getuid() == 2000 and Path('/etc/hostname').read_text().strip() == 'commander-linux-clean54' and (os.geteuid() == 2000) and (Path.home() == Q), 'QA_REQUIREMENT_FAILED')
normalize_qa_environment()
v = dict((line.split('=', 1) for line in C.read_text().splitlines() if '=' in line))
DEV = 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'
require(v['HARA_COMMANDER_URL'] == DEV, 'QA_REQUIREMENT_FAILED')
require(not (D / 'operator-session.json').exists(), 'QA_REQUIREMENT_FAILED')
require(re.fullmatch('[0-9a-f]{64}', a.expected_agent_sha256) and re.fullmatch('[0-9a-f]{64}', a.expected_installer_sha256), 'QA_REQUIREMENT_FAILED')
require(not C.is_symlink() and C.stat().st_uid == 2000, 'QA_REQUIREMENT_FAILED')
require(not (D / 'hara-commander-agent').is_symlink() and (D / 'hara-commander-agent').stat().st_uid == 2000 and (hashlib.sha256((D / 'hara-commander-agent').read_bytes()).hexdigest() == a.expected_agent_sha256), 'QA_REQUIREMENT_FAILED')
require(subprocess.check_output(['python3', str(D / 'hara-commander-agent'), '--version'], text=True, timeout=5).strip() == a.expected_version, 'QA_REQUIREMENT_FAILED')
require(not (F / 'linux.sh').is_symlink() and (F / 'linux.sh').stat().st_uid == 2000 and (hashlib.sha256((F / 'linux.sh').read_bytes()).hexdigest() == a.expected_installer_sha256), 'QA_REQUIREMENT_FAILED')
keep = F / 'unrelated-user-file.txt'
keep.write_text('exclusive QA unrelated file must survive\n')
keep_sha = hashlib.sha256(keep.read_bytes()).hexdigest()
result = {'schema': 'hara.commander-linux-clean54-native-uninstall.v1', 'device_id': v['HARA_DEVICE_ID'], 'backend': 'remote_DEV_worker', 'systemctl_backend': 'real', 'private_credentials_exposed': False, 'agent_version': a.expected_version}

def clean(text):
    return text.replace(v['HARA_DEVICE_TOKEN'], '[DEVICE_TOKEN_REDACTED]')
try:
    support = subprocess.run(['bash', str(F / 'linux.sh'), 'support'], capture_output=True, text=True, timeout=40)
    require(support.returncode == 0, 'QA_REQUIREMENT_FAILED')
    report = json.loads(support.stdout.strip().splitlines()[-1])
    require(report['schema'] == 'hara.commander-support-report.v2' and report['privacy']['secret_material_exposed'] is False, 'QA_REQUIREMENT_FAILED')
    result['support_schema'] = report['schema']
    result['support_privacy_pass'] = True
    require(dict((line.split('=', 1) for line in C.read_text().splitlines() if '=' in line))['HARA_COMMANDER_URL'] == DEV, 'QA_REQUIREMENT_FAILED')
    require(hashlib.sha256((F / 'linux.sh').read_bytes()).hexdigest() == a.expected_installer_sha256 and hashlib.sha256((D / 'hara-commander-agent').read_bytes()).hexdigest() == a.expected_agent_sha256, 'QA_REQUIREMENT_FAILED')
    uninstall = subprocess.run(['bash', str(F / 'linux.sh'), 'uninstall'], capture_output=True, text=True, timeout=90)
    text = clean(uninstall.stdout + uninstall.stderr)
    result['uninstall_exit_code'] = uninstall.returncode
    result['output'] = text
    require(uninstall.returncode == 0 and 'HARA_COMMANDER_AGENT_UNINSTALL=PASS' in text and ('SERVER_DEVICE_REVOKE=PASS' in text), 'QA_REQUIREMENT_FAILED')
    checks = {'config_removed': not C.parent.exists(), 'agent_data_removed': not D.exists(), 'systemd_unit_removed': not (Q / '.config/systemd/user/hara-commander-agent.service').exists(), 'cli_removed': not (Q / '.local/bin/hara-commander').exists(), 'managed_wrapper_removed': not (Q / '.local/bin/hara').exists(), 'unrelated_file_preserved': hashlib.sha256(keep.read_bytes()).hexdigest() == keep_sha, 'service_inactive': subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'hara-commander-agent.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20).returncode != 0}
    result['cleanup_checks'] = checks
    require(all(checks.values()), 'QA_REQUIREMENT_FAILED')
    req = Request(DEV + '/api/device/heartbeat', data=json.dumps({'device_id': v['HARA_DEVICE_ID'], 'platform': 'LINUX', 'architecture': 'x86_64', 'agent_version': a.expected_version}).encode(), method='POST', headers={'authorization': 'Bearer ' + v['HARA_DEVICE_TOKEN'], 'content-type': 'application/json', 'user-agent': 'HARA-Commander-LinuxClean-DEV/1'})
    try:
        with DEV_HTTP.open(req, timeout=20) as response:
            status = response.status
    except HTTPError as error:
        status = error.code
    result['revoked_credential_http_status'] = status
    require(status in (401, 403), 'QA_REQUIREMENT_FAILED')
    result['state'] = 'PASS_NATIVE_LINUX_UNINSTALL_REVOKE_CLEANUP'
except Exception as error:
    result.update(state='FAIL_NATIVE_LINUX_UNINSTALL_REVOKE_CLEANUP', error_type=type(error).__name__)
print(json.dumps(result))
raise SystemExit(0 if result['state'].startswith('PASS') else 1)
