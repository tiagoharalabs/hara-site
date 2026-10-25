"""Offline #163 ramp arithmetic and stop decisions; never a hosted acceptance.

All observations and receipts below are synthetic test fixtures. No queue, D1,
Agent, VM, network, runtime budget, or rollback operation is executed.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).with_name("event_v2_scale_preflight_r163.py")
PROPOSED = {
    "events": 20000, "queue_ops": 30000, "d1_reads": 5000000,
    "d1_writes": 1500000, "active_ms": 21600000,
}
REVIEW_CAPS = {**PROPOSED, "events": 50000, "queue_ops": 100000}
METERING = {
    "reads_per_device": 11, "writes_per_device": 3,
    "reads_per_event": 7, "writes_per_event": 2,
    "status_polls": 20, "reads_per_status": 1024, "writes_per_status": 4,
}
COUNTERS = tuple(PROPOSED)


def receipt(number):
    event_id = "HARA-REC-" + format(number, "048x")
    fingerprint = hashlib.sha256(("synthetic-payload-" + str(number)).encode()).hexdigest()
    return {
        "tenant_id": "SYNTHETIC-TENANT-A",
        "device_id": "SYNTHETIC-DEVICE-" + str((number - 1) // 2),
        "event_id": event_id, "receipt_event_id": event_id,
        "receipt_tenant_id": "SYNTHETIC-TENANT-A",
        "fingerprint": fingerprint, "receipt_fingerprint": fingerprint,
    }


def observation(*, second_checkpoint=False):
    # Completed 500-device checkpoint, then the repeated 2,000-device cohort.
    first, last, expected = (1001, 5000, 2000) if second_checkpoint else (1, 1000, 500)
    return {
        "counters": {
            "events": last, "queue_ops": 2000 if second_checkpoint else 500,
            "d1_reads": 60000 if second_checkpoint else 12000,
            "d1_writes": 20000 if second_checkpoint else 4000,
            "active_ms": 120000 if second_checkpoint else 60000,
        },
        "active_connections": expected, "expected_connections": expected,
        "last_detection_s": 120.0, "last_recovery_s": 200.0,
        "latency_p95_ms": 500.0, "latency_p99_ms": 1000.0,
        "reconnect_peak_per_s": 10.0,
        "tenant_leaks": 0, "duplicate_effects": 0, "missing_receipts": 0,
        "retry_anomalies": 0, "dlq_unexpected": 0,
        "receipts": [receipt(number) for number in range(first, last + 1)],
    }


class ScalePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("r163_scale_preflight_under_test", MODULE)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def ready_plan(self, **kwargs):
        return self.module.build_plan(proposed=copy.deepcopy(REVIEW_CAPS),
                                      metering=copy.deepcopy(METERING),
                                      reconnect_limit_per_s=25, **kwargs)

    def assert_review_only(self, result):
        self.assertEqual(result["hosted_gate"], "HOSTED_20K_HOLD")
        self.assertIs(result["execute_allowed"], False)

    def assert_stop(self, plan, current, previous=None):
        result = self.module.evaluate_observation(plan, previous, current)
        self.assertEqual(result["state"], "STOP")
        self.assertIs(result["rollback_requested"], True)
        self.assertIsInstance(result["reasons"], list)
        self.assertTrue(result["reasons"])
        self.assert_review_only(result)
        return result

    def assert_continue(self, plan, current, previous=None):
        result = self.module.evaluate_observation(plan, previous, current)
        self.assertEqual(result["state"], "CONTINUE_REVIEW_ONLY")
        self.assertIs(result["rollback_requested"], False)
        self.assert_review_only(result)
        return result

    def test_default_caps_are_exactly_a_proposal_and_never_execution_authority(self):
        plan = self.module.build_plan()
        self.assertEqual(plan["proposed"], PROPOSED)
        self.assert_review_only(plan)
        self.assertEqual(plan["runtime_parity"], "HOLD_AGENT_EVENT_V2_PARITY")

    def test_complete_repeated_ramp_is_45000_events_not_22500(self):
        plan = self.module.build_plan()
        self.assertEqual([stage["devices"] for stage in plan["stages"]], [500, 2000, 20000])
        self.assertEqual([stage["events"] for stage in plan["stages"]], [1000, 4000, 40000])
        self.assertEqual(plan["totals"]["devices"], 22500)
        self.assertEqual(plan["totals"]["events"], 45000)
        self.assertNotEqual(plan["totals"]["events"], plan["totals"]["devices"])

    def test_scan_delivery_jobs_and_twelve_queue_operations_are_cumulative(self):
        plan = self.module.build_plan()
        self.assertEqual([stage["scan_jobs"] for stage in plan["stages"]], [6, 21, 209])
        self.assertEqual([stage["delivery_jobs"] for stage in plan["stages"]], [100, 400, 4000])
        self.assertEqual(plan["totals"]["scan_jobs"], 236)
        self.assertEqual(plan["totals"]["delivery_jobs"], 4500)
        self.assertEqual(plan["totals"]["queue_ops_upper"], 56832)
        self.assertEqual([stage["queue_ops_upper"] for stage in plan["stages"]], [1272, 5052, 50508])

    def test_default_proposed_budget_cannot_cover_the_complete_ramp(self):
        plan = self.module.build_plan()
        self.assertEqual(plan["state"], "HOLD_PLAN_BUDGET")
        self.assertTrue(plan["reasons"])
        self.assert_review_only(plan)

    def test_unbound_d1_metering_is_unknown_not_a_zero_cost_estimate(self):
        plan = self.module.build_plan(proposed=REVIEW_CAPS, reconnect_limit_per_s=25)
        self.assertIsNone(plan["totals"]["d1_reads"])
        self.assertIsNone(plan["totals"]["d1_writes"])
        self.assertEqual(plan["state"], "HOLD_UNBOUND_LIMITS")

    def test_unbound_reconnect_limit_does_not_assume_provider_throughput(self):
        plan = self.module.build_plan(proposed=REVIEW_CAPS, metering=METERING)
        self.assertEqual(plan["state"], "HOLD_UNBOUND_LIMITS")
        self.assert_review_only(plan)

    def test_explicit_synthetic_d1_bounds_include_all_devices_events_and_status_polling(self):
        plan = self.ready_plan()
        self.assertEqual(plan["totals"]["d1_reads"], 22500 * 11 + 45000 * 7 + 20 * 1024)
        self.assertEqual(plan["totals"]["d1_writes"], 22500 * 3 + 45000 * 2 + 20 * 4)
        self.assertEqual(plan["state"], "PLAN_REVIEW_READY")
        self.assert_review_only(plan)

    def test_caps_are_not_reset_between_ramp_stages(self):
        for key, cap in [("events", 40000), ("queue_ops", 55000)]:
            with self.subTest(counter=key):
                caps = {**REVIEW_CAPS, key: cap}
                plan = self.module.build_plan(proposed=caps, metering=METERING, reconnect_limit_per_s=25)
                self.assertEqual(plan["state"], "HOLD_PLAN_BUDGET")
                self.assert_review_only(plan)

    def test_malformed_metering_cannot_create_a_ready_plan(self):
        for change in [{"reads_per_event": True}, {"reads_per_event": float("nan")},
                       {"writes_per_device": -1}, {"status_polls": None}]:
            with self.subTest(change=change):
                try:
                    plan = self.module.build_plan(proposed=REVIEW_CAPS,
                                                  metering={**METERING, **change}, reconnect_limit_per_s=25)
                except (TypeError, ValueError):
                    continue
                self.assertNotEqual(plan["state"], "PLAN_REVIEW_READY")
                self.assert_review_only(plan)

    def test_positive_first_checkpoint_is_review_only_with_correlated_receipts(self):
        self.assert_continue(self.ready_plan(), observation())

    def test_positive_second_checkpoint_uses_cumulative_counters_and_only_new_receipts(self):
        self.assert_continue(self.ready_plan(), observation(second_checkpoint=True), observation())

    def test_missing_current_counters_request_stop_and_rollback(self):
        for field in COUNTERS:
            with self.subTest(counter=field):
                current = observation()
                del current["counters"][field]
                self.assert_stop(self.ready_plan(), current)

    def test_negative_boolean_nan_and_non_numeric_counters_are_not_measurements(self):
        for field in COUNTERS:
            for value in [-1, True, float("nan"), "12"]:
                with self.subTest(counter=field, value=value):
                    current = observation()
                    current["counters"][field] = value
                    self.assert_stop(self.ready_plan(), current)

    def test_missing_or_malformed_counter_container_stops(self):
        for value in [None, [], "measured", {}]:
            with self.subTest(value=value):
                current = observation()
                current["counters"] = value
                self.assert_stop(self.ready_plan(), current)

    def test_decreasing_any_counter_never_authorizes_a_campaign_reset(self):
        previous = observation()
        for field in COUNTERS:
            with self.subTest(counter=field):
                current = observation(second_checkpoint=True)
                current["counters"][field] = previous["counters"][field] - 1
                self.assert_stop(self.ready_plan(), current, previous)

    def test_missing_previous_counter_cannot_silently_become_a_fresh_baseline(self):
        for field in COUNTERS:
            with self.subTest(counter=field):
                previous = observation()
                del previous["counters"][field]
                self.assert_stop(self.ready_plan(), observation(second_checkpoint=True), previous)

    def test_every_cumulative_proposed_cap_is_a_hard_stop_when_exceeded(self):
        plan = self.ready_plan()
        for field, cap in REVIEW_CAPS.items():
            with self.subTest(counter=field):
                previous, current = observation(), observation()
                current["receipts"] = []
                previous["counters"][field] = cap
                current["counters"][field] = cap + 1
                if field == "events":
                    current["receipts"] = [receipt(1001)]
                self.assert_stop(plan, current, previous)

    def test_connection_mismatch_missing_or_invalid_presence_stops(self):
        for field, value in [("active_connections", 499), ("active_connections", True),
                             ("expected_connections", None), ("expected_connections", -1)]:
            with self.subTest(field=field, value=value):
                current = observation()
                if value is None:
                    del current[field]
                else:
                    current[field] = value
                self.assert_stop(self.ready_plan(), current)

    def test_detection_and_recovery_slos_are_180_and_300_seconds(self):
        current = observation()
        current.update(last_detection_s=180.0, last_recovery_s=300.0)
        self.assert_continue(self.ready_plan(), current)
        for field, value in [("last_detection_s", 180.001), ("last_recovery_s", 300.001)]:
            with self.subTest(field=field):
                current = observation()
                current[field] = value
                self.assert_stop(self.ready_plan(), current)

    def test_missing_negative_or_nonfinite_latency_and_liveness_metrics_stop(self):
        for field in ["last_detection_s", "last_recovery_s", "latency_p95_ms", "latency_p99_ms"]:
            for value in [None, -1, float("nan")]:
                with self.subTest(field=field, value=value):
                    current = observation()
                    if value is None:
                        del current[field]
                    else:
                        current[field] = value
                    self.assert_stop(self.ready_plan(), current)

    def test_p99_cannot_be_less_than_p95(self):
        current = observation()
        current.update(latency_p95_ms=1000, latency_p99_ms=500)
        self.assert_stop(self.ready_plan(), current)

    def test_reconnect_requires_a_bound_limit_and_stops_above_it(self):
        unbound = self.module.build_plan(proposed=REVIEW_CAPS, metering=METERING)
        self.assert_stop(unbound, observation())
        current = observation()
        current["reconnect_peak_per_s"] = 25.001
        self.assert_stop(self.ready_plan(), current)

    def test_leaks_duplicate_effects_missing_receipts_retries_and_dlq_stop_independently(self):
        for field in ["tenant_leaks", "duplicate_effects", "missing_receipts", "retry_anomalies", "dlq_unexpected"]:
            with self.subTest(anomaly=field):
                current = observation()
                current[field] = 1
                self.assert_stop(self.ready_plan(), current)

    def test_receipt_count_matches_new_unique_events_not_reserved_or_historical_events(self):
        current = observation()
        current["receipts"].pop()
        self.assert_stop(self.ready_plan(), current)
        current = observation(second_checkpoint=True)
        current["receipts"] = observation()["receipts"] + current["receipts"]
        self.assert_stop(self.ready_plan(), current, observation())

    def test_recipient_tenant_event_and_fingerprint_must_correlate(self):
        for field, value in [("receipt_tenant_id", "OTHER-TENANT"),
                             ("receipt_event_id", "HARA-REC-" + "f" * 48),
                             ("receipt_fingerprint", "f" * 64), ("device_id", "")]:
            with self.subTest(field=field):
                current = observation()
                current["receipts"][0][field] = value
                self.assert_stop(self.ready_plan(), current)

    def test_human_ack_or_missing_receipt_fields_cannot_replace_delivery_evidence(self):
        current = observation()
        current["receipts"][0] = {"ack": "PORTAL_ACKNOWLEDGED", "event_id": receipt(1)["event_id"]}
        self.assert_stop(self.ready_plan(), current)
        current = observation()
        del current["receipts"][0]["receipt_fingerprint"]
        self.assert_stop(self.ready_plan(), current)

    def test_duplicate_event_identity_with_conflicting_payload_in_a_checkpoint_stops(self):
        current = observation()
        current["receipts"][1]["event_id"] = current["receipts"][0]["event_id"]
        current["receipts"][1]["receipt_event_id"] = current["receipts"][0]["event_id"]
        self.assertNotEqual(current["receipts"][0]["fingerprint"], current["receipts"][1]["fingerprint"])
        self.assert_stop(self.ready_plan(), current)

    def test_duplicate_event_payload_conflict_across_checkpoints_stops(self):
        previous, current = observation(), observation(second_checkpoint=True)
        current["receipts"][0]["event_id"] = previous["receipts"][0]["event_id"]
        current["receipts"][0]["receipt_event_id"] = previous["receipts"][0]["event_id"]
        self.assertNotEqual(previous["receipts"][0]["fingerprint"], current["receipts"][0]["fingerprint"])
        self.assert_stop(self.ready_plan(), current, previous)

    def test_positive_review_does_not_clear_agent_parity_or_accept_input_approval_claims(self):
        current = observation()
        current.update(execute_allowed=True, hosted_gate="GO", approved=True)
        plan = self.ready_plan()
        self.assertEqual(plan["runtime_parity"], "HOLD_AGENT_EVENT_V2_PARITY")
        result = self.module.evaluate_observation(plan, None, current)
        self.assertIn(result["state"], ["STOP", "CONTINUE_REVIEW_ONLY"])
        self.assert_review_only(result)
        self.assert_review_only(plan)

    def test_ramp_cannot_skip_cohorts_or_report_fewer_events_than_devices_require(self):
        self.assert_stop(self.ready_plan(), observation(second_checkpoint=True))
        current=observation();current['counters']['events']=1;current['receipts']=current['receipts'][:1]
        self.assert_stop(self.ready_plan(),current)

    def test_receipt_identity_and_fingerprint_are_strict_not_just_equal_strings(self):
        for key,pair in [('event_id','receipt_event_id'),('fingerprint','receipt_fingerprint')]:
            current=observation();current['receipts'][0][key]='human-ack';current['receipts'][0][pair]='human-ack'
            self.assert_stop(self.ready_plan(),current)

    def test_cumulative_history_is_carried_to_later_cohorts_and_cannot_be_omitted(self):
        first=observation();a=self.assert_continue(self.ready_plan(),first)
        second=observation(second_checkpoint=True)
        b=self.assert_continue(self.ready_plan(),second,a['next_checkpoint'])
        self.assertEqual(len(b['next_checkpoint']['receipt_history']),5000)
        third=copy.deepcopy(second);third.update(active_connections=20000,expected_connections=20000)
        third['counters']={**third['counters'],'events':45000};third['receipts']=[]
        result=self.assert_stop(self.ready_plan(),third,second)
        self.assertIn('MISSING_CUMULATIVE_RECEIPT_HISTORY',result['reasons'])


if __name__ == "__main__":
    unittest.main()
