"""Offline .56 heartbeat driver tests; no socket or enrollment is installed."""
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PATH = ROOT / 'release-candidates/commercial-0.3.56-source/agent/event_v2_dev.py'


class HeartbeatContract(unittest.TestCase):
    def module(self):
        spec = importlib.util.spec_from_file_location('commercial_dev_test', PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def test_guardian_progress_continues_during_startup_spread(self):
        mod = self.module()
        clock = [0.0]
        events = []
        def sleep(seconds):
            clock[0] += seconds
        mod.progress_sleep(119.0, lambda kind, **fields: events.append((clock[0], kind, fields)),
                           sleep=sleep, monotonic=lambda: clock[0])
        self.assertEqual(clock[0], 119.0)
        self.assertGreaterEqual(len(events), 8)
        self.assertTrue(all(e[1] == 'HEARTBEAT_RETRY' and e[2]['delay'] <= 15 for e in events))

    def test_only_live_probe_ack_confirms_health(self):
        mod = self.module()
        state = mod.ProbeState(0.0)
        self.assertFalse(state.confirm('HARA_EVENT_V2_PROBE_ACK_V1', 0.0))
        self.assertTrue(state.due(0.0))
        state.sent(0.0)
        self.assertFalse(state.confirm('wrong', 1.0))
        self.assertTrue(state.confirm('HARA_EVENT_V2_PROBE_ACK_V1', 1.0))
        self.assertFalse(state.due(59.9))
        self.assertTrue(state.due(60.0))

    def test_ack_after_deadline_is_not_recovery(self):
        state = self.module().ProbeState(0.0)
        state.sent(0.0)
        self.assertFalse(state.confirm('HARA_EVENT_V2_PROBE_ACK_V1', 20.0))
        with self.assertRaisesRegex(RuntimeError, 'PROBE_TIMEOUT'):
            state.check(20.0)

    def test_default_contract_cannot_execute_transient_frames(self):
        mod = self.module()
        self.assertFalse(mod.is_durable_wake({'type': 'CALL_TRANSIENT'}))
        self.assertTrue(mod.is_durable_wake({'type': 'CALL_AVAILABLE'}))


if __name__ == '__main__':
    unittest.main()
