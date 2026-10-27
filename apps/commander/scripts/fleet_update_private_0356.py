#!/usr/bin/env python3
"""Finite, per-user .56 private QA migration. inventory is read-only.

inventory --target <allowlisted label> --stage <directory> > contract.json
execute --contract contract.json --stage <directory> --out <new directory>
The operator reviews the contract before execute. No enrollment/trust mutation,
no second Agent, no public release claim. Run via an independent user service.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import signal
import ssl
import stat
import subprocess
import sys
import time

TARGETS = ('sentinela-a', 'sentinela-b', 'sentinela-c', 'sentinela-d',
           'observer', 'storage', 'nucleo-a', 'ninja-blue', 'services')
STD = 'hara-commander-agent.service'
V2 = 'hara-commander-agent-v2.service'
UNITS = (STD, V2)
INSTALLER_SHA = 'a63542827372f73f5b0f48bf924fb847156c9d7f6f1adb371d73f78effade93f'
CA_SHA = '713a52a80b80e129b7f85d61d90d02cee49495eddc7dcc9f574e39c85cec97d4'
AGENT_SHA = 'ad92b9100b9b4599fc73815a5ba44ffb665ce5c1d0973c03923f1d8d45b1d03d'
RELEASE_URL = 'https://192.168.10.23:18443/releases/0.3.56'
DROP_NAME = '90-private-qa-0356.conf'
SCHEMA = 'hara.commander.private-fleet-update-0356.v1'


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def read(path, limit=4 * 1024**2):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_size <= limit, 'FILE_TYPE_OR_SIZE:' + str(path))
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        t = os.fstat(fd)
        need(len(data) <= limit and (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns) ==
             (t.st_dev, t.st_ino, t.st_size, t.st_mtime_ns, t.st_ctime_ns), 'FILE_CHANGED:' + str(path))
        return bytes(data)
    finally:
        os.close(fd)


def item(path):
    try:
        s = path.lstat()
    except FileNotFoundError:
        return {'kind': 'absent'}
    row = {'uid': s.st_uid, 'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode)}
    if stat.S_ISLNK(s.st_mode):
        row.update(kind='symlink', target=os.readlink(path))
        target = path.resolve(strict=True)
        row['resolved'] = str(target)
        row['target_sha256'] = sha(read(target))
    else:
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'UNEXPECTED_FILE:' + str(path))
        row.update(kind='file', sha256=sha(read(path)), bytes=s.st_size)
    return row


def atomic(path, data, mode=0o600, gid=None):
    temp = path.with_name(path.name + '.fleet-' + str(os.getpid()) + '-' + str(time.monotonic_ns()) + '.tmp')
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            need(n > 0, 'SHORT_WRITE')
            view = view[n:]
        if gid is not None and os.fstat(fd).st_gid != gid:
            os.fchown(fd, -1, gid)
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp, path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class Migration:
    def __init__(self, stage):
        self.uid = os.geteuid()
        need(self.uid > 0 and os.getuid() == self.uid, 'RUN_AS_EXISTING_AGENT_OWNER')
        self.home = Path(pwd.getpwuid(self.uid).pw_dir)
        need(self.home.is_absolute(), 'HOME_INVALID')
        self.stage = Path(stage).absolute()
        stage_stat = self.stage.lstat()
        need(stat.S_ISDIR(stage_stat.st_mode) and stage_stat.st_uid == self.uid and
             stat.S_IMODE(stage_stat.st_mode) == 0o700, 'STAGE_PRIVATE_OWNER')
        self.bin = self.home / '.local/share/hara-commander'
        self.agent = self.bin / 'hara-commander-agent'
        self.config = self.home / '.config/hara-commander/device.env'
        self.status = self.bin / 'runtime-status.json'
        self.unitdir = self.home / '.config/systemd/user'
        self.drop = self.unitdir / (STD + '.d') / DROP_NAME
        self.paths = {'agent': self.agent, 'rollback': Path(str(self.agent) + '.rollback'),
                      'cli': self.home / '.local/bin/hara-commander',
                      'hara': self.home / '.local/bin/hara', 'config': self.config,
                      'standard_unit': self.unitdir / STD, 'v2_unit': self.unitdir / V2,
                      'migration_dropin': self.drop}
        self.env = {'HOME': str(self.home), 'USER': pwd.getpwuid(self.uid).pw_name,
                    'LOGNAME': pwd.getpwuid(self.uid).pw_name,
                    'PATH': '/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'C', 'LC_ALL': 'C',
                    'XDG_RUNTIME_DIR': '/run/user/' + str(self.uid),
                    'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/run/user/' + str(self.uid) + '/bus'}
        self.deadline = time.monotonic() + 300
        self.out = None
        self.backups = {}
        self.mutated = False
        self.drop_dir_created = False
        self.lock_fd = None
        self.report = {'schema': SCHEMA, 'started_at': stamp(), 'state': 'HOLD',
                       'version': '0.3.56', 'public_release': False, 'event_v2': 'OFF',
                       'enrollment_or_trust_config_changed': False, 'steps': []}

    def cmd(self, argv, limit=30, env=None, okay=(0,)):
        timeout = min(limit, self.deadline - time.monotonic())
        need(timeout > 0, 'MIGRATION_DEADLINE')
        p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=self.env if env is None else env,
                             start_new_session=True)
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except BaseException:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                p.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.communicate(timeout=2)
            raise
        need(len(stdout) <= 2 * 1024**2 and len(stderr) <= 2 * 1024**2, 'COMMAND_OUTPUT_LIMIT')
        if p.returncode not in okay:
            raise RuntimeError('COMMAND_FAILED:' + str(p.returncode) + ':' + argv[0] + ':' + ' '.join(argv[1:3]))
        return p.returncode, stdout, stderr

    def ctl(self, *args, okay=(0,), limit=30):
        return self.cmd(['/usr/bin/systemctl', '--user', *args], limit=limit, okay=okay)

    def unit(self, name, limit=30):
        props = ('LoadState', 'ActiveState', 'SubState', 'MainPID', 'FragmentPath',
                 'DropInPaths', 'Environment', 'EnvironmentFiles', 'UnitFileState')
        rc, out, _ = self.ctl('show', name, '--no-pager',
                            '--property=' + ','.join(props), okay=(0, 1), limit=limit)
        values = dict(line.split('=', 1) for line in out.decode().splitlines() if '=' in line)
        environment = dict(part.split('=', 1) for part in shlex.split(values.get('Environment', '')))
        allowed_environment = ({}, {'HARA_COMMANDER_EVENT_V2_OPT_IN': '1', 'PYTHONDONTWRITEBYTECODE': '1'}) if name == V2 else ({}, {'PYTHONDONTWRITEBYTECODE': '1'})
        need(environment in allowed_environment and not values.get('EnvironmentFiles'), 'CUSTOM_UNIT_ENVIRONMENT:' + name)
        load = values.get('LoadState')
        if load == 'not-found':
            return {'present': False, 'active': False, 'enabled': 'not-found', 'pid': 0, 'dropins': []}
        need(rc == 0 and load == 'loaded', 'UNIT_LOAD_STATE:' + name)
        need(values.get('ActiveState') in ('active', 'inactive') and
             values.get('SubState') in ('running', 'dead'), 'UNIT_TRANSITION:' + name)
        need(values.get('UnitFileState') in ('enabled', 'disabled'), 'UNIT_ENABLE_STATE:' + name)
        need(values.get('FragmentPath') == str(self.unitdir / name), 'UNIT_FRAGMENT:' + name)
        rows = []
        for raw in values.get('DropInPaths', '').split():
            path = Path(raw)
            need(path.is_absolute(), 'DROPIN_PATH')
            data = read(path)
            need(path == self.drop or path.name == '10-timeout-abort.conf', 'UNREVIEWED_DROPIN:' + str(path))
            rows.append({'path': str(path), 'sha256': sha(data)})
        pid = int(values.get('MainPID', '0'))
        active = values['ActiveState'] == 'active'
        need((pid > 0) == active, 'UNIT_PID_STATE:' + name)
        row = {'present': True, 'active': active, 'enabled': values['UnitFileState'], 'pid': pid, 'dropins': rows,
               'environment': environment}
        if active:
            cmdline = read(Path('/proc') / str(pid) / 'cmdline', 65536).split(b'\0')
            candidates = [x.decode() for x in cmdline if x and Path(os.fsdecode(x)).name in
                          ('linux.py', 'linux_founder_event_v2.py', 'hara-commander-agent')]
            need(len(candidates) == 1, 'ACTIVE_AGENT_CMDLINE:' + name)
            script = Path(candidates[0])
            need(script.is_absolute() and script.is_relative_to(self.home), 'ACTIVE_AGENT_OUTSIDE_HOME')
            row['agent_path'] = str(script)
            row['agent_sha256'] = sha(read(script))
            procstat = read(Path('/proc') / str(pid) / 'stat', 65536).decode()
            row['birth_ticks'] = int(procstat.rsplit(')', 1)[1].split()[19])
        return row

    def configuration(self):
        data = read(self.config)
        values = {}
        for line in data.decode().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k, v = line.split('=', 1)
                values[k.strip()] = v.strip().strip('"').strip("'")
        need(values.get('HARA_COMMANDER_URL', '').rstrip('/') == 'https://commander.haralabs.com.br', 'CONFIG_ORIGIN')
        need(values.get('HARA_COMMANDER_APPROVAL_MODE') == 'PERSISTENT_TRUSTED', 'CONFIG_TRUST_MODE')
        need(values.get('HARA_COMMANDER_EVENT_V2_DEV_ENABLED', 'false').lower() in ('false', '0', 'off', ''), 'EVENT_V2_ENABLED')
        need(values.get('HARA_COMMANDER_TRANSPORT_MODE', 'OUTBOUND_RELAY') == 'OUTBOUND_RELAY', 'TRANSPORT_REQUIRES_SEPARATE_HEALTH_REVIEW')
        need(bool(values.get('HARA_DEVICE_ID')) and bool(values.get('HARA_DEVICE_TOKEN')), 'ENROLLMENT_MISSING')
        return {'sha256': sha(data), 'origin': 'https://commander.haralabs.com.br',
                'approval_mode': 'PERSISTENT_TRUSTED', 'transport': 'OUTBOUND_RELAY', 'event_v2': False}

    def manager_environment(self):
        _, out, _ = self.ctl('show-environment')
        values = dict(line.split('=', 1) for line in out.decode().splitlines() if '=' in line)
        need(not any(key.startswith('HARA_') for key in values), 'MANAGER_HARA_OVERRIDE_REQUIRES_REVIEW')
        expected = {'HOME': str(self.home), 'XDG_CONFIG_HOME': str(self.home / '.config'),
                    'XDG_DATA_HOME': str(self.home / '.local/share'),
                    'XDG_STATE_HOME': str(self.home / '.local/state'),
                    'XDG_RUNTIME_DIR': '/run/user/' + str(self.uid)}
        need(all(key not in values or values[key] == value for key, value in expected.items()),
             'MANAGER_HOME_XDG_OVERRIDE')
        return {'authority_overrides_absent': True, 'home_xdg_defaults': True}

    def inventory(self, target):
        need(target in TARGETS, 'TARGET_NOT_ALLOWLISTED')
        need(sha(read(self.stage / 'install-linux.sh')) == INSTALLER_SHA, 'INSTALLER_PIN')
        need(sha(read(self.stage / 'ca.pem')) == CA_SHA, 'QA_CA_PIN')
        units = {name: self.unit(name) for name in UNITS}
        need(units[STD]['present'], 'STANDARD_UNIT_REQUIRED')
        need(sum(row['active'] for row in units.values()) == 1, 'EXACTLY_ONE_ACTIVE_AGENT_REQUIRED')
        files = {name: item(path) for name, path in self.paths.items()}
        groups = set(os.getgroups()) | {os.getegid()}
        for name in ('agent', 'rollback', 'cli', 'hara'):
            row = files[name]
            if row['kind'] != 'absent':
                need(row['uid'] == self.uid and row['gid'] in groups, 'RESTORABLE_FILE_OWNER_GROUP:' + name)
        need(files['agent']['kind'] == 'file', 'INSTALLED_AGENT_REQUIRED')
        need(files['migration_dropin']['kind'] == 'absent', 'EXISTING_MIGRATION_DROPIN_REFUSED')
        cli = files['cli']
        need(cli['kind'] in ('absent', 'symlink'), 'CLI_REGULAR_FILE_REQUIRES_SEPARATE_REVIEW')
        if cli['kind'] == 'symlink':
            resolved = Path(cli['resolved'])
            need(resolved == self.agent or resolved.is_relative_to(self.bin), 'CLI_OUTSIDE_REVIEWED_PRODUCT_TREE')
            need(Path(cli['resolved']).name in ('linux.py', 'hara-commander-agent'), 'CLI_TARGET_NAME')
        return {'schema': SCHEMA, 'target': target, 'hostname': os.uname().nodename,
                'uid': self.uid, 'home': str(self.home), 'stage': str(self.stage),
                'configuration': self.configuration(), 'manager_environment': self.manager_environment(),
                'units': units, 'files': files,
                'release_url': RELEASE_URL, 'installer_sha256': INSTALLER_SHA, 'ca_sha256': CA_SHA}

    def progress(self, step):
        self.report['steps'].append({'at': stamp(), 'step': step})
        if self.out is not None:
            try:
                atomic(self.out / 'progress.json', (json.dumps(self.report, sort_keys=True, indent=2) + '\n').encode())
            except Exception as error:
                self.report.setdefault('progress_write_errors', []).append(str(error))

    def snapshot(self, name, path):
        row = item(path)
        self.backups[name] = row
        if row['kind'] == 'file':
            atomic(self.out / (name + '.before'), read(path))
        elif row['kind'] == 'symlink':
            atomic(self.out / (name + '.symlink.json'), json.dumps(row, sort_keys=True).encode())

    def restore(self, name, path):
        row = self.backups[name]
        if row['kind'] == 'absent':
            if path.exists() or path.is_symlink():
                need(not path.is_dir(), 'ROLLBACK_UNEXPECTED_DIRECTORY:' + name)
                path.unlink()
        elif row['kind'] == 'file':
            atomic(path, read(self.out / (name + '.before')), row['mode'], row['gid'])
        else:
            temp = path.with_name(path.name + '.fleet-restore-' + str(os.getpid()))
            os.symlink(row['target'], temp)
            if temp.lstat().st_gid != row['gid']:
                os.chown(temp, -1, row['gid'], follow_symlinks=False)
            os.replace(temp, path)
        need(item(path) == row, 'ROLLBACK_FILE_READBACK:' + name)

    def no_agent_process(self, old):
        paths = {str(self.agent)} | {x['agent_path'] for x in old['units'].values() if x.get('active')}
        for path in Path('/proc').iterdir():
            if not path.name.isdigit():
                continue
            try:
                if path.stat().st_uid != self.uid:
                    continue
                args = read(path / 'cmdline', 65536).split(b'\0')
                need(not any(os.fsencode(x) in args for x in paths), 'AGENT_PROCESS_STILL_RUNNING:' + path.name)
            except (FileNotFoundError, ProcessLookupError):
                continue

    def stop_all(self, old):
        for name in UNITS:
            if old['units'][name]['present']:
                self.ctl('stop', name, limit=45)
        need(not any(self.unit(name)['active'] for name in UNITS), 'UNIT_DID_NOT_STOP')
        self.no_agent_process(old)

    def unit_after_start(self, name, end):
        # Type=simple can report a MainPID before the Python/Agent exec. Retry
        # only that incomplete observation after our own start; inventory and
        # all other unit failures remain strict. Callers still verify identity.
        end = min(end, self.deadline, time.monotonic() + 5)
        while True:
            remaining = end - time.monotonic()
            need(remaining > 0, 'POST_START_CMDLINE_TIMEOUT:' + name)
            try:
                return self.unit(name, limit=remaining)
            except RuntimeError as error:
                if str(error) != 'ACTIVE_AGENT_CMDLINE:' + name:
                    raise
            remaining = end - time.monotonic()
            need(remaining > 0, 'POST_START_CMDLINE_TIMEOUT:' + name)
            time.sleep(min(0.1, remaining))

    def health(self, previous, since):
        end = min(self.deadline, time.monotonic() + 90)
        while time.monotonic() < end:
            row = self.unit_after_start(STD, end)
            need(not self.unit(V2)['active'], 'DUAL_AGENT_RUNTIME')
            if row['active']:
                need(row['agent_path'] == str(self.agent) and row['agent_sha256'] == AGENT_SHA, 'WRONG_RUNTIME_AGENT')
                try:
                    status = json.loads(read(self.status, 65536))
                    started = status.get('started_at_utc')
                    heartbeat = status.get('last_successful_heartbeat_at_utc')
                    def parsed(value):
                        return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()
                    if (status.get('agent_version') == '0.3.56' and started and started != previous and heartbeat and
                            parsed(started) >= since - 2 and parsed(heartbeat) >= parsed(started)):
                        time.sleep(2)
                        again = self.unit_after_start(STD, end)
                        need(again['active'] and again['pid'] == row['pid'] and
                             again.get('birth_ticks') == row.get('birth_ticks') and
                             again.get('agent_path') == str(self.agent) and
                             again.get('agent_sha256') == AGENT_SHA, 'RUNTIME_NOT_STABLE')
                        return {'pid': row['pid'], 'birth_ticks': row['birth_ticks'], 'agent_sha256': AGENT_SHA,
                                'agent_version': '0.3.56', 'started_at_utc': started,
                                'last_successful_heartbeat_at_utc': heartbeat,
                                'external_commander_e2e': 'PENDING_OPERATOR_READBACK'}
                except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
                    pass
            time.sleep(1)
        raise RuntimeError('FRESH_RUNTIME_HEARTBEAT_TIMEOUT')

    def rollback(self, old):
        self.deadline = time.monotonic() + 180
        self.progress('ROLLBACK_STARTED')
        self.stop_all(old)
        for name in ('agent', 'rollback', 'cli', 'hara', 'migration_dropin'):
            self.restore(name, self.paths[name])
        if self.drop_dir_created:
            self.drop.parent.rmdir()
        self.ctl('daemon-reload')
        for name in UNITS:
            row = old['units'][name]
            if row['present']:
                self.ctl('enable' if row['enabled'] == 'enabled' else 'disable', name)
        need(self.configuration() == old['configuration'], 'ROLLBACK_CONFIG_CHANGED_NOT_OVERWRITTEN')
        for name in UNITS:
            if old['units'][name]['active']:
                self.ctl('start', name, limit=45)
        after = {name: self.unit_after_start(name, self.deadline)
                 if old['units'][name]['active'] else self.unit(name) for name in UNITS}
        for name in UNITS:
            expected = old['units'][name]
            need(after[name]['active'] == expected['active'] and after[name]['enabled'] == expected['enabled'], 'ROLLBACK_UNIT_STATE')
            if expected['active']:
                need(after[name]['agent_path'] == expected['agent_path'] and after[name]['agent_sha256'] == expected['agent_sha256'], 'ROLLBACK_ACTIVE_BINARY')
        self.report['rollback'] = {'state': 'PASS_FILES_UNITS_ACTIVE_BINARY_RESTORED',
                                   'fresh_remote_operation': 'NOT_CLAIMED', 'units': after}

    def execute(self, old, output):
        need(old.get('schema') == SCHEMA, 'CONTRACT_SCHEMA')
        self.lock_fd = os.open(self.stage / 'fleet-update.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        lock_stat = os.fstat(self.lock_fd)
        need(stat.S_ISREG(lock_stat.st_mode) and lock_stat.st_uid == self.uid and lock_stat.st_nlink == 1,
             'LOCK_OWNER_TYPE')
        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fresh = self.inventory(old.get('target'))
        need(fresh == old, 'INVENTORY_CONTRACT_CHANGED')
        self.out = Path(output).absolute()
        need(self.out.parent == self.stage, 'OUTPUT_MUST_BE_NEW_STAGE_SUBDIRECTORY')
        self.out.mkdir(mode=0o700)
        need(self.out.stat().st_uid == self.uid, 'OUTPUT_OWNER')
        self.report['target'] = old['target']
        atomic(self.out / 'contract.json', (json.dumps(old, sort_keys=True, indent=2) + '\n').encode())
        for name, path in self.paths.items():
            self.snapshot(name, path)
        for name, row in old['units'].items():
            if row['active']:
                atomic(self.out / ('active-' + name + '.before.py'), read(Path(row['agent_path'])))
        self.progress('BACKUPS_COMPLETE')
        # The supplied public QA CA is pinned; system roots remain available.
        qa = read(self.stage / 'ca.pem')
        roots_path = None
        for candidate in (Path('/etc/ssl/certs/ca-certificates.crt'),
                          Path(ssl.get_default_verify_paths().openssl_cafile)):
            if candidate.is_file():
                roots_path = candidate.resolve(strict=True)
                break
        need(roots_path is not None, 'SYSTEM_CA_BUNDLE_NOT_FOUND')
        roots = read(roots_path)
        need(b'PRIVATE KEY' not in qa and b'BEGIN CERTIFICATE' in qa, 'QA_CA_CONTENT')
        bundle = self.out / 'process-ca-bundle.pem'
        atomic(bundle, roots + b'\n' + qa)
        installer = self.out / 'install-linux.sh'
        atomic(installer, read(self.stage / 'install-linux.sh'), 0o700)
        env = {**self.env, 'HARA_COMMANDER_RELEASE_URL': RELEASE_URL,
               'SSL_CERT_FILE': str(bundle), 'CURL_CA_BUNDLE': str(bundle)}
        previous = None
        try:
            previous = json.loads(read(self.status, 65536)).get('started_at_utc')
        except (FileNotFoundError, ValueError):
            pass
        try:
            self.mutated = True
            self.stop_all(old)
            self.progress('OLD_AGENT_STOPPED')
            # Only a reviewed Commander symlink may be retargeted; ordinary
            # preexisting files are refused by inventory, not overwritten.
            if old['files']['cli']['kind'] == 'symlink':
                temp = self.paths['cli'].with_name('hara-commander.fleet-' + str(os.getpid()))
                os.symlink(str(self.agent), temp)
                os.replace(temp, self.paths['cli'])
            rc, stdout, stderr = self.cmd(['/usr/bin/bash', str(installer), 'update'], limit=160, env=env,
                                           okay=tuple(range(256)))
            atomic(self.out / 'updater.stdout', stdout)
            atomic(self.out / 'updater.stderr', stderr)
            self.report['updater_exit'] = rc
            need(rc == 0 and b'HARA_COMMANDER_AGENT_UPDATE=PASS' in stdout and
                 b'HARA_COMMANDER_AGENT_INTEGRITY=PASS' in stdout, 'UPDATER_FAILED')
            need(sha(read(self.agent)) == AGENT_SHA and sha(read(Path(str(self.agent) + '.rollback'))) == old['files']['agent']['sha256'], 'UPDATED_AGENT_OR_PREIMAGE_PIN')
            need(self.configuration() == old['configuration'], 'CONFIG_CHANGED')
            for name in ('standard_unit', 'v2_unit'):
                need(item(self.paths[name]) == old['files'][name], 'UNIT_FILE_CHANGED:' + name)
            if not self.drop.parent.exists():
                self.drop.parent.mkdir(mode=0o700)
                self.drop_dir_created = True
            need(not self.drop.exists() and not self.drop.is_symlink(), 'DROPIN_ALREADY_EXISTS')
            need(not any(x in str(self.agent) for x in ('\n', '\r', '%', '"', '\\')), 'EXECSTART_PATH_UNSAFE')
            atomic(self.drop, ('[Service]\nExecStart=\nExecStart="' + str(self.agent) + '"\n').encode())
            self.ctl('daemon-reload')
            self.progress('UPDATED_BYTES_AND_STANDARD_EXECSTART_READY')
            since = time.time()
            self.ctl('start', STD, limit=30)
            self.progress('NEW_STANDARD_STARTED_AWAITING_HEARTBEAT')
            self.report['runtime'] = self.health(previous, since)
            self.progress('NEW_RUNTIME_HEALTH_PASS')
            enabled = any(row['active'] and row['enabled'] == 'enabled' for row in old['units'].values())
            if old['units'][V2]['present']:
                self.ctl('disable', V2)
            self.ctl('enable' if enabled else 'disable', STD)
            final = {name: self.unit(name) for name in UNITS}
            need(final[STD]['active'] and final[STD]['enabled'] == ('enabled' if enabled else 'disabled') and
                 not final[V2]['active'] and final[V2]['enabled'] in ('disabled', 'not-found'), 'FINAL_UNIT_STATE')
            need(self.configuration() == old['configuration'], 'FINAL_CONFIG_CHANGED')
            self.report['units_after'] = final
            self.report['state'] = 'PASS_PRIVATE_0356_RUNTIME_MIGRATION'
        except BaseException as error:
            self.report['error'] = str(error)
            if self.mutated:
                try:
                    self.rollback(old)
                except BaseException as rollback_error:
                    self.report['rollback'] = {'state': 'HOLD', 'error': str(rollback_error)}
        self.report['finished_at'] = stamp()
        self.progress('FINISHED')
        atomic(self.out / 'result.json', (json.dumps(self.report, sort_keys=True, indent=2) + '\n').encode())
        print(json.dumps(self.report, sort_keys=True))
        return 0 if self.report['state'].startswith('PASS_') else 2


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    inv = sub.add_parser('inventory')
    inv.add_argument('--target', choices=TARGETS, required=True)
    inv.add_argument('--stage', required=True)
    exe = sub.add_parser('execute')
    exe.add_argument('--contract', required=True)
    exe.add_argument('--stage', required=True)
    exe.add_argument('--out', required=True)
    args = parser.parse_args()
    op = Migration(args.stage)
    def interrupted(signum, frame):
        raise RuntimeError('SIGNAL:' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    if args.action == 'inventory':
        print(json.dumps(op.inventory(args.target), sort_keys=True, indent=2))
        return 0
    try:
        return op.execute(json.loads(read(Path(args.contract))), args.out)
    finally:
        if op.lock_fd is not None:
            os.close(op.lock_fd)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'state': 'HOLD_HELPER_ERROR', 'error': str(error)}, sort_keys=True))
        raise SystemExit(2)
