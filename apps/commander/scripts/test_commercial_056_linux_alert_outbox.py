"""Real private SQLite outbox; synthetic transport, no enrollment or runtime install."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'release-candidates/commercial-0.3.56-source/agent/linux.py'


class RecoveryOutboxTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('alert_agent_056', SOURCE)
        self.a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.a)
        self.tmp = tempfile.TemporaryDirectory(prefix='hara-r163-agent-')
        self.addCleanup(self.tmp.cleanup)
        self.a.DATA_DIR = Path(self.tmp.name)
        self.cfg = {'HARA_COMMANDER_URL': 'https://commander.invalid',
                    'HARA_DEVICE_ID': 'SYNTHETIC-DEVICE', 'HARA_DEVICE_TOKEN': 'synthetic-only-credential'}
        self.outbox = self.a.RecoveryEventOutbox(self.cfg)

    @staticmethod
    def ack(event):
        return {'schema': 'hara.commander.recovery-ingest.v1', 'ack': 'PERSISTED',
                'event_id': 'HARA-REC-' + 'a' * 48, 'client_event_id': event['event_id'],
                'external_delivery_confirmed': False}

    def test_restart_sequence_and_ack_durable_without_delivery_claim(self):
        first = self.outbox.enqueue('executor', 'STALLED')
        self.assertEqual(self.outbox.enqueue('executor', 'STALLED'), first)
        second = self.a.RecoveryEventOutbox(self.cfg).enqueue('executor', 'RECOVERING')
        self.assertEqual(first['client_incident_key'], second['client_incident_key'])
        self.assertEqual(second['transition_seq'], 2)
        seen = []
        def send(url, token, event, timeout):
            self.assertEqual(url, self.cfg['HARA_COMMANDER_URL'] + '/api/device/recovery-events')
            self.assertEqual(token, self.cfg['HARA_DEVICE_TOKEN'])
            seen.append(event)
            return self.ack(event)
        with patch.object(self.a, 'post_json', side_effect=send):
            self.assertEqual(self.outbox.send_once()['state'], 'PERSISTED')
            self.assertEqual(self.a.RecoveryEventOutbox(self.cfg).send_once()['state'], 'PERSISTED')
            self.assertEqual(self.outbox.send_once()['state'], 'EMPTY')
        self.assertEqual(seen, [first, second])
        with sqlite3.connect(self.outbox.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM recovery_events WHERE state='PERSISTED'").fetchone()[0], 2)

    def test_failure_retry_preserves_bytes_and_sequence(self):
        first = self.outbox.enqueue('heartbeat', 'STALLED')
        self.outbox.enqueue('heartbeat', 'RECOVERING')
        sent = []
        def send(url, token, event, timeout):
            sent.append(json.dumps(event, sort_keys=True))
            if len(sent) == 1:
                raise urllib.error.HTTPError(url, 503, 'fixture', None, None)
            return self.ack(event)
        with patch.object(self.a, 'post_json', side_effect=send):
            self.assertEqual(self.outbox.send_once(now_ms=1000)['state'], 'RETRY')
            self.assertEqual(self.outbox.send_once(now_ms=1001)['state'], 'EMPTY')
            self.assertEqual(self.outbox.send_once(now_ms=1000000)['state'], 'PERSISTED')
        self.assertEqual(sent[0], sent[1])
        self.assertEqual(json.loads(sent[1]), first)

    def test_wrong_receipt_or_human_ack_cannot_remove_pending_event(self):
        event = self.outbox.enqueue('executor', 'DEGRADED')
        for bad in [{'ack': 'PORTAL_ACKNOWLEDGED'},
                    {**self.ack(event), 'client_event_id': 'b' * 32},
                    {**self.ack(event), 'external_delivery_confirmed': True},
                    {**self.ack(event), 'event_id': 'invented'}]:
            with patch.object(self.a, 'post_json', return_value=bad):
                result = self.outbox.send_once(now_ms=1000000 * (len(str(bad)) + 1))
                self.assertNotEqual(result['state'], 'PERSISTED')
        with patch.object(self.a, 'post_json', side_effect=lambda u, t, e, timeout: self.ack(e)):
            self.assertEqual(self.outbox.send_once(now_ms=10**12)['state'], 'PERSISTED')

    def test_stop_and_revocation_cannot_send_or_recover_automatically(self):
        self.outbox.enqueue('heartbeat', 'STALLED')
        with patch.object(self.a, 'post_json') as send:
            self.assertEqual(self.outbox.send_once(authorized=False)['state'], 'PAUSED')
            send.assert_not_called()
        with patch.object(self.a, 'post_json', side_effect=urllib.error.HTTPError('https://commander.invalid', 403, 'fixture', None, None)):
            self.assertEqual(self.outbox.send_once()['state'], 'REVOKED')
        with patch.object(self.a, 'post_json') as send:
            self.assertEqual(self.a.RecoveryEventOutbox(self.cfg).send_once()['state'], 'REVOKED')
            send.assert_not_called()

    def test_outbox_is_separate_from_tool_journal_and_has_no_credential_bytes(self):
        scope = self.outbox.path.parent
        db = sqlite3.connect(scope / 'operations.sqlite3')
        self.addCleanup(db.close)
        db.execute('CREATE TABLE fixture(n)')
        db.execute('BEGIN EXCLUSIVE')
        event = self.outbox.enqueue('executor', 'STALLED')
        self.assertEqual(event['detector'], 'LINUX_PROCESS_GUARDIAN')
        self.assertEqual(set(event), {'schema', 'event_id', 'client_incident_key', 'transition_seq',
                                    'worker', 'state', 'observed_at_utc', 'detector'})
        self.assertNotIn(self.cfg['HARA_DEVICE_TOKEN'].encode(), self.outbox.path.read_bytes())
        self.assertEqual(self.outbox.path.stat().st_mode & 0o777, 0o600)
        other = self.a.RecoveryEventOutbox({**self.cfg, 'HARA_DEVICE_TOKEN': 'other-synthetic'})
        self.assertNotEqual(other.path, self.outbox.path)
        with patch.object(self.a, 'post_json') as send:
            self.assertEqual(other.send_once()['state'], 'EMPTY')
            send.assert_not_called()

    def test_next_failure_after_recovery_has_new_incident(self):
        first = self.outbox.enqueue('executor', 'STALLED')
        self.outbox.enqueue('executor', 'RECOVERING')
        self.outbox.enqueue('executor', 'RECOVERED')
        next_event = self.outbox.enqueue('executor', 'STALLED')
        self.assertNotEqual(first['client_incident_key'], next_event['client_incident_key'])
        self.assertEqual(next_event['transition_seq'], 1)

    def test_guardian_retries_busy_storage_before_later_transition(self):
        sink = self.outbox
        guard = self.a.RelaySupervisor(self.cfg, report=lambda event: None, recovery_outbox=sink)
        with patch.object(sink, 'enqueue', side_effect=sqlite3.OperationalError('locked')):
            guard._event('executor', 'STALLED', 1)
        guard._event('executor', 'RECOVERING', 2)
        with sink._connect() as db:
            rows = db.execute('SELECT body FROM recovery_events ORDER BY sequence').fetchall()
        self.assertEqual([json.loads(row['body'])['state'] for row in rows], ['STALLED', 'RECOVERING'])

    def test_spawned_worker_uses_enrollment_journal_before_target(self):
        observed = []
        channel = unittest.mock.Mock()
        target = lambda config, pipe: observed.append(self.a.OPERATIONS_DB_FILE)
        with patch.object(self.a.os, 'setsid'), patch.object(self.a.signal, 'signal'), patch.object(self.a, 'cleanup_process_sessions'):
            self.a._relay_worker_entry(target, self.cfg, channel)
        self.assertEqual(observed, [self.outbox.path.parent / 'operations.sqlite3'])


if __name__ == '__main__':
    unittest.main()
