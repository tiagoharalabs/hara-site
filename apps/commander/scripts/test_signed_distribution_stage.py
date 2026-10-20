#!/usr/bin/env python3
"""Offline regressions for the exact commercial assets selected for staging."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from verify_signed_distribution import ReleaseValidationError, verify_bundle
from stage_signed_commercial_assets import BUNDLES, ROLLBACK_RELEASE, stage
from build_commander_commercial_terminal_drain_candidate import prepare

APP = Path(__file__).resolve().parents[1]
V3 = APP / "release-bundles/commercial-0.3.43-v3"
V4 = APP / "release-bundles/commercial-0.3.43-v4-autoreconnect"
WINDOWS_RC = APP / "release-bundles/commercial-0.3.52-v12-rc"


class SignedDistributionTests(unittest.TestCase):
    def test_current_commercial_bundle_is_cryptographically_valid(self):
        self.assertEqual(verify_bundle(V4)["agent_version"], "0.3.43")

    def test_rollback_bundle_is_cryptographically_valid(self):
        self.assertEqual(verify_bundle(V3)["agent_version"], "0.3.43")

    def test_old_signed_manifest_with_new_agent_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(V4, bundle)
            shutil.copyfile(WINDOWS_RC / "agent/windows.ps1", bundle / "agent/windows.ps1")
            with self.assertRaisesRegex(ReleaseValidationError, "FILE_HASH_MISMATCH"):
                verify_bundle(bundle)

    def test_unsigned_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(V4, bundle)
            with (bundle / "install/linux.sh").open("ab") as file:
                file.write(b"\n# unsigned change\n")
            with self.assertRaisesRegex(ReleaseValidationError, "FILE_HASH_MISMATCH"):
                verify_bundle(bundle)

    def test_matching_hashes_do_not_replace_a_valid_signature(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary) / "bundle"
            shutil.copytree(V4, bundle)
            target = bundle / "install/linux.sh"
            target.write_bytes(target.read_bytes() + b"\n# altered\n")
            manifest_path = bundle / "release/agent-manifest.json"
            manifest = json.loads(manifest_path.read_bytes())
            for row in manifest["files"]:
                if row["path"] == "install/linux.sh":
                    data = target.read_bytes()
                    row["bytes"] = len(data)
                    row["sha256"] = hashlib.sha256(data).hexdigest()
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            (bundle / "release/SHA256SUMS").write_text("".join(
                f"{row['sha256']}  {row['path']}\n" for row in manifest["files"]
            ))
            signature_path = bundle / "release/agent-manifest.sig.json"
            signature = json.loads(signature_path.read_bytes())
            signature["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            signature_path.write_text(json.dumps(signature, indent=2, sort_keys=True) + "\n")
            with self.assertRaisesRegex(ReleaseValidationError, "SIGNATURE_INVALID"):
                verify_bundle(bundle)

    def test_signed_windows_rc_with_older_linux_agent_is_not_a_commercial_bundle(self):
        with self.assertRaisesRegex(ReleaseValidationError, "AGENT_VERSION_MISMATCH"):
            verify_bundle(WINDOWS_RC)

    def test_production_config_requires_explicit_staged_assets(self):
        config = json.loads((APP / "wrangler.jsonc").read_text())
        self.assertEqual(config["assets"]["directory"], "signed-assets-stage-required")
        self.assertFalse((APP / config["assets"]["directory"]).exists())

    def test_default_stage_waits_for_new_officially_signed_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "assets"
            with self.assertRaisesRegex(RuntimeError, "AWAITING_OFFICIAL_SIGNATURE"):
                stage(output)
            self.assertFalse(output.exists())

    def test_rollback_stage_is_explicit_and_reports_known_regression(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "assets"
            with self.assertRaisesRegex(RuntimeError, "REQUIRES_ROLLBACK_ONLY"):
                stage(output, BUNDLES[ROLLBACK_RELEASE])
            self.assertFalse(output.exists())
            report = stage(output, BUNDLES[ROLLBACK_RELEASE], rollback_only=True)
            self.assertEqual(report["release"], ROLLBACK_RELEASE)
            self.assertEqual(report["state"], "ROLLBACK_ONLY_KNOWN_PROCESS_DRAIN_REGRESSION")
            self.assertEqual(verify_bundle(output), verify_bundle(BUNDLES[ROLLBACK_RELEASE]))

    def test_signed_rollback_linux_fails_real_pty_drain_regression(self):
        validator = APP / "scripts/validate_process_terminal_drain.py"
        current = subprocess.run([sys.executable, "-B", str(validator)],
                                 capture_output=True, text=True, check=False)
        self.assertEqual(current.returncode, 0, current.stderr[-500:])
        historical = subprocess.run(
            [sys.executable, "-B", str(validator), "--source",
             str(BUNDLES[ROLLBACK_RELEASE] / "agent/linux.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(historical.returncode, 0)
        self.assertIn("120_lines_available", historical.stderr)

    def test_manifest_builder_cannot_overwrite_signed_public_manifest(self):
        manifest = APP / "public/release/agent-manifest.json"
        before = hashlib.sha256(manifest.read_bytes()).digest()
        result = subprocess.run(
            [sys.executable, "-B", str(APP / "scripts/build_release_manifest.py")],
            capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SIGNED_MANIFEST_REQUIRES_PRIVATE_STAGING_AND_RESIGNING", result.stderr)
        self.assertEqual(hashlib.sha256(manifest.read_bytes()).digest(), before)

    def test_candidate_preserves_linux_drain_and_commercial_windows(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            report = prepare(output)
            public = output / "apps/commander/public"
            self.assertEqual(report["state"], "AWAITING_OFFICIAL_SIGNATURE")
            self.assertFalse((public / "release/agent-manifest.sig.json").exists())
            self.assertEqual((public / "agent/linux.py").read_bytes(),
                             (APP / "public/agent/linux.py").read_bytes())
            for relative in ("agent/windows.ps1", "install/linux.sh", "install/windows.ps1"):
                self.assertEqual((public / relative).read_bytes(),
                                 (BUNDLES[ROLLBACK_RELEASE] / relative).read_bytes())
            for relative in ("index.html", "app.js"):
                self.assertEqual((public / relative).read_bytes(),
                                 (APP / "public" / relative).read_bytes())
            manifest = json.loads((public / "release/agent-manifest.json").read_bytes())
            self.assertEqual(manifest["agent_version"], "0.3.43")
            with self.assertRaisesRegex(ReleaseValidationError, "FILE_MISSING"):
                verify_bundle(public)


if __name__ == "__main__":
    unittest.main()
