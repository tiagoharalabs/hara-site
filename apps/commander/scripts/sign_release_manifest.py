#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
MANIFEST = APP / "public" / "release" / "agent-manifest.json"
SIGNATURE = APP / "public" / "release" / "agent-manifest.sig.json"
PUBLIC_JWK = APP / "public" / "release" / "release-signing-public.jwk"
SCHEMA = "hara.commander-release-signature.v1"
ALG = "RS256"
KID = "commander-release-v1"


def b64ud(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * ((4 - len(value) % 4) % 4))


def b64u(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def sign_pkcs1_v15_sha256(data: bytes, jwk: dict) -> str:
    n = int.from_bytes(b64ud(jwk["n"]), "big")
    d = int.from_bytes(b64ud(jwk["d"]), "big")
    size = (n.bit_length() + 7) // 8
    digest = hashlib.sha256(data).digest()
    digest_info = bytes.fromhex("3031300d060960864801650304020105000420") + digest
    padding = size - len(digest_info) - 3
    if padding < 8:
        raise SystemExit("RELEASE_SIGNING_KEY_INVALID")
    em = b"\x00\x01" + b"\xff" * padding + b"\x00" + digest_info
    signature = pow(int.from_bytes(em, "big"), d, n).to_bytes(size, "big")
    return b64u(signature)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-jwk", default=os.environ.get("HARA_COMMANDER_RELEASE_SIGNING_PRIVATE_JWK_FILE"))
    args = parser.parse_args()
    if not args.private_jwk:
        raise SystemExit("RELEASE_SIGNING_PRIVATE_JWK_REQUIRED")
    private = json.loads(Path(args.private_jwk).read_text(encoding="utf-8"))
    public = json.loads(PUBLIC_JWK.read_text(encoding="utf-8"))
    if (
        private.get("kty") != "RSA" or private.get("alg") != ALG or private.get("kid") != KID
        or not private.get("d") or private.get("n") != public.get("n")
        or private.get("e") != public.get("e")
    ):
        raise SystemExit("RELEASE_SIGNING_KEY_MISMATCH")
    data = MANIFEST.read_bytes()
    payload = {
        "alg": ALG,
        "kid": KID,
        "manifest_sha256": hashlib.sha256(data).hexdigest(),
        "schema": SCHEMA,
        "signature": sign_pkcs1_v15_sha256(data, private),
    }
    SIGNATURE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("COMMANDER_RELEASE_SIGNATURE_WRITTEN=" + str(SIGNATURE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
