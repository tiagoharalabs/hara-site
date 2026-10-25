"""#163 four-artifact private review only; never signs or installs anything.

Reuse the owned temporary Git fixture setup, without inheriting/running its
test campaign. Only public installer/JWK bytes are copied read-only into the
fixtures. Production, frozen packages and real Git refs remain untouched.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import sys
import unittest


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2]
PUBLIC_JWK_RELATIVE = "scripts/fixtures/commercial_v2_043_signature/release-signing-public.jwk"
PUBLIC_JWK_SHA256 = "4e68608fa891f1b7a1e89c75936a089daeab0ba862a764f9bb31eca849cdfb9b"
INSTALLER_SHA256 = {
    "install/linux.sh": "a63542827372f73f5b0f48bf924fb847156c9d7f6f1adb371d73f78effade93f",
    "install/windows.ps1": "2219d2cf657ccb52471ae5c5e6544877946b24621185b0303e0d1e1c6ad1a401",
}
ARTIFACTS = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
MANIFEST = "candidate/release/agent-manifest.json"
SUMS = "candidate/release/SHA256SUMS"
KEY = "candidate/release/release-signing-public.jwk"
PROPOSED_POLICY = "candidate/source-policy.proposed.json"
CANDIDATE_STATE = "candidate/candidate.json"


def public_fixture_bytes(relative):
    return (SOURCE / relative).read_bytes()


class ReleaseReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        support_path = HERE / "test_commander_0356_source_review.py"
        spec = importlib.util.spec_from_file_location("source_review_release_fixture_support", support_path)
        cls.support = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.support
        spec.loader.exec_module(cls.support)
        cls.support.SourceReviewTests.setUpClass()
        cls.builder = cls.support.SourceReviewTests.builder

    def setUp(self):
        self.fixture = self.support.SourceReviewTests(methodName="test_exact_layout_hashes_and_byte_identical_txt_aliases")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.inputs = {}
        for relative, expected in INSTALLER_SHA256.items():
            path = self.support.CANDIDATE + "/" + relative
            raw = public_fixture_bytes(path)
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected, "public source fixture changed")
            self.inputs[path] = raw
            self.fixture.write(path, raw)
        key = public_fixture_bytes(PUBLIC_JWK_RELATIVE)
        self.assertEqual(hashlib.sha256(key).hexdigest(), PUBLIC_JWK_SHA256)
        public = json.loads(key)
        self.assertNotIn("d", public, "only the public trust fixture is authorized")
        self.inputs[PUBLIC_JWK_RELATIVE] = key
        self.fixture.write(PUBLIC_JWK_RELATIVE, key)
        self.fixture.commit("fixture public installers and pinned public trust")
        self.refresh_identity()

    def refresh_identity(self):
        self.fixture.head = self.fixture.git("rev-parse", "HEAD").decode().strip()
        self.fixture.tree = self.fixture.git("rev-parse", "HEAD^{tree}").decode().strip()

    def build(self, *, output=None, ref="HEAD", include=True):
        return self.builder.build_review(
            self.fixture.repo, output or self.fixture.output,
            ref=ref, expected_head=self.fixture.head,
            include_release_candidate=include,
        )

    def artifact_bytes(self, relative):
        if relative.startswith("agent/"):
            return self.fixture.files[self.support.CANDIDATE + "/" + relative]
        return self.inputs[self.support.CANDIDATE + "/" + relative]

    def assert_candidate(self, index, payloads):
        manifest = json.loads(payloads[MANIFEST])
        state = json.loads(payloads[CANDIDATE_STATE])
        self.assertEqual(manifest["schema"], "hara.commander-agent-release.v1")
        self.assertEqual(manifest["agent_version"], "0.3.56")
        self.assertEqual(manifest["channel"], "stable")
        self.assertEqual({row["path"] for row in manifest["files"]}, set(ARTIFACTS))
        self.assertEqual(len(manifest["files"]), 4)
        for row in manifest["files"]:
            raw = self.artifact_bytes(row["path"])
            packaged = payloads["candidate/" + row["path"]]
            self.assertEqual(packaged, raw, row["path"])
            self.assertEqual(row["bytes"], len(raw), row["path"])
            self.assertEqual(row["sha256"], hashlib.sha256(raw).hexdigest(), row["path"])
        self.assertEqual(payloads[KEY], self.inputs[PUBLIC_JWK_RELATIVE])
        actual_sums = {}
        for line in payloads[SUMS].decode("ascii").splitlines():
            digest, relative = line.split("  ", 1)
            self.assertNotIn(relative, actual_sums)
            actual_sums[relative] = digest
        self.assertEqual(actual_sums, {row["path"]: row["sha256"] for row in manifest["files"]})
        self.fixture.assert_not_approved(index)
        self.assertEqual(state["state"], "UNSIGNED_DRAFT_REQUIRES_ADMISSION")
        self.assertIs(state["installable"], False)
        self.assertIs(state["native_acceptance"], False)
        self.assertIsNone(state["signature"])
        self.assertIsNone(state["independent_pin"])
        self.assertIsNone(state["admission_receipt"])
        self.assertEqual(state["event_v2_runtime"], "OFF_REQUIRES_SEPARATE_OWNER_DECISION")
        self.assertFalse(manifest.get("signature"))
        self.assertFalse(any(name.endswith((".sig", ".signature")) for name in payloads))
        # The four-file v1 release contract does not silently admit helpers.
        self.assertFalse(any(name.startswith("candidate/agent/event_v2_") for name in payloads))
        self.assertEqual(index["source_commit"], self.fixture.head)
        self.assertEqual(index["source_tree"], self.fixture.tree)
        for name, raw in payloads.items():
            if name != "review-index.json":
                self.assertEqual(index["files"][name]["size_bytes"], len(raw), name)
                self.assertEqual(index["files"][name]["sha256"], hashlib.sha256(raw).hexdigest(), name)
        mode = stat.S_IMODE(self.fixture.output.stat().st_mode)
        self.assertEqual(mode, 0o400)

    def test_default_source_review_does_not_include_release_candidate(self):
        self.builder.build_review(self.fixture.repo, self.fixture.output,
                                  expected_head=self.fixture.head)
        index, payloads = self.fixture.inspect_archive()
        self.assertFalse(any(name.startswith("candidate/") for name in payloads))
        self.fixture.assert_not_approved(index)

    def test_opt_in_contains_four_exact_artifacts_coherent_hashes_and_unsigned_state(self):
        self.build()
        index, payloads = self.fixture.inspect_archive()
        self.assert_candidate(index, payloads)
        second = self.fixture.output_dir / "second-private-candidate.tar.gz"
        self.build(output=second)
        self.assertEqual(self.fixture.output.read_bytes(), second.read_bytes())

    def test_installer_version_or_trust_drift_holds_without_partial_candidate(self):
        variants = (
            (self.support.CANDIDATE + "/install/linux.sh", b"0.3.56", b"0.3.55", "INSTALLER_AGENT_VERSION_MISMATCH"),
            (self.support.CANDIDATE + "/install/linux.sh", b"commander-release-v2", b"commander-release-v1", "INSTALLER_TRUST_ANCHOR"),
            (self.support.CANDIDATE + "/install/windows.ps1", b"commander-release-v2", b"commander-release-v1", "INSTALLER_TRUST_ANCHOR"),
            (PUBLIC_JWK_RELATIVE, b"\n", b"\n\n", "PUBLIC_TRUST_ANCHOR_NOT_PINNED"),
        )
        for relative, old, new, code in variants:
            with self.subTest(source=relative, code=code):
                original = self.inputs[relative]
                changed = original.replace(old, new)
                self.assertNotEqual(changed, original)
                self.fixture.write(relative, changed)
                self.fixture.commit("fixture candidate version or trust drift")
                self.refresh_identity()
                try:
                    with self.assertRaisesRegex((ValueError, RuntimeError, OSError), code):
                        self.build()
                    self.assertFalse(self.fixture.output.exists())
                finally:
                    self.fixture.write(relative, original)
                    self.fixture.commit("fixture restore public candidate bytes")
                    self.refresh_identity()

    def test_missing_installer_or_pinned_public_key_is_refused(self):
        for relative in self.inputs:
            with self.subTest(missing=relative):
                path = self.fixture.repo / relative
                path.unlink()
                self.fixture.commit("fixture missing candidate input")
                self.refresh_identity()
                try:
                    with self.assertRaisesRegex((ValueError, RuntimeError, OSError), "SOURCE_REVIEW_MISSING_SOURCE"):
                        self.build()
                    self.assertFalse(self.fixture.output.exists())
                finally:
                    path.write_bytes(self.inputs[relative])
                    self.fixture.commit("fixture restore candidate input")
                    self.refresh_identity()

    def test_candidate_uses_original_git_commit_not_dirty_files_or_replace_refs(self):
        original_head, original_tree = self.fixture.head, self.fixture.tree
        installer = self.support.CANDIDATE + "/install/windows.ps1"
        self.fixture.write(installer, self.inputs[installer] + b"\n# SYNTHETIC_REPLACEMENT_NOT_IN_PINNED_COMMIT\n")
        self.fixture.commit("fixture replacement candidate installer")
        replacement = self.fixture.git("rev-parse", "HEAD").decode().strip()
        self.fixture.git("replace", original_head, replacement)
        self.fixture.write(installer, b"UNCOMMITTED_CANDIDATE_BYTES_MUST_NOT_PACKAGE")
        self.fixture.write(PUBLIC_JWK_RELATIVE, b"UNCOMMITTED_KEY_MUST_NOT_REPIN_TRUST")
        self.fixture.head, self.fixture.tree = original_head, original_tree
        self.build(ref=original_head)
        index, payloads = self.fixture.inspect_archive()
        self.assert_candidate(index, payloads)

    def test_proposed_policy_is_separate_and_never_rewrites_or_admits_frozen_provenance(self):
        frozen = {relative: (self.fixture.repo / relative).read_bytes() for relative in self.support.PROVENANCE}
        self.build()
        index, payloads = self.fixture.inspect_archive()
        proposed = json.loads(payloads[PROPOSED_POLICY])
        self.assertEqual(proposed["schema"], "hara.commander-commercial-source-review.v1")
        self.assertEqual(proposed["status"], "SOURCE_ADAPTATION_PROPOSED")
        self.assertEqual(proposed["version"], "0.3.56")
        self.assertEqual(set(proposed["artifacts"]), set(ARTIFACTS))
        for relative in ARTIFACTS:
            row = proposed["artifacts"][relative]
            self.assertEqual(row["classification"], "commercial-candidate")
            self.assertEqual(row["source_commit"], self.fixture.head)
            self.assertEqual(row["sha256"], hashlib.sha256(self.artifact_bytes(relative)).hexdigest())
        for relative, raw in frozen.items():
            self.assertEqual((self.fixture.repo / relative).read_bytes(), raw)
            self.assertEqual(payloads["source/" + relative], raw)
        self.assert_candidate(index, payloads)

    def test_cli_with_release_candidate_produces_private_noninstallable_review(self):
        result = subprocess.run(
            [sys.executable, str(self.support.BUILDER), "--repo", str(self.fixture.repo),
             "--output", str(self.fixture.output), "--expected-head", self.fixture.head,
             "--with-release-candidate"],
            capture_output=True, text=True, timeout=10, env=self.fixture.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        index, payloads = self.fixture.inspect_archive()
        self.assert_candidate(index, payloads)


if __name__ == "__main__":
    unittest.main()
