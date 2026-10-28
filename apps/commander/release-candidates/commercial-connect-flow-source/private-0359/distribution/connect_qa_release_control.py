#!/usr/bin/python3.10
"""One bounded .59 QA distribution; owns only its two tagged port-18446 rules."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

ROOT = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028/connect-flow-20261028/private-0359')
BASE = ROOT / 'distribution'
TLS = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027/windows-install-20261028/distribution-r3/tls')
UNIT = TAG = 'hara-connect-qa-0359-20261028'
HARD_DEADLINE = dt.datetime(2026, 10, 28, 19, 35, 0, tzinfo=dt.timezone.utc)
MAX_SECONDS = 2700
ADDRESSES = ('192.168.252.113', '192.168.252.130')
SERVER_SHA = 'f958a1894d52cbc7ef780a0d04a8c154afae2f32c969157e603b4687b84c1216'


def run(args, check=True, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, timeout=15, **kwargs)
    if check and result.returncode:
        raise RuntimeError(args[0] + '_FAILED')
    return result


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ufw_args(address):
    if address not in ADDRESSES:
        raise RuntimeError('FIXED_QA_ADDRESS_REQUIRED')
    return ['allow', 'in', 'on', 'virbr96', 'proto', 'tcp', 'from', address,
            'to', '192.168.10.23', 'port', '18446']


def save(name, obj, exclusive=False):
    if name not in ('start-intent.json', 'start-result.json', 'cleanup-result.json'):
        raise RuntimeError('FIXED_RECEIPT_REQUIRED')
    path = BASE / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write((json.dumps(obj, sort_keys=True) + '\n').encode())
        handle.flush()
        os.fsync(handle.fileno())


def rules():
    result = run(['nft', '-j', 'list', 'table', 'inet', 'hara_review_guard'], check=False)
    if result.returncode:
        tables = json.loads(run(['nft', '-j', 'list', 'tables']).stdout)
        if not any(row.get('table', {}).get('name') == 'hara_review_guard' and
                   row.get('table', {}).get('family') == 'inet' for row in tables['nftables']):
            return []
        raise RuntimeError('NFT_RULE_READ_FAILED')
    value = json.loads(result.stdout)
    return [row['rule'] for row in value['nftables']
            if 'rule' in row and row['rule'].get('comment') == TAG]


def listener():
    return bool(run(['ss', '-H', '-ltn', 'sport', '=', ':18446']).stdout.strip())


def tagged_ufw_addresses():
    found = set()
    for line in run(['ufw', 'show', 'added']).stdout.splitlines():
        if TAG not in line:
            continue
        tokens = shlex.split(line)
        if TAG not in tokens or '18446' not in tokens or '192.168.10.23' not in tokens:
            raise RuntimeError('TAGGED_UFW_RULE_UNEXPECTED')
        for address in ADDRESSES:
            if address in tokens:
                found.add(address)
    return found


def cleanup():
    removed = []
    errors = []
    try:
        for rule in rules():
            result = run(['nft', 'delete', 'rule', rule['family'], rule['table'],
                          rule['chain'], 'handle', str(rule['handle'])], check=False)
            if result.returncode == 0:
                removed.append(rule['handle'])
            else:
                errors.append('NFT_DELETE_FAILED')
    except Exception as error:
        errors.append('NFT_CLEANUP_' + type(error).__name__)
    # Each source gets an independent attempt, even when the other deletion fails.
    ufw_codes = {}
    for address in ADDRESSES:
        try:
            if address in tagged_ufw_addresses():
                ufw_codes[address] = run(['ufw', '--force', 'delete', *ufw_args(address)],
                                         check=False).returncode
            else:
                ufw_codes[address] = None
        except Exception as error:
            errors.append('UFW_CLEANUP_' + address + '_' + type(error).__name__)
    nft_absent = ufw_absent = listener_absent = False
    try:
        nft_absent = not rules()
    except Exception as error:
        errors.append('NFT_VERIFY_' + type(error).__name__)
    try:
        ufw_absent = TAG not in run(['ufw', 'show', 'added']).stdout
    except Exception as error:
        errors.append('UFW_VERIFY_' + type(error).__name__)
    try:
        listener_absent = not listener()
    except Exception as error:
        errors.append('LISTENER_VERIFY_' + type(error).__name__)
    result = {'at_utc': stamp(), 'state': 'CONNECT_QA_DISTRIBUTION_CLOSED'
              if nft_absent and ufw_absent and listener_absent else 'CLEANUP_HOLD',
              'nft_handles_removed': removed, 'nft_rule_absent': nft_absent,
              'ufw_delete_codes': ufw_codes, 'ufw_rule_absent': ufw_absent,
              'listener_absent': listener_absent, 'errors': errors}
    save('cleanup-result.json', result)
    return result


def read_intent():
    path = BASE / 'start-intent.json'
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or
            stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
        raise RuntimeError('START_INTENT_INVALID')
    value = json.loads(path.read_text())
    expires = dt.datetime.fromisoformat(value['expires_at_utc'])
    if (value.get('unit') != UNIT or value.get('source_ips') != list(ADDRESSES) or
            value.get('destination') != '192.168.10.23:18446' or
            expires.tzinfo is None or expires > HARD_DEADLINE or
            expires <= dt.datetime.now(dt.timezone.utc)):
        raise RuntimeError('START_INTENT_EXPIRED_OR_CHANGED')
    return value


def configure():
    # This phase only runs within the transient unit, whose ExecStopPost already
    # owns cleanup. It cannot be used as a standalone persistent firewall opener.
    invocation = os.environ.get('INVOCATION_ID', '')
    groups = Path('/proc/self/cgroup').read_text().splitlines()
    if (not re.fullmatch('[0-9a-fA-F]{32}', invocation) or
            not any(line.endswith('/' + UNIT + '.service') for line in groups)):
        raise RuntimeError('EXPECTED_TRANSIENT_UNIT_PRESTART')
    read_intent()
    if rules() or tagged_ufw_addresses():
        raise RuntimeError('EXPECTED_CLEAN_FIREWALL_START')
    try:
        for address in ADDRESSES:
            read_intent()
            run(['ufw', *ufw_args(address), 'comment', TAG])
            rule = ('insert rule inet hara_review_guard input iifname "virbr96" '
                    'ip saddr ' + address + ' ip daddr 192.168.10.23 '
                    'tcp dport 18446 accept comment "' + TAG + '"\n')
            run(['nft', '-f', '-'], input=rule)
        read_intent()
        return {'state': 'FIREWALL_READY', 'at_utc': stamp(),
                'source_ips': list(ADDRESSES), 'nft_handles': [row['handle'] for row in rules()]}
    except BaseException:
        cleanup()
        raise


def start():
    now = dt.datetime.now(dt.timezone.utc)
    seconds = min(MAX_SECONDS, math.floor((HARD_DEADLINE - now).total_seconds()))
    if seconds <= 0:
        raise RuntimeError('DISTRIBUTION_WINDOW_EXPIRED')
    if os.path.lexists(BASE / 'start-intent.json'):
        raise RuntimeError('ALREADY_STARTED_USE_STATUS')
    source = BASE / 'serve_connect_qa_0359.py'
    if source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest() != SERVER_SHA:
        raise RuntimeError('SERVER_PIN_MISMATCH')
    status = run(['ufw', 'status']).stdout
    if 'Status: active' not in status or '18446' in status or rules() or tagged_ufw_addresses():
        raise RuntimeError('FIREWALL_BASELINE_MISMATCH')
    run(['nft', '-j', 'list', 'chain', 'inet', 'hara_review_guard', 'input'])
    if listener():
        raise RuntimeError('PORT_IN_USE')
    expires = now + dt.timedelta(seconds=seconds)
    intent = {'at_utc': now.isoformat(), 'expires_at_utc': expires.isoformat(),
              'hard_deadline_utc': HARD_DEADLINE.isoformat(), 'unit': UNIT,
              'source_ips': list(ADDRESSES), 'destination': '192.168.10.23:18446',
              'runtime_max_s': seconds, 'server_sha256': SERVER_SHA}
    save('start-intent.json', intent, exclusive=True)
    try:
        if expires <= dt.datetime.now(dt.timezone.utc):
            raise RuntimeError('DISTRIBUTION_WINDOW_EXPIRED')
        control = '/usr/bin/python3.10 -I -S ' + str(BASE / 'connect_qa_release_control.py')
        run(['systemd-run', '--quiet', '--no-block', '--unit=' + UNIT,
             '--property=RuntimeMaxSec=' + str(seconds), '--property=Restart=no',
             '--property=KillMode=control-group', '--property=TimeoutStartSec=60',
             '--property=TimeoutStopSec=90',
             '--property=ExecStartPre=' + control + ' configure',
             '--property=ExecStopPost=' + control + ' cleanup',
             '/usr/bin/python3.10', '-I', '-S', str(source),
             '--assets', str(ROOT / 'signed'), '--tls-cert', str(TLS / 'qa-server.crt'),
             '--tls-key', str(TLS / 'qa-server.key'), '--expires-utc', expires.isoformat()])
        result = dict(intent, state='CONNECT_QA_DISTRIBUTION_START_REQUESTED',
                      service=run(['systemctl', 'is-active', UNIT], check=False).stdout.strip(),
                      release_url='https://192.168.10.23:18446/releases/0.3.59',
                      automatic_firewall_cleanup=True)
        save('start-result.json', result)
        return result
    except BaseException:
        try:
            run(['systemctl', 'stop', UNIT], check=False)
        finally:
            cleanup()
        raise


def main():
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'sentinela-b':
        raise SystemExit('EXPECTED_NATIVE_B_ROOT')
    if len(sys.argv) != 2 or sys.argv[1] not in ('start', 'status', 'stop', 'cleanup', 'configure'):
        raise SystemExit('EXPECTED_FIXED_OPERATION')
    action = sys.argv[1]
    if action == 'start':
        result = start()
    elif action == 'configure':
        result = configure()
    elif action == 'cleanup':
        result = cleanup()
    elif action == 'stop':
        try:
            run(['systemctl', 'stop', UNIT], check=False)
        finally:
            result = cleanup()
    else:
        result = {'at_utc': stamp(),
                  'service': run(['systemctl', 'is-active', UNIT], check=False).stdout.strip(),
                  'nft_handles': [row['handle'] for row in rules()],
                  'ufw_source_ips': sorted(tagged_ufw_addresses()), 'listener': listener(),
                  'hard_deadline_utc': HARD_DEADLINE.isoformat()}
    print(json.dumps(result))


if __name__ == '__main__':
    main()
