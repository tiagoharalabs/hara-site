#!/usr/bin/env python3
"""Offline regressions for the GET-only gate against exact signed bundle bytes."""
from __future__ import annotations

import json
from pathlib import Path
import urllib.error
from unittest.mock import patch

from verify_live_release_integrity import ASSETS, DOMAIN, PATHS, inspect, read_live

APP = Path(__file__).resolve().parents[1]
BUNDLE = APP / "release-bundles/commercial-0.3.43-v4-autoreconnect"


def original() -> dict[str, bytes]:
    return {name: (BUNDLE / name).read_bytes() for name in PATHS}


def expect_hold(blobs: dict[str, bytes], marker: str) -> None:
    result = inspect(blobs)
    assert result["state"] == "HOLD", result
    assert any(error.startswith(marker) for error in result["errors"]), result


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
    print("LIVE_GATE_OFFLINE_CHECKS=10")


if __name__ == "__main__":
    main()
