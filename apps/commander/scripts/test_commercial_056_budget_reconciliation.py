"""Real SQLite/filesystem regressions for relay budget recovery; synthetic state only."""
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
import multiprocessing
import signal
import threading
import urllib.error
from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SOURCE = (Path(__file__).resolve().parents[1] /
          'release-candidates/commercial-0.3.56-source/agent/linux.py')


def _synthetic_network_reply(url, token, body, **kwargs):
    if url.endswith('/calls/complete'):
        return {'ok': True, 'call_id': body['call_id'], 'state': body['state']}
    return {'ok': True}


def _effect_then_wait_before_checkpoint(root, config, lease, call, channel):
    """Disposable fault-injection child; no daemon, network, or real enrollment."""
    root = Path(root)
    spec = importlib.util.spec_from_file_location('budget_crash_child_056', SOURCE)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    agent.DATA_DIR = root / 'data'
    agent.CONFIG_FILE = root / 'config' / 'device.env'
    agent.STATUS_FILE = root / 'runtime-status.json'
    agent.SESSION_FILE = root / 'operator-session.json'
    agent.configure_enrollment_state(config)

    def wait_before_checkpoint(*args, **kwargs):
        channel.send({'phase': 'EFFECT_DONE_BEFORE_CHECKPOINT',
                      'content': Path(call['payload']['path']).read_text()})
        while True:
            signal.pause()

    with patch.object(agent, '_active_verified_product_lease', return_value=lease), \
         patch.object(agent, 'post_json', side_effect=_synthetic_network_reply), \
         patch.object(agent, '_relay_completion', side_effect=wait_before_checkpoint):
        agent.execute_call(config, call)


class RelayBudgetReconciliationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hara-056-budget-reconciliation-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = {
            'HARA_COMMANDER_URL': 'https://commander.invalid',
            'HARA_DEVICE_ID': 'synthetic-review-device',
            'HARA_TENANT_ID': 'synthetic-review-tenant',
            'HARA_DEVICE_TOKEN': 'synthetic-not-a-credential',
            'HARA_DEVICE_ARCH': 'synthetic-test',
            'HARA_COMMANDER_APPROVAL_MODE': 'PERSISTENT_TRUSTED',
            'HARA_COMMANDER_TRANSPORT_MODE': 'OUTBOUND_RELAY',
        }
        self.lease = {
            'usage_mode': 'LOCAL_BUDGET', 'tenant_id': 'synthetic-review-tenant',
            'device_id': 'synthetic-review-device', 'entitlement_id': 'synthetic-entitlement',
            'plan_code': 'SYNTHETIC_QA', 'meter_id': 'synthetic-meter',
        }
        self.agent = self.import_agent()
        now = datetime.now(timezone.utc)
        with self.agent._ops_connect() as conn:
            conn.execute(
                '''INSERT INTO local_budget_blocks
                   (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,
                    period_key,allocated_units,lease_token,issued_at_utc,expires_at_utc,state)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,'ACTIVE')''',
                ('synthetic-block', self.lease['tenant_id'], self.lease['device_id'],
                 self.lease['entitlement_id'], self.lease['plan_code'], self.lease['meter_id'],
                 'synthetic-period', 100, 'synthetic-lease-not-a-credential', now.isoformat(),
                 (now + timedelta(days=1)).isoformat()),
            )
            conn.commit()

    def import_agent(self):
        spec = importlib.util.spec_from_file_location('budget_reconciliation_056', SOURCE)
        agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(agent)
        agent.DATA_DIR = self.root / 'data'
        agent.CONFIG_FILE = self.root / 'config' / 'device.env'
        agent.STATUS_FILE = self.root / 'runtime-status.json'
        agent.SESSION_FILE = self.root / 'operator-session.json'
        agent.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        agent.CONFIG_FILE.write_text(''.join(k + '=' + v + '\n' for k, v in self.config.items()))
        agent.configure_enrollment_state(self.config)
        verify = patch.object(agent, '_active_verified_product_lease', return_value=self.lease)
        verify.start()
        self.addCleanup(verify.stop)
        network = patch.object(agent, 'post_json', side_effect=_synthetic_network_reply)
        agent.synthetic_network = network.start()
        self.addCleanup(network.stop)
        return agent

    def call(self, suffix='one', *, metered=True):
        return {
            'call_id': 'synthetic-call-' + suffix,
            'request_id': 'synthetic-request-' + suffix,
            'tool_id': 'hara.files.write',
            'payload': {'path': str(self.root / ('effect-' + suffix + '.txt')),
                        'content': 'synthetic-effect-' + suffix, 'mode': 'rewrite'},
            'usage': ({'mode': 'LOCAL_BUDGET', 'units': 2, 'period_key': 'synthetic-period',
                       'budget_id': 'synthetic-block'} if metered else {'mode': 'UNMETERED'}),
        }

    def debit(self, call, agent=None):
        with (agent or self.agent)._ops_connect() as conn:
            row = conn.execute(
                'SELECT state,units FROM local_budget_debits WHERE request_id=?',
                (call['request_id'],),
            ).fetchone()
            return None if row is None else (str(row['state']), int(row['units']))

    def counts(self, agent=None):
        with (agent or self.agent)._ops_connect() as conn:
            return (agent or self.agent)._budget_counts(conn, 'synthetic-block')

    def refuse_replay(self, agent, call):
        with self.assertRaisesRegex(ValueError, 'CALL_REPLAY_REFUSED|CALL_IDEMPOTENCY_CONFLICT'):
            agent.execute_call(self.config, copy.deepcopy(call))

    def test_completed_effect_with_commit_io_failure_does_not_refund_or_report_denial(self):
        call = self.call('commit-failure')
        with patch.object(self.agent, 'local_budget_commit',
                          side_effect=sqlite3.OperationalError('synthetic disk failure')):
            try:
                self.agent.execute_call(self.config, copy.deepcopy(call))
            except sqlite3.OperationalError:
                pass
        self.assertEqual(Path(call['payload']['path']).read_text(), call['payload']['content'])
        self.assertEqual(self.debit(call), ('RESERVED', 2))
        completions = [c.args[2] for c in self.agent.synthetic_network.call_args_list
                       if c.args[0].endswith('/calls/complete')]
        self.assertFalse(any(body['state'] == 'FAILED' for body in completions), completions)
        restarted = self.import_agent()
        restarted.reconcile_relay_calls()
        self.assertEqual(self.debit(call, restarted), ('COMMITTED', 2))
        self.assertEqual(self.counts(restarted), (2, 0))
        self.refuse_replay(restarted, call)
        self.assertEqual(Path(call['payload']['path']).read_text(), call['payload']['content'])

    def test_unmetered_request_cannot_repeat_filesystem_effect_after_restart(self):
        call = self.call('unmetered', metered=False)
        self.agent.execute_call(self.config, copy.deepcopy(call))
        target = Path(call['payload']['path'])
        target.write_text('independent-later-content')
        restarted = self.import_agent()
        self.refuse_replay(restarted, call)
        self.assertEqual(target.read_text(), 'independent-later-content')
        self.assertIsNone(self.debit(call, restarted))

    def test_executed_checkpoint_commits_once_after_restart_without_repeating_effect(self):
        call = self.call('executed')
        self.agent.relay_call_begin(call)
        self.agent.local_budget_reserve(self.config, call)
        self.agent.relay_call_phase(call, 'EXECUTING')
        executable = copy.deepcopy(call)
        executable['_transport'] = 'OUTBOUND_RELAY'
        executable['_local_approval'] = self.agent.request_local_approval(executable)
        result = self.agent.execute_tool(self.config, executable)
        self.agent.relay_call_phase(call, 'EXECUTED', receipt_sha=result['bridge_receipt_sha256'])
        target = Path(call['payload']['path'])
        target.write_text('independent-later-content')
        restarted = self.import_agent()
        restarted.reconcile_relay_calls()
        restarted.reconcile_relay_calls()
        self.assertEqual(self.debit(call, restarted), ('COMMITTED', 2))
        self.assertEqual(self.counts(restarted), (2, 0))
        self.assertEqual(target.read_text(), 'independent-later-content')
        self.refuse_replay(restarted, call)

    def test_pre_execution_reservation_is_released_after_restart(self):
        for phase in ('PREPARING', 'RESERVED'):
            with self.subTest(phase=phase):
                call = self.call('before-' + phase.lower())
                self.agent.relay_call_begin(call)
                self.agent.local_budget_reserve(self.config, call)
                if phase == 'RESERVED':
                    self.agent.relay_call_phase(call, phase)
                restarted = self.import_agent()
                restarted.reconcile_relay_calls()
                self.assertEqual(self.debit(call, restarted), ('RELEASED', 2))
                self.assertFalse(Path(call['payload']['path']).exists())
                self.refuse_replay(restarted, call)
        self.assertEqual(self.counts(), (0, 0))

    def test_uncertain_execution_keeps_reservation_and_refuses_replay(self):
        call = self.call('uncertain')
        self.agent.relay_call_begin(call)
        self.agent.local_budget_reserve(self.config, call)
        self.agent.relay_call_phase(call, 'EXECUTING')
        restarted = self.import_agent()
        restarted.reconcile_relay_calls()
        restarted.reconcile_relay_calls()
        self.assertEqual(self.debit(call, restarted), ('RESERVED', 2))
        self.assertEqual(self.counts(restarted), (0, 2))
        self.refuse_replay(restarted, call)
        self.assertFalse(Path(call['payload']['path']).exists())

    def test_uncertain_orphan_without_completion_recovers_without_replay(self):
        # Reproduce crash after UNCERTAIN but before durable completion.
        call = self.call('uncertain-orphan')
        self.agent.relay_call_begin(call)
        self.agent.local_budget_reserve(self.config, call)
        self.agent.relay_call_phase(call, 'UNCERTAIN')
        self.assertEqual(self.journal(call), {
            'phase': 'UNCERTAIN', 'delivery_state': 'NONE', 'completion_json': None,
        })
        restarted = self.import_agent()
        with patch.object(restarted, 'execute_tool', wraps=restarted.execute_tool) as tool:
            summary = restarted.reconcile_relay_calls()
            self.assertEqual(summary['uncertain'], 1)
            pending = self.journal(call, restarted)
            self.assertEqual(pending['phase'], 'UNCERTAIN')
            self.assertEqual(pending['delivery_state'], 'PENDING')
            completion = json.loads(pending['completion_json'])
            self.assertEqual(completion['state'], 'FAILED')
            self.assertEqual(completion['result']['state'], 'INDETERMINATE')
            self.assertIsNone(completion['result']['mutation_performed'])
            self.assertEqual(completion['error_code'], 'CALL_OUTCOME_UNCERTAIN')
            restarted.reconcile_relay_calls(self.config)
            restarted.reconcile_relay_calls(self.config)
            tool.assert_not_called()
        self.assertEqual(self.journal(call, restarted), {
            'phase': 'UNCERTAIN', 'delivery_state': 'ACKNOWLEDGED',
            'completion_json': None,
        })
        self.assertEqual(restarted.synthetic_network.call_count, 1)
        self.assertEqual(self.debit(call, restarted), ('RESERVED', 2))
        self.assertEqual(self.counts(restarted), (0, 2))
        self.refuse_replay(restarted, call)

    def test_failed_orphan_before_completion_releases_reservation_and_delivers(self):
        # A crash after durable FAILED and before _relay_completion must be visible.
        call = self.call('failed-orphan')
        self.agent.relay_call_begin(call)
        self.agent.local_budget_reserve(self.config, call)
        self.agent.relay_call_phase(call, 'RESERVED')
        self.agent.relay_call_phase(call, 'FAILED')
        restarted = self.import_agent()
        with patch.object(restarted, 'execute_tool', wraps=restarted.execute_tool) as tool:
            summary = restarted.reconcile_relay_calls()
            self.assertEqual(summary['released'], 1)
            pending = self.journal(call, restarted)
            self.assertEqual(pending['phase'], 'FAILED')
            self.assertEqual(pending['delivery_state'], 'PENDING')
            completion = json.loads(pending['completion_json'])
            self.assertEqual(completion['state'], 'FAILED')
            self.assertEqual(completion['result']['state'], 'INDETERMINATE')
            self.assertEqual(completion['error_code'], 'CALL_OUTCOME_UNCERTAIN')
            restarted.reconcile_relay_calls(self.config)
            restarted.reconcile_relay_calls(self.config)
            tool.assert_not_called()
        self.assertEqual(self.debit(call, restarted), ('RELEASED', 2))
        self.assertEqual(self.journal(call, restarted)['delivery_state'], 'ACKNOWLEDGED')
        self.assertEqual(restarted.synthetic_network.call_count, 1)
        self.refuse_replay(restarted, call)
        self.assertFalse(Path(call['payload']['path']).exists())

    def test_executed_orphan_without_completion_commits_once_and_delivers_uncertain(self):
        # A confirmed effect with a lost result must not be silently forgotten.
        call = self.call('executed-orphan')
        self.agent.relay_call_begin(call)
        self.agent.local_budget_reserve(self.config, call)
        self.agent.relay_call_phase(call, 'EXECUTING')
        Path(call['payload']['path']).write_text(call['payload']['content'])
        self.agent.relay_call_phase(call, 'EXECUTED')
        target = Path(call['payload']['path'])
        target.write_text('independent-later-content')
        restarted = self.import_agent()
        with patch.object(restarted, 'execute_tool', wraps=restarted.execute_tool) as tool:
            summary = restarted.reconcile_relay_calls()
            self.assertEqual(summary['committed'], 1)
            pending = self.journal(call, restarted)
            self.assertEqual(pending['phase'], 'EXECUTED')
            self.assertEqual(pending['delivery_state'], 'PENDING')
            completion = json.loads(pending['completion_json'])
            self.assertEqual(completion['state'], 'FAILED')
            self.assertEqual(completion['result']['state'], 'INDETERMINATE')
            self.assertEqual(completion['error_code'], 'CALL_OUTCOME_UNCERTAIN')
            restarted.reconcile_relay_calls(self.config)
            restarted.reconcile_relay_calls(self.config)
            tool.assert_not_called()
        self.assertEqual(self.debit(call, restarted), ('COMMITTED', 2))
        self.assertEqual(self.counts(restarted), (2, 0))
        self.assertEqual(self.journal(call, restarted)['delivery_state'], 'ACKNOWLEDGED')
        self.assertEqual(restarted.synthetic_network.call_count, 1)
        self.refuse_replay(restarted, call)
        self.assertEqual(target.read_text(), 'independent-later-content')

    def test_changed_payload_under_recorded_identity_is_rejected(self):
        call = self.call('identity-conflict')
        self.agent.relay_call_begin(call)
        changed = copy.deepcopy(call)
        changed['payload']['content'] = 'different-request-under-same-identity'
        with self.assertRaisesRegex(ValueError, 'CALL_IDEMPOTENCY_CONFLICT'):
            self.agent.relay_call_begin(changed)
        self.assertFalse(Path(call['payload']['path']).exists())


    def journal(self, call, agent=None):
        with (agent or self.agent)._ops_connect() as conn:
            row = conn.execute(
                'SELECT phase,delivery_state,completion_json FROM relay_call_journal '
                'WHERE request_id=?', (call['request_id'],),
            ).fetchone()
            return None if row is None else dict(row)

    def test_concurrent_reservations_cannot_spend_the_last_unit_twice(self):
        with self.agent._ops_connect() as conn:
            conn.execute('UPDATE local_budget_blocks SET allocated_units=1 '
                         'WHERE budget_id=?', ('synthetic-block',))
            conn.commit()
        barrier = threading.Barrier(2, timeout=5)
        # This is the local reservation component, not a relay enrollment.
        # LOCAL_TUNNEL prevents an exhausted budget triggering a lease refresh;
        # only the synthetic, verified lease and real SQLite transaction are used.
        config = {**self.config, 'HARA_COMMANDER_TRANSPORT_MODE': 'LOCAL_TUNNEL'}

        def reserve(suffix):
            call = self.call(suffix)
            call['usage']['units'] = 1
            barrier.wait()
            try:
                return ('RESERVED', self.agent.local_budget_reserve(config, call))
            except ValueError as error:
                return ('DENIED', str(error))

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(reserve, suffix) for suffix in ('last-a', 'last-b')]
            outcomes = [future.result(timeout=10) for future in pending]
        self.assertEqual(sorted(x[0] for x in outcomes), ['DENIED', 'RESERVED'])
        self.assertEqual([x[1] for x in outcomes if x[0] == 'DENIED'],
                         ['LOCAL_BUDGET_EXHAUSTED'])
        self.assertEqual(self.counts(), (0, 1))
        with self.agent._ops_connect() as conn:
            self.assertEqual(conn.execute(
                'SELECT COUNT(*) FROM local_budget_debits WHERE state=?', ('RESERVED',)
            ).fetchone()[0], 1)
        self.agent.synthetic_network.assert_not_called()

    def test_expired_completion_after_effect_keeps_charge_and_prevents_replay(self):
        call = self.call('expired-after-effect')

        def expired(url, token, body, **kwargs):
            self.assertTrue(url.endswith('/calls/complete'))
            raise urllib.error.HTTPError(
                url, 409, 'Conflict', {'Content-Type': 'application/json'},
                io.BytesIO(b'{"error":"DEVICE_CALL_EXPIRED"}'),
            )

        self.agent.synthetic_network.side_effect = expired
        with self.assertRaises(urllib.error.HTTPError):
            self.agent.execute_call(self.config, copy.deepcopy(call))
        self.assertEqual(self.debit(call), ('COMMITTED', 2))
        self.assertEqual(self.counts(), (2, 0))
        self.assertEqual(self.journal(call),
                         {'phase': 'EXECUTED', 'delivery_state': 'EXPIRED',
                          'completion_json': None})
        self.assertEqual(self.agent.synthetic_network.call_count, 1)
        self.assertEqual(self.agent.synthetic_network.call_args.args[2]['state'], 'COMPLETED')
        target = Path(call['payload']['path'])
        self.assertEqual(target.read_text(), call['payload']['content'])
        target.write_text('independent-later-content')
        restarted = self.import_agent()
        restarted.reconcile_relay_calls(self.config)
        self.refuse_replay(restarted, call)
        self.assertEqual(target.read_text(), 'independent-later-content')
        self.assertEqual(self.debit(call, restarted), ('COMMITTED', 2))
        restarted.synthetic_network.assert_not_called()

    def test_pending_outbox_resends_exact_completion_then_ack_scrubs_result(self):
        call = self.call('pending-delivery')
        self.agent.synthetic_network.side_effect = urllib.error.URLError('synthetic outage')
        with self.assertRaises(urllib.error.URLError):
            self.agent.execute_call(self.config, copy.deepcopy(call))
        pending = self.journal(call)
        self.assertEqual(pending['phase'], 'EXECUTED')
        self.assertEqual(pending['delivery_state'], 'PENDING')
        self.assertIsNotNone(pending['completion_json'])
        expected_body = json.loads(pending['completion_json'])
        self.assertEqual(expected_body, self.agent.synthetic_network.call_args.args[2])
        self.assertEqual(expected_body['state'], 'COMPLETED')
        self.assertEqual(self.debit(call), ('COMMITTED', 2))
        target = Path(call['payload']['path'])
        target.write_text('independent-later-content')
        restarted = self.import_agent()
        with patch.object(restarted, 'execute_tool', wraps=restarted.execute_tool) as tool:
            restarted.reconcile_relay_calls(self.config)
            restarted.reconcile_relay_calls(self.config)
            tool.assert_not_called()
        self.assertEqual(restarted.synthetic_network.call_count, 1)
        self.assertEqual(restarted.synthetic_network.call_args.args[2], expected_body)
        self.assertEqual(self.journal(call, restarted),
                         {'phase': 'EXECUTED', 'delivery_state': 'ACKNOWLEDGED',
                          'completion_json': None})
        self.assertEqual(self.counts(restarted), (2, 0))
        self.assertEqual(target.read_text(), 'independent-later-content')
        self.refuse_replay(restarted, call)

    def test_sigkill_after_effect_before_checkpoint_preserves_uncertain_reservation(self):
        call = self.call('sigkill-before-checkpoint')
        ctx = multiprocessing.get_context('spawn')
        receiver, sender = ctx.Pipe(duplex=False)
        process = ctx.Process(target=_effect_then_wait_before_checkpoint,
                              args=(str(self.root), self.config, self.lease,
                                    copy.deepcopy(call), sender))
        process.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(10), 'Child did not reach the effect boundary')
            observed = receiver.recv()
            self.assertEqual(observed,
                             {'phase': 'EFFECT_DONE_BEFORE_CHECKPOINT',
                              'content': call['payload']['content']})
            self.assertTrue(process.is_alive())
            process.kill()
            process.join(timeout=5)
            self.assertFalse(process.is_alive(), 'Disposable child was not reaped')
            self.assertEqual(process.exitcode, -signal.SIGKILL)
        finally:
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            receiver.close()
        self.assertEqual(self.journal(call)['phase'], 'EXECUTING')
        self.assertEqual(self.debit(call), ('RESERVED', 2))
        target = Path(call['payload']['path'])
        self.assertEqual(target.read_text(), call['payload']['content'])
        target.write_text('independent-later-content')
        restarted = self.import_agent()
        with patch.object(restarted, 'execute_tool', wraps=restarted.execute_tool) as tool:
            restarted.reconcile_relay_calls(self.config)
            tool.assert_not_called()
        self.assertEqual(self.journal(call, restarted)['phase'], 'UNCERTAIN')
        self.assertEqual(self.debit(call, restarted), ('RESERVED', 2))
        self.assertEqual(self.counts(restarted), (0, 2))
        completion = restarted.synthetic_network.call_args.args[2]
        self.assertEqual(completion['state'], 'FAILED')
        self.assertEqual(completion['result']['state'], 'INDETERMINATE')
        self.assertIsNone(completion['result']['mutation_performed'])
        self.assertNotEqual(completion['result']['state'], 'PASS')
        self.refuse_replay(restarted, call)
        self.assertEqual(target.read_text(), 'independent-later-content')

    def test_journal_keeps_payload_digest_instead_of_raw_content(self):
        call = self.call('private-content')
        marker = 'synthetic-private-payload-do-not-store-in-journal'
        call['payload']['content'] = marker
        self.agent.relay_call_begin(call)
        with self.agent._ops_connect() as conn:
            persisted = '\n'.join(conn.iterdump())
        self.assertNotIn(marker, persisted)
        self.assertNotIn(self.config['HARA_DEVICE_TOKEN'], persisted)


if __name__ == '__main__':
    unittest.main(verbosity=2)
