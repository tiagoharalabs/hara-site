#!/usr/bin/env python3
"""R20: guards cannot mark 0.3.43 or a mere 0.3.55 label as unified."""
from __future__ import annotations
import copy
import json
import unittest

from commander_release_train_parity_gate import (
    ROOT, INVENTORY, evaluate
)

class ReleaseTrainPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(INVENTORY.read_text())

    def test_real_installed_and_public_state_fails_closed(self):
        r = evaluate(copy.deepcopy(self.inventory))
        self.assertEqual(r["state"], "HOLD")
        self.assertEqual(r["versions_observed"]["linux_runtime"], "0.3.54")
        self.assertEqual(r["versions_observed"]["commercial_signed"], "0.3.43")
        self.assertEqual(r["versions_observed"]["windows_candidate"], "0.3.55")
        self.assertIn("LATEST_LINUX_AND_WINDOWS_INSTALLERS_SIGNED_TO_SAME_TARGET",r["blockers"])
        self.assertIn("PUBLIC_DOWNLOADS_PASS_SIGNED_TARGET_READBACK",r["blockers"])
        self.assertFalse(r["mutation_performed"])

    def test_signed_v5_signature_not_same_as_latest_055(self):
        r = evaluate(copy.deepcopy(self.inventory))
        self.assertTrue(r["checks"]["COMMERCIAL_BUNDLE_CRYPTOGRAPHICALLY_VALID"])
        self.assertFalse(r["checks"]["LATEST_LINUX_AND_WINDOWS_INSTALLERS_SIGNED_TO_SAME_TARGET"])

    def test_inventory_cannot_relabel_unsigned_old_assets(self):
        d=copy.deepcopy(self.inventory)
        d["commercial_current"]["signed_package_version"]="0.3.55"
        d["commercial_current"]["linux_agent_version"]="0.3.55"
        d["commercial_current"]["windows_agent_version"]="0.3.55"
        r=evaluate(d)
        self.assertFalse(r["checks"]["SIGNED_RELEASE_INVENTORY_MATCHES_BYTES"])
        self.assertFalse(r["checks"]["LATEST_LINUX_AND_WINDOWS_INSTALLERS_SIGNED_TO_SAME_TARGET"])

    def test_changed_windows_source_digest_blocks(self):
        d=copy.deepcopy(self.inventory)
        d["windows"]["candidate_source_sha256"]="0"*64
        r=evaluate(d)
        self.assertFalse(r["checks"]["WINDOWS_CANDIDATE_SOURCE_HASH_INTACT"])

    def test_fake_windows_homogeneity_does_not_override_signature(self):
        d=copy.deepcopy(self.inventory)
        d["windows"].update({"runtime_state":"RUNNING","registered_agent_version":"0.3.55",
            "candidate_signed":True,"candidate_installed":True,"live_clean_install_055_pass":True})
        d["linux"].update({"installed_version":"0.3.55",
            "loop_variants_approved_as_equivalent":True})
        r=evaluate(d)
        self.assertEqual(r["state"],"HOLD")
        self.assertFalse(r["checks"]["LATEST_LINUX_AND_WINDOWS_INSTALLERS_SIGNED_TO_SAME_TARGET"])

    def test_missing_linux_target_source_never_assumed_by_label(self):
        d=copy.deepcopy(self.inventory)
        d["linux"]["proposed_commercial_source_sha256"]="0"*64
        d["linux"]["commercial_target_runtime_regressions_pass"]=True
        r=evaluate(d)
        self.assertFalse(r["checks"]["LINUX_TARGET_COMMERCIAL_SOURCE_PROVEN"])

    def test_capability_differences_need_explicit_policy(self):
        r=evaluate(copy.deepcopy(self.inventory))
        self.assertFalse(r["checks"]["CROSS_PLATFORM_CAPABILITY_PARITY_QUALIFIED"])
        self.assertEqual(r["linux_declared_capabilities"],31)
        self.assertEqual(r["windows_candidate_declared_capabilities"],22)

    def test_invalid_target_rejected(self):
        with self.assertRaisesRegex(ValueError,"TARGET_RELEASE_VERSION_INVALID"):
            evaluate(copy.deepcopy(self.inventory),target="latest")

if __name__=="__main__":
    unittest.main()
