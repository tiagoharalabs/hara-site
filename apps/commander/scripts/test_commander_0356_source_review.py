"""#163 private SOURCE review packaging; no signing, install or native QA.

Every Git repository, branch, commit and file mutated here is an owned fixture
inside TemporaryDirectory. Real checkout refs and original packages are read
by neither the fixture nor the builder tests.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch


BUILDER = Path(__file__).with_name("commander_0356_source_review.py")
CANDIDATE = "apps/commander/release-candidates/commercial-0.3.56-source"
AGENTS = tuple(f"{CANDIDATE}/agent/{name}" for name in (
    "linux.py", "windows.ps1", "event_v2_dev.py", "event_v2_dev.ps1",
    "event_v2_wire.py", "event_v2_wire.ps1",
))
HARNESSES = tuple(f"apps/commander/scripts/{name}" for name in (
    "test_event_v2_commercial_windows_0356_r163.ps1",
    "test_event_v2_commercial_windows_heartbeat_r163.ps1",
    "test_commercial_056_windows_recovery.ps1",
    "test_commercial_056_windows_journal_orphans.ps1",
    "test_commercial_056_windows_supervisor.ps1",
    "test_commercial_056_windows_job_native.ps1",
))
PROVENANCE = (f"{CANDIDATE}/draft-source-policy.json", f"{CANDIDATE}/origin.json")
REQUIRED = AGENTS + HARNESSES + PROVENANCE
ALIASES = {
    "valk/windows-agent-0.3.56-eventv2-review.txt": AGENTS[1],
    "valk/event-v2-dev-0.3.56-review.txt": AGENTS[3],
    "valk/event-v2-wire-0.3.56-review.txt": AGENTS[5],
}


class SourceReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BUILDER.is_file():
            raise AssertionError(f"SOURCE_REVIEW_BUILDER_ABSENT: {BUILDER}")
        spec = importlib.util.spec_from_file_location("commander_0356_source_review_qa", BUILDER)
        cls.builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.builder
        spec.loader.exec_module(cls.builder)
        if not callable(getattr(cls.builder, "build_review", None)):
            raise AssertionError("SOURCE_REVIEW_BUILD_API_ABSENT")

    def setUp(self):
        self.area = tempfile.TemporaryDirectory(prefix="hara-0356-review-fixture-")
        self.addCleanup(self.area.cleanup)
        self.base = Path(self.area.name)
        self.repo = self.base / "fixture-repo"
        self.repo.mkdir(mode=0o700)
        self.output_dir = self.base / "private-output"
        self.output_dir.mkdir(mode=0o700)
        self.output = self.output_dir / "private-source-review.tar.gz"
        self.env = dict(os.environ)
        for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
            self.env.pop(name, None)
        self.env.update({
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "HARA QA Fixture", "GIT_COMMITTER_NAME": "HARA QA Fixture",
            "GIT_AUTHOR_EMAIL": "qa@example.invalid", "GIT_COMMITTER_EMAIL": "qa@example.invalid",
            "GIT_AUTHOR_DATE": "2026-10-25T00:00:00Z", "GIT_COMMITTER_DATE": "2026-10-25T00:00:00Z",
        })
        self.git("init", "-q", "--initial-branch=source-review-fixture")
        self.files = {}
        for relative in REQUIRED:
            if relative.endswith(".ps1"):
                # BOM, CRLF, and non-ASCII prove the .txt copy is bytes, not a
                # decoded/re-encoded or newline-normalized rendition.
                raw = ("\ufeff# Revisão sintética; não executar\r\n"
                       "$AgentVersion = \"0.3.56\"\r\n"
                       f"# {relative}\r\n").encode("utf-8")
            elif relative.endswith(".py"):
                raw = f'# Fixture source, never executed\nAGENT_VERSION = "0.3.56"\n# {relative}\n'.encode()
            else:
                raw = json.dumps({"source": "SYNTHETIC_REVIEW_FIXTURE", "installable": True,
                                  "native_acceptance": True, "signature": "FORGED_FIXTURE_CLAIM",
                                  "independent_pin": "f" * 64}).encode()
            self.files[relative] = raw
            self.write(relative, raw)
        self.commit("fixture source")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], env=self.env,
            stderr=subprocess.PIPE,
        )

    def write(self, relative, data):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def commit(self, message):
        self.git("add", "--all")
        self.git("-c", "commit.gpgsign=false", "commit", "-q", "-m", message)

    def build(self, output=None, ref="HEAD", expected_head=None):
        return self.builder.build_review(
            self.repo, output or self.output, ref=ref,
            expected_head=self.head if expected_head is None else expected_head,
        )

    def inspect_archive(self, output=None):
        with tarfile.open(output or self.output, "r:gz") as archive:
            members = archive.getmembers()
            self.assertEqual(len(members), len({member.name for member in members}), "duplicate tar member")
            payloads = {}
            for member in members:
                self.assertTrue(member.isfile(), f"not a regular review file: {member.name}")
                self.assertFalse(member.name.startswith("/"))
                self.assertNotIn("..", PurePosixPath(member.name).parts)
                self.assertEqual(member.mtime, 0)
                self.assertEqual((member.uid, member.gid), (0, 0))
                self.assertEqual((member.uname, member.gname), ("", ""))
                self.assertEqual(member.mode & 0o111, 0, "review content must not be executable")
                payloads[member.name] = archive.extractfile(member).read()
        self.assertIn("review-index.json", payloads)
        index = json.loads(payloads["review-index.json"])
        return index, payloads

    def assert_not_approved(self, index):
        self.assertIs(index["native_acceptance"], False)
        self.assertIs(index["installable"], False)
        self.assertIsNone(index["independent_pin"])
        self.assertIsNone(index["signature"])
        self.assertIs(index.get("release_approved", False), False)
        self.assertIsNone(index.get("admission_receipt"))

    def assert_no_output(self):
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.is_symlink())

    def test_exact_layout_hashes_and_byte_identical_txt_aliases(self):
        self.build()
        index, payloads = self.inspect_archive()
        expected = {"source/" + name for name in REQUIRED} | set(ALIASES) | {"review-index.json"}
        self.assertEqual(set(payloads), expected)
        self.assertEqual(index["source_commit"], self.head)
        self.assertEqual(index["source_tree"], self.tree)
        self.assertRegex(index["source_commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(index["source_tree"], r"^[0-9a-f]{40}$")
        self.assertEqual(set(index["files"]), expected - {"review-index.json"})
        for name, raw in payloads.items():
            if name == "review-index.json":
                continue
            self.assertEqual(index["files"][name]["size_bytes"], len(raw), name)
            self.assertEqual(index["files"][name]["sha256"], hashlib.sha256(raw).hexdigest(), name)
        for relative, raw in self.files.items():
            self.assertEqual(payloads["source/" + relative], raw, relative)
        for alias, original in ALIASES.items():
            self.assertEqual(payloads[alias], self.files[original], alias)
            self.assertEqual(payloads[alias], payloads["source/" + original], alias)
        # Default PSScriptRoot paths in each harness stay inside this layout.
        for harness in HARNESSES:
            directory = PurePosixPath("source/" + harness).parent
            resolved = directory.parent / "release-candidates/commercial-0.3.56-source/agent/windows.ps1"
            self.assertIn(str(resolved), payloads)
        self.assert_not_approved(index)

    def test_deterministic_gzip_tar_and_private_readonly_archive(self):
        self.build()
        second = self.output_dir / "different-filename.tar.gz"
        self.build(output=second)
        self.assertEqual(self.output.read_bytes(), second.read_bytes())
        self.assertEqual(self.output.read_bytes()[4:8], b"\0\0\0\0", "gzip mtime must be zero")
        mode = stat.S_IMODE(self.output.stat().st_mode)
        self.assertEqual(mode & 0o077, 0, "archive must be private")
        self.assertEqual(mode & 0o222, 0, "archive must be readonly")
        self.assertTrue(mode & 0o400)
        self.assertEqual(stat.S_IMODE(self.output_dir.stat().st_mode), 0o700)

    def test_git_commit_blobs_exclude_dirty_untracked_installers_and_credentials(self):
        # Tracked-but-excluded files must not join the source review allowlist.
        for relative in (f"{CANDIDATE}/install/windows.ps1", "apps/commander/public/install/windows.ps1",
                         "apps/commander/public/release/agent-manifest.json", ".env", "new-handoff.md"):
            self.write(relative, b"SYNTHETIC_EXCLUDED_MATERIAL_NEVER_PACKAGE")
        self.commit("fixture excluded files")
        self.head = self.git("rev-parse", "HEAD").decode().strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").decode().strip()
        self.write(AGENTS[1], b"UNCOMMITTED_WRONG_AGENT_BYTES")
        self.write("private-untracked-token.txt", b"SYNTHETIC_UNTRACKED_NEVER_PACKAGE")
        (self.repo / "ignored-link").symlink_to("/SYNTHETIC_NOT_READ")
        self.build()
        index, payloads = self.inspect_archive()
        self.assertEqual(payloads["source/" + AGENTS[1]], self.files[AGENTS[1]])
        self.assertFalse(any("install/" in name or "agent-manifest.json" in name or ".env" in name
                             or "handoff" in name or "untracked" in name or "ignored-link" in name
                             for name in payloads))
        self.assertEqual(index["source_commit"], self.head)

    def test_missing_adjacent_helper_or_harness_fails_without_partial_archive(self):
        for relative in (AGENTS[3], AGENTS[4], HARNESSES[3], HARNESSES[-1], PROVENANCE[-1]):
            with self.subTest(missing=relative):
                path = self.repo / relative
                prior = path.read_bytes()
                path.unlink()
                self.commit("fixture missing required source")
                missing_head = self.git("rev-parse", "HEAD").decode().strip()
                with self.assertRaisesRegex((ValueError, RuntimeError, OSError), "SOURCE_REVIEW_MISSING_SOURCE"):
                    self.build(expected_head=missing_head)
                self.assert_no_output()
                path.write_bytes(prior)
                self.commit("fixture restore required source")

    def test_selected_git_symlink_is_refused_and_never_dereferenced(self):
        selected = self.repo / AGENTS[5]
        selected.unlink()
        selected.symlink_to("/SYNTHETIC_PRIVATE_TARGET_NOT_READ")
        self.commit("fixture selected symlink")
        symlink_head = self.git("rev-parse", "HEAD").decode().strip()
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            self.build(expected_head=symlink_head)
        self.assert_no_output()

    def test_existing_output_is_never_overwritten_or_unlinked(self):
        before = b"ORIGINAL_PRIVATE_PACKAGE_PRESERVE_EXACTLY"
        self.output.write_bytes(before)
        self.output.chmod(0o400)
        with self.assertRaisesRegex((ValueError, RuntimeError, OSError), "SOURCE_REVIEW_OUTPUT_EXISTS"):
            self.build()
        self.assertEqual(self.output.read_bytes(), before)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o400)

    def test_output_symlink_is_not_followed(self):
        protected = self.output_dir / "protected-original"
        protected.write_bytes(b"ORIGINAL_NOT_REPLACED")
        protected.chmod(0o400)
        self.output.symlink_to(protected.name)
        with self.assertRaises((ValueError, RuntimeError, OSError)):
            self.build()
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(protected.read_bytes(), b"ORIGINAL_NOT_REPLACED")

    def test_expected_head_mismatch_fails_before_archive_creation(self):
        wrong = "a" * 40 if self.head != "a" * 40 else "b" * 40
        with self.assertRaisesRegex((ValueError, RuntimeError, OSError), "SOURCE_REVIEW_HEAD_MISMATCH"):
            self.build(expected_head=wrong)
        self.assert_no_output()

    def test_main_agent_version_mismatch_cannot_be_labelled_0356(self):
        # A review is not installable, but it must still name its source
        # accurately. Change each main Agent's assignment separately while
        # retaining the .56 path/comment, which must not count as version proof.
        for relative in AGENTS[:2]:
            with self.subTest(agent=relative):
                original = self.files[relative]
                changed = original.replace(b'"0.3.56"', b'"0.3.55"')
                self.assertNotEqual(changed, original)
                self.write(relative, changed)
                self.commit("fixture wrong main Agent version")
                wrong_head = self.git("rev-parse", "HEAD").decode().strip()
                output = self.output_dir / (Path(relative).stem + "-wrong-version.tar.gz")
                try:
                    with self.assertRaisesRegex((ValueError, RuntimeError, OSError),
                                                "SOURCE_REVIEW_VERSION_MISMATCH"):
                        self.build(output=output, expected_head=wrong_head)
                    self.assertFalse(output.exists())
                finally:
                    self.write(relative, original)
                    self.commit("fixture restore correct main Agent version")

    def moving_git(self):
        original = self.builder._git
        changed = False

        def call(repo, *args):
            nonlocal changed
            result = original(repo, *args)
            # Change only after the builder has read the original commit's
            # exact identity. This does not depend on its choice of show vs
            # cat-file for the subsequent immutable blob reads.
            resolved_original = bool(args) and args[0] == "rev-parse" and result.strip() == self.head.encode()
            if resolved_original and not changed:
                changed = True
                self.write("race-marker", b"fixture concurrent ref change")
                self.commit("fixture ref moved while reading blobs")
            return result

        return call

    def test_mutable_ref_change_aborts_without_mixed_or_mislabelled_archive(self):
        with patch.object(self.builder, "_git", side_effect=self.moving_git()):
            with self.assertRaisesRegex((ValueError, RuntimeError, OSError), "SOURCE_REVIEW_REF_CHANGED"):
                self.build()
        self.assertNotEqual(self.git("rev-parse", "HEAD").decode().strip(), self.head)
        self.assert_no_output()

    def test_immutable_commit_ref_remains_valid_when_unrelated_head_moves(self):
        with patch.object(self.builder, "_git", side_effect=self.moving_git()):
            self.build(ref=self.head)
        self.assertNotEqual(self.git("rev-parse", "HEAD").decode().strip(), self.head)
        index, payloads = self.inspect_archive()
        self.assertEqual(index["source_commit"], self.head)
        self.assertEqual(index["source_tree"], self.tree)
        self.assertEqual(payloads["source/" + AGENTS[1]], self.files[AGENTS[1]])

    def test_replace_refs_cannot_substitute_bytes_for_exact_pinned_commit(self):
        # Replacement refs are navigation/repair overlays, not the original
        # commit's content identity. Only this owned fixture creates one.
        replacement_bytes = self.files[AGENTS[1]] + b"\n# SYNTHETIC_REPLACEMENT_NOT_IN_PINNED_COMMIT\n"
        self.write(AGENTS[1], replacement_bytes)
        self.commit("fixture replacement content")
        replacement = self.git("rev-parse", "HEAD").decode().strip()
        self.git("replace", self.head, replacement)
        self.build(ref=self.head)
        index, payloads = self.inspect_archive()
        self.assertEqual(index["source_commit"], self.head)
        self.assertEqual(index["source_tree"], self.tree,
                         "replacement tree must not be attributed to the original commit SHA")
        self.assertEqual(payloads["source/" + AGENTS[1]], self.files[AGENTS[1]],
                         "Git replacement bytes must not enter the source review")
        self.assertEqual(payloads["valk/windows-agent-0.3.56-eventv2-review.txt"], self.files[AGENTS[1]])

    def test_provenance_claims_cannot_fabricate_signing_pin_admission_or_installability(self):
        self.build()
        index, payloads = self.inspect_archive()
        self.assert_not_approved(index)
        for relative in PROVENANCE:
            # Provenance remains bytes from Git, labelled as source evidence;
            # it cannot override the review index's authority boundaries.
            self.assertEqual(payloads["source/" + relative], self.files[relative])
            self.assertIs(json.loads(payloads["source/" + relative])["installable"], True)

    def test_cli_builds_same_source_review_with_explicit_head(self):
        result = subprocess.run(
            [sys.executable, str(BUILDER), "--repo", str(self.repo), "--output", str(self.output),
             "--ref", "HEAD", "--expected-head", self.head],
            capture_output=True, text=True, env=self.env, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        index, _ = self.inspect_archive()
        self.assertEqual(index["source_commit"], self.head)
        self.assert_not_approved(index)


if __name__ == "__main__":
    unittest.main()
