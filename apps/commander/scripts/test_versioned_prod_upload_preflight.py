#!/usr/bin/env python3
"""Offline checks for the signed-stage to Wrangler upload boundary."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import commander_versioned_prod_upload as upload
from stage_signed_commercial_assets import BUNDLES, ROLLBACK_RELEASE, require_signed_stage, stage


class VersionedUploadPreflightTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.staged = Path(temporary.name) / "assets"
        self.bundle = BUNDLES[ROLLBACK_RELEASE]
        self.report = stage(self.staged, self.bundle, rollback_only=True)

    def verified_stage(self, path, *, expected_tree_sha256):
        return require_signed_stage(
            path, expected_bundle=self.bundle,
            expected_tree_sha256=expected_tree_sha256,
        )

    def call(self, *, execute=False, digest=None):
        return upload.upload_version(
            self.staged, digest or self.report["stage_tree_sha256"],
            self.report["source_public_tree"], "offline fixture", execute=execute,
        )

    def test_default_preflight_never_calls_wrangler(self):
        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload") as run:
            report = self.call()
            self.assertEqual(report["state"], "VERIFIED_NOT_UPLOADED")
            run.assert_not_called()

    def test_wrong_recorded_digest_fails_before_wrangler(self):
        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload") as run:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_TREE_DIGEST_MISMATCH"):
                self.call(execute=True, digest="0" * 64)
            run.assert_not_called()

    def test_wrong_reviewed_source_tree_fails_before_wrangler(self):
        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload") as run:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_UPLOAD_SOURCE_TREE_MISMATCH"):
                upload.upload_version(
                    self.staged, self.report["stage_tree_sha256"], "0" * 40,
                    "offline fixture", execute=True,
                )
            run.assert_not_called()

    def test_execute_uses_exact_verified_directory_once(self):
        completed = subprocess.CompletedProcess([], 0, "uploaded", "")
        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload", return_value=completed) as run:
            report = self.call(execute=True)
            self.assertEqual(report["state"], "UPLOADED_VERSION_READBACK_REQUIRED")
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args, (self.staged, "offline fixture"))

    def test_wrangler_command_uses_only_supplied_stage(self):
        completed = subprocess.CompletedProcess([], 0, "uploaded", "")
        with patch.object(upload.subprocess, "run", return_value=completed) as run:
            upload.run_wrangler_upload(self.staged, "offline fixture")
        args = run.call_args.args[0]
        self.assertEqual(args[1:3], ["versions", "upload"])
        self.assertEqual(args[args.index("--assets") + 1], str(self.staged))
        self.assertIn("--config", args)

    def test_timeout_does_not_retry_mutating_upload(self):
        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload", side_effect=subprocess.TimeoutExpired("wrangler", 1)) as run:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_UPLOAD_OUTCOME_UNKNOWN"):
                self.call(execute=True)
            self.assertEqual(run.call_count, 1)

    def test_wrangler_error_does_not_retry_mutating_upload(self):
        failed = subprocess.CompletedProcess([], 1, "", "failed")
        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload", return_value=failed) as run:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_UPLOAD_OUTCOME_UNKNOWN"):
                self.call(execute=True)
            self.assertEqual(run.call_count, 1)

    def test_change_during_upload_leaves_outcome_unknown(self):
        def changed(_stage, _message):
            html = self.staged / "index.html"
            html.write_bytes(html.read_bytes() + b"changed during upload")
            return subprocess.CompletedProcess([], 0, "uploaded", "")

        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload", side_effect=changed) as run:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_UPLOAD_OUTCOME_UNKNOWN"):
                self.call(execute=True)
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
