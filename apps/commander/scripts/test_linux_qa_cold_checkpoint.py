#!/usr/bin/env python3
"""Directed local tests; never opens libvirt or launches a guest process."""
from pathlib import Path
import errno
import hashlib
import importlib.util
import os
import tempfile
import unittest
from unittest import mock

SOURCE = Path(__file__).with_name('linux_qa_cold_checkpoint.py')
spec = importlib.util.spec_from_file_location('cold_checkpoint', SOURCE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def guest():
    return {'machine_id': m.MACHINE_ID,
            'account': {'uid': 2000, 'name': 'commanderqa', 'home': '/home/commanderqa'},
            'files': {path: {'sha256': pin} for path, pin in m.PINS.items()}}


def xml():
    return f'''<domain type="kvm"><name>{m.NAME}</name><uuid>{m.UUID}</uuid>
    <os><type>hvm</type></os><devices><emulator>/usr/bin/qemu-system-x86_64</emulator>
    <disk type="file" device="disk"><driver type="qcow2"/><source file="{m.DISK}"/></disk>
    <interface type="network"><source network="hara-review-isolated"/></interface>
    <interface type="network"><source network="hara-review-egress"/></interface>
    </devices></domain>'''.encode()


class ScopeTests(unittest.TestCase):
    def test_cold_owner_can_be_restored_by_libvirt(self):
        for uid, gid, mode in ((64055, 109, 0o640), (0, 0, 0o600), (0, 109, 0o640), (64055, 0, 0o644)):
            self.assertTrue(m.cold_metadata_ok({'uid': uid, 'gid': gid, 'mode': 0o100000 | mode}))
        for uid, gid, mode in ((1002, 109, 0o640), (0, 1002, 0o640), (64055, 109, 0o660),
                               (64055, 109, 0o642), (0, 0, 0o4600), (0, 0, 0o700)):
            self.assertFalse(m.cold_metadata_ok({'uid': uid, 'gid': gid, 'mode': 0o100000 | mode}))

    def test_exact_original_domain_and_storage(self):
        raw = xml()
        self.assertEqual(m.validate_xml(raw), hashlib.sha256(raw).hexdigest())
        for old, new in ((m.UUID, '9ee73ce0-80a9-4b20-93e3-026b6294d660'),
                         (m.NAME, 'some-other-vm'),
                         ('/usr/bin/qemu-system-x86_64', '/usr/lib/libvirt/hara-qa-qemu-confined-r9'),
                         (str(m.DISK), '/tmp/disk.qcow2'),
                         ('hara-review-egress', 'default')):
            with self.subTest(new=new), self.assertRaises(RuntimeError):
                m.validate_xml(raw.replace(old.encode(), new.encode()))

    def test_external_writable_state_requires_own_backup(self):
        for addition in (b'<tpm/>', b'<filesystem/>', b'<hostdev/>',
                         b'<disk type="file" device="disk"><source file="/other"/></disk>'):
            with self.subTest(addition=addition), self.assertRaises(RuntimeError):
                m.validate_xml(xml().replace(b'</devices>', addition + b'</devices>'))
        with self.assertRaises(RuntimeError):
            m.validate_xml(xml().replace(b'</os>', b'<nvram>/vars</nvram></os>'))

    def test_baseline_requires_every_pin_and_identity(self):
        self.assertEqual(m.validate_guest(guest()), guest())
        for path in m.PINS:
            bad = guest()
            bad['files'][path]['sha256'] = '0' * 64
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                m.validate_guest(bad)
        bad = guest()
        bad['machine_id'] = '0' * 32
        with self.assertRaises(RuntimeError):
            m.validate_guest(bad)
        bad = guest()
        bad['account']['uid'] = 0
        with self.assertRaises(RuntimeError):
            m.validate_guest(bad)

    def test_guest_script_is_compileable_and_contains_no_mutation(self):
        compile(m.GUEST_SCRIPT, '<fixed-read-only-guest>', 'exec')
        for token in ('subprocess', 'os.system', 'os.unlink', 'os.remove', 'chmod(', 'chown(', 'O_WRONLY', 'O_RDWR'):
            self.assertNotIn(token, m.GUEST_SCRIPT)
        self.assertEqual(m.ACTIONS, ('checkpoint_restore_boot', 'verify_boot'))


class FilesTests(unittest.TestCase):
    def test_bound_directories_drive_copy_hash_xattrs_and_cross_directory_rename(self):
        with tempfile.TemporaryDirectory() as temp:
            lab, protected = Path(temp) / 'lab', Path(temp) / 'protected'
            lab.mkdir(mode=0o770)
            protected.mkdir(mode=0o700)
            disk, baseline, original = lab / 'root.qcow2', protected / 'baseline', protected / 'original'
            disk.write_bytes(b'cold source via directory fd')
            os.setxattr(disk, 'user.hara_qa_test', b'bound metadata')
            with mock.patch.multiple(m, DISK=disk, FOLDER=protected), mock.patch.object(m, 'protected'):
                op = m.Operator()
                op.disk_dirfd = os.open(lab, os.O_RDONLY | os.O_DIRECTORY)
                op.checkpoint_dirfd = os.open(protected, os.O_RDONLY | os.O_DIRECTORY)
                op.off = mock.Mock()
                try:
                    self.assertIn('/proc/self/fd/', op.bound_path(disk))
                    op.copy(disk, baseline)
                    self.assertEqual(op.hash_file(disk), op.hash_file(baseline))
                    self.assertEqual(op.file_xattrs(disk), op.file_xattrs(baseline))
                    op.move(disk, original)
                    self.assertFalse(disk.exists())
                    op.move(baseline, disk)
                    self.assertEqual(disk.read_bytes(), original.read_bytes())
                    with self.assertRaises(OSError):
                        op.move(original, disk)
                    self.assertEqual(disk.read_bytes(), original.read_bytes())
                finally:
                    op.close_fds()

    def test_sparse_materialization_and_original_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            source, baseline, restored = (Path(temp) / name for name in ('source', 'baseline', 'restored'))
            with source.open('wb') as handle:
                handle.write(b'header')
                handle.seek(2 * 1024**2)
                handle.write(b'tail')
            source.chmod(0o640)
            os.utime(source, ns=(1700000000000000000, 1700000000000000000))
            os.setxattr(source, 'user.hara_qa_test', b'metadata')
            op = m.Operator()
            op.off = mock.Mock()
            op.copy(source, baseline)
            baseline.chmod(0o600)
            op.copy(baseline, restored)
            op.run(['/usr/bin/cp', '--attributes-only', '--preserve=all', '--', str(source), str(restored)])
            self.assertEqual(op.hash_file(source), op.hash_file(baseline))
            self.assertEqual(op.hash_file(source), op.hash_file(restored))
            self.assertEqual(restored.stat().st_mode & 0o777, 0o640)
            self.assertEqual(restored.stat().st_mtime_ns, source.stat().st_mtime_ns)
            self.assertEqual(m.xattrs(restored), m.xattrs(source))
            self.assertLess(restored.stat().st_blocks * 512, restored.stat().st_size)
            self.assertEqual(op.off.call_count, 4)

    def test_rename_noreplace_preserves_existing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'source', Path(temp) / 'target'
            a.write_bytes(b'original')
            b.write_bytes(b'other')
            with self.assertRaises(OSError) as context:
                m.rename_noreplace(a, b)
            self.assertEqual(context.exception.errno, errno.EEXIST)
            self.assertEqual(a.read_bytes(), b'original')
            self.assertEqual(b.read_bytes(), b'other')
            b.unlink()
            m.rename_noreplace(a, b)
            self.assertFalse(a.exists())
            self.assertEqual(b.read_bytes(), b'original')

    def test_hash_refuses_symlink_and_shared_inode(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'source', Path(temp) / 'alias'
            a.write_bytes(b'checkpoint')
            op = m.Operator()
            self.assertEqual(op.hash_file(a), hashlib.sha256(b'checkpoint').hexdigest())
            b.symlink_to(a)
            with self.assertRaises(RuntimeError):
                op.hash_file(b)
            b.unlink()
            os.link(a, b)
            with self.assertRaises(RuntimeError):
                op.hash_file(a)

    def test_hash_rejects_change_during_read(self):
        with tempfile.TemporaryDirectory() as temp:
            a = Path(temp) / 'source'
            a.write_bytes(b'checkpoint')
            original_read = os.read
            changed = False
            def reading(fd, size):
                nonlocal changed
                value = original_read(fd, size)
                if value and not changed:
                    changed = True
                    with a.open('ab') as handle:
                        handle.write(b' changed')
                return value
            with mock.patch.object(m.os, 'read', reading), self.assertRaisesRegex(RuntimeError, 'FILE_CHANGED'):
                m.Operator().hash_file(a)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.folder = root / 'checkpoint'
        self.folder.mkdir()
        self.disk = root / 'root.qcow2'
        self.original = self.folder / 'original-before-056.qcow2'
        self.restored = self.folder / 'restored-ready.qcow2'
        self.failed = self.folder / 'restored-failed.qcow2'
        self.patch = mock.patch.multiple(m, DISK=self.disk, ORIGINAL=self.original,
                                        RESTORED=self.restored, FAILED=self.failed)
        self.patch.start()
        self.disk.write_bytes(b'exact cold original')
        self.op = m.Operator()
        self.op.source = m.meta(self.disk)
        self.op.source_hash = self.op.hash_file(self.disk)
        self.op.source_fd = os.open(self.disk, os.O_RDONLY | os.O_NOFOLLOW)
        self.op.shutdown_requested = True
        self.events = []
        self.op.state = lambda: 'shut off'
        self.op.off = lambda: self.events.append('off-confirmed')
        self.op.virsh = lambda *args: self.events.append(args)
        self.op.wait_state = lambda *args: self.events.append(('wait', *args))
        self.op.verify_boot = lambda: guest()

    def tearDown(self):
        self.op.close_fds()
        self.patch.stop()
        self.temp.cleanup()

    def swapped(self):
        self.restored.write_bytes(b'copy subsequently modified by failed boot')
        r = m.meta(self.restored)
        self.op.restored_inode = (r['dev'], r['ino'])
        self.op.restored_fd = os.open(self.restored, os.O_RDONLY | os.O_NOFOLLOW)
        m.rename_noreplace(self.disk, self.original)
        m.rename_noreplace(self.restored, self.disk)

    def assert_started_only_target(self):
        commands = [x for x in self.events if isinstance(x, tuple) and x[0] != 'wait']
        self.assertEqual(commands, [('start', m.UUID)])
        self.assertTrue(self.op.report['recovery']['original_boot_verified'])

    def test_copy_failure_before_rename_boots_verified_original(self):
        self.op.recover()
        self.assertEqual(self.disk.read_bytes(), b'exact cold original')
        self.assertEqual(self.op.report['recovery']['action'], 'ORIGINAL_DISK_UNCHANGED')
        self.assert_started_only_target()

    def test_failure_between_renames_restores_original(self):
        m.rename_noreplace(self.disk, self.original)
        self.op.recover()
        self.assertEqual(self.disk.read_bytes(), b'exact cold original')
        self.assertFalse(self.original.exists())
        self.assert_started_only_target()

    def test_known_replacement_preserved_then_original_restored(self):
        self.swapped()
        self.op.recover()
        self.assertEqual(self.disk.read_bytes(), b'exact cold original')
        self.assertEqual(self.failed.read_bytes(), b'copy subsequently modified by failed boot')
        self.assert_started_only_target()

    def test_running_guest_is_never_stopped_or_modified(self):
        self.swapped()
        before = self.disk.read_bytes()
        self.op.state = lambda: 'running'
        self.op.recover()
        self.assertEqual(self.disk.read_bytes(), before)
        self.assertTrue(self.original.exists())
        self.assertEqual(self.events, [])
        self.assertFalse(self.op.report['recovery']['boot_attempted'])

    def test_unknown_current_file_is_never_overwritten(self):
        self.swapped()
        self.disk.unlink()
        self.disk.write_bytes(b'foreign inode')
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY_UNKNOWN_CURRENT_DISK'):
            self.op.recover()
        self.assertEqual(self.disk.read_bytes(), b'foreign inode')
        self.assertTrue(self.original.exists())
        self.assertFalse(self.failed.exists())

    def test_changed_original_is_not_restored(self):
        self.swapped()
        self.original.write_bytes(b'corrupted original')
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY_ORIGINAL_IDENTITY'):
            self.op.recover()
        self.assertTrue(self.original.exists())
        self.assertEqual(self.disk.read_bytes(), b'copy subsequently modified by failed boot')

    def test_original_hash_is_mandatory_even_with_metadata_match(self):
        self.swapped()
        self.op.source_hash = '0' * 64
        with self.assertRaisesRegex(RuntimeError, 'RECOVERY_ORIGINAL_HASH'):
            self.op.recover()
        self.assertTrue(self.original.exists())
        self.assertFalse(self.failed.exists())

    def test_unknown_or_unverified_source_is_preserved(self):
        self.op.source_hash = None
        self.op.recover()
        self.assertEqual(self.events, [])
        self.assertFalse(self.op.report['recovery']['boot_attempted'])
        self.assertEqual(self.disk.read_bytes(), b'exact cold original')

    def test_symlink_at_canonical_disk_is_refused(self):
        self.swapped()
        self.disk.unlink()
        self.disk.symlink_to(self.original)
        with self.assertRaisesRegex(RuntimeError, 'NOT_SINGLE_REGULAR'):
            self.op.recover()
        self.assertTrue(self.disk.is_symlink())
        self.assertTrue(self.original.exists())

    def test_existing_failed_artifact_is_not_overwritten(self):
        self.swapped()
        self.failed.write_bytes(b'prior evidence')
        with self.assertRaises(OSError):
            self.op.recover()
        self.assertEqual(self.failed.read_bytes(), b'prior evidence')
        self.assertTrue(self.original.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
