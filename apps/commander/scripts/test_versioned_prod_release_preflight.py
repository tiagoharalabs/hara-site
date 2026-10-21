#!/usr/bin/env python3
"""Offline promotion regressions; never call Wrangler or production."""
from __future__ import annotations

from pathlib import Path
import contextlib
import io
import shutil
import subprocess
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
        self.stage_report = stage(self.staged, self.rollback_bundle, rollback_only=True)

    def test_exact_signed_stage_is_accepted_against_its_approved_bundle(self):
        report = require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)
        self.assertEqual(report["agent_version"], "0.3.43")

    def test_v5_ui_tree_is_bound_to_frozen_reviewed_source(self):
        frozen_tree = subprocess.check_output(
            ["git", "rev-parse", "a13b4d2eec16be7a17bcab1c9c5ad23364aba3b4:apps/commander/public"],
            cwd=stage_module.ROOT, text=True,
        ).strip()
        self.assertEqual(stage_module.FROZEN_V5_PUBLIC_TREE, frozen_tree)
        stage_module.require_frozen_v5_source(BUNDLES[CURRENT_RELEASE], frozen_tree)
        with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_V5_SOURCE_TREE_CHANGED"):
            stage_module.require_frozen_v5_source(BUNDLES[CURRENT_RELEASE], "0" * 40)
        fixture = self.root / CURRENT_RELEASE
        shutil.copytree(self.rollback_bundle, fixture)
        with patch.dict(stage_module.BUNDLES, {CURRENT_RELEASE: fixture}), \
             patch.object(stage_module, "require_current_linux_regressions"), \
             patch.object(stage_module, "public_source_tree", return_value="0" * 40):
            with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_V5_SOURCE_TREE_CHANGED"):
                require_signed_stage(self.staged)

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

    def test_web_page_and_static_media_drift_are_rejected(self):
        for relative in ("index.html", "styles.css", "assets/hara-commander-royal.webp"):
            with self.subTest(relative=relative):
                target = self.staged / relative
                original = target.read_bytes()
                target.write_bytes(original + b"unexpected-stage-edit")
                with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_UI_CHANGED"):
                    require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)
                target.write_bytes(original)

    def test_web_source_and_stage_cotamper_cannot_rebase_approved_source(self):
        alternate_public = self.root / "altered-public"
        shutil.copytree(stage_module.PUBLIC, alternate_public)
        target = alternate_public / "index.html"
        altered = target.read_bytes() + b"\n<!-- unexpected source edit -->\n"
        target.write_bytes(altered)
        (self.staged / "index.html").write_bytes(altered)
        with patch.object(stage_module, "PUBLIC", alternate_public):
            with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_UI_SOURCE_UNCOMMITTED"):
                require_signed_stage(self.staged, expected_bundle=self.rollback_bundle)

    def test_stage_tree_digest_detects_post_stage_change(self):
        digest = self.stage_report["stage_tree_sha256"]
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(require_signed_stage(
            self.staged, expected_bundle=self.rollback_bundle,
            expected_tree_sha256=digest,
        )["stage_tree_sha256"], digest)
        with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_TREE_DIGEST_MISMATCH"):
            require_signed_stage(
                self.staged, expected_bundle=self.rollback_bundle,
                expected_tree_sha256="0" * 64,
            )

    def test_verify_assets_cli_requires_recorded_digest_and_rechecks_web_ui(self):
        argv = ["stage", "--verify-assets", str(self.staged), "--bundle",
                ROLLBACK_RELEASE, "--rollback-only"]
        with patch.object(sys, "argv", argv), self.assertRaisesRegex(
            SystemExit, "SIGNED_STAGE_EXPECTED_TREE_SHA256_REQUIRED"
        ):
            stage_module.main()
        argv += ["--expected-tree-sha256", self.stage_report["stage_tree_sha256"]]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(stage_module.main(), 0)
        html = self.staged / "index.html"
        html.write_bytes(html.read_bytes() + b"\n<!-- changed after stage -->\n")
        with patch.object(sys, "argv", argv), self.assertRaisesRegex(
            RuntimeError, "SIGNED_STAGE_UI_CHANGED"
        ):
            stage_module.main()

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
        for relative in ("brand/chatgpt-official.webp", "brand/claude-official.svg",
                         "release/v2/release-signing-public.jwk"):
            self.assertEqual(sources["/" + relative], self.staged / relative)
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
            for tampered_path in ("/agent/linux.py", "/brand/claude-official.svg"):
                def tampered(path):
                    body, status, content_type = fetch(path)
                    return (body + b"changed" if path == tampered_path else body), status, content_type
                with self.subTest(path=tampered_path), \
                     patch.object(drift, "fetch", side_effect=tampered), \
                     contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError, "EXPECTED_CURRENT_GOT_MIXED"):
                        drift.main()


if __name__ == "__main__":
    unittest.main()
