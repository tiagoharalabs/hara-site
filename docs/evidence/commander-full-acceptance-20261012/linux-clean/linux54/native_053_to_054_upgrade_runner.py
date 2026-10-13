#!/usr/bin/env python3
"""Real installed signed 0.3.53 to 0.3.54 update with actual managed53 inode migration."""
import argparse, hashlib, json, os, re, stat, subprocess
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
F = Q / 'commander-qa'
D = Q / '.local/share/hara-commander'
A = D / 'hara-commander-agent'
C = Q / '.config/hara-commander/device.env'
S = D / 'operator-session.json'
DEV = 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'
OLD = 'db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e'
NEW = '6aecef8f8dd05bf8f2ab0c1b9c71308647892e70a0b34e2ccbe4322ad826df2e'
INSTALL = 'd2057adfff5c2b475d1520ae44f1ed76a7ec0ecc673f65cf08631d7a0083d0fa'
MANAGED53 = 'c69151f87529aebc0ebbf5c54e7f5ad4ef1a897b37c47a9ec68d9a6959bf3953'
MANAGED54 = '19463b9d3c9f1c4072bb2017029ecc71da6a07c8dd7f61c4140e4f48c7fda8ae'
p = argparse.ArgumentParser()
p.add_argument('--expected-version', default='0.3.54', choices=['0.3.54'])
p.add_argument('--expected-agent-sha256', default=NEW)
p.add_argument('--expected-installer-sha256', default=INSTALL)
a = p.parse_args()
require(re.fullmatch('[0-9a-f]{64}', a.expected_agent_sha256) and re.fullmatch('[0-9a-f]{64}', a.expected_installer_sha256), 'QA_REQUIREMENT_FAILED')
NEW = a.expected_agent_sha256
INSTALL = a.expected_installer_sha256
require(os.getuid() == 2000 and os.geteuid() == 2000 and (Path.home() == Q) and (Path('/etc/hostname').read_text().strip() == 'commander-linux-clean54'), 'QA_REQUIREMENT_FAILED')
normalize_qa_environment()
v = dict((line.split('=', 1) for line in C.read_text().splitlines() if '=' in line))
require(v['HARA_COMMANDER_URL'] == DEV and v['HARA_COMMANDER_APPROVAL_MODE'] == 'ASK_EVERY_ACTION', 'QA_REQUIREMENT_FAILED')
require(not S.exists(), 'QA_ALREADY_HAS_OPERATOR_SESSION')
before_config = C.read_bytes()
old_started = json.loads((D / 'runtime-status.json').read_text())['started_at_utc']
require(not A.is_symlink() and hashlib.sha256(A.read_bytes()).hexdigest() == OLD, 'QA_REQUIREMENT_FAILED')
require(subprocess.check_output(['python3', str(A), '--version'], text=True).strip() == '0.3.53', 'QA_REQUIREMENT_FAILED')
wrapper = Q / '.local/bin/hara'
old_wrapper = wrapper.read_bytes()
old_wrapper_stat = wrapper.stat()
require(not wrapper.is_symlink() and old_wrapper_stat.st_uid == 2000 and (stat.S_IMODE(old_wrapper_stat.st_mode) == 448) and (hashlib.sha256(old_wrapper).hexdigest() == MANAGED53), 'QA_REQUIREMENT_FAILED')

def ctl(*args):
    return subprocess.run(['systemctl', '--user', *args], capture_output=True, timeout=20).returncode
require(ctl('is-active', '--quiet', 'hara-commander-agent.service') == 0 and ctl('is-enabled', '--quiet', 'hara-commander-agent.service') != 0, 'QA_REQUIREMENT_FAILED')
result = {'schema': 'hara.commander-linux-clean54-native-upgrade-053-054.v1', 'backend': 'remote_DEV_worker', 'systemctl_backend': 'real', 'device_id': v['HARA_DEVICE_ID'], 'prior_version': '0.3.53', 'target_version': '0.3.54', 'old_wrapper_manually_changed': False, 'customer_secrets_exposed': False}
try:
    tmp = F / 'linux-054-download.sh'
    download = subprocess.run(['curl', '-fsS', '--proto', '=https', '--max-time', '30', DEV + '/install/linux.sh', '-o', str(tmp)], capture_output=True, timeout=40)
    require(download.returncode == 0 and hashlib.sha256(tmp.read_bytes()).hexdigest() == INSTALL, 'SIGNED_054_INSTALLER_HTTPS_DOWNLOAD_OR_PIN')
    original = F / 'linux-053-original.sh'
    require(not original.exists(), 'BASELINE_INSTALLER_ARCHIVE_ALREADY_PRESENT')
    (F / 'linux.sh').rename(original)
    tmp.replace(F / 'linux.sh')
    update = subprocess.run(['bash', str(F / 'linux.sh'), 'update'], capture_output=True, text=True, timeout=150)
    text = update.stdout + update.stderr
    for key in ('HARA_DEVICE_TOKEN', 'HARA_OPERATOR_SESSION_TOKEN'):
        if v.get(key):
            text = text.replace(v[key], '[REDACTED]')
    result.update(update_exit_code=update.returncode, output=text)
    require(update.returncode == 0 and 'HARA_COMMANDER_AGENT_UPDATE=PASS' in text, 'QA_REQUIREMENT_FAILED')
    require('HARA_COMMANDER_CLI_WRAPPER_STATE=MANAGED53_MIGRATED' in text, 'QA_REQUIREMENT_FAILED')
    require(hashlib.sha256(A.read_bytes()).hexdigest() == NEW and subprocess.check_output(['python3', str(A), '--version'], text=True).strip() == '0.3.54', 'QA_REQUIREMENT_FAILED')
    require(C.read_bytes() == before_config, 'QA_REQUIREMENT_FAILED')
    require(not wrapper.is_symlink() and hashlib.sha256(wrapper.read_bytes()).hexdigest() == MANAGED54, 'QA_REQUIREMENT_FAILED')
    snapshot = D / 'installer-preimages' / ('hara-wrapper-' + MANAGED53 + '.preimage')
    ss = snapshot.stat()
    require(not snapshot.is_symlink() and snapshot.read_bytes() == old_wrapper and (hashlib.sha256(snapshot.read_bytes()).hexdigest() == MANAGED53), 'QA_REQUIREMENT_FAILED')
    require(stat.S_IMODE(ss.st_mode) == 384 and ss.st_uid == 2000 and (ss.st_ino == old_wrapper_stat.st_ino) and (ss.st_dev == old_wrapper_stat.st_dev), 'QA_REQUIREMENT_FAILED')
    metadata_path = snapshot.with_suffix('.json')
    ms = metadata_path.stat()
    metadata = json.loads(metadata_path.read_text())
    require(stat.S_IMODE(ms.st_mode) == 384 and ms.st_uid == 2000 and (metadata['schema'] == 'hara.commander-owned-cli-preimage.v2') and (metadata['displaced_inode'] == old_wrapper_stat.st_ino), 'QA_REQUIREMENT_FAILED')
    runtime = json.loads((D / 'runtime-status.json').read_text())
    require(runtime['agent_version'] == '0.3.54' and runtime['started_at_utc'] != old_started, 'QA_REQUIREMENT_FAILED')
    require(ctl('is-active', '--quiet', 'hara-commander-agent.service') == 0 and ctl('is-enabled', '--quiet', 'hara-commander-agent.service') != 0 and (not S.exists()), 'QA_REQUIREMENT_FAILED')
    rc = subprocess.run([str(wrapper), 'commander', 'approval-mode'], capture_output=True, text=True, timeout=30)
    require(rc.returncode == 0 and 'HARA_COMMANDER_APPROVAL_MODE=ASK_EVERY_ACTION' in rc.stdout, 'QA_REQUIREMENT_FAILED')
    result.update(state='PASS_NATIVE_053_TO_SIGNED_054_MANAGED53_MIGRATION', new_agent_sha256=NEW, signed_installer_sha256=INSTALL, managed53_preimage_sha256=MANAGED53, managed54_wrapper_sha256=MANAGED54, preimage_mode='0600', preimage_owner_uid=2000, actual_displaced_inode_preserved=True, source_version_attested=True, device_credentials_preserved=True, manual_boot_policy_preserved=True, public_wrapper_approval_get_pass=True)
except Exception as error:
    result.update(state='FAIL_NATIVE_053_TO_SIGNED_054_MANAGED53_MIGRATION', error_type=type(error).__name__, error_code=str(error) if isinstance(error, AssertionError) else 'NATIVE_UPGRADE_PHASE_FAILED')
print(json.dumps(result))
raise SystemExit(0 if result['state'].startswith('PASS') else 1)
