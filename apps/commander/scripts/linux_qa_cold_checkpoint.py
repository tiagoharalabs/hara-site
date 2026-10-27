#!/usr/bin/python3.10
"""Finite operator helper: cold restore of the ORIGINAL Linux QA baseline.

Run as root with /usr/bin/python3.10 -I -S after reviewing/deploying this source.
Only checkpoint_restore_boot and verify_boot are accepted. No installer, XML
change, clone operation, forced shutdown, campaign reset, or credential output.
verify_boot checks the pinned .53 baseline; it is not a .56 installation test.
"""
from pathlib import Path
import base64
import ctypes
import datetime
import fcntl
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

UUID = 'd7a27a4a-41c3-4c14-a84e-187443566a3c'
NAME = 'hara-review-linux'
DISK = Path('/var/lib/libvirt/images/hara-review/linux/root.qcow2')
PREP = Path('/var/lib/hara-qa/restore-linux-056-preparation-20261027')
FOLDER = PREP / 'original-linux-commander-0356-cold-checkpoint-20261027'
BASELINE = FOLDER / 'baseline.qcow2'
RESTORED = FOLDER / 'restored-ready.qcow2'
ORIGINAL = FOLDER / 'original-before-056.qcow2'
FAILED = FOLDER / 'restored-failed.qcow2'
MACHINE_ID = '27acff5ddd62442699e84f73400bc8b2'
AGENT = '/home/commanderqa/.local/share/hara-commander/hara-commander-agent'
CONFIG = '/home/commanderqa/.config/hara-commander/device.env'
UNIT = '/home/commanderqa/.config/systemd/user/hara-commander-agent.service'
RUNTIME = '/home/commanderqa/.local/share/hara-commander/runtime-status.json'
PINS = {
    AGENT: 'db91714140b63684917e46d6a327778183a5829dbf2b298098b31da4d463985e',
    CONFIG: 'a9ef1718628959756ab5b160511d88d78574f079dcbc5bea0767ab7f16067755',
    UNIT: 'cbbe5136041ce4a2900477ec73ae42f88c0c6bbe7b2c0a88f7a15802670d460b',
}
OTHERS = {
    'hara-review-win11': '7fb8e9ba-57c5-4457-8aaa-465b568a4c62',
    'hara-review-linux-restoretest-20261024': '9ee73ce0-80a9-4b20-93e3-026b6294d660',
    'hara-review-win11-restoretest-20261024': '154e2853-3d1d-4d23-a43d-706f76ad7939',
}
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'HOME': '/root'}
HEADROOM = 2 * 1024**3
ACTIONS = ('checkpoint_restore_boot', 'verify_boot')


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def protected(path):
    for p in (path, *path.parents):
        s = p.lstat()
        need(stat.S_ISDIR(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022,
             'UNPROTECTED_DIRECTORY:' + str(p))


def meta(path, dir_fd=None):
    s = path.lstat() if dir_fd is None else os.stat(path.name, dir_fd=dir_fd, follow_symlinks=False)
    need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1, 'NOT_SINGLE_REGULAR:' + str(path))
    return {k: getattr(s, 'st_' + k) for k in
            ('dev', 'ino', 'size', 'uid', 'gid', 'mode', 'nlink', 'mtime_ns', 'ctime_ns')}


def identity(m):
    # rename changes ctime, but does not replace an inode or its contents.
    return {k: v for k, v in m.items() if k != 'ctime_ns'}


def xattrs(path):
    if isinstance(path, int):
        return {name: os.getxattr(path, name) for name in os.listxattr(path)}
    return {name: os.getxattr(path, name, follow_symlinks=False)
            for name in os.listxattr(path, follow_symlinks=False)}


def cold_metadata_ok(m):
    mode = stat.S_IMODE(m['mode'])
    return (m['uid'] in (0, 64055) and m['gid'] in (0, 109) and
            mode & 0o600 == 0o600 and mode & 0o7133 == 0)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def put(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)
            need(n > 0, 'SHORT_WRITE')
            view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_dir(path.parent)


def put_json(path, data):
    put(path, (json.dumps(data, sort_keys=True, indent=2) + '\n').encode())


def rename_noreplace(source, target, source_dirfd=None, target_dirfd=None):
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100 if source_dirfd is None else source_dirfd,
              os.fsencode(source if source_dirfd is None else source.name),
              -100 if target_dirfd is None else target_dirfd,
              os.fsencode(target if target_dirfd is None else target.name), 1) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code), str(target))
    fsync_dir(source.parent) if source_dirfd is None else os.fsync(source_dirfd)
    if source.parent != target.parent or source_dirfd != target_dirfd:
        fsync_dir(target.parent) if target_dirfd is None else os.fsync(target_dirfd)


def validate_xml(raw):
    need(len(raw) < 1024**2 and b'<!DOCTYPE' not in raw and b'<!ENTITY' not in raw, 'XML_SIZE_OR_ENTITY')
    r = ET.fromstring(raw)
    need(r.findtext('uuid') == UUID and r.findtext('name') == NAME, 'DOMAIN_IDENTITY')
    need(r.findtext('./devices/emulator') == '/usr/bin/qemu-system-x86_64', 'EMULATOR_CHANGED')
    disks = r.findall('./devices/disk')
    writable = [d for d in disks if d.find('readonly') is None]
    need(len(writable) == 1, 'REQUIRES_ONE_WRITABLE_DISK')
    disk = writable[0]
    need(disk.get('type') == 'file' and disk.get('device') == 'disk' and
         disk.find('source') is not None and disk.find('source').get('file') == str(DISK) and
         disk.find('driver') is not None and disk.find('driver').get('type') == 'qcow2', 'DISK_CHANGED')
    networks = sorted(n.get('network') for n in r.findall('./devices/interface/source'))
    need(networks == ['hara-review-egress', 'hara-review-isolated'], 'NETWORKS_CHANGED')
    need(r.find('./os/nvram') is None and not r.findall('./devices/tpm') and
         not r.findall('./devices/filesystem') and not r.findall('./devices/hostdev'),
         'EXTERNAL_WRITABLE_STATE_REQUIRES_SEPARATE_BACKUP')
    return sha(raw)


def validate_guest(data):
    need(data.get('machine_id') == MACHINE_ID, 'GUEST_MACHINE_ID')
    need(data.get('account') == {'uid': 2000, 'name': 'commanderqa', 'home': '/home/commanderqa'}, 'GUEST_ACCOUNT')
    files = data.get('files', {})
    for path, pin in PINS.items():
        need(files.get(path, {}).get('sha256') == pin, 'BASELINE_FILE_PIN:' + path)
    return data


# The guest command is constant, read-only and never emits configuration bytes.
GUEST_SCRIPT = r'''
import hashlib,json,os,pwd,re,stat
paths = {
 '/home/commanderqa/.local/share/hara-commander/hara-commander-agent': 134217728,
 '/home/commanderqa/.config/hara-commander/device.env': 65536,
 '/home/commanderqa/.config/systemd/user/hara-commander-agent.service': 65536,
}
def read(path,limit,contents=False):
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  a=os.fstat(fd)
  if not stat.S_ISREG(a.st_mode) or a.st_size>limit: raise RuntimeError('file shape')
  h=hashlib.sha256(); result=[]; count=0
  while True:
   b=os.read(fd,1048576)
   if not b: break
   count+=len(b)
   if count>limit: raise RuntimeError('file growth')
   h.update(b)
   if contents: result.append(b)
  z=os.fstat(fd)
  keys=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns','st_uid','st_gid','st_mode')
  if any(getattr(a,k)!=getattr(z,k) for k in keys): raise RuntimeError('file changed')
  info={'sha256':h.hexdigest(),'size':count,'uid':a.st_uid,'gid':a.st_gid,'mode':stat.S_IMODE(a.st_mode)}
  return info,b''.join(result)
 finally: os.close(fd)
user=pwd.getpwuid(2000)
out={'machine_id':read('/etc/machine-id',128,True)[1].decode('ascii').strip(),
 'account':{'uid':user.pw_uid,'name':user.pw_name,'home':user.pw_dir},
 'files':{p:read(p,n)[0] for p,n in paths.items()},
 'runtime_status_is_historical_not_liveness':True}
try:
 r=json.loads(read('/home/commanderqa/.local/share/hara-commander/runtime-status.json',1048576,True)[1])
 out['runtime_status_selected']={k:v for k,v in r.items() if isinstance(v,str) and len(v)<=64 and
  ((k in ('version','agent_version') and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?',v)) or
   (k in ('started_at','updated_at') and re.fullmatch(r'[0-9TZ:+.-]+',v)))}
except FileNotFoundError: out['runtime_status_selected']=None
except Exception as e: out['runtime_status_observation_error']=type(e).__name__
print(json.dumps(out,sort_keys=True))
'''


class Operator:
    def __init__(self):
        self.deadline = time.monotonic() + 1200
        self.report = {'schema': 'hara.qa.original-linux.cold-recovery.v1', 'started_at': stamp(),
                       'uuid': UUID, 'disk': str(DISK), 'checkpoint_dir': str(FOLDER),
                       'state': 'HOLD', 'baseline_version': '0.3.53', 'installation_performed': False,
                       'forced_shutdowns': 0, 'xml_mutations': 0, 'clone_operations': 0,
                       'old_campaign_reopened': False}
        self.old_xml = None
        self.source = None
        self.source_hash = None
        self.restored_inode = None
        self.source_fd = None
        self.restored_fd = None
        self.disk_dirfd = None
        self.checkpoint_dirfd = None
        self.disk_tree = None
        self.shutdown_requested = False

    def close_fds(self):
        for name in ('source_fd', 'restored_fd', 'disk_dirfd', 'checkpoint_dirfd'):
            fd = getattr(self, name)
            if fd is not None:
                os.close(fd)
                setattr(self, name, None)

    def owned_file(self, path, fd, expected_inode):
        need(fd is not None, 'OWNED_FILE_REFERENCE_MISSING')
        current = self.file_meta(path)
        held = os.fstat(fd)
        need((current['dev'], current['ino']) == expected_inode == (held.st_dev, held.st_ino)
             and stat.S_ISREG(held.st_mode) and held.st_nlink == 1, 'OWNED_FILE_CHANGED')
        return current

    @staticmethod
    def directory_observation(path):
        s = path.lstat()
        need(stat.S_ISDIR(s.st_mode), 'DIRECTORY_SYMLINK_OR_TYPE:' + str(path))
        return {'dev': s.st_dev, 'ino': s.st_ino, 'uid': s.st_uid, 'gid': s.st_gid,
                'mode': stat.S_IMODE(s.st_mode)}

    def open_disk_directory(self):
        # The existing lab tree is UID1002/group kvm and group writable. Record
        # its real identity; do not change its ownership or invent root custody.
        self.disk_tree = {str(p): self.directory_observation(p) for p in (DISK.parent, *DISK.parent.parents)}
        self.disk_dirfd = os.open(DISK.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.check_directories()
        protected(FOLDER.parent)
        need(os.fstat(self.disk_dirfd).st_dev == FOLDER.parent.stat().st_dev,
             'CHECKPOINT_RENAME_REQUIRES_SAME_FILESYSTEM')
        self.report['libvirt_directory_tree_observed'] = self.disk_tree
        self.report['scope_assumes_trusted_host_and_libvirt'] = True

    def check_directories(self):
        if self.disk_tree is not None:
            need(all(self.directory_observation(Path(p)) == expected for p, expected in self.disk_tree.items()),
                 'LIBVIRT_DIRECTORY_BINDING_CHANGED')
            held = os.fstat(self.disk_dirfd)
            expected = self.disk_tree[str(DISK.parent)]
            need((held.st_dev, held.st_ino) == (expected['dev'], expected['ino']), 'LIBVIRT_DIRECTORY_FD_CHANGED')
        if self.checkpoint_dirfd is not None:
            protected(FOLDER)
            held = os.fstat(self.checkpoint_dirfd)
            current = FOLDER.lstat()
            need((held.st_dev, held.st_ino) == (current.st_dev, current.st_ino), 'CHECKPOINT_DIRECTORY_CHANGED')

    def parent_fd(self, path):
        if path.parent == DISK.parent:
            return self.disk_dirfd
        if path.parent == FOLDER:
            return self.checkpoint_dirfd
        return None

    def file_meta(self, path):
        return meta(path, self.parent_fd(path))

    def open_file(self, path):
        fd = self.parent_fd(path)
        return os.open(path if fd is None else path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)

    def bound_path(self, path):
        fd = self.parent_fd(path)
        return str(path) if fd is None else '/proc/self/fd/' + str(fd) + '/' + path.name

    def file_xattrs(self, path):
        fd = self.open_file(path)
        try:
            return xattrs(fd)
        finally:
            os.close(fd)

    def move(self, source, target):
        self.check_directories()
        rename_noreplace(source, target, self.parent_fd(source), self.parent_fd(target))

    def remaining(self, limit):
        result = min(limit, self.deadline - time.monotonic())
        need(result > 0, 'OPERATION_DEADLINE')
        return result

    def run(self, argv, limit=30, pass_directories=False):
        p = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, env=ENV, timeout=self.remaining(limit), check=False,
                           pass_fds=tuple(fd for fd in (self.disk_dirfd, self.checkpoint_dirfd) if fd is not None)
                           if pass_directories else ())
        need(len(p.stdout) <= 1024**2 and len(p.stderr) <= 16384, 'TOOL_OUTPUT_LIMIT')
        if p.returncode:
            # Commands here contain no credentials; preserve a bounded native diagnostic.
            raise RuntimeError('TOOL_FAILED:' + json.dumps({'argv': argv[:5], 'exit': p.returncode,
                                                          'stderr': p.stderr.decode(errors='replace')[:2048]}))
        return p.stdout

    def virsh(self, *args, limit=30):
        return self.run(['/usr/bin/virsh', '-c', 'qemu:///system', *args], limit)

    def state(self):
        return self.virsh('domstate', UUID).decode().strip()

    def unchanged_xml(self):
        raw = self.virsh('dumpxml', UUID, '--inactive')
        validate_xml(raw)
        need(self.old_xml is None or raw == self.old_xml, 'INACTIVE_XML_CHANGED')
        return raw

    def off(self):
        self.check_directories()
        need(self.state() == 'shut off', 'DOMAIN_NOT_OFF')
        self.unchanged_xml()

    def others(self):
        result = {}
        for name, uuid in OTHERS.items():
            raw = self.virsh('dumpxml', uuid, '--inactive')
            r = ET.fromstring(raw)
            need(r.findtext('name') == name and r.findtext('uuid') == uuid, 'OTHER_DOMAIN_IDENTITY')
            result[name] = {'uuid': uuid, 'state': self.virsh('domstate', uuid).decode().strip(),
                            'id': self.virsh('domid', uuid).decode().strip(), 'xml_sha256': sha(raw)}
        return result

    def wait_state(self, target, seconds):
        end = time.monotonic() + self.remaining(seconds)
        while True:
            if self.state() == target:
                return
            need(time.monotonic() < end, 'DOMAIN_WAIT_TIMEOUT:' + target)
            time.sleep(min(1, max(0, end - time.monotonic())))

    def hash_file(self, path):
        before = self.file_meta(path)
        fd = self.open_file(path)
        try:
            s = os.fstat(fd)
            need((s.st_dev, s.st_ino) == (before['dev'], before['ino']), 'HASH_PATH_CHANGED')
            h = hashlib.sha256()
            while True:
                self.remaining(1)
                chunk = os.read(fd, 4 * 1024**2)
                if not chunk:
                    break
                h.update(chunk)
            need(self.file_meta(path) == before and os.fstat(fd).st_size == before['size'], 'FILE_CHANGED_DURING_HASH')
            return h.hexdigest()
        finally:
            os.close(fd)

    def image_check(self, path):
        self.off()
        info = json.loads(self.run(['/usr/bin/qemu-img', 'info', '--output=json', '-f', 'qcow2', self.bound_path(path)], 60, True))
        def dependent(value):
            if isinstance(value, dict):
                return any((k in ('backing-filename', 'full-backing-filename', 'data-file') and bool(v)) or dependent(v)
                           for k, v in value.items())
            return isinstance(value, list) and any(dependent(x) for x in value)
        need(info.get('format') == 'qcow2' and not dependent(info), 'IMAGE_HAS_EXTERNAL_DEPENDENCY')
        check = json.loads(self.run(['/usr/bin/qemu-img', 'check', '--output=json', '-f', 'qcow2', self.bound_path(path)], 120, True))
        need(all(check.get(k, 0) == 0 for k in ('check-errors', 'corruptions', 'leaks')), 'IMAGE_CHECK_ERRORS')
        self.off()
        return {'info': info, 'check': check}

    def copy(self, source, target):
        self.off()
        need(not target.exists() and not target.is_symlink(), 'COPY_TARGET_EXISTS')
        self.run(['/usr/bin/cp', '--sparse=always', '--reflink=never', '--preserve=all', '--', self.bound_path(source), self.bound_path(target)], 300, True)
        fd = self.open_file(target)
        try:
            need(stat.S_ISREG(os.fstat(fd).st_mode), 'COPY_TARGET_TYPE')
            os.fsync(fd)
        finally:
            os.close(fd)
        fsync_dir(target.parent)
        self.off()

    def qga(self, execute, arguments=None):
        cmd = {'execute': execute}
        if arguments is not None:
            cmd['arguments'] = arguments
        result = json.loads(self.virsh('qemu-agent-command', UUID, '--timeout', '10', json.dumps(cmd), limit=15))
        need('return' in result and 'error' not in result, 'QGA_ERROR:' + execute)
        return result['return']

    def verify_boot(self):
        need(self.state() == 'running', 'GUEST_NOT_RUNNING')
        self.unchanged_xml()
        end = time.monotonic() + self.remaining(240)
        while True:
            try:
                self.qga('guest-ping')
                break
            except (RuntimeError, subprocess.TimeoutExpired):
                need(time.monotonic() < end and self.state() == 'running', 'QGA_READY_TIMEOUT')
                time.sleep(1)
        result = self.qga('guest-exec', {'path': '/usr/bin/python3', 'arg': ['-I', '-S', '-c', GUEST_SCRIPT],
                                        'capture-output': True})
        pid = result.get('pid')
        need(type(pid) is int and pid > 0, 'QGA_EXEC_PID')
        self.report.setdefault('guest_readback_pids', []).append(pid)
        evidence = {'pid': pid, 'observed_at': stamp()}
        self.report.setdefault('guest_readbacks', []).append(evidence)
        end = time.monotonic() + self.remaining(45)
        while True:
            status = self.qga('guest-exec-status', {'pid': pid})
            if status.get('exited'):
                break
            need(time.monotonic() < end, 'GUEST_READBACK_TIMEOUT_NO_KILL_NO_RETRY')
            time.sleep(0.5)
        self.report['guest_readback_exit'] = status.get('exitcode')
        evidence['native_status'] = {k: status[k] for k in
                                     ('exited', 'exitcode', 'signal', 'out-truncated', 'err-truncated', 'err-data') if k in status}
        need(status.get('exitcode') == 0 and not status.get('out-truncated') and not status.get('err-truncated'),
             'GUEST_READBACK_EXIT_OR_TRUNCATION')
        raw = base64.b64decode(status.get('out-data', ''), validate=True)
        need(len(raw) < 16384, 'GUEST_READBACK_SIZE')
        evidence['stdout_sha256'] = sha(raw)
        evidence['observation'] = json.loads(raw)
        data = validate_guest(evidence['observation'])
        need(self.state() == 'running', 'GUEST_STOPPED_DURING_READBACK')
        self.unchanged_xml()
        return data

    def checkpoint_restore_boot(self):
        need(self.state() == 'running', 'INITIAL_DOMAIN_NOT_RUNNING')
        self.old_xml = self.unchanged_xml()
        validate_xml(self.virsh('dumpxml', UUID))
        info = self.virsh('dominfo', UUID).decode()
        fields = {k.strip(): v.strip() for k, v in (x.split(':', 1) for x in info.splitlines() if ':' in x)}
        need(fields.get('Managed save') == 'no', 'MANAGED_SAVE_PRESENT_OR_UNKNOWN')
        need(fields.get('Persistent') == 'yes', 'PERSISTENT_DOMAIN_REQUIRED_FOR_RESTART')
        self.report['other_domains_before'] = self.others()
        self.report['guest_before'] = self.verify_boot()
        observed = self.file_meta(DISK)
        need((observed['uid'], observed['gid'], stat.S_IMODE(observed['mode'])) == (64055, 109, 0o640), 'SOURCE_METADATA')
        free = os.statvfs(DISK.parent).f_bavail * os.statvfs(DISK.parent).f_frsize
        need(free >= 3 * observed['size'] + HEADROOM, 'INSUFFICIENT_SPACE')
        self.report['initial_disk_observation'] = observed
        self.report['initial_free_bytes'] = free
        FOLDER.mkdir(mode=0o700)  # Refuse an old/partial operation; never reset it.
        self.checkpoint_dirfd = os.open(FOLDER, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        need(os.fstat(self.checkpoint_dirfd).st_dev == os.fstat(self.disk_dirfd).st_dev, 'CROSS_FILESYSTEM_CHECKPOINT')
        fsync_dir(FOLDER.parent)
        put(FOLDER / 'domain-before.xml', self.old_xml)
        put_json(FOLDER / 'operation-start.json', self.report)
        self.shutdown_requested = True
        self.virsh('shutdown', UUID, '--mode', 'agent')
        self.wait_state('shut off', 180)
        self.off()
        self.source = self.file_meta(DISK)
        need((self.source['dev'], self.source['ino']) == (observed['dev'], observed['ino']), 'SOURCE_REPLACED_DURING_SHUTDOWN')
        # Holding these read-only descriptors prevents inode-number reuse. They
        # belong to this operator, never to QEMU or libvirt's pidfile/lock.
        self.source_fd = self.open_file(DISK)
        self.owned_file(DISK, self.source_fd, (self.source['dev'], self.source['ino']))
        need(cold_metadata_ok(self.source), 'COLD_SOURCE_METADATA')
        free = os.statvfs(DISK.parent).f_bavail * os.statvfs(DISK.parent).f_frsize
        need(free >= 3 * self.source['size'] + HEADROOM, 'COLD_INSUFFICIENT_SPACE')
        self.report['cold_free_bytes'] = free
        self.report['required_free_bytes'] = 3 * self.source['size'] + HEADROOM
        self.report['cold_image_check'] = self.image_check(DISK)
        self.source_hash = self.hash_file(DISK)
        self.report['cold_source'] = {**self.source, 'sha256': self.source_hash}
        self.copy(DISK, BASELINE)
        fd = self.open_file(BASELINE)
        try:
            os.fchown(fd, 0, 0)
            os.fchmod(fd, 0o600)
            os.fsync(fd)
        finally:
            os.close(fd)
        need(self.hash_file(BASELINE) == self.source_hash, 'CHECKPOINT_HASH_MISMATCH')
        self.copy(BASELINE, RESTORED)
        # The protected checkpoint intentionally has root0600 custody. Restore
        # exact original ownership/mode/times/xattrs onto the materialized copy.
        self.run(['/usr/bin/cp', '--attributes-only', '--preserve=all', '--', self.bound_path(DISK), self.bound_path(RESTORED)], 30, True)
        need(self.hash_file(RESTORED) == self.source_hash, 'RESTORED_HASH_MISMATCH')
        need(self.file_xattrs(RESTORED) == self.file_xattrs(DISK), 'RESTORED_XATTRS')
        need(self.file_meta(DISK) == self.source, 'COLD_SOURCE_CHANGED')
        restored_meta = self.file_meta(RESTORED)
        need(all(restored_meta[k] == self.source[k] for k in ('size', 'uid', 'gid', 'mode', 'mtime_ns')), 'RESTORED_METADATA')
        self.restored_inode = (restored_meta['dev'], restored_meta['ino'])
        self.restored_fd = self.open_file(RESTORED)
        self.owned_file(RESTORED, self.restored_fd, self.restored_inode)
        self.report['restored_image_check'] = self.image_check(RESTORED)
        fd = self.open_file(RESTORED)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        fd = self.open_file(BASELINE)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        self.report['xattr_sha256'] = {key: sha(value) for key, value in self.file_xattrs(DISK).items()}
        self.report['checkpoint'] = {**self.file_meta(BASELINE), 'path': str(BASELINE), 'sha256': self.source_hash}
        self.report['restored_before_boot'] = {**restored_meta, 'sha256': self.source_hash}
        self.off()
        need(self.file_meta(DISK) == self.source, 'SOURCE_CHANGED_BEFORE_RENAME')
        put_json(FOLDER / 'ready-to-restore.json', self.report)
        self.move(DISK, ORIGINAL)
        self.move(RESTORED, DISK)
        self.report['restored_file_committed'] = True
        self.off()
        self.owned_file(DISK, self.restored_fd, self.restored_inode)
        put_json(FOLDER / 'restored-committed.json', {'at': stamp(), 'disk': self.file_meta(DISK), 'sha256_before_boot': self.source_hash,
                                                  'original_preserved': str(ORIGINAL)})
        self.virsh('start', UUID)
        self.wait_state('running', 60)
        self.report['guest_after'] = self.verify_boot()
        after_xml = self.unchanged_xml()
        put(FOLDER / 'domain-after.xml', after_xml)
        self.report['xml_after_sha256'] = sha(after_xml)
        self.report['other_domains_after'] = self.others()
        need(self.report['other_domains_after'] == self.report['other_domains_before'], 'OTHER_DOMAIN_CHANGED')
        self.report['state'] = 'PASS_COLD_RESTORE_AND_BASELINE_BOOT'

    def recover(self):
        """Only our own known files, only while OFF. Never stop a running guest."""
        if not self.shutdown_requested:
            return
        self.deadline = time.monotonic() + 300  # Separate finite recovery allowance.
        recovery = self.report['recovery'] = {'forced_shutdown': False, 'boot_attempted': False}
        current = self.state()
        recovery['initial_state'] = current
        if current != 'shut off' or self.source is None or self.source_hash is None:
            recovery['action'] = 'PRESERVE_STATE_NO_DISK_MUTATION'
            return
        self.off()
        if ORIGINAL.exists():
            self.owned_file(ORIGINAL, self.source_fd, (self.source['dev'], self.source['ino']))
            need(identity(self.file_meta(ORIGINAL)) == identity(self.source), 'RECOVERY_ORIGINAL_IDENTITY')
            need(self.hash_file(ORIGINAL) == self.source_hash, 'RECOVERY_ORIGINAL_HASH')
            if DISK.exists() or DISK.is_symlink():
                m = self.file_meta(DISK)
                need((m['dev'], m['ino']) == self.restored_inode, 'RECOVERY_UNKNOWN_CURRENT_DISK')
                self.owned_file(DISK, self.restored_fd, self.restored_inode)
                self.off()
                self.move(DISK, FAILED)
            self.off()
            self.move(ORIGINAL, DISK)
            recovery['action'] = 'ORIGINAL_DISK_RESTORED'
        else:
            self.owned_file(DISK, self.source_fd, (self.source['dev'], self.source['ino']))
            need(identity(self.file_meta(DISK)) == identity(self.source), 'RECOVERY_SOURCE_IDENTITY')
            need(self.hash_file(DISK) == self.source_hash, 'RECOVERY_SOURCE_HASH')
            recovery['action'] = 'ORIGINAL_DISK_UNCHANGED'
        self.off()
        recovery['boot_attempted'] = True
        self.virsh('start', UUID)
        self.wait_state('running', 60)
        recovery['guest_readback'] = self.verify_boot()
        recovery['original_boot_verified'] = True


def entry():
    need(len(sys.argv) == 2 and sys.argv[1] in ACTIONS, 'EXACT_ACTION_REQUIRED')
    need(os.geteuid() == 0 and sys.flags.isolated and sys.flags.no_site, 'ROOT_ISOLATED_NO_SITE_REQUIRED')
    need(os.uname().nodename.split('.')[0] == 'sentinela-b', 'HOST_IDENTITY')
    protected(Path(__file__).absolute().parent)
    s = Path(__file__).lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'SOURCE_CUSTODY')
    protected(FOLDER.parent)
    for path in ('/usr/bin/virsh', '/usr/bin/qemu-img', '/usr/bin/cp'):
        s = Path(path).stat()
        need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and not s.st_mode & 0o022, 'TOOL_CUSTODY')
    os.umask(0o077)
    lock = os.open(FOLDER.parent / 'original-linux-commander-0356-cold-checkpoint.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    op = None
    try:
        s = os.fstat(lock)
        need(stat.S_ISREG(s.st_mode) and s.st_uid == 0 and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600, 'LOCK_CUSTODY')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        op = Operator()
        op.report['action'] = sys.argv[1]
        def interrupted(signum, frame):
            raise RuntimeError('OPERATOR_SIGNAL:' + str(signum))
        signal.signal(signal.SIGTERM, interrupted)
        try:
            op.open_disk_directory()
            if sys.argv[1] == 'checkpoint_restore_boot':
                op.checkpoint_restore_boot()
            else:
                protected(FOLDER)
                op.checkpoint_dirfd = os.open(FOLDER, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                op.old_xml = (FOLDER / 'domain-before.xml').read_bytes()
                validate_xml(op.old_xml)
                op.report['guest_after'] = op.verify_boot()
                op.report['state'] = 'PASS_PINNED_BASELINE_BOOT_VERIFIED'
        except BaseException as error:
            op.report['error'] = repr(error)
            try:
                op.recover()
            except BaseException as recovery_error:
                op.report['recovery_error'] = repr(recovery_error)
        op.report['finished_at'] = stamp()
        if FOLDER.exists():
            protected(FOLDER)
            report_path = FOLDER / ('result-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
            put_json(report_path, op.report)
            op.report['report_path'] = str(report_path)
        print(json.dumps(op.report, sort_keys=True))
        return 0 if op.report['state'].startswith('PASS_') else 2
    finally:
        if op is not None:
            op.close_fds()
        os.close(lock)


if __name__ == '__main__':
    raise SystemExit(entry())
