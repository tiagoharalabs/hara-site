"""Offline financial decision fixtures; no price or resource below is admitted.

Rates, billing units, caps and identities are deliberately synthetic. Official
documentation URLs identify the required reference shape, not verification of
these fixture rates, an invoice, an account allocation or permission to run.
"""
import copy
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import unittest


MODULE = Path(__file__).with_name("event_v2_campaign_decision_r163.py")
SOURCE_HEAD = "f" * 40
METERS = (
    "worker_requests", "worker_cpu_us", "do_requests", "do_active_gb_us",
    "do_storage_reads", "do_storage_writes", "do_storage_byte_seconds",
    "d1_rows_read", "d1_rows_written", "queue_billable_ops", "dlq_billable_ops",
)


def fixture():
    caps = {meter: 100001 for meter in METERS}
    pricing = {}
    for index, meter in enumerate(METERS):
        product = ("workers" if meter.startswith("worker_") else
                   "durable-objects" if meter.startswith("do_") else
                   "d1" if meter.startswith("d1_") else "queues")
        pricing[meter] = {
            "usd_per_unit": format(Decimal("0.000000001") * (index + 1), "f"),
            "reference": "https://developers.cloudflare.com/" + product + "/platform/pricing/",
            "billing_unit": "SYNTHETIC_REVIEW_UNIT_" + meter,
            "rounding_units": 1000 if index % 2 else 128,
        }
    resources = {
        "account_id": "1" * 32,
        "worker": "synthetic-r163-worker-review-only",
        "worker_version": "11111111-1111-4111-8111-111111111111",
        "do_namespace": "2" * 32,
        "d1_database": "22222222-2222-4222-8222-222222222222",
        "queue": "synthetic-r163-queue-review-only",
        "dlq": "synthetic-r163-dlq-review-only",
        "recipient": "synthetic-r163-recipient-review-only",
        "cohort_sha256": "3" * 64,
    }
    stop = {
        "owner": "SYNTHETIC_OWNER_REVIEW_ONLY",
        "executor_ref": "SYNTHETIC_NATIVE_EXECUTOR_REF",
        "stop_ref": "SYNTHETIC_NATIVE_STOP_REF",
        "rollback_version": "33333333-3333-4333-8333-333333333333",
        "rollback_sha256": "4" * 64,
        "concurrency_limit": 4, "reconnect_limit_per_s": 25,
        "active_ms": 3600000,
    }
    return {"caps": caps, "pricing": pricing, "resources": resources, "stop": stop}


def expected_model(caps, pricing):
    # An independent exact-Decimal calculation includes every billing meter,
    # including storage duration, Worker CPU and DLQ. No float/currency truncation.
    values = {}
    for meter in METERS:
        quantum = pricing[meter]["rounding_units"]
        rounded = ((caps[meter] + quantum - 1) // quantum) * quantum
        values[meter] = Decimal(rounded) * Decimal(pricing[meter]["usd_per_unit"])
    return values


class CampaignDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("r163_campaign_decision_under_test", MODULE)
        cls.module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.module
        spec.loader.exec_module(cls.module)

    def build(self, data=None, *, source_head=SOURCE_HEAD, alternative="A", **kwargs):
        return self.module.build_decision(source_head, alternative=alternative,
                                          **(data or {}), **kwargs)

    def assert_unapproved(self, result):
        self.assertEqual(result["approval_status"], "NOT_APPROVED")
        self.assertIs(result["execute_allowed"], False)
        self.assertEqual(result["hosted_gate"], "HOSTED_20K_HOLD")
        self.assertIsNone(result["actual_cost_usd"])

    def assert_incomplete_hold(self, result):
        self.assertEqual(result["state"], "HOLD")
        self.assertTrue(result["reasons"])
        self.assertIsNone(result["modeled_max_usd"])
        self.assertEqual(set(result["modeled_by_meter_usd"]), set(METERS))
        self.assertTrue(all(value is None for value in result["modeled_by_meter_usd"].values()))
        self.assert_unapproved(result)

    def test_default_five_dollar_ceiling_is_an_incomplete_unapproved_proposal(self):
        result = self.build()
        self.assertEqual(result["alternative"], "A")
        self.assertEqual(result["max_total_usd"], "5.00")
        self.assert_incomplete_hold(result)

    def test_complete_A_models_all_eleven_meters_exactly_and_holds_above_the_ceiling(self):
        data = fixture()
        result = self.build(data)
        expected = expected_model(data["caps"], data["pricing"])
        self.assertEqual(result["state"], "REVIEW_ONLY")
        self.assertEqual(result["source_head"], SOURCE_HEAD)
        self.assertEqual(result["campaign"]["totals"]["events"], 45000)
        self.assertEqual(result["campaign"]["totals"]["queue_ops_upper"], 56832)
        self.assertEqual(result["cohort_observer_reads_hint"], 22500)
        self.assertEqual(set(result["modeled_by_meter_usd"]), set(METERS))
        for meter in METERS:
            with self.subTest(meter=meter):
                self.assertIsInstance(result["modeled_by_meter_usd"][meter], str)
                self.assertEqual(Decimal(result["modeled_by_meter_usd"][meter]), expected[meter])
        self.assertEqual(Decimal(result["modeled_max_usd"]), sum(expected.values(), Decimal(0)))
        self.assert_unapproved(result)
        data["pricing"]["worker_cpu_us"]["usd_per_unit"] = "1.00"
        expensive = self.build(data)
        self.assertEqual(expensive["state"], "HOLD")
        self.assertGreater(Decimal(expensive["modeled_max_usd"]), Decimal("5.00"))
        self.assertTrue(expensive["reasons"])
        self.assert_unapproved(expensive)

    def test_B_preserves_20k_connections_but_only_10k_recovery_devices(self):
        data = fixture()
        data["caps"]["queue_billable_ops"] = 26832
        result = self.build(data, alternative="B")
        self.assertEqual(result["state"], "REVIEW_ONLY")
        self.assertEqual(result["alternative"], "B")
        campaign = result["campaign"]
        self.assertEqual(campaign["connection_target"], 20000)
        self.assertEqual(campaign["recovery_selected_devices"], 10000)
        self.assertEqual(campaign["totals"]["events"], 20000)
        self.assertEqual(campaign["totals"]["queue_ops_upper"], 26832)
        self.assertIs(campaign["full_20k_recovery_target"], False)
        self.assertIs(campaign["full_20k_recovery_homologated"], False)
        self.assertEqual(result["cohort_observer_reads_hint"], 22500)
        self.assert_unapproved(result)

    def test_queue_caps_must_cover_the_chosen_cumulative_alternative(self):
        for alternative, required in [("A", 56832), ("B", 26832)]:
            with self.subTest(alternative=alternative):
                data = fixture()
                data["caps"]["queue_billable_ops"] = required - 1
                result = self.build(data, alternative=alternative)
                self.assertEqual(result["state"], "HOLD")
                self.assertTrue(result["reasons"])
                self.assert_unapproved(result)

    def test_missing_native_resources_stop_references_or_source_head_cannot_yield_a_total(self):
        cases = []
        for field in ["account_id", "worker_version", "do_namespace", "cohort_sha256"]:
            data = fixture()
            del data["resources"][field]
            cases.append((field, data, SOURCE_HEAD))
        for field in ["owner", "stop_ref", "rollback_sha256"]:
            data = fixture()
            del data["stop"][field]
            cases.append((field, data, SOURCE_HEAD))
        cases.append(("source_head", fixture(), "not-a-native-source-head"))
        for name, data, head in cases:
            with self.subTest(missing=name):
                self.assert_incomplete_hold(self.build(data, source_head=head))

    def test_unknown_or_invalid_caps_rates_references_and_rounding_are_not_free_usage(self):
        for name in ["missing-cap", "zero-cap", "boolean-cap", "missing-rate",
                     "NaN-rate", "non-string-rate", "reference", "rounding"]:
            with self.subTest(invalid=name):
                data = fixture()
                if name == "missing-cap":
                    del data["caps"]["do_storage_byte_seconds"]
                elif name == "zero-cap":
                    data["caps"]["d1_rows_read"] = 0
                elif name == "boolean-cap":
                    data["caps"]["do_active_gb_us"] = True
                elif name == "missing-rate":
                    del data["pricing"]["worker_cpu_us"]
                elif name == "NaN-rate":
                    data["pricing"]["worker_cpu_us"]["usd_per_unit"] = "NaN"
                elif name == "non-string-rate":
                    data["pricing"]["worker_cpu_us"]["usd_per_unit"] = 0.01
                elif name == "reference":
                    data["pricing"]["dlq_billable_ops"]["reference"] = "UNKNOWN"
                else:
                    data["pricing"]["do_requests"]["rounding_units"] = True
                self.assert_incomplete_hold(self.build(data))

    def test_imported_approved_flags_are_rejected_without_promoting_authority(self):
        for target in ["resources", "stop", "pricing"]:
            with self.subTest(target=target):
                data = fixture()
                if target == "pricing":
                    data[target]["worker_requests"]["approved"] = True
                else:
                    data[target]["approved"] = True
                self.assert_incomplete_hold(self.build(data))

    def test_references_containing_credentials_are_not_a_reviewable_decision(self):
        for target in ["resources", "stop", "pricing"]:
            with self.subTest(target=target):
                data = copy.deepcopy(fixture())
                if target == "resources":
                    data[target]["recipient"] = "https://synthetic-user:synthetic-secret@recipient.invalid/"
                elif target == "stop":
                    data[target]["executor_ref"] = "Bearer synthetic-fixture-secret"
                else:
                    data[target]["worker_requests"]["reference"] = (
                        "https://synthetic-user:synthetic-secret@developers.cloudflare.com/workers/platform/pricing/")
                self.assert_incomplete_hold(self.build(data))

    def test_unknown_stop_refs_and_invalid_native_versions_cannot_claim_a_complete_model(self):
        for value in ["UNKNOWN", "TBD", "PENDING", "UNBOUND", "None", None]:
            with self.subTest(stop_reference=value):
                data = fixture()
                data["stop"]["stop_ref"] = value
                result = self.build(data)
                self.assert_incomplete_hold(result)
                self.assertIsNone(result["stop"])
        for group, field in [("resources", "worker_version"),
                             ("resources", "d1_database"), ("stop", "rollback_version")]:
            with self.subTest(invalid_uuid=field):
                data = fixture()
                data[group][field] = "not-a-native-uuid"
                result = self.build(data)
                self.assert_incomplete_hold(result)
                self.assertIsNone(result[group])
            with self.subTest(credential_reference=field):
                data = fixture()
                data[group][field] = "https://synthetic-user:synthetic-secret@native-reference.invalid/"
                result = self.build(data)
                self.assert_incomplete_hold(result)
                self.assertIsNone(result[group])
                self.assertNotIn("synthetic-secret", str(result))


if __name__ == "__main__":
    unittest.main()
