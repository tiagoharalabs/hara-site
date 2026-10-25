"""#163 DEV-only Event V2 integration into the real commercial .56 Agent.

Synthetic configuration, local SQLite and disposable file effects only.
No socket, native Agent, VM, production credential or release gate is used.
"""
import importlib.util
import copy
import json
import tempfile
import sys
import threading
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SOURCE = (Path(__file__).resolve().parents[1] /
          'release-candidates/commercial-0.3.56-source/agent/linux.py')
DEV_ORIGIN = 'https://hara-commander-r163-canary-20261024.tiago-sartori.workers.dev'


class StopFixture(BaseException):
    """Stop the actual infinite worker at an injected idle boundary."""


class Clock:
    def __init__(self, initial=1.0, max_sleeps=64):
        self.now = initial
        self.sleeps = []
        self.max_sleeps = max_sleeps

    def monotonic(self):
        return self.now

    def sleep(self, delay):
        self.sleeps.append(float(delay))
        self.now += delay
        if len(self.sleeps) >= self.max_sleeps:
            raise StopFixture()


class HintSignal:
    """One-bit semaphore fixture, preserving concurrent wakes without a socket."""
    def __init__(self, clock, idle_limit=2):
        self.clock = clock
        self.value = 0
        self.idle_waits = 0
        self.idle_limit = idle_limit

    def release(self):
        if self.value:
            raise ValueError('already signaled')
        self.value = 1

    def acquire(self, blocking=True, timeout=None):
        if self.value:
            self.value = 0
            return True
        if not blocking or timeout == 0:
            return False
        self.idle_waits += 1
        self.clock.now += float(timeout or 0.5)
        if self.idle_waits >= self.idle_limit:
            raise StopFixture()
        return False


class Channel:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(copy.deepcopy(message))

    def close(self):
        pass


class CommercialEventV2Tests(unittest.TestCase):
    def setUp(self):
        self.agent = self.import_agent()
        self.config = {
            'HARA_COMMANDER_URL': DEV_ORIGIN,
            'HARA_COMMANDER_ENVIRONMENT': 'DEV',
            'HARA_COMMANDER_EVENT_V2_DEV_ENABLED': 'true',
            'HARA_COMMANDER_TRANSPORT_MODE': 'OUTBOUND_RELAY',
            'HARA_COMMANDER_APPROVAL_MODE': 'PERSISTENT_TRUSTED',
            'HARA_DEVICE_ID': 'synthetic-event-v2-device',
            'HARA_TENANT_ID': 'synthetic-event-v2-tenant',
            'HARA_DEVICE_TOKEN': 'synthetic-test-only-not-a-credential',
            'HARA_DEVICE_ARCH': 'synthetic-test',
        }
        self.work = None

    def import_agent(self, suffix=''):
        name = 'commercial_event_v2_' + self.id().split('.')[-1] + suffix
        spec = importlib.util.spec_from_file_location(name, SOURCE)
        agent = importlib.util.module_from_spec(spec)
        sys.modules[name] = agent
        spec.loader.exec_module(agent)
        return agent

    def local_state(self, agent=None):
        agent = agent or self.agent
        if self.work is None:
            temporary = tempfile.TemporaryDirectory(prefix='hara-r163-commercial-dev-')
            self.addCleanup(temporary.cleanup)
            self.work = Path(temporary.name)
        agent.DATA_DIR = self.work / 'data'
        agent.CONFIG_FILE = self.work / 'config/device.env'
        agent.STATUS_FILE = self.work / 'runtime-status.json'
        agent.SESSION_FILE = self.work / 'operator-session.json'
        agent.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        agent.CONFIG_FILE.write_text(''.join(k + '=' + str(v) + '\n'
                                            for k, v in self.config.items() if not k.startswith('_')))
        agent.configure_enrollment_state(self.config)
        lease = {
            'usage_mode': 'LOCAL_BUDGET', 'tenant_id': self.config['HARA_TENANT_ID'],
            'device_id': self.config['HARA_DEVICE_ID'], 'entitlement_id': 'synthetic-entitlement',
            'plan_code': 'SYNTHETIC_QA', 'meter_id': 'synthetic-meter',
        }
        # Signature/remote lease acquisition is a test boundary. Reservation,
        # commit, journal, execution, receipts and file effects stay real.
        verified = patch.object(agent, '_active_verified_product_lease', return_value=lease)
        verified.start()
        self.addCleanup(verified.stop)
        now = datetime.now(timezone.utc)
        with agent._ops_connect() as conn:
            conn.execute('''INSERT OR IGNORE INTO local_budget_blocks
                (budget_id,tenant_id,device_id,entitlement_id,plan_code,meter_id,
                 period_key,allocated_units,lease_token,issued_at_utc,expires_at_utc,state)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,'ACTIVE')''',
                ('synthetic-block', lease['tenant_id'], lease['device_id'], lease['entitlement_id'],
                 lease['plan_code'], lease['meter_id'], 'synthetic-period', 100,
                 'synthetic-lease-not-a-credential', now.isoformat(),
                 (now + timedelta(days=1)).isoformat()))
            conn.commit()

    def call(self, suffix='one', *, expired=False):
        self.assertIsNotNone(self.work)
        return {
            'call_id': 'synthetic-call-' + suffix, 'request_id': 'synthetic-request-' + suffix,
            'tool_id': 'hara.files.write',
            'payload': {'path': str(self.work / ('effect-' + suffix + '.txt')),
                        'content': 'synthetic-effect-' + suffix, 'mode': 'rewrite'},
            'usage': {'mode': 'LOCAL_BUDGET', 'units': 2, 'period_key': 'synthetic-period',
                      'budget_id': 'synthetic-block'},
            'expires_at_utc': (datetime.now(timezone.utc) +
                               timedelta(seconds=-1 if expired else 300)).isoformat(),
        }

    def journal(self, request_id, agent=None):
        with (agent or self.agent)._ops_connect() as conn:
            row = conn.execute('SELECT * FROM relay_call_journal WHERE request_id=?',
                               (request_id,)).fetchone()
            return dict(row) if row else None

    def budget(self, agent=None):
        agent = agent or self.agent
        with agent._ops_connect() as conn:
            return agent._budget_counts(conn, 'synthetic-block')

    def run_worker(self, replies, *, signal=None, agent=None, clock=None,
                   complete_handler=None, revoked=False):
        agent = agent or self.agent
        clock = clock or Clock()
        signal = signal or HintSignal(clock)
        config = {**self.config, '_event_v2_wake_signal': signal}
        responses = iter(replies)
        claimed = []
        completed = []
        channel = Channel()

        def post(url, token, body, **_kwargs):
            self.assertEqual(token, self.config['HARA_DEVICE_TOKEN'])
            if url == DEV_ORIGIN + '/api/device/calls/next':
                self.assertEqual(body, {}, 'wake metadata became execution authority')
                claimed.append(copy.deepcopy(body))
                if len(claimed) > 40:
                    raise StopFixture()
                response = next(responses, None)
                if isinstance(response, BaseException):
                    raise response
                return copy.deepcopy(response(signal) if callable(response) else response)
            self.assertEqual(url, DEV_ORIGIN + '/api/device/calls/complete')
            completed.append(copy.deepcopy(body))
            if complete_handler:
                complete_handler(body)
            return {'ok': True, 'call_id': body['call_id'], 'state': body['state']}

        with patch.object(agent, 'post_json', side_effect=post), \
             patch.object(agent, 'refresh_product_lease'), \
             patch.object(agent, '_RELAY_PROGRESS_CHANNEL', channel), \
             patch.object(agent.time, 'monotonic', side_effect=clock.monotonic), \
             patch.object(agent.time, 'sleep', side_effect=clock.sleep), \
             patch.object(agent, 'execute_tool', wraps=agent.execute_tool) as execute_tool:
            if revoked:
                agent._relay_executor_worker(config, channel)
            else:
                with self.assertRaises(StopFixture):
                    agent._relay_executor_worker(config, channel)
            effects = execute_tool.call_count
        return SimpleNamespace(claimed=claimed, completed=completed, effects=effects,
                               progress=channel.messages, clock=clock, signal=signal)

    def gate(self, semaphore=None):
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(1)
            semaphore.acquire()
        return self.agent.event_v2_dev_module().WakeGate(semaphore, max_drain=8)

    def test_default_configuration_does_not_enable_event_v2(self):
        self.assertFalse(self.agent.event_v2_dev_enabled({}))
        disabled = {**self.config, 'HARA_COMMANDER_EVENT_V2_DEV_ENABLED': 'false'}
        self.assertFalse(self.agent.event_v2_dev_enabled(disabled))
        self.assertEqual(self.agent.transport_mode(disabled), 'OUTBOUND_RELAY')

    def test_exact_dev_opt_in_selects_event_v2(self):
        self.assertTrue(self.agent.event_v2_dev_enabled(self.config))
        self.assertEqual(self.agent.transport_mode(self.config), 'EVENT_V2')

    def test_raw_transport_setting_cannot_bypass_dev_admission(self):
        with self.assertRaisesRegex((ValueError, RuntimeError), 'EVENT_V2|TRANSPORT'):
            self.agent.transport_mode({'HARA_COMMANDER_TRANSPORT_MODE': 'EVENT_V2'})

    def test_wake_gate_yields_after_eight_claims_without_stranding_backlog(self):
        gate = self.gate()
        with patch.object(self.agent.time, 'sleep') as sleep:
            for _ in range(8):
                self.assertTrue(gate.wait(timeout=0))
                gate.after_claim(True)
            sleep.assert_called_once_with(0.1)
            self.assertTrue(gate.wait(timeout=0), 'remaining durable backlog was stranded')
            gate.after_claim(False)
            self.assertFalse(gate.wait(timeout=0), 'empty claim became periodic idle polling')

    def test_flag_types_and_non_exact_spellings_do_not_enable_event_v2(self):
        for flag in [True, False, 1, None, {}, [], 'TRUE', ' true ', '1']:
            with self.subTest(flag=repr(flag)):
                with self.assertRaisesRegex((ValueError, RuntimeError), 'EVENT_V2'):
                    self.agent.event_v2_dev_enabled({**self.config, 'HARA_COMMANDER_EVENT_V2_DEV_ENABLED': flag})

    def test_dev_opt_in_rejects_prod_other_origins_paths_queries_and_credentials(self):
        for overrides in [
            {'HARA_COMMANDER_ENVIRONMENT': 'PROD'}, {'HARA_COMMANDER_ENVIRONMENT': 'dev'},
            {'HARA_COMMANDER_URL': 'https://commander.haralabs.com.br'},
            {'HARA_COMMANDER_URL': DEV_ORIGIN + '/different-path'},
            {'HARA_COMMANDER_URL': DEV_ORIGIN + '?canary=true'},
            {'HARA_COMMANDER_URL': DEV_ORIGIN + '#fragment'},
            {'HARA_COMMANDER_URL': DEV_ORIGIN.replace('https://', 'https://user:password@')},
            {'HARA_COMMANDER_TRANSPORT_MODE': 'LOCAL_TUNNEL'},
        ]:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex((ValueError, RuntimeError), 'EVENT_V2'):
                    self.agent.event_v2_dev_enabled({**self.config, **overrides})

    def test_duplicate_wake_hints_coalesce_to_one_empty_claim(self):
        gate = self.gate()
        self.assertTrue(gate.wait(timeout=0))
        gate.after_claim(False)
        for _ in range(100):
            gate.notify()
        self.assertTrue(gate.wait(timeout=0))
        gate.after_claim(False)
        self.assertFalse(gate.wait(timeout=0))

    def test_wake_arriving_during_empty_claim_is_not_lost(self):
        gate = self.gate()
        self.assertTrue(gate.wait(timeout=0))
        gate.notify()
        gate.after_claim(False)
        self.assertTrue(gate.wait(timeout=0))
        gate.after_claim(False)
        self.assertFalse(gate.wait(timeout=0))

    def test_default_guardian_wires_real_event_heartbeat_and_executor_to_same_bounded_signal(self):
        captures = []
        context = SimpleNamespace()
        context.BoundedSemaphore = lambda count: threading.BoundedSemaphore(count)
        context.Pipe = lambda **_kwargs: (Channel(), Channel())

        class Process:
            def __init__(self, **kwargs):
                captures.append(kwargs)
                self.alive = False
            def start(self): self.alive = True
            def is_alive(self): return self.alive
            def terminate(self): self.alive = False
            def kill(self): self.alive = False
            def join(self, **_kwargs): pass

        context.Process = Process
        with patch('multiprocessing.get_context', return_value=context):
            guard = self.agent.RelaySupervisor(self.config, report=lambda _event: None)
            try:
                self.assertIs(guard.targets['heartbeat'], self.agent._event_v2_heartbeat_worker)
                self.assertIs(guard.targets['executor'], self.agent._relay_executor_worker)
                guard._spawn('heartbeat', 0)
                guard._spawn('executor', 0)
                signal = captures[0]['args'][1]['_event_v2_wake_signal']
                self.assertIs(captures[1]['args'][1]['_event_v2_wake_signal'], signal)
                self.assertFalse(signal.acquire(blocking=False), 'initial wake signal was not empty')
            finally:
                guard.close()

    def test_feature_off_preserves_existing_guardian_heartbeat_and_executor(self):
        config = {**self.config, 'HARA_COMMANDER_EVENT_V2_DEV_ENABLED': 'false'}
        context = SimpleNamespace()
        with patch('multiprocessing.get_context', return_value=context):
            guard = self.agent.RelaySupervisor(config, report=lambda _event: None)
            self.assertIs(guard.targets['heartbeat'], self.agent._relay_heartbeat_worker)
            self.assertIs(guard.targets['executor'], self.agent._relay_executor_worker)
            self.assertIsNone(guard.wake_signal)

    def test_idle_real_executor_claims_once_then_waits_without_http_polling(self):
        self.local_state()
        result = self.run_worker([None])
        self.assertEqual(len(result.claimed), 1)
        self.assertEqual(result.effects, 0)
        self.assertEqual(result.completed, [])
        self.assertGreaterEqual(result.signal.idle_waits, 2)

    def test_disabled_feature_preserves_existing_v1_executor_polling(self):
        self.config['HARA_COMMANDER_EVENT_V2_DEV_ENABLED'] = 'false'
        self.local_state()
        result = self.run_worker([None], clock=Clock(max_sleeps=3))
        self.assertGreaterEqual(len(result.claimed), 2)
        self.assertEqual(result.signal.idle_waits, 0)

    def test_real_entry_preserves_wake_that_arrives_during_empty_http_claim(self):
        self.local_state()
        call = self.call('racing-wake')
        def empty_then_wake(signal):
            signal.release()
            return None
        result = self.run_worker([empty_then_wake, call, None])
        self.assertEqual(len(result.claimed), 3)
        self.assertEqual(result.effects, 1)
        self.assertEqual(Path(call['payload']['path']).read_text(), call['payload']['content'])
        self.assertEqual(self.budget(), (2, 0))

    def test_actual_executor_drains_seventeen_calls_in_yielding_batches_without_duplicate_effects(self):
        self.local_state()
        calls = [self.call(str(i)) for i in range(17)]
        result = self.run_worker([*calls, None])
        self.assertEqual(len(result.claimed), 18)
        self.assertEqual(result.effects, 17)
        self.assertEqual(result.clock.sleeps.count(0.1), 2)
        self.assertEqual(self.budget(), (34, 0))
        self.assertEqual(len(result.completed), 17)
        for call in calls:
            self.assertEqual(Path(call['payload']['path']).read_text(), call['payload']['content'])
            row = self.journal(call['request_id'])
            self.assertEqual((row['phase'], row['delivery_state']), ('EXECUTED', 'ACKNOWLEDGED'))

    def test_duplicate_authenticated_claim_never_repeats_effect_or_quota(self):
        self.local_state()
        call = self.call('same-intent')
        result = self.run_worker([call, copy.deepcopy(call), None])
        self.assertEqual(result.effects, 1)
        self.assertEqual(self.budget(), (2, 0))
        self.assertEqual(len(result.completed), 1)
        self.assertTrue(any(message.get('code') == 'CALL_REPLAY_REFUSED' for message in result.progress))

    def test_restart_retries_exact_completion_after_lost_ack_without_effect_or_quota_replay(self):
        self.local_state()
        call = self.call('lost-ack')
        def lose_reply(_body):
            raise OSError('SYNTHETIC_REPLY_LOST')
        first = self.run_worker([call, None], complete_handler=lose_reply)
        self.assertEqual(first.effects, 1)
        self.assertEqual(self.budget(), (2, 0))
        self.assertEqual(self.journal(call['request_id'])['delivery_state'], 'PENDING')
        Path(call['payload']['path']).write_text('independent-later-content')
        restarted = self.import_agent('_restart')
        self.local_state(restarted)
        second = self.run_worker([None], agent=restarted, clock=Clock(initial=100.0))
        self.assertEqual(second.effects, 0)
        self.assertEqual(self.budget(restarted), (2, 0))
        self.assertEqual(first.completed, second.completed)
        self.assertEqual(Path(call['payload']['path']).read_text(), 'independent-later-content')
        row = self.journal(call['request_id'], restarted)
        self.assertEqual((row['phase'], row['delivery_state']), ('EXECUTED', 'ACKNOWLEDGED'))
        self.assertIsNone(row['completion_json'])

    def test_revoked_claim_stops_real_executor_before_any_effect_or_quota(self):
        self.local_state()
        error = urllib.error.HTTPError(DEV_ORIGIN, 403, 'SYNTHETIC_REVOKED', {}, None)
        result = self.run_worker([error], revoked=True)
        self.assertEqual(len(result.claimed), 1)
        self.assertEqual(result.effects, 0)
        self.assertEqual(self.budget(), (0, 0))
        self.assertTrue(any(message.get('kind') == 'REVOKED' for message in result.progress))

    def test_expired_claim_never_enters_tool_or_spends_quota(self):
        self.local_state()
        call = self.call('expired', expired=True)
        result = self.run_worker([call, None])
        self.assertEqual(result.effects, 0)
        self.assertFalse(Path(call['payload']['path']).exists())
        self.assertEqual(self.budget(), (0, 0))
        self.assertIsNone(self.journal(call['request_id']))
        self.assertTrue(any(message.get('code') == 'DEVICE_CALL_EXPIRED' for message in result.progress))


if __name__ == '__main__':
    unittest.main(verbosity=2)
