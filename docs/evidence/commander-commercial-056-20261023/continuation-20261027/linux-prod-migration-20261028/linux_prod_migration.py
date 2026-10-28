#!/usr/bin/env python3
"""One explicitly authorized QA Linux DEV -> PROD binding migration.

Run as commanderqa inside the pinned Sentinela B VM. No Agent replacement,
release publication, credential export, database edits, or history replay.
The short-lived portal pairing code is accepted only on stdin for commit.
"""
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import sqlite3
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

HOME = Path('/home/commanderqa')
DATA = HOME / '.local/share/hara-commander'
CONFIG = HOME / '.config/hara-commander/device.env'
AGENT = DATA / 'hara-commander-agent'
UNIT = HOME / '.config/systemd/user/hara-commander-agent.service'
WORK = HOME / '.local/share/hara-commander-connect-qa/migration-prod-20261028'
OLD_ORIGIN = 'https://hara-commander-dev-v2.tiago-sartori.workers.dev'
OLD_DEVICE = 'HARA-DEVICE-962202bc-274a-486b-9794-b73d9f3a5889'
PROD = 'https://commander.haralabs.com.br'
AGENT_SHA = 'df8b2d09c5447f8d405200538a841e669a8f165e9043701d6c8efcbfe5a34d38'
VERSION = '0.3.59'
SERVICE = 'hara-commander-agent.service'
ENV = dict(os.environ, XDG_RUNTIME_DIR='/run/user/2000',
           DBUS_SESSION_BUS_ADDRESS='unix:path=/run/user/2000/bus')

class Hold(Exception):
    pass

def need(ok, code):
    if not ok:
        raise Hold(code)

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def read(path, private=False):
    for parent in path.parents:
        need(not parent.is_symlink(), 'SYMLINK_PARENT')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        s = os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_uid == 2000 and s.st_nlink == 1,
             'FILE_OWNER_OR_TYPE')
        need(not s.st_mode & (0o077 if private else 0o022), 'FILE_PERMISSIONS')
        need(s.st_size <= 2 * 1024 * 1024, 'FILE_SIZE')
        with os.fdopen(fd, 'rb', closefd=False) as f:
            data = f.read()
        need(len(data) == s.st_size, 'FILE_READ_CHANGED')
        return data
    finally:
        os.close(fd)

def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())

def atomic(path, data):
    pending = path.with_name(path.name + '.migration-pending')
    write_new(pending, data)
    os.replace(pending, path)
    fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def parsed(raw):
    result = {}
    for row in raw.decode().splitlines():
        if not row or row.startswith('#'):
            continue
        need('=' in row, 'CONFIG_SYNTAX')
        key, value = row.split('=', 1)
        need(key not in result, 'CONFIG_DUPLICATE_KEY')
        result[key] = value
    return result

def context(config):
    material = [config['HARA_COMMANDER_URL'], config['HARA_DEVICE_ID'],
                config.get('HARA_TENANT_ID', ''), digest(config['HARA_DEVICE_TOKEN'].encode())]
    return digest(json.dumps(material, separators=(',', ':')).encode())

def systemctl(*args, check=True):
    p = subprocess.run(['systemctl', '--user', *args], env=ENV,
                       capture_output=True, text=True, timeout=25)
    if check:
        need(p.returncode == 0, 'SERVICE_' + args[0].upper() + '_FAILED')
    return p.stdout.strip()

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def request(origin, path, body, token=None):
    need(origin in (OLD_ORIGIN, PROD), 'ORIGIN_NOT_ALLOWED')
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json',
               'User-Agent': 'HARA-QA-Linux-ProdMigration/1'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(origin + path, data=json.dumps(body).encode(),
                                 headers=headers, method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=20) as res:
            raw = res.read(65537)
            expected_status = 201 if path == '/api/device/enroll' else 200
            need(len(raw) <= 65536 and res.status == expected_status, 'SERVER_RESPONSE')
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise Hold('HTTP_' + str(exc.code) + '_' + path.rsplit('/', 1)[-1].upper()) from None

def heartbeat(config):
    result = request(config['HARA_COMMANDER_URL'], '/api/device/heartbeat', {
        'device_id': config['HARA_DEVICE_ID'], 'architecture': config['HARA_DEVICE_ARCH'],
        'agent_version': VERSION, 'approval_mode': config['HARA_COMMANDER_APPROVAL_MODE']
    }, config['HARA_DEVICE_TOKEN'])
    need(result.get('ok') is True and result.get('device_id') == config['HARA_DEVICE_ID'],
         'HEARTBEAT_IDENTITY')

def idle(config):
    path = DATA / 'enrollments' / context(config) / 'operations.sqlite3'
    if not path.exists():
        return {'journal_present': False}
    need(not path.is_symlink(), 'DATABASE_SYMLINK')
    with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
        tables = {r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        if 'relay_call_journal' not in tables:
            return {'journal_present': False}
        rows = list(db.execute('SELECT phase,delivery_state,COUNT(*) FROM relay_call_journal GROUP BY phase,delivery_state'))
    need(not any(phase in ('PREPARING', 'RESERVED', 'EXECUTING', 'UNCERTAIN') for phase, _, _ in rows),
         'UNFINISHED_CALLS')
    need(not any(delivery in ('PENDING', 'RETRY', 'SENDING') for _, delivery, _ in rows),
         'UNDELIVERED_RESULTS')
    return {'journal_present': True, 'states': rows}

def verify_agent():
    raw = read(AGENT)
    need(len(raw) == 265620 and digest(raw) == AGENT_SHA, 'SIGNED_AGENT_HASH')
    need(read(UNIT), 'UNIT_EMPTY')

def runtime():
    return json.loads(read(DATA / 'runtime-status.json'))

def report(name, value):
    value['observed_at_utc'] = now()
    value['credential_exposed'] = False
    atomic(WORK / name, (json.dumps(value, sort_keys=True, indent=2) + '\n').encode())
    print(json.dumps(value), flush=True)

def prepare():
    verify_agent()
    old = read(CONFIG, True)
    cfg = parsed(old)
    need(cfg.get('HARA_COMMANDER_URL') == OLD_ORIGIN and cfg.get('HARA_DEVICE_ID') == OLD_DEVICE,
         'EXPECTED_DEV_BINDING')
    need(not cfg.get('HARA_TENANT_ID'), 'EXPLICIT_TENANT_REQUIRES_REVIEW')
    need(cfg.get('HARA_COMMANDER_APPROVAL_MODE') == 'PERSISTENT_TRUSTED', 'EXPECTED_APPROVAL_POLICY')
    need(cfg.get('HARA_COMMANDER_TRANSPORT_MODE') == 'OUTBOUND_RELAY', 'EXPECTED_TRANSPORT')
    need(systemctl('is-active', SERVICE) == 'active', 'EXPECTED_ACTIVE_SERVICE')
    heartbeat(cfg)
    journal = idle(cfg)
    backup = WORK / 'dev-device.env'
    if backup.exists():
        need(read(backup, True) == old, 'PREIMAGE_CONFLICT')
    else:
        write_new(backup, old)
        write_new(WORK / 'unit.preimage', read(UNIT))
    report('prepared.json', {'state': 'READY_FOR_PROD_PAIRING', 'source': OLD_ORIGIN,
        'target': PROD, 'version': VERSION, 'agent_sha256': AGENT_SHA,
        'service': 'active', 'journal': journal, 'old_config_sha256': digest(old),
        'config_keys': sorted(cfg), 'production_enrollment_performed': False})

def wait_runtime(previous, since):
    deadline = time.monotonic() + 70
    while time.monotonic() < deadline:
        r = runtime()
        start = r.get('started_at_utc')
        beat = r.get('last_successful_heartbeat_at_utc')
        if start and start != previous and beat and r.get('agent_version') == VERSION:
            stamp = dt.datetime.fromisoformat(beat.replace('Z', '+00:00')).timestamp()
            if stamp >= since and systemctl('is-active', SERVICE, check=False) == 'active':
                return {k: r.get(k) for k in ('agent_version', 'started_at_utc', 'last_successful_heartbeat_at_utc', 'last_runtime_error_code')}
        time.sleep(1)
    raise Hold('NEW_RUNTIME_NOT_CONFIRMED')

def commit():
    verify_agent()
    old = read(WORK / 'dev-device.env', True)
    need(read(CONFIG, True) == old, 'CONFIG_CHANGED_SINCE_PREPARATION')
    need(read(UNIT) == read(WORK / 'unit.preimage'), 'UNIT_CHANGED')
    cfg = parsed(old)
    need(cfg['HARA_COMMANDER_URL'] == OLD_ORIGIN and cfg['HARA_DEVICE_ID'] == OLD_DEVICE, 'PREIMAGE_BINDING')
    idle(cfg)
    token = sys.stdin.readline(1024).strip()
    need(8 <= len(token) <= 512 and not any(c.isspace() for c in token), 'PAIRING_CODE_FORMAT')
    need(not (WORK / 'prod-device.env').exists(), 'PROD_ENROLLMENT_ALREADY_ATTEMPTED')
    enrolled = None
    switched = False
    stopped = False
    previous = runtime().get('started_at_utc')
    try:
        reply = request(PROD, '/api/device/enroll', {'pairing_token': token,
            'device_name': platform.node(), 'platform': 'LINUX', 'architecture': platform.machine(),
            'agent_version': VERSION, 'approval_mode': cfg['HARA_COMMANDER_APPROVAL_MODE']})
        token = None
        need(isinstance(reply.get('device_id'), str) and re.fullmatch(r'HARA-DEVICE-[a-zA-Z0-9-]{20,80}', reply['device_id']), 'ENROLL_DEVICE_ID')
        need(isinstance(reply.get('device_token'), str) and 16 <= len(reply['device_token']) <= 2048
             and not any(c.isspace() for c in reply['device_token']), 'ENROLL_TOKEN')
        enrolled = dict(cfg, HARA_COMMANDER_URL=PROD, HARA_DEVICE_ID=reply['device_id'], HARA_DEVICE_TOKEN=reply['device_token'])
        replacements = {k: enrolled[k] for k in ('HARA_COMMANDER_URL', 'HARA_DEVICE_ID', 'HARA_DEVICE_TOKEN')}
        new = ''.join((k + '=' + replacements[k] if (k := line.split('=', 1)[0]) in replacements else line) + '\n'
                      for line in old.decode().splitlines()).encode()
        write_new(WORK / 'prod-device.env', new)
        heartbeat(enrolled)
        systemctl('stop', SERVICE)
        stopped = True
        need(systemctl('show', SERVICE, '--property=MainPID', '--value') == '0', 'OLD_SERVICE_STILL_RUNNING')
        idle(cfg)
        need(read(CONFIG, True) == old, 'CONFIG_CHANGED_DURING_ENROLL')
        atomic(CONFIG, new)
        switched = True
        since = time.time() - 1
        systemctl('start', SERVICE)
        observed = wait_runtime(previous, since)
        heartbeat(enrolled)
        verify_agent()
        need(read(CONFIG, True) == new and read(UNIT) == read(WORK / 'unit.preimage'), 'POSTCHECK_FILES')
        report('committed.json', {'state': 'PROD_CONNECTED', 'origin': PROD, 'device_id': enrolled['HARA_DEVICE_ID'],
            'previous_device_id': OLD_DEVICE, 'version': VERSION, 'agent_sha256': AGENT_SHA,
            'runtime': observed, 'approval_mode': enrolled['HARA_COMMANDER_APPROVAL_MODE'],
            'authenticated_heartbeat_http': 200, 'old_history_preserved': True,
            'enrollment_scopes_distinct': context(cfg) != context(enrolled),
            'dev_revoke': 'PENDING_PORTAL_VERIFICATION', 'public_release_promoted': False})
    except Exception as exc:
        recovery = {'config_restored': not switched, 'runtime_restored': not stopped}
        if stopped:
            try:
                systemctl('stop', SERVICE)
                atomic(CONFIG, old)
                recovery['config_restored'] = read(CONFIG, True) == old
                before = runtime().get('started_at_utc')
                since = time.time() - 1
                systemctl('start', SERVICE)
                wait_runtime(before, since)
                heartbeat(cfg)
                recovery['runtime_restored'] = True
            except Exception as rollback_error:
                recovery['error_code'] = str(rollback_error) if isinstance(rollback_error, Hold) else type(rollback_error).__name__
        if enrolled is not None:
            try:
                response = request(PROD, '/api/device/revoke-self', {}, enrolled['HARA_DEVICE_TOKEN'])
                recovery['new_device_revoked'] = response.get('ok') is True
            except Exception:
                recovery['new_device_revoked'] = False
        report('failed.json', {'state': 'HOLD', 'error_code': str(exc) if isinstance(exc, Hold) else type(exc).__name__, 'rollback': recovery})
        raise SystemExit(2)

def finalize():
    verify_agent()
    new = read(WORK / 'prod-device.env', True)
    need(read(CONFIG, True) == new, 'PROD_CONFIG_CHANGED')
    current = parsed(new)
    heartbeat(current)
    need(systemctl('is-active', SERVICE) == 'active', 'PROD_SERVICE_NOT_ACTIVE')
    old = parsed(read(WORK / 'dev-device.env', True))
    response = request(OLD_ORIGIN, '/api/device/revoke-self', {}, old['HARA_DEVICE_TOKEN'])
    need(response.get('ok') is True, 'DEV_REVOKE_UNCONFIRMED')
    report('finalized.json', {'state': 'PASS_LINUX_PRODUCTION_MIGRATION', 'origin': PROD,
        'device_id': current['HARA_DEVICE_ID'], 'version': VERSION, 'old_dev_enrollment_revoked': True,
        'old_history_preserved': True, 'public_release_promoted': False})

def main():
    need(os.getuid() == 2000 and pwd.getpwuid(2000).pw_name == 'commanderqa', 'ACCOUNT_MISMATCH')
    need(Path(pwd.getpwuid(2000).pw_dir) == HOME, 'HOME_MISMATCH')
    for p in (WORK.parent,):
        need(p.is_dir() and not p.is_symlink() and p.stat().st_uid == 2000 and not p.stat().st_mode & 0o022, 'WORK_PARENT')
    WORK.mkdir(mode=0o700, exist_ok=True)
    need(not WORK.is_symlink() and WORK.stat().st_uid == 2000 and not WORK.stat().st_mode & 0o077, 'WORK_PRIVATE')
    fd = os.open(WORK / 'migration.lock', os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        action = sys.argv[1]
        need(action in ('prepare', 'commit', 'finalize'), 'ACTION_INVALID')
        {'prepare': prepare, 'commit': commit, 'finalize': finalize}[action]()
    finally:
        os.close(fd)

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'state': 'HOLD', 'error_code': str(exc) if isinstance(exc, Hold) else type(exc).__name__, 'credential_exposed': False}))
        raise SystemExit(2)
