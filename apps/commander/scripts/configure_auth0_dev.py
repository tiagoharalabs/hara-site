#!/usr/bin/env python3
from __future__ import annotations

import argparse
import getpass
import json
import pathlib
import re
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
GENERATED = APP / ".generated"
AUTH_FILE = GENERATED / "auth0-dev.json"
SECRET_FILE = GENERATED / "auth0-client-secret"

WORKER_URL = "https://hara-commander-dev-v2.tiago-sartori.workers.dev"
PLACEHOLDER_MARKERS = (
    "SEU-DOMINIO-AUTH0",
    "YOUR_AUTH0_DOMAIN",
    "SEU_CLIENT_ID",
    "YOUR_CLIENT_ID",
)


def reject_placeholder(value: str, label: str) -> None:
    upper = value.upper()
    if any(marker in upper for marker in PLACEHOLDER_MARKERS):
        raise SystemExit(f"{label} ainda está com placeholder de exemplo")


def normalize_issuer(value: str) -> str:
    value = value.strip()
    reject_placeholder(value, "issuer")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise SystemExit("issuer deve ser uma URL HTTPS do Auth0, sem query ou fragment")
    if "auth0.com" not in parsed.netloc and "auth0" not in parsed.netloc:
        raise SystemExit("issuer não parece ser um domínio Auth0")
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
    reject_placeholder(client_id, "client id")
    if not client_id or len(client_id) > 256 or not re.fullmatch(r"[A-Za-z0-9._~-]+", client_id):
        raise SystemExit("client id inválido")

    secret = None
    if not args.no_secret:
        secret = getpass.getpass("Auth0 client secret (input hidden): ").strip()
        reject_placeholder(secret, "client secret")
        if len(secret) < 16:
            raise SystemExit("client secret é curto demais; copie o Client Secret completo do Auth0")

    payload = {
        "issuer": issuer,
        "client_id": client_id,
        "provider_label": args.provider_label,
        "callback_url": WORKER_URL + "/auth/callback",
        "web_origin": WORKER_URL,
    }

    GENERATED.mkdir(parents=True, exist_ok=True)

    # Commit local config atomically only after every input is valid.
    auth_tmp = AUTH_FILE.with_suffix(".json.tmp")
    auth_tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    auth_tmp.chmod(0o600)

    if secret is not None:
        secret_tmp = SECRET_FILE.with_suffix(".tmp")
        secret_tmp.write_text(secret, encoding="utf-8")
        secret_tmp.chmod(0o600)
    else:
        secret_tmp = None

    auth_tmp.replace(AUTH_FILE)

    if secret_tmp is not None:
        secret_tmp.replace(SECRET_FILE)
    elif SECRET_FILE.exists():
        SECRET_FILE.unlink()

    print("AUTH0_DEV_METADATA=PASS")
    print("AUTH0_DEV_SECRET_STORED_LOCAL=" + ("FALSE" if args.no_secret else "TRUE"))
    print("AUTH0_DEV_CALLBACK=" + payload["callback_url"])
    print("AUTH0_DEV_CONFIG_GIT_TRACKED=FALSE")
    print("NEXT=python3 apps/commander/scripts/bootstrap_remote_dev.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
