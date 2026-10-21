#!/usr/bin/env python3
"""GET-only public release gate using the pins in both served installers.

The trusted v2 public key comes from the reviewed Git bundle. No installer is
executed and no private signing material is read. Exit 2 means release HOLD.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

APP = Path(__file__).resolve().parents[1]
TRUSTED_JWK = APP / "release-bundles/commercial-0.3.43-v4-autoreconnect/release/release-signing-public.jwk"
DOMAIN = "https://commander.haralabs.com.br"
ASSETS = ("agent/linux.py", "agent/windows.ps1", "install/linux.sh", "install/windows.ps1")
PATHS = ("release/agent-manifest.json", "release/agent-manifest.sig.json", *ASSETS)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args: object) -> None:
        raise ValueError("PUBLIC_RELEASE_REDIRECT_DENIED")


def b64bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def read_live(url: str) -> dict[str, bytes]:
    if not url.startswith("https://") or url.rstrip("/") != DOMAIN:
        raise ValueError("PUBLIC_RELEASE_DOMAIN_INVALID")
    opener = urllib.request.build_opener(NoRedirect)
    result: dict[str, bytes] = {}
    for path in PATHS:
        request = urllib.request.Request(
            DOMAIN + "/" + path,
            headers={"Accept": "application/octet-stream",
                     "Cache-Control": "no-cache",
                     "User-Agent": "HARA-Commander-Live-Release-Gate/1"},
            method="GET",
        )
        try:
            with opener.open(request, timeout=20) as response:
                if response.status != 200:
                    raise ValueError("PUBLIC_RELEASE_HTTP_INVALID:" + path)
                raw = response.read(5 * 1024 * 1024 + 1)
                if len(raw) > 5 * 1024 * 1024:
                    raise ValueError("PUBLIC_RELEASE_ASSET_TOO_LARGE:" + path)
                result[path] = raw
        except urllib.error.HTTPError as exc:
            raise ValueError(f"PUBLIC_ASSET_HTTP_{exc.code}:{path}") from None
        except urllib.error.URLError:
            raise ValueError("PUBLIC_ASSET_NETWORK_FAILURE:" + path) from None
    return result


def installer_pin(script: str, platform: str) -> tuple[str, str, str]:
    if platform == "LINUX":
        names = ("RELEASE_SIGNING_KID", "RELEASE_SIGNING_N", "RELEASE_SIGNING_E")
        patterns = [rf'^{name}="([^"]+)"$' for name in names]
    else:
        names = ("ReleaseSigningKid", "ReleaseSigningN", "ReleaseSigningE")
        patterns = [rf'^\${name} = "([^"]+)"$' for name in names]
    found = [re.findall(pattern, script, re.M) for pattern in patterns]
    if any(len(match) != 1 for match in found):
        raise ValueError("PUBLIC_INSTALLER_PIN_INVALID:" + platform)
    return tuple(match[0] for match in found)


def verifies_with_pin(pin: tuple[str, str, str], signature: dict, manifest_raw: bytes) -> bool:
    try:
        key = rsa.RSAPublicNumbers(int.from_bytes(b64bytes(pin[2]), "big"),
                                   int.from_bytes(b64bytes(pin[1]), "big")).public_key()
        key.verify(b64bytes(signature["signature"]), manifest_raw,
                   padding.PKCS1v15(), hashes.SHA256())
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False


def inspect(blobs: dict[str, bytes]) -> dict:
    trusted = json.loads(TRUSTED_JWK.read_text(encoding="utf-8"))
    manifest_raw = blobs[PATHS[0]]
    manifest = json.loads(manifest_raw)
    signature = json.loads(blobs[PATHS[1]])
    errors: list[str] = []
    pins = {}
    for platform, path in (("LINUX", "install/linux.sh"), ("WINDOWS", "install/windows.ps1")):
        try:
            pins[platform] = installer_pin(blobs[path].decode("utf-8"), platform)
            if pins[platform] != (trusted["kid"], trusted["n"], trusted["e"]):
                errors.append("SERVED_INSTALLER_UNTRUSTED_PIN:" + platform)
            if pins[platform][0] != signature.get("kid"):
                errors.append("RELEASE_SIGNATURE_KID_MISMATCH:" + platform)
        except (UnicodeError, ValueError):
            errors.append("PUBLIC_INSTALLER_PIN_INVALID:" + platform)
    if signature.get("schema") != "hara.commander-release-signature.v1" or signature.get("alg") != "RS256":
        errors.append("RELEASE_SIGNATURE_METADATA_INVALID")
    if signature.get("manifest_sha256") != hashlib.sha256(manifest_raw).hexdigest():
        errors.append("RELEASE_MANIFEST_DIGEST_MISMATCH")
    if signature.get("kid") != trusted["kid"]:
        errors.append("RELEASE_SIGNER_NOT_AUTHORIZED")
    trusted_valid = verifies_with_pin((trusted["kid"], trusted["n"], trusted["e"]),
                                      signature, manifest_raw)
    if not trusted_valid:
        errors.append("RELEASE_SIGNATURE_NOT_VALID_FOR_TRUSTED_KEY")
    rows = manifest.get("files")
    by_path = {}
    if isinstance(rows, list):
        try:
            by_path = {row["path"]: row for row in rows}
        except (TypeError, KeyError):
            pass
    if (manifest.get("schema") != "hara.commander-agent-release.v1" or
            not isinstance(rows, list) or len(rows) != 4):
        errors.append("RELEASE_MANIFEST_SCHEMA_INVALID")
    if manifest.get("channel") != "stable":
        errors.append("RELEASE_MANIFEST_CHANNEL_INVALID")
    paths = (tuple(row.get("path") for row in rows)
             if isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
             else ())
    if paths != ASSETS:
        errors.append("RELEASE_MANIFEST_FILESET_INVALID")
    checks = {}
    for path in ASSETS:
        raw = blobs[path]
        row = by_path.get(path, {})
        valid = (row.get("sha256") == hashlib.sha256(raw).hexdigest() and
                 type(row.get("bytes")) is int and row["bytes"] == len(raw))
        checks[path] = {"sha256": hashlib.sha256(raw).hexdigest(),
                        "bytes": len(raw), "manifest_match": valid}
        if not valid:
            errors.append("RELEASE_ASSET_DIGEST_MISMATCH:" + path)
    version = manifest.get("agent_version")
    linux = re.search(rb'^AGENT_VERSION = "([^"]+)"$', blobs["agent/linux.py"], re.M)
    windows = re.search(rb'^\$AgentVersion = "([^"]+)"$', blobs["agent/windows.ps1"], re.M)
    if not isinstance(version, str) or not linux or linux.group(1).decode() != version:
        errors.append("RELEASE_LINUX_AGENT_VERSION_MISMATCH")
    if not isinstance(version, str) or not windows or windows.group(1).decode() != version:
        errors.append("RELEASE_WINDOWS_AGENT_VERSION_MISMATCH")
    return {
        "schema": "hara.commander-live-release-integrity.v1",
        "domain": DOMAIN, "state": "PASS" if not errors else "HOLD",
        "manifest_agent_version": version,
        "served_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "served_signature_sha256": hashlib.sha256(blobs[PATHS[1]]).hexdigest(),
        "served_signature_kid": signature.get("kid"),
        "trusted_kid": trusted["kid"],
        "signature_valid_for_trusted_key": trusted_valid,
        "signature_valid_for_served_installer_pin": {
            platform: verifies_with_pin(pin, signature, manifest_raw)
            for platform, pin in pins.items()
        },
        "files": checks, "errors": errors,
        "installer_executed": False, "production_mutation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    args = parser.parse_args()
    assert args.live
    try:
        result = inspect(read_live(DOMAIN))
    except (ValueError, KeyError, TypeError) as exc:
        reason = str(exc)
        if not re.fullmatch(r"PUBLIC_[A-Z0-9_]+(?::[a-z0-9./-]+)?", reason):
            reason = "PUBLIC_RELEASE_PARSE_INVALID"
        result = {"schema": "hara.commander-live-release-integrity.v1",
                  "domain": DOMAIN, "state": "HOLD", "errors": [reason],
                  "installer_executed": False, "production_mutation": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
