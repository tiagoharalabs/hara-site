#!/usr/bin/env python3
"""Offline checks for version-specific asset readback; no Cloudflare calls."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import commander_versioned_asset_readback as readback
from stage_signed_commercial_assets import BUNDLES, ROLLBACK_RELEASE, stage
from validate_prod_runtime_drift import asset_sources


TARGET = "11111111-1111-1111-1111-111111111111"
ROLLBACK = "22222222-2222-2222-2222-222222222222"


class VersionAssetReadbackTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.staged = Path(temporary.name) / "assets"
        self.bundle = BUNDLES[ROLLBACK_RELEASE]
        self.report = stage(self.staged, self.bundle, rollback_only=True)
        self.sources = asset_sources(self.staged, expected_bundle=self.bundle)
        self.deployment = [{"versions": [
            {"version_id": ROLLBACK, "percentage": 100},
            {"version_id": TARGET, "percentage": 0},
        ]}]

    def check(self):
        return readback.readback_version_assets(
            self.staged, self.report["stage_tree_sha256"], TARGET, ROLLBACK,
            expected_bundle=self.bundle,
        )

    def fetch(self, path, version):
        body = self.sources[path].read_bytes()
        if version is None and path == "/release/agent-manifest.json":
            return body + b"old deployment"
        return body

    def test_exact_zero_percent_version_assets_are_verified(self):
        with patch.object(readback, "fetch_deployments", return_value=self.deployment) as deployments, \
             patch.object(readback, "fetch_asset", side_effect=self.fetch) as assets:
            result = self.check()
        self.assertEqual(result["state"], "VERSION_ASSETS_VERIFIED_0_PERCENT")
        self.assertTrue(result["version_asset_content_verified"])
        self.assertFalse(result["worker_code_verified"])
        self.assertEqual(result["version_id"], TARGET)
        self.assertEqual(result["asset_count"], 15)
        self.assertEqual(assets.call_count, 30)
        self.assertEqual(deployments.call_count, 2)

    def test_silently_ignored_override_is_rejected(self):
        def ignored(path, _version):
            return self.fetch(path, None)
        with patch.object(readback, "fetch_deployments", return_value=self.deployment), \
             patch.object(readback, "fetch_asset", side_effect=ignored):
            with self.assertRaisesRegex(RuntimeError, "VERSION_ASSET_MISMATCH"):
                self.check()

    def test_identical_baseline_cannot_prove_override_was_applied(self):
        with patch.object(readback, "fetch_deployments", return_value=self.deployment), \
             patch.object(readback, "fetch_asset", side_effect=lambda path, _version: self.sources[path].read_bytes()):
            with self.assertRaisesRegex(RuntimeError, "VERSION_OVERRIDE_NOT_PROVEN"):
                self.check()

    def test_missing_zero_percent_deployment_is_rejected_before_http(self):
        wrong = [{"versions": [{"version_id": ROLLBACK, "percentage": 100}]}]
        with patch.object(readback, "fetch_deployments", return_value=wrong), \
             patch.object(readback, "fetch_asset") as assets:
            with self.assertRaisesRegex(RuntimeError, "VERSION_DEPLOYMENT_NOT_ZERO_PERCENT"):
                self.check()
            assets.assert_not_called()

    def test_deployment_changes_during_readback_is_rejected(self):
        changed = [{"versions": [{"version_id": TARGET, "percentage": 100}]}]
        with patch.object(readback, "fetch_deployments", side_effect=[self.deployment, changed]), \
             patch.object(readback, "fetch_asset", side_effect=self.fetch):
            with self.assertRaisesRegex(RuntimeError, "VERSION_DEPLOYMENT_NOT_ZERO_PERCENT"):
                self.check()

    def test_wrong_stage_digest_is_rejected_before_remote_read(self):
        with patch.object(readback, "fetch_deployments") as deployments:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_TREE_DIGEST_MISMATCH"):
                readback.readback_version_assets(
                    self.staged, "0" * 64, TARGET, ROLLBACK,
                    expected_bundle=self.bundle,
                )
            deployments.assert_not_called()


if __name__ == "__main__":
    unittest.main()
