"""Offline scope/cost bounds; never reads or mutates a Cloudflare account."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('budget_envelope', Path(__file__).with_name('event_v2_scale_preflight_r163.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BudgetEnvelope(unittest.TestCase):
    def test_four_state_guardian_campaign_cannot_fit_the_two_event_proposals(self):
        result = MODULE.build_budget_alternatives()
        for key, events, queue in [('full', 90000, 110832), ('reduced', 40000, 50832)]:
            with self.subTest(scope=key):
                item = result['alternatives'][key]
                self.assertEqual(item['p0_322_four_state_envelope']['events'], events)
                self.assertEqual(item['p0_322_four_state_envelope']['queue_ops_upper'], queue)
                self.assertFalse(item['p0_322_four_state_envelope']['fits_proposed_events_and_queue'])
                self.assertTrue(item['requires_native_admission'])
                self.assertFalse(item['execute_allowed'])

    def test_published_rates_are_a_reference_not_an_account_invoice(self):
        result = MODULE.build_budget_alternatives()
        reference = result['pricing_reference']
        self.assertEqual(reference['observed_on'], '2026-10-25')
        self.assertEqual(reference['usd_per_million']['d1_reads'], 0.001)
        self.assertEqual(reference['usd_per_million']['d1_writes'], 1.0)
        self.assertEqual(reference['usd_per_million']['queue_ops'], 0.40)
        self.assertEqual(reference['usd_per_million']['do_requests'], 0.15)
        self.assertIsNone(result['cost']['total_usd'])
        self.assertFalse(reference['account_allocation_verified'])

    def test_partial_queue_unit_exposure_is_not_promoted_to_total_cost(self):
        result = MODULE.build_budget_alternatives()
        for key, ops in [('full', 56832), ('reduced', 26832)]:
            exposure = result['alternatives'][key]['unit_rate_exposure']
            self.assertAlmostEqual(exposure['queue_usd_equivalent'], ops * 0.40 / 1000000)
            self.assertIsNone(exposure['d1_usd_equivalent'])
            self.assertIsNone(exposure['total_usd'])
            self.assertEqual(exposure['claim'], 'PARTIAL_MODEL_BEFORE_ACCOUNT_ALLOWANCES_AND_ROUNDING')

    def test_agent_four_states_plus_independent_server_pair_are_both_budgeted(self):
        result = MODULE.build_budget_alternatives()
        for key, events, ops in [('full', 135000, 164832), ('reduced', 60000, 74832)]:
            envelope = result['alternatives'][key]['p0_322_combined_envelope']
            self.assertEqual(envelope['events'], events)
            self.assertEqual(envelope['queue_ops_upper'], ops)
            self.assertEqual(envelope['states_per_device_upper'], 6)
            self.assertFalse(envelope['fits_proposed_events_and_queue'])
        self.assertTrue(result['native_budget_gaps']['do_alarm_ops'])
        self.assertTrue(result['native_budget_gaps']['do_storage_and_duration'])


if __name__ == '__main__':
    unittest.main()
