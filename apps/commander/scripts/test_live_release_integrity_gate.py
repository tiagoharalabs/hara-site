#!/usr/bin/env python3
"""Offline regressions for the GET-only gate against exact signed bundle bytes."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import urllib.error
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from verify_live_release_integrity import ASSETS, DOMAIN, PATHS, TRUSTED_JWK, inspect, installer_pin, read_live

APP = Path(__file__).resolve().parents[1]
BUNDLE = APP / "release-bundles/commercial-0.3.43-v4-autoreconnect"


def original() -> dict[str, bytes]:
    return {name: (BUNDLE / name).read_bytes() for name in PATHS}


def expect_hold(blobs: dict[str, bytes], marker: str) -> None:
    result = inspect(blobs)
    assert result["state"] == "HOLD", result
    assert any(error.startswith(marker) for error in result["errors"]), result


def qa_signed_manifest(baseline: dict[str, bytes], change, key, qa_public: dict) -> dict[str, bytes]:
    """Create an internally consistent QA release; the private key stays in memory."""
    bad = dict(baseline)
    manifest = json.loads(bad["release/agent-manifest.json"])
    change(manifest)
    signature = json.loads(bad["release/agent-manifest.sig.json"])
    for platform, path in (("LINUX", "install/linux.sh"), ("WINDOWS", "install/windows.ps1")):
        old_n = installer_pin(baseline[path].decode(), platform)[1].encode()
        assert baseline[path].count(old_n) == 1
        bad[path] = baseline[path].replace(old_n, qa_public["n"].encode())
        for row in manifest["files"]:
            if row["path"] == path:
                row["bytes"] = len(bad[path])
                row["sha256"] = hashlib.sha256(bad[path]).hexdigest()
    manifest_raw = json.dumps(manifest).encode()
    bad["release/agent-manifest.json"] = manifest_raw
    signature["manifest_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
    signature["signature"] = base64.urlsafe_b64encode(
        key.sign(manifest_raw, padding.PKCS1v15(), hashes.SHA256())
    ).rstrip(b"=").decode()
    bad["release/agent-manifest.sig.json"] = json.dumps(signature).encode()
    return bad


def main() -> None:
    baseline = original()
    valid = inspect(baseline)
    assert valid["state"] == "PASS", valid
    print("LIVE_GATE_SIGNED_V2_BASE=PASS")

    bad = dict(baseline)
    bad["agent/linux.py"] += b"\n# newer unsigned agent\n"
    expect_hold(bad, "RELEASE_ASSET_DIGEST_MISMATCH:agent/linux.py")
    print("LIVE_GATE_OLD_MANIFEST_NEW_AGENT=DENIED")

    for path in ASSETS:
        bad = dict(baseline)
        bad[path] += b"\n# tampered\n"
        expect_hold(bad, "RELEASE_ASSET_DIGEST_MISMATCH:" + path)
    print("LIVE_GATE_FOUR_ASSET_TAMPER=DENIED")

    bad = dict(baseline)
    old_installer = APP / "public/install/linux.sh"
    bad["install/linux.sh"] = old_installer.read_bytes()
    expect_hold(bad, "SERVED_INSTALLER_UNTRUSTED_PIN:LINUX")
    print("LIVE_GATE_SERVED_INSTALLER_KEY_DRIFT=DENIED")

    bad = dict(baseline)
    signature = json.loads(bad["release/agent-manifest.sig.json"])
    signature["kid"] = "commander-release-v1"
    bad["release/agent-manifest.sig.json"] = json.dumps(signature).encode()
    expect_hold(bad, "RELEASE_SIGNATURE_KID_MISMATCH:LINUX")
    print("LIVE_GATE_KID_MISMATCH=DENIED")

    bad = dict(baseline)
    manifest = json.loads(bad["release/agent-manifest.json"])
    manifest["agent_version"] = "0.3.99"
    bad["release/agent-manifest.json"] = json.dumps(manifest).encode()
    expect_hold(bad, "RELEASE_SIGNATURE_NOT_VALID_FOR_TRUSTED_KEY")
    print("LIVE_GATE_MANIFEST_TAMPER=DENIED")

    # A valid RSA signature under an ephemeral QA trust anchor still cannot
    # turn a Founder channel or reordered manifest into a commercial release.
    qa_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    qa_public = json.loads(TRUSTED_JWK.read_text())
    numbers = qa_key.public_key().public_numbers()
    qa_public["n"] = base64.urlsafe_b64encode(
        numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
    ).rstrip(b"=").decode()
    with tempfile.TemporaryDirectory() as temporary:
        qa_public_path = Path(temporary) / "qa-public.jwk"
        qa_public_path.write_text(json.dumps(qa_public))
        for change, marker in (
            (lambda item: item.update(channel="FOUNDER_CANARY"),
             "RELEASE_MANIFEST_CHANNEL_INVALID"),
            (lambda item: item["files"].reverse(),
             "RELEASE_MANIFEST_FILESET_INVALID"),
        ):
            bad = qa_signed_manifest(baseline, change, qa_key, qa_public)
            with patch("verify_live_release_integrity.TRUSTED_JWK", qa_public_path):
                result = inspect(bad)
            assert result["signature_valid_for_trusted_key"] is True, result
            assert result["signature_valid_for_served_installer_pin"] == {
                "LINUX": True, "WINDOWS": True,
            }, result
            assert result["state"] == "HOLD", result
            assert result["errors"] == [marker], result
    print("LIVE_GATE_FOUNDER_CHANNEL_AND_FILE_ORDER=DENIED")

    class Unauthorized:
        def open(self, request, timeout):
            raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    with patch("verify_live_release_integrity.urllib.request.build_opener", return_value=Unauthorized()):
        try:
            read_live(DOMAIN)
        except ValueError as exc:
            assert str(exc) == "PUBLIC_ASSET_HTTP_401:release/agent-manifest.json"
        else:
            raise AssertionError("LIVE_GATE_HTTP_401_NOT_CLASSIFIED")
    print("LIVE_GATE_HTTP_401_CLASSIFIED_SEPARATELY=PASS")

    assert valid["installer_executed"] is False
    assert valid["production_mutation"] is False
    print("LIVE_GATE_OFFLINE_CHECKS=12")


if __name__ == "__main__":
    main()
