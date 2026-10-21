#!/usr/bin/env python3
"""Offline promotion regressions; never call Wrangler or production."""
from __future__ import annotations

from pathlib import Path
import contextlib
import io
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import commander_versioned_prod_promote as promote
import stage_signed_commercial_assets as stage_module
import validate_prod_runtime_drift as drift
from commander_versioned_prod_promote import require_signed_stage
from stage_signed_commercial_assets import BUNDLES, CURRENT_RELEASE, ROLLBACK_RELEASE, stage
from validate_prod_runtime_drift import asset_sources


class VersionedPromotionReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.rollback_bundle = BUNDLES[ROLLBACK_RELEASE]
        self.staged = self.root / "assets"
        stage(self.staged, self.rollback_bundle, rollback_only=True)

    def test_exact_signed_stage_is_accepted_against_its_approved_bundle(self):
        report = require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)
        self.assertEqual(report["agent_version"], "0.3.43")

    def test_legacy_signed_stage_is_not_current_promotion_candidate(self):
        with self.assertRaisesRegex(RuntimeError, "AWAITING_OFFICIAL_SIGNATURE"):
            require_signed_stage(self.staged)
        self.assertFalse(BUNDLES[CURRENT_RELEASE].exists())

    def test_manifest_old_agent_new_is_rejected_before_promotion(self):
        agent = self.staged / "agent/linux.py"
        agent.write_bytes(agent.read_bytes() + b"\n# newer but unsigned\n")
        with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_RELEASE_DRIFT"):
            require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)

    def test_ui_drift_is_rejected_before_promotion(self):
        js = self.staged / "app.js"
        js.write_bytes(js.read_bytes() + b"\n// unexpected stage edit\n")
        with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_UI_CHANGED"):
            require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)

    def test_symlink_in_signed_stage_is_rejected(self):
        installer = self.staged / "install/linux.sh"
        installer.unlink()
        installer.symlink_to(self.rollback_bundle / "install/linux.sh")
        with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_UNSAFE_SOURCE"):
            require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)

    def test_valid_signature_does_not_waive_terminal_drain_regression(self):
        signed_but_regressed = self.root / CURRENT_RELEASE
        shutil.copytree(self.rollback_bundle, signed_but_regressed)
        with patch.dict(stage_module.BUNDLES, {CURRENT_RELEASE: signed_but_regressed}):
            with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_LINUX_PROCESS_DRAIN_FAILED"):
                require_signed_stage(self.staged)

    def test_drift_sources_use_exact_supplied_stage(self):
        sources = asset_sources(self.staged, expected_bundle=self.rollback_bundle)
        self.assertEqual(sources["/release/agent-manifest.json"],
                         self.staged / "release/agent-manifest.json")
        self.assertEqual(sources["/install/linux.sh"], self.staged / "install/linux.sh")
        self.assertNotEqual(sources["/install/linux.sh"],
                            self.rollback_bundle / "install/linux.sh")

    def test_promotion_rejects_old_stage_before_remote_read(self):
        argv = ["promote", "--version", "11111111-1111-1111-1111-111111111111",
                "--rollback", "22222222-2222-2222-2222-222222222222",
                "--message", "offline test", "--stage", str(self.staged)]
        with patch.object(sys, "argv", argv), patch.object(promote, "run") as remote:
            with self.assertRaisesRegex(RuntimeError, "AWAITING_OFFICIAL_SIGNATURE"):
                promote.main()
            remote.assert_not_called()

    def test_live_readback_compares_exact_stage_bytes(self):
        sources = asset_sources(self.staged, expected_bundle=self.rollback_bundle)
        argv = ["drift", "--stage", str(self.staged), "--expect-assets", "current"]
        def fetch(path):
            return sources[path].read_bytes(), 200, "application/octet-stream"
        with patch.dict(stage_module.BUNDLES, {CURRENT_RELEASE: self.rollback_bundle}), \
             patch.object(sys, "argv", argv), \
             patch.object(drift, "fetch", side_effect=fetch), \
             patch.object(drift, "fetch_json", side_effect=lambda path: (
                 {"ok": True, "service": "hara-commander"} if path == "/api/health"
                 else {"configured": True})):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(drift.main(), 0)
            def tampered(path):
                body, status, content_type = fetch(path)
                return (body + b"changed" if path == "/agent/linux.py" else body), status, content_type
            with patch.object(drift, "fetch", side_effect=tampered), \
                 contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "EXPECTED_CURRENT_GOT_MIXED"):
                    drift.main()


if __name__ == "__main__":
    unittest.main()
