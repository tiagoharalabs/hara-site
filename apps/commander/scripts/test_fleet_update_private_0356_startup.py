"""Directed, synthetic tests for the systemd Type=simple pre-exec read race.

No service, subprocess, Agent, native credential, or operational record is used.
"""
import datetime
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location(
    'fleet_startup_under_test', HERE / 'fleet_update_private_0356.py')
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        if seconds < 0:
            raise AssertionError('negative sleep')
        self.sleeps.append(seconds)
        self.now += seconds


def inactive(present=True):
    return {'present': present, 'active': False,
            'enabled': 'disabled' if present else 'not-found',
            'pid': 0, 'dropins': []}


class StartupRaceTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.op = S.Migration.__new__(S.Migration)
        self.op.deadline = self.clock.now + 100
        self.op.agent = Path('/synthetic-owner/.local/share/hara-commander/hara-commander-agent')
        self.op.status = Path('/synthetic-owner/runtime-status.json')
        self.op.stage = Path('/synthetic-private-stage')
        self.row = {'present': True, 'active': True, 'enabled': 'disabled',
                    'pid': 12345, 'birth_ticks': 67890, 'dropins': [],
                    'agent_path': str(self.op.agent), 'agent_sha256': S.AGENT_SHA}
        self.since = 1700000000.0
        started = datetime.datetime.fromtimestamp(
            self.since, datetime.timezone.utc).isoformat()
        self.status = json.dumps({'agent_version': '0.3.56',
            'started_at_utc': started,
            'last_successful_heartbeat_at_utc': started}).encode()
        self.addCleanup(patch.stopall)
        patch.object(S.time, 'monotonic', self.clock.monotonic).start()
        patch.object(S.time, 'sleep', self.clock.sleep).start()
        patch.object(S, 'read', return_value=self.status).start()

    def pre_exec(self):
        return RuntimeError('ACTIVE_AGENT_CMDLINE:' + S.STD)

    def test_health_retries_pre_exec_then_validates_real_identity_and_heartbeat(self):
        observations = [self.pre_exec(), self.row, self.row]

        def unit(name, limit=30):
            if name == S.V2:
                return inactive()
            value = observations.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        self.op.unit = Mock(side_effect=unit)
        result = self.op.health('previous-synthetic-start', self.since)
        self.assertEqual(result['pid'], self.row['pid'])
        self.assertEqual(result['agent_sha256'], S.AGENT_SHA)
        self.assertEqual(result['external_commander_e2e'], 'PENDING_OPERATOR_READBACK')
        self.assertEqual(observations, [])
        self.assertTrue(any(0 < value < 1 for value in self.clock.sleeps))

    def test_health_never_accepts_wrong_path_or_hash(self):
        for field, wrong in (('agent_path', '/synthetic-owner/wrong/linux.py'),
                             ('agent_sha256', '0' * 64)):
            with self.subTest(field=field):
                row = {**self.row, field: wrong}
                self.op.unit = Mock(side_effect=lambda name, **_kwargs: row if name == S.STD else inactive())
                with self.assertRaisesRegex(RuntimeError, '^WRONG_RUNTIME_AGENT$'):
                    self.op.health(None, self.since)
                self.assertEqual(self.clock.sleeps, [])

    def test_health_rechecks_identity_during_stability_observation(self):
        changed = {**self.row, 'agent_sha256': '0' * 64}
        observations = [self.row, changed]
        self.op.unit = Mock(side_effect=lambda name, **_kwargs: observations.pop(0)
                            if name == S.STD else inactive())
        with self.assertRaisesRegex(RuntimeError, '^RUNTIME_NOT_STABLE$'):
            self.op.health(None, self.since)

    def test_other_unit_errors_are_not_retried(self):
        self.op.unit = Mock(side_effect=RuntimeError('ACTIVE_AGENT_OUTSIDE_HOME'))
        with self.assertRaisesRegex(RuntimeError, '^ACTIVE_AGENT_OUTSIDE_HOME$'):
            self.op.health(None, self.since)
        self.assertEqual(self.op.unit.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])

    def test_pre_exec_retry_obeys_existing_deadline(self):
        self.op.deadline = self.clock.now + 0.25
        self.op.unit = Mock(side_effect=self.pre_exec())
        with self.assertRaisesRegex(RuntimeError, '^POST_START_CMDLINE_TIMEOUT:' + S.STD + '$'):
            self.op.health(None, self.since)
        self.assertGreater(self.op.unit.call_count, 1)
        self.assertLessEqual(self.clock.now, 100.25)

    def test_inventory_keeps_pre_exec_failure_strict(self):
        self.op.unit = Mock(side_effect=self.pre_exec())
        with patch.object(S, 'read', return_value=b'fixture'), \
             patch.object(S, 'INSTALLER_SHA', S.sha(b'fixture')), \
             patch.object(S, 'CA_SHA', S.sha(b'fixture')):
            with self.assertRaisesRegex(RuntimeError, '^ACTIVE_AGENT_CMDLINE:' + S.STD + '$'):
                self.op.inventory('storage')
        self.assertEqual(self.op.unit.call_count, 1)
        self.assertEqual(self.clock.sleeps, [])

    def rollback_setup(self, wrong=False):
        old_row = {**self.row, 'agent_path': '/synthetic-owner/legacy/linux.py',
                   'agent_sha256': '1' * 64, 'enabled': 'enabled'}
        old = {'units': {S.STD: old_row, S.V2: inactive(False)},
               'configuration': {'sha256': 'synthetic-configuration'}}
        self.op.paths = {name: Path('/synthetic-owner') / name
                        for name in ('agent', 'rollback', 'cli', 'hara', 'migration_dropin')}
        self.op.drop_dir_created = False
        self.op.report = {}
        self.op.progress = Mock()
        self.op.stop_all = Mock()
        self.op.restore = Mock()
        self.op.ctl = Mock(return_value=(0, b'', b''))
        self.op.configuration = Mock(return_value=old['configuration'])
        row = {**old_row, 'pid': 54321, 'birth_ticks': 98765}
        if wrong:
            row['agent_sha256'] = '0' * 64
        observations = [self.pre_exec(), row]

        def unit(name, limit=30):
            if name == S.V2:
                return inactive(False)
            value = observations.pop(0)
            if isinstance(value, Exception):
                raise value
            return value

        self.op.unit = Mock(side_effect=unit)
        return old

    def test_rollback_retries_post_start_readback_and_verifies_original_binary(self):
        old = self.rollback_setup()
        self.op.rollback(old)
        result = self.op.report['rollback']
        self.assertEqual(result['state'], 'PASS_FILES_UNITS_ACTIVE_BINARY_RESTORED')
        self.assertEqual(result['units'][S.STD]['agent_sha256'], '1' * 64)
        self.assertEqual(result['fresh_remote_operation'], 'NOT_CLAIMED')
        self.op.stop_all.assert_called_once_with(old)
        self.op.ctl.assert_any_call('start', S.STD, limit=45)

    def test_rollback_still_refuses_wrong_original_binary_after_retry(self):
        old = self.rollback_setup(wrong=True)
        with self.assertRaisesRegex(RuntimeError, '^ROLLBACK_ACTIVE_BINARY$'):
            self.op.rollback(old)
        self.assertNotIn('rollback', self.op.report)


if __name__ == '__main__':
    unittest.main(verbosity=2)
