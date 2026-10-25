"""Offline structure tests only; all identities, captures and receipts are synthetic.

No socket, provider request, credential, native admission or campaign is used.
Even the consistent 500-connection fixture must remain REVIEW_ONLY. JSON can
describe measurements; this validator cannot authenticate their provenance.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest


MODULE = Path(__file__).with_name('event_v2_hosted_evidence_r163.py')
START = 1_700_000_000_000
NOW = START + 600_000
QUERY = 'query SyntheticOfflineReview { syntheticFixtureOnly }'
METERS = (
    'worker_requests', 'worker_cpu_us', 'do_requests', 'do_active_gb_us',
    'do_storage_reads', 'do_storage_writes', 'do_storage_byte_seconds',
    'd1_rows_read', 'd1_rows_written', 'queue_billable_ops', 'dlq_billable_ops',
)


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def fixture():
    binding = {
        'source_head': '1' * 40, 'agent_version': '0.3.56',
        'worker_version': 'SYNTHETIC_WORKER_VERSION_REVIEW_ONLY',
        'resources': {
            'account': 'SYNTHETIC_ACCOUNT', 'worker': 'SYNTHETIC_DEV_WORKER',
            'do_namespace': 'SYNTHETIC_DO', 'd1_database': 'SYNTHETIC_D1',
            'queue': 'SYNTHETIC_QUEUE', 'dlq': 'SYNTHETIC_DLQ',
            'recipient': 'SYNTHETIC_DEV_RECIPIENT_NO_ENDPOINT',
        },
        'artifacts_sha256': {
            'linux_agent': '2' * 64, 'windows_agent': '3' * 64,
            'worker': '4' * 64, 'device_channel': '5' * 64,
        },
        'query_sha256': hashlib.sha256(QUERY.encode()).hexdigest(),
        'rollback_sha256': '6' * 64,
    }
    plan = {
        'schema': 'hara.commander.r163.hosted-evidence-plan.v1',
        'campaign_id': 'SYNTHETIC_500_OFFLINE_ONLY', 'environment': 'DEV',
        'binding': copy.deepcopy(binding), 'target_connections': 500,
        'window': {'from_ms': START, 'to_ms': START + 500_000},
        'executor_id': 'SYNTHETIC_EXECUTOR_A', 'observer_id': 'SYNTHETIC_OBSERVER_B',
        'limits': {'latency_p95_ms': 6000, 'latency_p99_ms': 12000,
                   'detection_s': 180, 'recovery_s': 300},
    }
    meter = {
        'source': 'IMPORTED_PROVIDER_CAPTURE', 'source_head': binding['source_head'],
        'resources': copy.deepcopy(binding['resources']), 'query': QUERY,
        'query_sha256': binding['query_sha256'],
        'window': {'from_ms': START, 'to_ms': START + 502_000},
        'captured_ms': START + 550_000, 'complete_through_ms': START + 502_000,
        'meters': {name: 100 + index for index, name in enumerate(METERS)},
    }
    receipts = []
    for suffix in ('a', 'b'):
        identity = {'tenant_id': 'tenant-' + suffix, 'device_id': 'device-' + suffix,
                    'call_id': 'call-' + suffix}
        fingerprint = digest({'synthetic_payload': suffix})
        receipt_id = 'SYNTHETIC_RECEIPT_' + suffix
        receipts.append({
            **identity, 'fingerprint': fingerprint, 'claim': copy.deepcopy(identity),
            'complete': {**identity, 'fingerprint': fingerprint, 'receipt_id': receipt_id},
            'effect_count': 1,
            'replay': {'existing': True, 'receipt_id': receipt_id, 'additional_effects': 0},
        })
    evidence = {
        'schema': 'hara.commander.r163.hosted-evidence.v1',
        'campaign_id': plan['campaign_id'], 'binding': copy.deepcopy(binding),
        'live_wss': {
            role: {
                'identity': plan[role + '_id'], 'kind': 'LIVE_WSS',
                'samples': [{'at_ms': START + offset, 'live_connections': 500}
                            for offset in (10_000, 20_000)],
            } for role in ('executor', 'observer')
        },
        'latency_samples_ms': list(range(10, 1001, 10)),
        'latency_summary': {'p95_ms': 950, 'p99_ms': 990},
        'recoveries': [{'device_id': 'device-a', 'fault_at_ms': START + 30_000,
                        'detected_at_ms': START + 150_000,
                        'recovered_at_ms': START + 260_000}],
        'isolation_checks': [{'request_tenant_id': 'tenant-a', 'resource_tenant_id': 'tenant-b',
                              'http_status': 403, 'effect_count': 0}],
        'durable_receipts': receipts,
        'native_meter': meter,
        'post_close_receipt': {
            'receipt_id': 'SYNTHETIC_POST_CLOSE_RECEIPT_REVIEW_ONLY',
            'closed_ms': START + 501_000, 'captured_ms': START + 560_000,
            'open_wss': 0, 'binding_sha256': digest(binding),
            'native_capture_sha256': digest(meter),
        },
    }
    return plan, evidence


class HostedEvidenceTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('hosted_evidence_under_test', MODULE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def validate(self, plan, evidence):
        return self.module.validate_hosted_evidence(plan, evidence, NOW)

    def require_hold(self, plan, evidence):
        result = self.validate(plan, evidence)
        self.assertEqual(result['state'], 'HOLD')
        self.assertIs(result['execute_allowed'], False)
        self.assertTrue(result['reasons'])
        return result

    def test_consistent_small_evidence_is_review_only_never_execution_or_go(self):
        plan, evidence = fixture()
        result = self.validate(plan, evidence)
        self.assertEqual(result['state'], 'REVIEW_ONLY')
        self.assertIs(result['execute_allowed'], False)
        self.assertEqual(result['reasons'], [])
        self.assertEqual(result['observed']['simultaneous_wss'], 500)
        self.assertEqual(result['observed']['latency_p95_ms'], 950)
        self.assertEqual(result['observed']['latency_p99_ms'], 990)
        self.assertEqual(result['observed']['last_detection_s'], 120)
        self.assertEqual(result['observed']['last_recovery_s'], 230)

    def test_approved_true_in_either_file_is_never_an_admission(self):
        for where in ('plan', 'evidence'):
            with self.subTest(where=where):
                plan, evidence = fixture()
                (plan if where == 'plan' else evidence)['approved'] = True
                self.require_hold(plan, evidence)

    def test_source_version_resources_artifacts_query_and_rollback_are_bound(self):
        for field in ('source_head', 'agent_version', 'worker_version', 'resources',
                      'artifacts_sha256', 'query_sha256', 'rollback_sha256'):
            with self.subTest(field=field):
                plan, evidence = fixture()
                if isinstance(evidence['binding'][field], dict):
                    key = next(iter(evidence['binding'][field]))
                    evidence['binding'][field][key] = 'CHANGED_SYNTHETIC_BINDING'
                else:
                    evidence['binding'][field] = 'CHANGED_SYNTHETIC_BINDING'
                self.require_hold(plan, evidence)

    def test_live_executor_and_independent_observer_must_share_a_real_measurement_window(self):
        for failure in ('same_identity', 'cumulative_metric', 'below_target', 'nonoverlap'):
            with self.subTest(failure=failure):
                plan, evidence = fixture()
                observer = evidence['live_wss']['observer']
                if failure == 'same_identity': observer['identity'] = plan['executor_id']
                if failure == 'cumulative_metric': observer['kind'] = 'CUMULATIVE_OPENED_SOCKETS'
                if failure == 'below_target':
                    for sample in observer['samples']: sample['live_connections'] = 499
                if failure == 'nonoverlap':
                    for sample in observer['samples']: sample['at_ms'] += 100_000
                self.require_hold(plan, evidence)

    def test_percentiles_come_from_samples_and_detection_recovery_obey_180_300_slos(self):
        for failure in ('missing_samples', 'forged_summary', 'p99_exceeded', 'detection', 'recovery'):
            with self.subTest(failure=failure):
                plan, evidence = fixture()
                if failure == 'missing_samples': del evidence['latency_samples_ms']
                if failure == 'forged_summary': evidence['latency_summary'] = {'p95_ms': 1, 'p99_ms': 1}
                if failure == 'p99_exceeded':
                    evidence['latency_samples_ms'][-2:] = [12_001, 12_002]
                    evidence['latency_summary'] = {'p95_ms': 950, 'p99_ms': 12_001}
                if failure == 'detection': evidence['recoveries'][0]['detected_at_ms'] = START + 210_001
                if failure == 'recovery': evidence['recoveries'][0]['recovered_at_ms'] = START + 330_001
                self.require_hold(plan, evidence)

    def test_tenant_isolation_and_durable_claim_complete_receipts_fence_effects(self):
        for failure in ('cross_tenant', 'claim_mismatch', 'complete_mismatch', 'missing_receipt', 'replay_effect'):
            with self.subTest(failure=failure):
                plan, evidence = fixture()
                receipt = evidence['durable_receipts'][0]
                if failure == 'cross_tenant': evidence['isolation_checks'][0]['http_status'] = 200
                if failure == 'claim_mismatch': receipt['claim']['device_id'] = 'device-b'
                if failure == 'complete_mismatch': receipt['complete']['tenant_id'] = 'tenant-b'
                if failure == 'missing_receipt': del receipt['complete']['receipt_id']
                if failure == 'replay_effect': receipt['replay']['additional_effects'] = 1
                self.require_hold(plan, evidence)

    def test_all_eleven_native_meters_are_explicit_and_query_scope_is_pinned(self):
        for failure in ('missing', 'null', 'negative', 'query', 'resource'):
            with self.subTest(failure=failure):
                plan, evidence = fixture()
                capture = evidence['native_meter']
                if failure == 'missing': del capture['meters']['do_active_gb_us']
                if failure == 'null': capture['meters']['dlq_billable_ops'] = None
                if failure == 'negative': capture['meters']['worker_cpu_us'] = -1
                if failure == 'query': capture['query'] += ' changed'
                if failure == 'resource': capture['resources']['do_namespace'] = 'OTHER_SYNTHETIC_DO'
                # Keep the receipt hash internally consistent: it cannot rescue
                # incomplete, negative or differently scoped provider evidence.
                evidence['post_close_receipt']['native_capture_sha256'] = digest(capture)
                self.require_hold(plan, evidence)

    def test_post_close_receipt_is_mandatory_and_bound_to_complete_final_metering(self):
        for failure in ('missing', 'still_open', 'early_receipt', 'late_metrics', 'wrong_digest', 'future'):
            with self.subTest(failure=failure):
                plan, evidence = fixture()
                receipt = evidence['post_close_receipt']
                if failure == 'missing': del evidence['post_close_receipt']
                if failure == 'still_open': receipt['open_wss'] = 1
                if failure == 'early_receipt': receipt['captured_ms'] = receipt['closed_ms'] - 1
                if failure == 'late_metrics':
                    evidence['native_meter']['complete_through_ms'] = receipt['closed_ms'] - 1
                    receipt['native_capture_sha256'] = digest(evidence['native_meter'])
                if failure == 'wrong_digest': receipt['native_capture_sha256'] = '0' * 64
                if failure == 'future': receipt['captured_ms'] = NOW + 1
                self.require_hold(plan, evidence)

    def test_preflight_cli_holds_missing_post_close_without_granting_execution(self):
        import subprocess
        import sys
        import tempfile
        plan, evidence = fixture()
        del evidence['post_close_receipt']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'plan.json').write_text(json.dumps(plan))
            (root / 'evidence.json').write_text(json.dumps(evidence))
            result = subprocess.run([sys.executable, '-I', '-B',
                str(MODULE.with_name('event_v2_scale_preflight_r163.py')),
                '--hosted-evidence-plan', str(root / 'plan.json'),
                '--hosted-evidence', str(root / 'evidence.json'),
                '--hosted-evidence-now-ms', str(NOW)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2, result.stderr)
        reviewed = json.loads(result.stdout)['hosted_evidence']
        self.assertEqual(reviewed['state'], 'HOLD')
        self.assertIs(reviewed['execute_allowed'], False)


if __name__ == '__main__':
    unittest.main()
