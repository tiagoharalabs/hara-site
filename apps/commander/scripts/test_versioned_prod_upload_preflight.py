#!/usr/bin/env python3
"""Offline checks for the signed-stage to Wrangler upload boundary."""
from __future__ import annotations

from pathlib import Path
import hashlib
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

    def test_snapshot_changed_during_copy_is_rejected_before_wrangler(self):
        real_copy = upload.copy_snapshot

        def altered_copy(source, destination):
            real_copy(source, destination)
            html = destination / "index.html"
            html.write_bytes(html.read_bytes() + b"unapproved copy bytes")

        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "copy_snapshot", side_effect=altered_copy), \
             patch.object(upload, "run_wrangler_upload") as run:
            with self.assertRaisesRegex(RuntimeError, "SIGNED_STAGE_UI_CHANGED"):
                self.call(execute=True)
            run.assert_not_called()

    def test_execute_uses_exact_verified_private_snapshot_once(self):
        observed = {}

        def read_snapshot(snapshot, _message):
            observed["path"] = snapshot
            observed["asset"] = (snapshot / "index.html").read_bytes()
            return subprocess.CompletedProcess([], 0, "uploaded", "")

        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload", side_effect=read_snapshot) as run:
            report = self.call(execute=True)
            self.assertEqual(report["state"], "UPLOAD_SUBMITTED_VERSION_READBACK_REQUIRED")
            self.assertFalse(report["version_content_verified"])
            self.assertEqual(run.call_count, 1)
            self.assertNotEqual(observed["path"], self.staged)
            self.assertEqual(observed["asset"], (self.staged / "index.html").read_bytes())
            self.assertFalse(observed["path"].exists())

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

    def test_transient_change_to_source_stage_cannot_change_uploaded_bytes(self):
        html = self.staged / "index.html"
        original = html.read_bytes()
        approved_sha = hashlib.sha256(original).hexdigest()
        observed = {}

        def transient(upload_stage, _message):
            html.write_bytes(original + b"\n<!-- transient unapproved edit -->\n")
            try:
                observed["upload_stage"] = upload_stage
                observed["asset_sha256"] = hashlib.sha256(
                    (upload_stage / "index.html").read_bytes()
                ).hexdigest()
            finally:
                html.write_bytes(original)
            return subprocess.CompletedProcess([], 0, "uploaded", "")

        with patch.object(upload, "require_signed_stage", side_effect=self.verified_stage), \
             patch.object(upload, "run_wrangler_upload", side_effect=transient):
            result = self.call(execute=True)
        self.assertEqual(html.read_bytes(), original)
        self.assertNotEqual(observed["upload_stage"], self.staged)
        self.assertEqual(observed["asset_sha256"], approved_sha)
        self.assertEqual(result["state"], "UPLOAD_SUBMITTED_VERSION_READBACK_REQUIRED")


if __name__ == "__main__":
    unittest.main()
