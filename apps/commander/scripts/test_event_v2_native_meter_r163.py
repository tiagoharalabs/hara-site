"""Synthetic exports only: no provider request, credential or billable work."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import time
import unittest


MODULE = Path(__file__).with_name('event_v2_native_meter_r163.py')
QUERY = 'query NativeMeter($accountTag:string!){viewer{accounts(filter:{accountTag:$accountTag}){accountTag}}}'
NOW = int(time.time())
ACCOUNT = 'a' * 32
HEAD = 'b' * 40


def fixture():
    policy = {
        'schema': 'hara.commander.r163.native-meter-policy.v1',
        'source_head': HEAD,
        'account_id': ACCOUNT,
        'resources': {'worker': 'qa-only', 'do_namespace': 'c' * 32,
                      'd1_database': 'synthetic-database', 'queues': ['d' * 32, 'e' * 32]},
        'query_sha256': hashlib.sha256(QUERY.encode()).hexdigest(),
        'variables': {'accountTag': ACCOUNT,
                      'namespace': 'c' * 32, 'worker': 'qa-only'},
        'window_start': NOW - 1000,
        'max_age_seconds': 120,
        'max_ingestion_lag_seconds': 120,
        'limits': {'do_requests': 1000, 'do_storage_bytes': 100000,
                   'd1_reads': 10000, 'd1_writes': 1000, 'queue_ops': 5000},
    }
    account = {
        'accountTag': ACCOUNT,
        'durableObjectsInvocationsAdaptiveGroups': [{'sum': {'requests': 20}}],
        'durableObjectsStorageGroups': [{'max': {'storedBytes': 4096}}],
        'd1AnalyticsAdaptiveGroups': [{'sum': {'rowsRead': 100, 'rowsWritten': 10}}],
        'queueMessageOperationsAdaptiveGroups': [
            {'sum': {'billableOperations': 3}}, {'sum': {'billableOperations': 6}}],
    }
    capture = {
        'schema': 'hara.commander.r163.native-meter-capture.v1',
        'source_head': HEAD, 'resources': copy.deepcopy(policy['resources']),
        'captured_at': NOW - 10, 'window_start': NOW - 1000, 'window_end': NOW - 20,
        'rows_complete': True,
        'request': {'query': QUERY, 'variables': {**policy['variables'], 'start': NOW - 1000, 'end': NOW - 20}},
        'response': {'data': {'viewer': {'accounts': [account]}}},
    }
    return policy, capture


class NativeMeterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('native_meter_under_test', MODULE)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def evaluate(self, policy=None, capture=None, previous=None):
        p, c = fixture()
        return self.module.evaluate_native_meter(policy or p, capture or c, previous, now=NOW)

    def preflight_objects(self):
        path = MODULE.with_name('test_event_v2_scale_preflight_r163.py')
        spec = importlib.util.spec_from_file_location('existing_preflight_fixtures', path)
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        spec = importlib.util.spec_from_file_location('preflight_integration_under_test', fixtures.MODULE)
        preflight = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(preflight)
        plan = preflight.build_plan(proposed=fixtures.REVIEW_CAPS, metering=fixtures.METERING, reconnect_limit_per_s=25)
        return preflight, fixtures, plan

    def test_documented_raw_fields_are_not_caller_normalized_counters(self):
        result = self.evaluate()
        self.assertEqual(result['state'], 'CONTINUE_REVIEW_ONLY')
        self.assertEqual(result['observed'], {'do_requests': 20, 'do_storage_bytes': 4096,
                                            'd1_reads': 100, 'd1_writes': 10, 'queue_ops': 9})
        self.assertIs(result['execute_allowed'], False)
        self.assertEqual(result['claim'], 'IMPORTED_PROVIDER_EXPORT_NOT_NATIVE_ADMISSION')
        self.assertIsNone(result['total_cost_usd'])

    def test_cumulative_exports_are_replaced_not_added_on_overlapping_poll(self):
        first = self.evaluate()
        policy, capture = fixture()
        capture['window_end'] += 1
        capture['request']['variables']['end'] = capture['window_end']
        capture['response']['data']['viewer']['accounts'][0]['d1AnalyticsAdaptiveGroups'][0]['sum']['rowsRead'] = 125
        result = self.evaluate(policy, capture, first['next_checkpoint'])
        self.assertEqual(result['observed']['d1_reads'], 125)

    def test_counter_decrease_and_changed_baseline_fail_closed(self):
        first = self.evaluate()['next_checkpoint']
        for change in ['counter', 'baseline', 'end', 'identity', 'highwater']:
            p, c = fixture()
            old = copy.deepcopy(first)
            if change == 'counter': c['response']['data']['viewer']['accounts'][0]['d1AnalyticsAdaptiveGroups'][0]['sum']['rowsRead'] = 99
            if change == 'baseline': c['window_start'] += 1
            if change == 'end': c['window_end'] -= 1
            if change == 'identity': old['policy_sha256'] = 'f' * 64
            if change == 'highwater': old['high_water']['do_storage_bytes'] = 0
            with self.subTest(change=change): self.assertEqual(self.evaluate(p, c, old)['state'], 'STOP')

    def test_missing_native_dimension_is_unknown_never_zero(self):
        p, c = fixture()
        p['limits']['do_duration_gb_s'] = 100
        result = self.evaluate(p, c)
        self.assertEqual(result['state'], 'STOP')
        self.assertIsNone(result['observed']['do_duration_gb_s'])
        self.assertIn('NATIVE_METRIC_UNAVAILABLE_DO_DURATION_GB_S', result['reasons'])

    def test_required_dataset_missing_empty_or_null_is_not_zero(self):
        for value in [None, [], 'zero', {}]:
            p, c = fixture()
            c['response']['data']['viewer']['accounts'][0]['durableObjectsInvocationsAdaptiveGroups'] = value
            with self.subTest(value=value): self.assertEqual(self.evaluate(p, c)['state'], 'STOP')

    def test_native_zero_is_valid_only_as_explicit_provider_value(self):
        p, c = fixture()
        c['response']['data']['viewer']['accounts'][0]['durableObjectsInvocationsAdaptiveGroups'][0]['sum']['requests'] = 0
        result = self.evaluate(p, c)
        self.assertEqual(result['state'], 'CONTINUE_REVIEW_ONLY')
        self.assertEqual(result['observed']['do_requests'], 0)

    def test_nonfinite_negative_boolean_or_string_native_values_are_denied(self):
        for value in [None, -1, True, '20', float('nan'), float('inf'), 10**500]:
            p, c = fixture()
            c['response']['data']['viewer']['accounts'][0]['durableObjectsInvocationsAdaptiveGroups'][0]['sum']['requests'] = value
            with self.subTest(value=value): self.assertEqual(self.evaluate(p, c)['state'], 'STOP')

    def test_provider_errors_partial_rows_or_extra_account_are_denied(self):
        for change in ['errors', 'incomplete', 'account', 'multiaccount']:
            p, c = fixture()
            if change == 'errors': c['response']['errors'] = [{'message': 'synthetic denied'}]
            if change == 'incomplete': c['rows_complete'] = False
            if change == 'account': c['response']['data']['viewer']['accounts'][0]['accountTag'] = 'f' * 32
            if change == 'multiaccount': c['response']['data']['viewer']['accounts'].append(copy.deepcopy(c['response']['data']['viewer']['accounts'][0]))
            with self.subTest(change=change): self.assertEqual(self.evaluate(p, c)['state'], 'STOP')

    def test_query_variables_resources_and_source_are_bound(self):
        for change in ['query', 'variables', 'resources', 'source']:
            p, c = fixture()
            if change == 'query': c['request']['query'] += ' # changed'
            if change == 'variables': c['request']['variables']['namespace'] = 'f' * 32
            if change == 'resources': c['resources']['worker'] = 'production'
            if change == 'source': c['source_head'] = 'f' * 40
            with self.subTest(change=change): self.assertEqual(self.evaluate(p, c)['state'], 'STOP')

    def test_stale_future_and_lagging_exports_do_not_pass(self):
        for change in ['stale', 'future', 'lag', 'order']:
            p, c = fixture()
            if change == 'stale': c['captured_at'] = NOW - 121
            if change == 'future': c['captured_at'] = NOW + 1
            if change == 'lag': c['window_end'] = NOW - 200
            if change == 'order': c['window_end'] = c['captured_at'] + 1
            with self.subTest(change=change): self.assertEqual(self.evaluate(p, c)['state'], 'STOP')

    def test_any_observed_limit_exceeded_stops(self):
        for key in fixture()[0]['limits']:
            p, c = fixture()
            p['limits'][key] = 1
            with self.subTest(key=key): self.assertIn('NATIVE_BUDGET_EXCEEDED_' + key.upper(), self.evaluate(p, c)['reasons'])

    def test_storage_uses_maximum_not_sum_and_does_not_require_monotonic_gauge(self):
        p, c = fixture()
        rows = c['response']['data']['viewer']['accounts'][0]['durableObjectsStorageGroups']
        rows.append({'max': {'storedBytes': 2048}})
        first = self.evaluate(p, c)
        self.assertEqual(first['observed']['do_storage_bytes'], 4096)
        rows[0]['max']['storedBytes'] = 1024
        result = self.evaluate(p, c, first['next_checkpoint'])
        self.assertEqual(result['state'], 'CONTINUE_REVIEW_ONLY')
        self.assertEqual(result['observed']['do_storage_bytes'], 2048)
        self.assertEqual(result['next_checkpoint']['high_water']['do_storage_bytes'], 4096)

    def test_caller_approved_flag_never_becomes_execution_authority(self):
        p, c = fixture()
        for target in [p, c]:
            target['approved'] = True
        result = self.evaluate(p, c)
        self.assertIs(result['execute_allowed'], False)
        self.assertIn('NATIVE_FILE_APPROVAL_REJECTED', result['reasons'])

    def test_json_duplicates_nonfinite_and_oversized_inputs_are_rejected(self):
        for raw in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            with self.subTest(raw=raw), self.assertRaises(ValueError): self.module.parse_json(raw)

    def test_preflight_currently_must_not_ignore_a_required_missing_native_meter(self):
        preflight, fixtures, plan = self.preflight_objects()
        policy, capture = fixture()
        policy['limits']['do_duration_gb_s'] = 100
        plan['native_meter_policy'] = policy
        current = fixtures.observation()
        current['native_meter_capture'] = capture
        result = preflight.evaluate_observation(plan, None, current)
        self.assertEqual(result['state'], 'STOP')
        self.assertIn('NATIVE_METRIC_UNAVAILABLE_DO_DURATION_GB_S', result['reasons'])

    def test_preflight_carries_native_checkpoint_and_refuses_its_removal(self):
        preflight, fixtures, plan = self.preflight_objects()
        policy, capture = fixture()
        plan['native_meter_policy'] = policy
        current = fixtures.observation()
        current['native_meter_capture'] = capture
        first = preflight.evaluate_observation(plan, None, current)
        self.assertEqual(first['state'], 'CONTINUE_REVIEW_ONLY')
        checkpoint = first['next_checkpoint']
        self.assertIn('native_meter_checkpoint', checkpoint)
        second = fixtures.observation(second_checkpoint=True)
        second['native_meter_capture'] = capture
        result = preflight.evaluate_observation(plan, checkpoint, second)
        self.assertEqual(result['state'], 'CONTINUE_REVIEW_ONLY')
        del checkpoint['native_meter_checkpoint']
        result = preflight.evaluate_observation(plan, checkpoint, second)
        self.assertEqual(result['state'], 'STOP')
        self.assertIn('NATIVE_PREVIOUS_CHECKPOINT_MISSING', result['reasons'])

    def test_preflight_rejects_an_unbound_capture_instead_of_ignoring_it(self):
        preflight, fixtures, plan = self.preflight_objects()
        current = fixtures.observation()
        current['native_meter_capture'] = fixture()[1]
        result = preflight.evaluate_observation(plan, None, current)
        self.assertEqual(result['state'], 'STOP')
        self.assertIn('NATIVE_POLICY_OR_CAPTURE_INVALID', result['reasons'])


if __name__ == '__main__': unittest.main()
