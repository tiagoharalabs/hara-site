#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import pathlib
import re
import subprocess
import sys
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
GENERATED = APP / ".generated"
AUTH_FILE = GENERATED / "auth0-dev.json"
SECRET_FILE = GENERATED / "auth0-client-secret"

WORKER_URL = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"


def normalize_issuer(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("issuer must be an HTTPS origin/path without query or fragment")
    return value if value.endswith("/") else value + "/"


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Auth0 DEV metadata without committing secrets.")
    parser.add_argument("--issuer", required=True, help="Auth0 issuer, e.g. https://tenant.region.auth0.com/")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--provider-label", default="Auth0")
    parser.add_argument("--no-secret", action="store_true", help="Configure a public client without a client secret.")
    args = parser.parse_args()

    issuer = normalize_issuer(args.issuer)
    client_id = args.client_id.strip()
    if not client_id or len(client_id) > 256 or not re.fullmatch(r"[A-Za-z0-9._~-]+", client_id):
        raise SystemExit("invalid client id")

    GENERATED.mkdir(parents=True, exist_ok=True)
    payload = {
        "issuer": issuer,
        "client_id": client_id,
        "provider_label": args.provider_label,
        "callback_url": WORKER_URL + "/auth/callback",
        "web_origin": WORKER_URL,
    }
    AUTH_FILE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    AUTH_FILE.chmod(0o600)

    if args.no_secret:
        if SECRET_FILE.exists():
            SECRET_FILE.unlink()
    else:
        secret = getpass.getpass("Auth0 client secret (input hidden): ").strip()
        if len(secret) < 16:
            raise SystemExit("client secret is unexpectedly short")
        SECRET_FILE.write_text(secret, encoding="utf-8")
        SECRET_FILE.chmod(0o600)

    print("AUTH0_DEV_METADATA=PASS")
    print("AUTH0_DEV_SECRET_STORED_LOCAL=" + ("FALSE" if args.no_secret else "TRUE"))
    print("AUTH0_DEV_CALLBACK=" + payload["callback_url"])
    print("AUTH0_DEV_CONFIG_GIT_TRACKED=FALSE")
    print("NEXT=python3 apps/commander/scripts/bootstrap_remote_dev.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
