"""Only synthetic sources and the existing PUBLIC v2 key; no signer/installer."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("builder", HERE / "build_release_manifest.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
ROOT = HERE.parents[2]
KEY = json.loads((ROOT / "scripts/fixtures/commercial_v2_043_signature/release-signing-public.jwk").read_text())


class JointBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "candidate"
        self.blobs = {
            "agent/linux.py": b'AGENT_VERSION = "0.3.56"\n',
            "agent/windows.ps1": b'$AgentVersion = "0.3.56"\n',
            "install/linux.sh": (f'RELEASE_SIGNING_KID="{KEY["kid"]}"\nRELEASE_SIGNING_N="{KEY["n"]}"\nRELEASE_SIGNING_E="AQAB"\n'
                                 '# {"agent_version":"0.3.56"}\n').encode(),
            "install/windows.ps1": (f'$ReleaseSigningKid = "{KEY["kid"]}"\n$ReleaseSigningN = "{KEY["n"]}"\n$ReleaseSigningE = "AQAB"\n'
                                    '# agent_version="0.3.56"\n').encode(),
        }
        self.policy = {"schema": "hara.commander-commercial-source-review.v1",
                       "status": "SOURCE_ADAPTION_REVIEWED", "version": "0.3.56", "artifacts": {}}
        self.write()

    def write(self):
        for rel, blob in self.blobs.items():
            p = self.source / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(blob)
            self.policy["artifacts"][rel] = {
                "classification": "commercial", "source_commit": "a" * 40,
                "review_reference": "synthetic-review-not-product-admission",
                "sha256": hashlib.sha256(blob).hexdigest(),
            }

    def build(self):
        return builder.build_candidate(self.source, self.output, self.policy)

    def test_all_four_exact_bytes_and_unsigned_manifest_are_built_together(self):
        result = self.build()
        self.assertEqual(result["artifact_count"], 4)
        self.assertFalse(result["signature_issued"])
        m = json.loads((self.output / "release/agent-manifest.json").read_text())
        raw = (self.output / "release/agent-manifest.json").read_bytes()
        self.assertNotIn(b"\r\n", raw)
        self.assertEqual(result["manifest_sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotIn(b"\r\n", (self.output / "release/SHA256SUMS").read_bytes())
        self.assertEqual([r["path"] for r in m["files"]], list(builder.FILES))
        for row in m["files"]:
            blob = (self.output / row["path"]).read_bytes()
            self.assertEqual(blob, self.blobs[row["path"]])
            self.assertEqual(row["bytes"], len(blob))
            self.assertEqual(row["sha256"], hashlib.sha256(blob).hexdigest())
        self.assertFalse((self.output / "release/agent-manifest.sig.json").exists())
        self.assertEqual(builder.snapshot(self.source), self.blobs)

    def test_mixed_agent_versions_are_not_renumbered(self):
        self.blobs["agent/linux.py"] = b'AGENT_VERSION = "0.3.54"\n'
        self.write()
        with self.assertRaisesRegex(SystemExit, "AGENT_VERSION_MISMATCH"):
            self.build()
        self.assertFalse(self.output.exists())

    def test_installer_literal_drift_fails(self):
        for path in ("install/linux.sh", "install/windows.ps1"):
            bad = copy.deepcopy(self.blobs)
            bad[path] = bad[path].replace(b"0.3.56", b"0.3.49")
            with self.assertRaisesRegex(ValueError, "INSTALLER_AGENT_VERSION_MISMATCH"):
                builder.render(bad)

    def test_current_floor_cannot_be_lowered_by_source_policy(self):
        self.blobs = {p: b.replace(b"0.3.56", b"0.3.54") for p, b in self.blobs.items()}
        self.policy["version"] = "0.3.54"
        self.write()
        with self.assertRaisesRegex(ValueError, "COMMON_VERSION_BELOW_FLOOR"):
            self.build()

    def test_private_or_unreviewed_source_cannot_be_admitted_by_stable_channel(self):
        self.policy["status"] = "PRIVATE_RC"
        with self.assertRaisesRegex(ValueError, "COMMERCIAL_SOURCE_REVIEW_REQUIRED"):
            self.build()

    def test_each_source_hash_is_independently_pinned(self):
        for rel in builder.FILES:
            policy = copy.deepcopy(self.policy)
            policy["artifacts"][rel]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "SOURCE_PROVENANCE_OR_DIGEST"):
                builder.build_candidate(self.source, self.output, policy)

    def test_private_component_and_missing_review_are_rejected(self):
        for field, value in (("classification", "FOUNDER_CANARY"), ("review_reference", ""),
                             ("source_commit", "main")):
            policy = copy.deepcopy(self.policy)
            policy["artifacts"]["agent/linux.py"][field] = value
            with self.assertRaisesRegex(ValueError, "SOURCE_PROVENANCE_OR_DIGEST"):
                builder.build_candidate(self.source, self.output, policy)

    def test_symlink_source_fails_without_following_it(self):
        p = self.source / "agent/linux.py"
        p.rename(self.root / "agent.py")
        p.symlink_to(self.root / "agent.py")
        with self.assertRaisesRegex(ValueError, "SYMLINK"):
            self.build()

    def test_existing_stage_and_its_signature_are_preserved(self):
        self.output.mkdir()
        signature = self.output / "old-signature"
        signature.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "DESTINATION_UNSAFE_OR_EXISTS"):
            self.build()
        self.assertEqual(signature.read_bytes(), b"preserve")

    def test_changed_source_cannot_leave_a_partial_stage(self):
        altered = dict(self.blobs)
        altered["agent/linux.py"] += b"# changed"
        with patch.object(builder, "snapshot", side_effect=[self.blobs, altered]):
            with self.assertRaisesRegex(ValueError, "SOURCE_CHANGED_DURING_BUILD"):
                self.build()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob(".commander-unsigned-*")), [])

    def test_v1_or_changed_installer_key_cannot_be_used_for_new_release(self):
        self.blobs["install/windows.ps1"] = self.blobs["install/windows.ps1"].replace(
            b"commander-release-v2", b"commander-release-v1")
        self.write()
        with self.assertRaisesRegex(ValueError, "INSTALLER_TRUST_ANCHOR"):
            self.build()

    def test_duplicate_version_declaration_fails(self):
        bad = dict(self.blobs)
        bad["agent/linux.py"] += b'AGENT_VERSION = "0.3.56"\n'
        with self.assertRaisesRegex(SystemExit, "AGENT_VERSION_NOT_FOUND"):
            builder.render(bad)

    def test_explicit_draft_mode_builds_proposal_without_admitting_it(self):
        self.policy["status"] = "SOURCE_ADAPTATION_PROPOSED"
        for row in self.policy["artifacts"].values():
            row["classification"] = "commercial-candidate"
        with self.assertRaisesRegex(ValueError, "COMMERCIAL_SOURCE_REVIEW_REQUIRED"):
            self.build()
        result = builder.build_candidate(self.source, self.output, self.policy, draft=True)
        self.assertEqual(result["state"], "UNSIGNED_DRAFT_REQUIRES_ADMISSION")
        self.assertFalse(result["signature_issued"])
        self.assertFalse(result["published"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
