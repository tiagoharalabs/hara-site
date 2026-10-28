#!/usr/bin/python3.10
"""Bounded internal distribution for the existing Windows QA VM; no product API."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027')
BASE = ROOT / 'windows-install-20261028/distribution'
UNIT = 'hara-windows-qa-0356-20261028'
TAG = 'hara-windows-qa-0356-20261028'
UFW = ['allow', 'in', 'on', 'virbr96', 'proto', 'tcp', 'from',
       '192.168.252.113', 'to', '192.168.10.23', 'port', '18443']
SERVER_SHA = '751ff27d6e1ff2d3d220fcd2a6259937abf7e21844ada46292a71ad926cedaca'

def run(args, check=True, **kwargs):
    p = subprocess.run(args, capture_output=True, text=True, timeout=15, **kwargs)
    if check and p.returncode:
        raise RuntimeError(args[0] + '_FAILED: ' + p.stderr[:300])
    return p

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def save(name, obj):
    path = BASE / name
    data = (json.dumps(obj, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def rules():
    p = run(['nft', '-j', 'list', 'table', 'inet', 'hara_review_guard'], check=False)
    if p.returncode:
        tables = json.loads(run(['nft', '-j', 'list', 'tables']).stdout)
        if not any(x.get('table', {}).get('name') == 'hara_review_guard' and
                   x.get('table', {}).get('family') == 'inet' for x in tables['nftables']):
            return []
        raise RuntimeError('NFT_RULE_READ_FAILED')
    value = json.loads(p.stdout)
    return [x['rule'] for x in value['nftables'] if 'rule' in x and x['rule'].get('comment') == TAG]

def cleanup():
    removed = []
    errors = []
    try:
        for rule in rules():
            p = run(['nft', 'delete', 'rule', rule['family'], rule['table'], rule['chain'],
                     'handle', str(rule['handle'])], check=False)
            if p.returncode == 0:
                removed.append(rule['handle'])
    except Exception as exc:
        errors.append('nft_cleanup:' + type(exc).__name__)
    ufw_rc = None
    try:
        ufw_rc = run(['ufw', '--force', 'delete', *UFW], check=False).returncode
    except Exception as exc:
        errors.append('ufw_cleanup:' + type(exc).__name__)
    nft_absent = ufw_absent = False
    try:
        nft_absent = not rules()
    except Exception as exc:
        errors.append('nft_verify:' + type(exc).__name__)
    try:
        ufw_absent = TAG not in run(['ufw', 'show', 'added']).stdout
    except Exception as exc:
        errors.append('ufw_verify:' + type(exc).__name__)
    result = {'at_utc': stamp(),
              'state': 'WINDOWS_QA_DISTRIBUTION_CLOSED' if nft_absent and ufw_absent else 'CLEANUP_HOLD',
              'nft_handles_removed': removed, 'nft_rule_absent': nft_absent,
              'ufw_delete_rc': ufw_rc, 'ufw_rule_absent': ufw_absent, 'errors': errors}
    save('cleanup-result.json', result)
    return result

def configure():
    # Called only as the transient service's ExecStartPre; ExecStopPost owns cleanup
    # even if this process, its SSH launcher, or the asset server is interrupted.
    if not (BASE / 'start-intent.json').exists() or rules():
        raise RuntimeError('EXPECTED_CLEAN_START_INTENT')
    run(['ufw', *UFW, 'comment', TAG])
    rule = ('insert rule inet hara_review_guard input iifname "virbr96" '
            'ip saddr 192.168.252.113 ip daddr 192.168.10.23 '
            'tcp dport 18443 accept comment "' + TAG + '"\n')
    run(['nft', '-f', '-'], input=rule)
    return {'state': 'FIREWALL_READY', 'at_utc': stamp()}

def start():
    if (BASE / 'start-intent.json').exists():
        raise RuntimeError('ALREADY_STARTED_USE_STATUS')
    source = BASE / 'serve_windows_qa_0356.py'
    if hashlib.sha256(source.read_bytes()).hexdigest() != SERVER_SHA:
        raise RuntimeError('SERVER_PIN_MISMATCH')
    status = run(['ufw', 'status']).stdout
    if 'Status: active' not in status or '18443' in status or rules():
        raise RuntimeError('FIREWALL_BASELINE_MISMATCH')
    if run(['ss', '-H', '-ltn', 'sport', '=', ':18443']).stdout.strip():
        raise RuntimeError('PORT_IN_USE')
    save('start-intent.json', {'at_utc': stamp(), 'source_ip': '192.168.252.113',
          'destination': '192.168.10.23:18443', 'runtime_max_s': 3600})
    try:
        control = '/usr/bin/python3.10 -I -S ' + str(BASE / 'windows_qa_release_control.py')
        run(['systemd-run', '--quiet', '--unit=' + UNIT,
             '--property=RuntimeMaxSec=3600', '--property=KillMode=control-group',
             '--property=TimeoutStartSec=45', '--property=TimeoutStopSec=90',
             '--property=ExecStartPre=' + control + ' configure',
             '--property=ExecStopPost=' + control + ' cleanup',
             '/usr/bin/python3.10', '-I', '-S', str(source),
             '--assets', str(ROOT / 'install-0356-private/assets'),
             '--tls-cert', str(ROOT / 'install-0356-private/tls/qa-server.crt'),
             '--tls-key', str(ROOT / 'install-0356-private/tls/qa-server.key')])
        state = run(['systemctl', 'is-active', UNIT]).stdout.strip()
        result = {'at_utc': stamp(), 'state': 'WINDOWS_QA_DISTRIBUTION_STARTED',
                  'service': state, 'source_ip': '192.168.252.113',
                  'release_url': 'https://192.168.10.23:18443/releases/0.3.56',
                  'runtime_max_s': 3600, 'automatic_firewall_cleanup': True,
                  'nft_handles': [x['handle'] for x in rules()]}
        save('start-result.json', result)
        return result
    except BaseException:
        run(['systemctl', 'stop', UNIT], check=False)
        cleanup()
        raise

def main():
    if os.geteuid() != 0 or os.uname().nodename.split('.')[0] != 'sentinela-b':
        raise SystemExit('EXPECTED_NATIVE_B_ROOT')
    if len(sys.argv) != 2 or sys.argv[1] not in ('start', 'status', 'stop', 'cleanup', 'configure'):
        raise SystemExit('EXPECTED_FIXED_OPERATION')
    if sys.argv[1] == 'start':
        result = start()
    elif sys.argv[1] == 'cleanup':
        result = cleanup()
    elif sys.argv[1] == 'configure':
        result = configure()
    elif sys.argv[1] == 'stop':
        run(['systemctl', 'stop', UNIT], check=False)
        result = cleanup()
    else:
        result = {'at_utc': stamp(), 'service': run(['systemctl', 'is-active', UNIT], check=False).stdout.strip(),
                  'nft_handles': [x['handle'] for x in rules()],
                  'listener': bool(run(['ss', '-H', '-ltn', 'sport', '=', ':18443']).stdout.strip())}
    print(json.dumps(result))

if __name__ == '__main__':
    main()
