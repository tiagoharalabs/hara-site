#!/usr/bin/env python3
"""Inject one real QA process crash to exercise immutable installer rollback."""
import argparse, hashlib, json, os, re, subprocess, time
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
Q = Path('/home/commanderqa')
D = Q / '.local/share/hara-commander'
A = D / 'hara-commander-agent'
C = Q / '.config/hara-commander/device.env'
F = Q / 'commander-qa'
U = Q / '.config/systemd/user/hara-commander-agent.service.d'
DROP = U / '90-qa-rollback-fault.conf'
MARK = F / 'crash-once.marker'
FAULT = F / 'qa_crash_once.py'
S = 'hara-commander-agent.service'
PIN = '6aecef8f8dd05bf8f2ab0c1b9c71308647892e70a0b34e2ccbe4322ad826df2e'
parser = argparse.ArgumentParser()
parser.add_argument('--expected-agent-sha256', default=PIN)
parser.add_argument('--expected-version', default='0.3.54', choices=['0.3.53', '0.3.54'])
parser.add_argument('--expected-installer-sha256', default='d2057adfff5c2b475d1520ae44f1ed76a7ec0ecc673f65cf08631d7a0083d0fa')
a = parser.parse_args()
require(re.fullmatch('[0-9a-f]{64}', a.expected_agent_sha256), 'QA_REQUIREMENT_FAILED')
PIN = a.expected_agent_sha256
require(os.getuid() == 2000 and Path('/etc/hostname').read_text().strip() == 'commander-linux-clean54' and (os.geteuid() == 2000) and (Path.home() == Q), 'QA_REQUIREMENT_FAILED')
normalize_qa_environment()
require(not DROP.exists() and (not MARK.exists()), 'QA_REQUIREMENT_FAILED')
values = dict((line.split('=', 1) for line in C.read_text().splitlines() if '=' in line))
require(values['HARA_COMMANDER_URL'] == 'https://hara-commander-dev-v2.tiago-sartori.workers.dev', 'QA_REQUIREMENT_FAILED')
require(not C.is_symlink() and C.stat().st_uid == 2000, 'QA_REQUIREMENT_FAILED')
require(not A.is_symlink() and A.stat().st_uid == 2000 and (hashlib.sha256(A.read_bytes()).hexdigest() == PIN), 'QA_REQUIREMENT_FAILED')
require(subprocess.check_output(['python3', str(A), '--version'], text=True, timeout=5).strip() == a.expected_version, 'QA_REQUIREMENT_FAILED')
require(re.fullmatch('[0-9a-f]{64}', a.expected_installer_sha256), 'QA_REQUIREMENT_FAILED')
require(not (F / 'linux.sh').is_symlink() and (F / 'linux.sh').stat().st_uid == 2000 and (hashlib.sha256((F / 'linux.sh').read_bytes()).hexdigest() == a.expected_installer_sha256), 'QA_REQUIREMENT_FAILED')
require(not (D / 'operator-session.json').exists(), 'QA_REQUIREMENT_FAILED')

def ctl(*args):
    return subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, timeout=20)

def active():
    return ctl('is-active', '--quiet', S).returncode == 0
fault = "import os,signal,time\nfrom pathlib import Path\np=Path('/home/commanderqa/commander-qa/crash-once.marker')\nif p.exists():\n p.unlink()\n pid=int(os.environ['MAINPID'])\n child=os.fork()\n if child==0:\n  time.sleep(.5)\n  try:os.kill(pid,signal.SIGKILL)\n  except ProcessLookupError:pass\n  os._exit(0)\n"
result = {'schema': 'hara.commander-linux-clean54-native-rollback.v1', 'backend': 'remote_DEV_worker', 'systemctl_backend': 'real', 'fault': 'one SIGKILL against real QA Agent after successful systemd startup', 'signed_agent_edited': False, 'signed_installer_edited': False, 'same_version_update': True, 'agent_version': a.expected_version}
try:
    require(ctl('start', S).returncode == 0 and active(), 'QA_REQUIREMENT_FAILED')
    FAULT.write_text(fault)
    FAULT.chmod(384)
    U.mkdir(parents=True, exist_ok=True)
    DROP.write_text('[Service]\nExecStartPost=/usr/bin/python3 ' + str(FAULT) + '\nRestartSec=5\n')
    DROP.chmod(384)
    require(ctl('daemon-reload').returncode == 0, 'QA_REQUIREMENT_FAILED')
    MARK.write_text('exclusive QA crash-once\n')
    MARK.chmod(384)
    p = subprocess.run(['bash', str(F / 'linux.sh'), 'update'], capture_output=True, text=True, timeout=150)
    text = p.stdout + p.stderr
    for name in ('HARA_DEVICE_TOKEN', 'HARA_OPERATOR_SESSION_TOKEN'):
        if values.get(name):
            text = text.replace(values[name], '[REDACTED]')
    result.update(update_exit_code=p.returncode, output=text, fault_consumed=not MARK.exists(), service_active_after_rollback=active(), agent_sha256=hashlib.sha256(A.read_bytes()).hexdigest(), rollback_backup_consumed=not Path(str(A) + '.rollback').exists())
    ok = p.returncode == 7 and 'HARA_COMMANDER_AGENT_UPDATE_ROLLBACK=PASS' in text and (not MARK.exists()) and active() and (result['agent_sha256'] == PIN) and result['rollback_backup_consumed']
    result['state'] = 'PASS_NATIVE_SIGNED_UPDATE_ROLLBACK' if ok else 'FAIL_NATIVE_SIGNED_UPDATE_ROLLBACK'
except Exception as e:
    result.update(state='FAIL_NATIVE_SIGNED_UPDATE_ROLLBACK', error_type=type(e).__name__)
finally:
    cleanup_errors = []
    for stage, path in (('remove-drop-in', DROP), ('remove-marker', MARK)):
        try:
            path.unlink(missing_ok=True)
        except Exception as error:
            cleanup_errors.append({'stage': stage, 'error_type': type(error).__name__})
    try:
        U.rmdir()
    except FileNotFoundError:
        pass
    except OSError:
        pass
    try:
        reload = ctl('daemon-reload')
        if reload.returncode != 0:
            cleanup_errors.append({'stage': 'daemon-reload', 'error_type': 'NATIVE_EXIT_NONZERO'})
    except Exception as error:
        cleanup_errors.append({'stage': 'daemon-reload', 'error_type': type(error).__name__})
    try:
        current = dict((line.split('=', 1) for line in C.read_text().splitlines() if '=' in line))
        require(current['HARA_COMMANDER_URL'] == 'https://hara-commander-dev-v2.tiago-sartori.workers.dev' and (not A.is_symlink()) and (hashlib.sha256(A.read_bytes()).hexdigest() == PIN), 'QA_CLEANUP_SOURCE_OR_DEV_DRIFT')
        start = ctl('start', S)
        if start.returncode != 0:
            cleanup_errors.append({'stage': 'restore-real-service', 'error_type': 'NATIVE_EXIT_NONZERO'})
    except Exception as error:
        cleanup_errors.append({'stage': 'restore-real-service', 'error_type': type(error).__name__})
    try:
        result['qa_fault_removed'] = not DROP.exists() and (not MARK.exists())
        result['real_agent_source_intact'] = not A.is_symlink() and hashlib.sha256(A.read_bytes()).hexdigest() == PIN
    except Exception as error:
        result['qa_fault_removed'] = False
        result['real_agent_source_intact'] = False
        cleanup_errors.append({'stage': 'cleanup-attestation', 'error_type': type(error).__name__})
    result['cleanup_errors'] = cleanup_errors
    if cleanup_errors or not result['qa_fault_removed'] or (not result['real_agent_source_intact']):
        result['state'] = 'FAIL_NATIVE_SIGNED_UPDATE_ROLLBACK_CLEANUP'
print(json.dumps(result))
raise SystemExit(0 if result['state'].startswith('PASS') else 1)
