"""Synthetic call completion transport failures must not rewrite execution truth."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'release-candidates/commercial-0.3.56-source/agent/linux.py'


class CallCompletionTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('completion056', SOURCE)
        self.agent = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.agent)
        temporary=tempfile.TemporaryDirectory(prefix='hara-completion-')
        self.addCleanup(temporary.cleanup)
        self.agent.DATA_DIR=Path(temporary.name)
        self.agent.OPERATIONS_DB_FILE=Path(temporary.name)/'operations.sqlite3'
        self.config = {'HARA_COMMANDER_APPROVAL_MODE': 'PERSISTENT_TRUSTED'}
        self.call = {'call_id': 'synthetic-call', 'request_id': 'synthetic-request',
                     'tool_id': 'hara.ping', 'payload': {}}
        self.result = {'state': 'PASS', 'mutation_performed': True,
                       'bridge_receipt_sha256': '0' * 64}
        for name, value in [('append_console_event', None), ('local_budget_reserve', None),
                            ('execute_tool', self.result), ('local_budget_commit', {}),
                            ('local_budget_release', None), ('refresh_product_lease', None),
                            ('complete', None)]:
            p = patch.object(self.agent, name, return_value=value)
            setattr(self, name, p.start())
            self.addCleanup(p.stop)

    def test_failed_completion_delivery_does_not_report_failed_execution(self):
        self.complete.side_effect = OSError('synthetic offline')
        with self.assertRaises(OSError):
            self.agent.execute_call(self.config, self.call)
        self.assertEqual(self.complete.call_count, 1)
        self.assertEqual(self.complete.call_args.args[2:4], ('COMPLETED', self.result))
        self.execute_tool.assert_called_once()
        self.assertNotIn('DENIED', [c.args[0] for c in self.append_console_event.call_args_list])

    def test_expired_completion_preserves_committed_budget_and_receipt(self):
        self.local_budget_reserve.return_value = {'state': 'RESERVED'}
        self.local_budget_commit.return_value = {'state': 'COMMITTED'}
        self.complete.side_effect = ValueError('DEVICE_CALL_EXPIRED')
        with self.assertRaisesRegex(ValueError, 'DEVICE_CALL_EXPIRED'):
            self.agent.execute_call(self.config, self.call)
        self.assertEqual(self.complete.call_count, 1)
        self.assertEqual(self.complete.call_args.args[3], self.result)
        self.local_budget_commit.assert_called_once_with('synthetic-request')
        self.local_budget_release.assert_not_called()
        self.execute_tool.assert_called_once()

    def test_final_event_failure_does_not_emit_a_second_completion(self):
        def append(event, *args, **kwargs):
            if event == 'PASS':
                raise OSError('synthetic journal failure')
        self.append_console_event.side_effect = append
        with self.assertRaises(OSError):
            self.agent.execute_call(self.config, self.call)
        self.complete.assert_called_once_with(self.config, self.call, 'COMPLETED', self.result)

    def test_actual_tool_failure_releases_budget_once_and_reports_failure_once(self):
        self.local_budget_reserve.return_value = {'state': 'RESERVED'}
        self.execute_tool.side_effect = ValueError('FUNCTION_ARGUMENTS_DENIED')
        self.agent.execute_call(self.config, self.call)
        self.local_budget_release.assert_called_once_with('synthetic-request')
        self.local_budget_commit.assert_not_called()
        self.assertEqual(self.complete.call_count, 1)
        self.assertEqual(self.complete.call_args.args[2], 'FAILED')
        self.assertFalse(self.complete.call_args.args[3]['mutation_performed'])
        self.assertEqual(self.complete.call_args.args[4], 'FUNCTION_ARGUMENTS_DENIED')

    def test_failed_failure_delivery_does_not_reexecute_or_repeat_budget_release(self):
        self.local_budget_reserve.return_value = {'state': 'RESERVED'}
        self.execute_tool.side_effect = ValueError('FUNCTION_ARGUMENTS_DENIED')
        self.complete.side_effect = OSError('synthetic offline')
        with self.assertRaises(OSError):
            self.agent.execute_call(self.config, self.call)
        self.local_budget_release.assert_called_once_with('synthetic-request')
        self.execute_tool.assert_called_once()
        self.assertEqual(self.complete.call_count, 1)
        self.assertEqual(self.complete.call_args.args[2], 'FAILED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
