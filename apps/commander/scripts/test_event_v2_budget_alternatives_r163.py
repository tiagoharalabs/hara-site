"""Offline #163 budget alternatives; a proposal never authorizes a campaign.

No hosted resources, native budgets, Agents, queues, databases or network calls.
These tests cover alternative scope/arithmetic, not the earlier checkpoint suite.
"""
import copy
import importlib.util
import json
from pathlib import Path
import unittest


MODULE = Path(__file__).with_name("event_v2_scale_preflight_r163.py")
PROPOSED = {
    "events": 20000, "queue_ops": 30000, "d1_reads": 5000000,
    "d1_writes": 1500000, "active_ms": 21600000,
}
METERING = {
    "reads_per_device": 11, "writes_per_device": 3,
    "reads_per_event": 7, "writes_per_event": 2,
    "status_polls": 20, "reads_per_status": 1024, "writes_per_status": 4,
}
MEASUREMENTS = {
    "d1_reads", "d1_writes", "do_websocket_ops", "do_alarm_ops",
    "do_connection_duration_ms", "latency_p95_ms", "latency_p99_ms",
    "last_detection_s", "last_recovery_s",
}
COSTS = {
    "d1_usd", "queue_usd", "do_websocket_usd", "do_alarm_usd",
    "do_connection_duration_usd", "total_usd",
}


class BudgetAlternativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("r163_budget_alternatives_under_test", MODULE)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def build(self, **kwargs):
        return self.module.build_budget_alternatives(**kwargs)

    def assert_proposal_only(self, result):
        self.assertIs(result["execute_allowed"], False)
        self.assertEqual(result["hosted_gate"], "HOSTED_20K_HOLD")
        self.assertEqual(result["approval_status"], "NOT_APPROVED")

    def test_default_output_exposes_exactly_full_and_reduced_proposals(self):
        result = self.build()
        self.assertEqual(result["proposed"], PROPOSED)
        self.assertEqual(set(result["alternatives"]), {"full", "reduced"})
        self.assert_proposal_only(result)
        for alternative in result["alternatives"].values():
            self.assert_proposal_only(alternative)
            self.assertEqual(alternative["runtime_parity"], "HOLD_AGENT_EVENT_V2_PARITY")

    def test_full_alternative_keeps_disjoint_22500_devices_and_45000_events(self):
        full = self.build()["alternatives"]["full"]
        self.assertEqual(full["cohort_mode"], "DISJOINT")
        self.assertEqual(full["unique_devices"], 22500)
        self.assertEqual(full["device_observations"], 22500)
        self.assertEqual(full["connection_target"], 20000)
        self.assertEqual(full["recovery_selected_devices"], 22500)
        self.assertEqual(full["recovery_events_per_device"], 2)
        self.assertEqual([row["devices"] for row in full["stages"]], [500, 2000, 20000])
        self.assertEqual([row["events"] for row in full["stages"]], [1000, 4000, 40000])
        self.assertEqual(full["totals"]["events"], 45000)
        self.assertEqual(full["totals"]["queue_ops_upper"], 56832)

    def test_full_alternative_requires_a_new_explicit_budget_without_approving_it(self):
        full = self.build()["alternatives"]["full"]
        self.assertIs(full["requires_new_budget"], True)
        self.assertEqual(full["state"], "HOLD_PLAN_BUDGET")
        self.assertGreater(full["totals"]["events"], full["proposed"]["events"])
        self.assertGreater(full["totals"]["queue_ops_upper"], full["proposed"]["queue_ops"])
        self.assertIs(full["full_20k_recovery_target"], True)
        self.assertIs(full["full_20k_recovery_homologated"], False)
        self.assert_proposal_only(full)

    def test_reduced_alternative_reuses_connection_cohorts_without_duplicate_recovery_events(self):
        reduced = self.build()["alternatives"]["reduced"]
        self.assertEqual(reduced["cohort_mode"], "NESTED_REUSED")
        self.assertEqual(reduced["unique_devices"], 20000)
        self.assertEqual(reduced["device_observations"], 22500)
        self.assertEqual(reduced["connection_target"], 20000)
        self.assertEqual([row["devices"] for row in reduced["stages"]], [500, 2000, 20000])
        self.assertEqual([row["events"] for row in reduced["stages"]], [0, 0, 20000])
        self.assertEqual(reduced["recovery_selected_devices"], 10000)
        self.assertEqual(reduced["recovery_events_per_device"], 2)
        self.assertEqual(reduced["totals"]["events"], 20000)
        self.assertEqual(reduced["stages"][-1]["events"],
                         reduced["recovery_selected_devices"] * reduced["recovery_events_per_device"])

    def test_reduced_queue_bound_includes_all_scans_and_only_20000_delivery_events(self):
        reduced = self.build()["alternatives"]["reduced"]
        self.assertEqual([row["scan_jobs"] for row in reduced["stages"]], [6, 21, 209])
        self.assertEqual([row["delivery_jobs"] for row in reduced["stages"]], [0, 0, 2000])
        self.assertEqual(reduced["totals"]["queue_ops_upper"], 26832)
        self.assertLessEqual(reduced["totals"]["events"], PROPOSED["events"])
        self.assertLessEqual(reduced["totals"]["queue_ops_upper"], PROPOSED["queue_ops"])
        self.assertIs(reduced["requires_new_budget"], False)

    def test_reduced_scope_never_claims_full_20000_device_recovery_homologation(self):
        reduced = self.build()["alternatives"]["reduced"]
        self.assertIs(reduced["full_20k_recovery_target"], False)
        self.assertIs(reduced["full_20k_recovery_homologated"], False)
        self.assertLess(reduced["recovery_selected_devices"], reduced["connection_target"])
        self.assert_proposal_only(reduced)

    def test_unbound_d1_and_throughput_remain_unknown_without_zero_cost_or_readiness(self):
        result = self.build()
        for alternative in result["alternatives"].values():
            self.assertEqual(alternative["metering_basis"], "UNBOUND")
            self.assertIsNone(alternative["totals"]["d1_reads"])
            self.assertIsNone(alternative["totals"]["d1_writes"])
            self.assertIsNone(alternative["reconnect_limit_per_s"])
        self.assertEqual(result["alternatives"]["reduced"]["state"], "HOLD_UNBOUND_LIMITS")

    def test_supplied_unit_bounds_produce_a_model_not_measured_d1_consumption(self):
        result = self.build(metering=METERING, reconnect_limit_per_s=25)
        for name, events in [("full", 45000), ("reduced", 20000)]:
            with self.subTest(alternative=name):
                alternative = result["alternatives"][name]
                self.assertEqual(alternative["metering_basis"], "MODEL_FROM_SUPPLIED_UNIT_BOUNDS")
                self.assertEqual(alternative["totals"]["d1_reads"], 22500 * 11 + events * 7 + 20 * 1024)
                self.assertEqual(alternative["totals"]["d1_writes"], 22500 * 3 + events * 2 + 20 * 4)
                self.assertIsNone(result["measurements"]["d1_reads"])
                self.assertIsNone(result["measurements"]["d1_writes"])
        self.assertEqual(result["alternatives"]["reduced"]["state"], "PLAN_REVIEW_READY")
        self.assert_proposal_only(result["alternatives"]["reduced"])

    def test_unmeasured_do_operations_duration_latency_and_cost_are_null(self):
        result = self.build(metering=METERING, reconnect_limit_per_s=25)
        self.assertTrue(MEASUREMENTS.issubset(result["measurements"]))
        self.assertTrue(COSTS.issubset(result["cost"]))
        for field in MEASUREMENTS:
            with self.subTest(measurement=field):
                self.assertIsNone(result["measurements"][field])
        for field in COSTS:
            with self.subTest(cost=field):
                self.assertIsNone(result["cost"][field])
        json.dumps(result, allow_nan=False)

    def test_smaller_caps_cannot_be_hidden_by_reuse_or_reset_between_stages(self):
        for field, cap in [("events", 19999), ("queue_ops", 26831)]:
            with self.subTest(counter=field):
                proposed = {**PROPOSED, field: cap}
                result = self.build(proposed=proposed, metering=METERING, reconnect_limit_per_s=25)
                reduced = result["alternatives"]["reduced"]
                self.assertEqual(reduced["proposed"], proposed)
                self.assertEqual(reduced["state"], "HOLD_PLAN_BUDGET")
                self.assert_proposal_only(reduced)

    def test_larger_proposed_caps_make_math_reviewable_but_never_admit_execution(self):
        proposed = {**PROPOSED, "events": 50000, "queue_ops": 100000}
        result = self.build(proposed=proposed, metering=METERING, reconnect_limit_per_s=25)
        self.assert_proposal_only(result)
        for alternative in result["alternatives"].values():
            self.assertEqual(alternative["state"], "PLAN_REVIEW_READY")
            self.assertEqual(alternative["proposed"], proposed)
            self.assertIs(alternative["full_20k_recovery_homologated"], False)
            self.assert_proposal_only(alternative)

    def test_slos_and_rollback_remain_explicit_without_executing_any_action(self):
        result = self.build(metering=METERING, reconnect_limit_per_s=25)
        for alternative in result["alternatives"].values():
            self.assertEqual(alternative["limits"]["last_detection_s"], 180)
            self.assertEqual(alternative["limits"]["last_recovery_s"], 300)
            self.assertIs(alternative["rollback"]["automatic_execution"], False)
            self.assertTrue(alternative["rollback"]["requested_operations"])
        # Missing evidence is a stop decision, even for the mathematically
        # affordable alternative. This invokes no native rollback writer.
        reduced = result["alternatives"]["reduced"]
        evaluated = self.module.evaluate_observation(reduced, None, {})
        self.assertEqual(evaluated["state"], "STOP")
        self.assertTrue(evaluated["reasons"])
        self.assertIs(evaluated["rollback_requested"], True)
        self.assertIs(evaluated["execute_allowed"], False)
        self.assertEqual(evaluated["hosted_gate"], "HOSTED_20K_HOLD")

    def test_building_alternatives_does_not_rewrite_supplied_proposals_or_unit_bounds(self):
        proposed, metering = copy.deepcopy(PROPOSED), copy.deepcopy(METERING)
        self.build(proposed=proposed, metering=metering, reconnect_limit_per_s=25)
        self.assertEqual(proposed, PROPOSED)
        self.assertEqual(metering, METERING)


if __name__ == "__main__":
    unittest.main()
