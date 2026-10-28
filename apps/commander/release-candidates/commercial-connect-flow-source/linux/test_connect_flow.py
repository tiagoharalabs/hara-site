"""Local synthetic fixtures only; no real token, VM, enrollment, or release."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("connect", HERE / "commander_connect.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
BASE = "https://commander.synthetic.invalid"


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def agent(v):
    return ('#!/usr/bin/env python3\nAGENT_VERSION = "' + v + '"\n').encode()


class SyntheticHttp:
    def __init__(self):
        self.urls = {}
        self.auth_status = 200
        self.auth_code = None
        self.gets = []

    def get(self, url, limit=2097152):
        self.gets.append(url)
        if url not in self.urls:
            raise c.Hold("RELEASE_DOWNLOAD_HTTP_404")
        result = self.urls[url]
        c.need(len(result) <= limit, "HTTP_RESPONSE_TOO_LARGE")
        return result

    def request(self, url, *, payload=None, token=None, limit=65536):
        if self.auth_status == "network":
            raise c.Hold("CONNECTION_UNAVAILABLE")
        if self.auth_status == 200:
            return 200, json.dumps({"ok": True, "device_id": payload["device_id"]}).encode()
        return self.auth_status, json.dumps({"code": self.auth_code}).encode()


class ConnectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        n = cls.key.public_key().public_numbers().n
        cls.test_modulus = b64(n.to_bytes((n.bit_length() + 7) // 8, "big"))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.http = SyntheticHttp()
        self.flow = c.Connect(self.http)
        self.flow.config_file = self.root / "config/device.env"
        self.flow.agent = self.root / "data/agent.py"
        self.flow.unit = self.root / "unit.service"
        self.flow.status = self.root / "runtime.json"
        self.calls = []
        self.runtime_calls = []
        self.flow.invoke_installer = self.invoke_synthetic_installer
        self.flow.start_and_verify = lambda v, device: self.runtime_calls.append((v, device))
        self.key_patch = patch.object(c, "MODULUS", self.test_modulus)
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.uid_patch = patch.object(c.os, "geteuid", return_value=1000)
        self.uid_patch.start()
        self.addCleanup(self.uid_patch.stop)

    def write_agent(self, v):
        self.flow.agent.parent.mkdir(parents=True, exist_ok=True)
        self.flow.agent.write_bytes(agent(v))
        self.flow.agent.chmod(0o700)

    def write_config(self):
        self.flow.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.flow.config_file.write_text("HARA_COMMANDER_URL=" + BASE + "\nHARA_DEVICE_ID=synthetic-device\nHARA_DEVICE_TOKEN=synthetic-secret-not-real\nHARA_DEVICE_ARCH=x86_64\nHARA_COMMANDER_APPROVAL_MODE=PERSISTENT_TRUSTED\n")
        self.flow.config_file.chmod(0o600)

    def release(self, v, *, latest=False, pair_supported=False):
        payloads = {
            "agent/linux.py": agent(v), "agent/windows.ps1": b"# synthetic windows agent\n",
            "install/linux.sh": b"#!/bin/bash\n# synthetic fixture never executed\n" + (c.PAIR_MARKER + b"\n" if pair_supported else b""),
            "install/windows.ps1": b"# synthetic windows installer\n",
        }
        obj = {"schema": "hara.commander-agent-release.v1", "product": "H.A.R.A. Commander", "channel": "stable", "agent_version": v,
               "files": [{"path": name, "bytes": len(payloads[name]), "sha256": hashlib.sha256(payloads[name]).hexdigest()} for name in c.PATHS]}
        raw = json.dumps(obj, separators=(",", ":")).encode()
        signed = self.key.sign(raw, padding.PKCS1v15(), hashes.SHA256())
        signature = json.dumps({"schema": "hara.commander-release-signature.v1", "alg": "RS256", "kid": c.KID,
                                "manifest_sha256": hashlib.sha256(raw).hexdigest(), "signature": b64(signed)}).encode()
        url = BASE + "/releases/" + v
        self.http.urls[url + "/release/agent-manifest.json"] = raw
        self.http.urls[url + "/release/agent-manifest.sig.json"] = signature
        for name, data in payloads.items():
            self.http.urls[url + "/" + name] = data
        if latest:
            self.http.urls[BASE + "/release/agent-manifest.json"] = raw
            self.http.urls[BASE + "/release/agent-manifest.sig.json"] = signature
        return raw, signature

    def invoke_synthetic_installer(self, path, action, base, release):
        self.calls.append(action)
        self.assertEqual(base, BASE)
        self.assertEqual(path.read_bytes(), release.installer)
        if action in ("install", "pair-existing", "re-enroll"):
            self.write_config()
            self.http.auth_status = 200
        if action in ("install", "update"):
            self.write_agent(release.version)

    def run_flow(self):
        with patch.dict(os.environ, {"HARA_COMMANDER_URL": BASE}):
            return self.flow.run()

    def assert_hold(self, code):
        with self.assertRaises(c.Hold) as caught:
            self.run_flow()
        self.assertEqual(caught.exception.code, code)

    def test_paired_current_preserves_credential_and_skips_installer(self):
        self.write_config(); self.write_agent("0.3.56"); self.release("0.3.56", latest=True)
        before = self.flow.config_file.read_bytes()
        result = self.run_flow()
        self.assertEqual(result["state"], "CONNECTED")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.flow.config_file.read_bytes(), before)

    def test_paired_older_updates_without_pairing(self):
        self.write_config(); self.write_agent("0.3.56")
        self.release("0.3.56"); self.release("0.3.57", latest=True)
        self.run_flow()
        self.assertEqual(self.calls, ["update"])

    def test_older_channel_is_hold_and_preserves_valid_pairing(self):
        self.write_config(); self.write_agent("0.3.56"); self.release("0.3.54", latest=True)
        before = self.flow.config_file.read_bytes(), self.flow.agent.read_bytes()
        self.assert_hold("AUTO_DOWNGRADE_REFUSED")
        self.assertTrue(self.flow.report["pairing_validated"])
        self.assertEqual(self.flow.report["phase"], "CHECK_UPDATE")
        self.assertEqual(self.calls, [])
        self.assertEqual(before, (self.flow.config_file.read_bytes(), self.flow.agent.read_bytes()))

    def test_network_failure_never_prompts_or_fetches_release(self):
        self.write_config(); self.write_agent("0.3.56"); self.http.auth_status = "network"
        self.assert_hold("CONNECTION_UNAVAILABLE")
        self.assertEqual(self.calls, []); self.assertEqual(self.http.gets, [])

    def test_ambiguous_401_does_not_reenroll(self):
        self.write_config(); self.write_agent("0.3.56")
        self.http.auth_status = 401; self.http.auth_code = "SOMETHING_ELSE"
        self.assert_hold("ENROLLMENT_VALIDATION_AMBIGUOUS")
        self.assertEqual(self.calls, [])

    def test_immutable_manifest_difference_rejected(self):
        self.write_config(); self.write_agent("0.3.56")
        self.release("0.3.56", latest=True)
        self.release("0.3.56", pair_supported=True)
        self.assert_hold("LATEST_IMMUTABLE_MANIFEST_MISMATCH")
        self.assertEqual(self.calls, [])

    def test_agent_corruption_before_any_install_or_token(self):
        self.write_config(); self.write_agent("0.3.56"); self.release("0.3.56", latest=True)
        self.http.urls[BASE + "/releases/0.3.56/agent/linux.py"] = b"corrupt"
        self.assert_hold("RELEASE_PAYLOAD_MISMATCH")
        self.assertEqual(self.calls, [])

    def test_unknown_signature_key_rejected(self):
        self.write_config(); self.write_agent("0.3.56"); self.release("0.3.56", latest=True)
        url = BASE + "/release/agent-manifest.sig.json"
        sig = json.loads(self.http.urls[url]); sig["kid"] = "untrusted"
        self.http.urls[url] = json.dumps(sig).encode()
        self.assert_hold("RELEASE_SIGNATURE_INVALID")

    def test_installed_unpaired_old_installer_refuses_before_token(self):
        self.write_agent("0.3.56"); self.release("0.3.56", latest=True)
        self.assert_hold("SIGNED_INSTALLER_PAIR_EXISTING_UNSUPPORTED")
        self.assertEqual(self.calls, [])

    def test_installed_unpaired_uses_pair_existing_then_update(self):
        self.write_agent("0.3.56"); self.release("0.3.56"); self.release("0.3.57", latest=True, pair_supported=True)
        with patch.object(self.flow, "require_terminal"):
            result = self.run_flow()
        self.assertEqual(self.calls, ["pair-existing", "update"])
        self.assertEqual(result["state"], "CONNECTED")

    def test_tty_path_existence_is_not_authority_to_prompt(self):
        self.release("0.3.56", latest=True)
        with patch.object(c.os, "open", side_effect=OSError("synthetic no tty")):
            self.assert_hold("PAIRING_REQUIRES_LOCAL_TERMINAL")
        self.assertEqual(self.calls, [])

    def test_failed_post_pair_update_retains_pairing_confirmed(self):
        self.write_agent("0.3.56"); self.release("0.3.56"); self.release("0.3.57", latest=True, pair_supported=True)
        def fail_update(path, action, base, release):
            if action == "update":
                self.calls.append(action)
                raise c.Hold("SIGNED_INSTALLER_ACTION_FAILED")
            self.invoke_synthetic_installer(path, action, base, release)
        self.flow.invoke_installer = fail_update
        with patch.object(self.flow, "require_terminal"):
            self.assert_hold("SIGNED_INSTALLER_ACTION_FAILED")
        self.assertTrue(self.flow.report["pairing_validated"])
        self.assertEqual(self.flow.report["phase"], "UPDATE")
        self.assertEqual(self.calls, ["pair-existing", "update"])

    def test_signed_metadata_does_not_allow_mismatched_old_agent(self):
        self.write_config(); self.write_agent("0.3.56"); self.release("0.3.56", latest=True)
        self.flow.agent.write_bytes(agent("0.3.56") + b"# changed locally\n")
        self.assert_hold("INSTALLED_AGENT_INTEGRITY_FAILED")
        self.assertEqual(self.calls, [])

    def test_cross_origin_qa_override_refused(self):
        with self.assertRaises(c.Hold) as caught:
            c.Release(self.http, BASE, "https://elsewhere.invalid/releases/0.3.56")
        self.assertEqual(caught.exception.code, "QA_RELEASE_SELECTION_INVALID")
        self.assertEqual(self.http.gets, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
