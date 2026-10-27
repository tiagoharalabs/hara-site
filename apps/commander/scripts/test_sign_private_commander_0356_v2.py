"""Directed tests use a fresh disposable RSA key; never the HARA signing key.

Only test fixtures monkeypatch pins in memory. The production CLI exposes no
pin/version/key-generation override and still accepts only the recorded .56.
"""
from contextlib import ExitStack, contextmanager, redirect_stderr
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

HERE = Path(__file__).parent
SPEC = importlib.util.spec_from_file_location("private_qa_signer_under_test", HERE / "sign_private_commander_0356_v2.py")
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)


def b64int(value):
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def jwks(key):
    v = key.private_numbers()
    public = {"kty": "RSA", "alg": "RS256", "kid": S.KID, "use": "sig",
              "n": b64int(v.public_numbers.n), "e": b64int(v.public_numbers.e)}
    private = dict(public, d=b64int(v.d), p=b64int(v.p), q=b64int(v.q),
                   dp=b64int(v.dmp1), dq=b64int(v.dmq1), qi=b64int(v.iqmp))
    return public, private


class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public, cls.private = jwks(cls.key)

    @contextmanager
    def fixture(self):
        with tempfile.TemporaryDirectory(prefix="commander-private-sign-unit-") as temporary:
            base = Path(temporary)
            repo = base / "repo"
            repo.mkdir()
            source = repo / "source"
            source.mkdir()
            (source / "agent").mkdir()
            (source / "install").mkdir()
            blobs = {"agent/linux.py": b"# Synthetic Agent 0.3.56 fixture\n",
                     "agent/windows.ps1": b"# Synthetic Agent 0.3.56 fixture\r\n",
                     "install/linux.sh": (f'RELEASE_SIGNING_KID="{S.KID}"\n'
                         f'RELEASE_SIGNING_N="{self.public["n"]}"\n'
                         f'RELEASE_SIGNING_E="{self.public["e"]}"\n').encode(),
                     "install/windows.ps1": (f'$ReleaseSigningKid = "{S.KID}"\r\n'
                         f'$ReleaseSigningN = "{self.public["n"]}"\r\n'
                         f'$ReleaseSigningE = "{self.public["e"]}"\r\n').encode()}
            for name, raw in blobs.items():
                (source / name).write_bytes(raw)
            pins = {name: S.sha(raw) for name, raw in blobs.items()}
            manifest_raw = S.encoded({"schema": "hara.commander-agent-release.v1",
                "product": "H.A.R.A. Commander", "channel": "stable", "agent_version": "0.3.56",
                "files": [{"path": name, "sha256": pins[name], "bytes": len(raw)}
                          for name, raw in blobs.items()]})
            manifest = repo / "agent-manifest.unsigned.json"
            manifest.write_bytes(manifest_raw)
            public = repo / "public.jwk"
            public.write_bytes(S.encoded(self.public))
            secret = base / "private.jwk"
            secret.write_bytes(S.encoded(self.private))
            secret.chmod(0o600)
            stage = base / "private-stage"
            with ExitStack() as stack:
                stack.enter_context(patch.object(S, "ARTIFACT_SHA256", pins))
                stack.enter_context(patch.object(S, "MANIFEST_SHA256", S.sha(manifest_raw)))
                stack.enter_context(patch.object(S, "PUBLIC_SHA256", S.sha(public.read_bytes())))
                yield {"base": base, "repo": repo, "source": source, "manifest": manifest,
                       "public": public, "secret": secret, "stage": stage, "blobs": blobs,
                       "manifest_raw": manifest_raw}

    def sign(self, f):
        return S.sign_stage(f["repo"], f["source"], f["manifest"], f["public"],
                            f["secret"], f["stage"])

    def test_exact_byte_stage_real_signature_and_independent_openssl_verify(self):
        with self.fixture() as f:
            original_key = f["secret"].read_bytes()
            report = self.sign(f)
            self.assertEqual(S.resource.getrlimit(S.resource.RLIMIT_CORE), (0, 0))
            self.assertEqual(report, S.verify_stage(f["repo"], f["stage"]))
            self.assertEqual(report["rsa_bits_observed"], 2048)  # No fixed 3072-bit assumption.
            self.assertEqual((f["stage"] / "release/agent-manifest.json").read_bytes(), f["manifest_raw"])
            for name, raw in f["blobs"].items():
                self.assertEqual((f["stage"] / name).read_bytes(), raw)
                self.assertEqual((f["source"] / name).read_bytes(), raw)
            self.assertEqual(f["secret"].read_bytes(), original_key)
            self.assertEqual(os.stat(f["stage"]).st_mode & 0o777, 0o700)
            for key in ("native_acceptance", "installation_performed", "release_approval",
                        "runtime_activation_verified", "production_mutated", "private_key_exported"):
                self.assertFalse(report[key])
            self.assertEqual(report["intended_event_v2"], "OFF")
            self.assertTrue(report["signature_verified"])
            public_pem = f["base"] / "public.pem"
            public_pem.write_bytes(self.key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
            obj = json.loads((f["stage"] / "release/agent-manifest.sig.json").read_bytes())
            raw_signature = f["base"] / "signature.bin"
            raw_signature.write_bytes(S.unb64(obj["signature"]))
            openssl = shutil.which("openssl")
            self.assertIsNotNone(openssl)
            result = subprocess.run([openssl, "dgst", "-sha256", "-verify", str(public_pem),
                "-signature", str(raw_signature), str(f["manifest"])], capture_output=True,
                timeout=10, check=False)
            self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_artifact_tampering_denied_before_reading_private_key_or_output(self):
        with self.fixture() as f, patch.object(S, "make_signature") as private_read:
            (f["source"] / "agent/linux.py").write_bytes(b"changed\n")
            with self.assertRaisesRegex(S.SigningError, "ARTIFACT_BYTES_MISMATCH"):
                self.sign(f)
            private_read.assert_not_called()
            self.assertFalse(f["stage"].exists())

    def test_manifest_exact_bytes_and_public_raw_pin_are_enforced(self):
        for item, code in (("manifest", "MANIFEST_PIN_MISMATCH"), ("public", "PUBLIC_PIN_MISMATCH")):
            with self.subTest(item=item), self.fixture() as f:
                f[item].write_bytes(f[item].read_bytes() + b"\n")
                with self.assertRaisesRegex(S.SigningError, code):
                    self.sign(f)
                self.assertFalse(f["stage"].exists())

    def test_manifest_contract_duplicate_paths_and_bool_size_are_rejected(self):
        for change in ("version", "duplicate", "bool_bytes", "extra"):
            with self.subTest(change=change), self.fixture() as f:
                obj = json.loads(f["manifest_raw"])
                if change == "version": obj["agent_version"] = "0.3.43"
                elif change == "duplicate": obj["files"][3] = obj["files"][0]
                elif change == "bool_bytes": obj["files"][0]["bytes"] = True
                else: obj["acceptance"] = True
                raw = S.encoded(obj)
                f["manifest"].write_bytes(raw)
                with patch.object(S, "MANIFEST_SHA256", S.sha(raw)), self.assertRaises(S.SigningError):
                    self.sign(f)
                self.assertFalse(f["stage"].exists())
        with self.assertRaisesRegex(S.SigningError, "JSON_DUPLICATE_KEY"):
            S.strict_json(b'{"a":1,"a":2}')

    def test_installer_pin_mismatch_denied_even_with_fixture_artifact_pin(self):
        with self.fixture() as f:
            path = f["source"] / "install/windows.ps1"
            raw = path.read_bytes().replace(S.KID.encode(), b"commander-release-v1")
            path.write_bytes(raw)
            pins = dict(S.ARTIFACT_SHA256, **{"install/windows.ps1": S.sha(raw)})
            obj = json.loads(f["manifest_raw"])
            obj["files"][3]["sha256"] = pins["install/windows.ps1"]
            manifest = S.encoded(obj)
            f["manifest"].write_bytes(manifest)
            with patch.object(S, "ARTIFACT_SHA256", pins), patch.object(S, "MANIFEST_SHA256", S.sha(manifest)):
                with self.assertRaisesRegex(S.SigningError, "INSTALLER_PUBLIC_PIN_MISMATCH"):
                    self.sign(f)
            self.assertFalse(f["stage"].exists())

    def test_private_key_wrong_mode_or_symlink_or_hardlink_is_rejected(self):
        for mode in ("permissions", "symlink", "hardlink"):
            with self.subTest(mode=mode), self.fixture() as f:
                if mode == "permissions": f["secret"].chmod(0o644)
                elif mode == "symlink":
                    actual = f["base"] / "actual-key.jwk"
                    f["secret"].rename(actual)
                    f["secret"].symlink_to(actual)
                else: os.link(f["secret"], f["base"] / "key-hardlink")
                with self.assertRaises((S.SigningError, OSError)):
                    self.sign(f)
                self.assertFalse(f["stage"].exists())

    def test_mismatched_private_key_and_private_fields_in_public_jwk_rejected(self):
        with self.fixture() as f:
            wrong = dict(self.private, kid="other")
            f["secret"].write_bytes(S.encoded(wrong))
            with self.assertRaisesRegex(S.SigningError, "PRIVATE_PUBLIC_KEY_MISMATCH"):
                self.sign(f)
        raw = S.encoded(dict(self.public, d="AQAB"))
        with patch.object(S, "PUBLIC_SHA256", S.sha(raw)):
            with self.assertRaisesRegex(S.SigningError, "PUBLIC_JWK_INVALID"):
                S.public_key(raw)

    def test_create_only_output_and_repository_exclusion(self):
        with self.fixture() as f:
            self.sign(f)
            before = (f["stage"] / "release/agent-manifest.sig.json").read_bytes()
            with self.assertRaisesRegex(S.SigningError, "OUTPUT_ALREADY_EXISTS"):
                self.sign(f)
            self.assertEqual((f["stage"] / "release/agent-manifest.sig.json").read_bytes(), before)
        with self.fixture() as f:
            f["stage"] = f["repo"] / "public"
            with self.assertRaisesRegex(S.SigningError, "OUTPUT_MUST_BE_OUTSIDE_REPOSITORY"):
                self.sign(f)
            self.assertFalse(f["stage"].exists())

    def test_verification_rejects_changed_signature_and_extra_stage_files(self):
        with self.fixture() as f:
            self.sign(f)
            path = f["stage"] / "release/agent-manifest.sig.json"
            obj = json.loads(path.read_bytes())
            signature = bytearray(S.unb64(obj["signature"]))
            signature[-1] ^= 1
            obj["signature"] = base64.urlsafe_b64encode(signature).decode().rstrip("=")
            path.chmod(0o600)
            path.write_bytes(S.encoded(obj))
            with self.assertRaisesRegex(S.SigningError, "SIGNATURE_INVALID"):
                S.verify_stage(f["repo"], f["stage"])
        with self.fixture() as f:
            self.sign(f)
            (f["stage"] / "unexpected.txt").write_text("fixture")
            with self.assertRaisesRegex(S.SigningError, "OUTPUT_FILESET"):
                S.verify_stage(f["repo"], f["stage"])

    def test_signature_metadata_extra_fields_and_noncanonical_encoding_rejected(self):
        with self.fixture() as f:
            self.sign(f)
            manifest = f["manifest_raw"]
            original = json.loads((f["stage"] / "release/agent-manifest.sig.json").read_bytes())
            for change in ("kid", "hash", "extra", "padding"):
                obj = dict(original)
                if change == "kid": obj["kid"] = "commander-release-v1"
                elif change == "hash": obj["manifest_sha256"] = "0" * 64
                elif change == "extra": obj["native_acceptance"] = True
                else: obj["signature"] += "="
                with self.subTest(change=change), self.assertRaises(S.SigningError):
                    S.verify_signature(manifest, S.encoded(obj), self.key.public_key())

    def test_source_symlink_and_output_parent_symlink_are_denied(self):
        with self.fixture() as f:
            original = f["source"] / "agent/linux.py"
            replacement = f["base"] / "linux-copy.py"
            original.rename(replacement)
            original.symlink_to(replacement)
            with self.assertRaises(OSError): self.sign(f)
            self.assertFalse(f["stage"].exists())
        with self.fixture() as f:
            alias = f["base"] / "alias"
            alias.symlink_to(f["base"], target_is_directory=True)
            f["stage"] = alias / "output"
            with self.assertRaisesRegex(S.SigningError, "PARENT_NOT_DIRECTORY_OR_SYMLINK"):
                self.sign(f)

    def test_cli_failure_never_prints_jwk_or_raw_library_error(self):
        with self.fixture() as f:
            private = dict(self.private, d="A")
            f["secret"].write_bytes(S.encoded(private))
            stderr = io.StringIO()
            args = ["sign", "--repo-root", str(f["repo"]), "--output-dir", str(f["stage"]),
                    "--source-root", str(f["source"]), "--manifest", str(f["manifest"]),
                    "--public-jwk", str(f["public"]), "--private-jwk", str(f["secret"])]
            with redirect_stderr(stderr): self.assertEqual(S.main(args), 2)
            self.assertEqual(stderr.getvalue(), "PRIVATE_QA_SIGNING_HOLD=INPUT_OR_CRYPTO_OPERATION_FAILED\n")
            self.assertNotIn(self.private["d"], stderr.getvalue())
            self.assertNotIn(str(f["secret"]), stderr.getvalue())
            self.assertFalse(f["stage"].exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
