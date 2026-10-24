#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import ssl
import urllib.error
import urllib.request

ISSUER = "https://auth.haralabs.com.br"
GET_SECURITY = ISSUER + "/v2/settings/security"
SET_SECURITY = ISSUER + "/v2/policies/security"
REGISTER = ISSUER + "/oauth/v2/register"
USER_AGENT = "HARA-Identity-DCR-Provisioner/1"


def request_json(url: str, *, method: str = "GET", token: str | None = None, payload=None):
    headers = {"accept": "application/json", "user-agent": USER_AGENT}
    body = None
    if token:
        headers["authorization"] = "Bearer " + token
    if payload is not None:
        headers["content-type"] = "application/json"
        body = json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as resp:
        raw = resp.read()
        return resp.status, json.loads(raw) if raw else {}


def settings_payload(settings: dict, *, enabled: bool, allow_unauthenticated: bool) -> dict:
    payload = {}
    if isinstance(settings.get("embeddedIframe"), dict):
        payload["embeddedIframe"] = settings["embeddedIframe"]
    if isinstance(settings.get("enableImpersonation"), bool):
        payload["enableImpersonation"] = settings["enableImpersonation"]
    payload["dynamicClientRegistration"] = {
        "enabled": bool(enabled),
        "allowUnauthenticated": bool(allow_unauthenticated),
    }
    return payload


def registration_payload() -> dict:
    return {
        "client_name": "H.A.R.A. Commander MCP Introspection",
        "application_type": "web",
        "redirect_uris": [
            "https://commander.haralabs.com.br/auth/introspection-callback",
        ],
        "response_types": ["code"],
        "grant_types": ["authorization_code"],
        "token_endpoint_auth_method": "client_secret_basic",
    }


def sanitize_registration(payload: dict) -> dict:
    return {
        "client_id": payload.get("client_id"),
        "token_endpoint_auth_method": payload.get("token_endpoint_auth_method"),
        "registration_client_uri": payload.get("registration_client_uri"),
        "client_secret_present": bool(payload.get("client_secret")),
        "registration_access_token_present": bool(payload.get("registration_access_token")),
    }


def self_test() -> int:
    pre = {
        "embeddedIframe": {"enabled": False, "allowedOrigins": []},
        "enableImpersonation": False,
        "dynamicClientRegistration": {"enabled": False, "allowUnauthenticated": False},
    }
    opened = settings_payload(pre, enabled=True, allow_unauthenticated=True)
    restored = settings_payload(
        pre,
        enabled=pre["dynamicClientRegistration"]["enabled"],
        allow_unauthenticated=pre["dynamicClientRegistration"]["allowUnauthenticated"],
    )
    assert opened["dynamicClientRegistration"] == {"enabled": True, "allowUnauthenticated": True}
    assert restored["dynamicClientRegistration"] == pre["dynamicClientRegistration"]
    reg = registration_payload()
    assert reg["token_endpoint_auth_method"] == "client_secret_basic"
    assert reg["application_type"] == "web"
    assert USER_AGENT == "HARA-Identity-DCR-Provisioner/1"
    assert "client_secret" not in sanitize_registration({"client_secret": "secret"})
    print("HARA_IDENTITY_INTROSPECTION_PROVISIONER_SELFTEST=PASS")
    print("DCR_EXACT_PREIMAGE_RESTORE=BOUND")
    print("CLIENT_SECRET_OUTPUT=FILE_ONLY")
    print("ADMIN_EDGE_USER_AGENT=BOUND")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pat-file", type=pathlib.Path)
    ap.add_argument("--secret-output", type=pathlib.Path)
    ap.add_argument("--sanitized-output", type=pathlib.Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.pat_file or not args.secret_output or not args.sanitized_output:
        ap.error("--pat-file, --secret-output and --sanitized-output are required")

    pat = args.pat_file.read_text(encoding="utf-8").strip()
    if not pat:
        raise SystemExit("PAT_EMPTY")

    _, current = request_json(GET_SECURITY, token=pat)
    settings = current.get("settings")
    if not isinstance(settings, dict):
        raise SystemExit("SECURITY_PREIMAGE_INVALID")
    pre_dcr = settings.get("dynamicClientRegistration") or {}
    pre_enabled = bool(pre_dcr.get("enabled"))
    pre_open = bool(pre_dcr.get("allowUnauthenticated"))

    secret_payload = None
    try:
        open_payload = settings_payload(settings, enabled=True, allow_unauthenticated=True)
        status, _ = request_json(SET_SECURITY, method="PUT", token=pat, payload=open_payload)
        if status != 200:
            raise RuntimeError("DCR_OPEN_FAILED")

        status, secret_payload = request_json(
            REGISTER,
            method="POST",
            payload=registration_payload(),
        )
        if status != 201:
            raise RuntimeError("DCR_REGISTER_FAILED")
        if not secret_payload.get("client_id") or not secret_payload.get("client_secret"):
            raise RuntimeError("DCR_CONFIDENTIAL_CLIENT_INCOMPLETE")

        args.secret_output.parent.mkdir(parents=True, exist_ok=True)
        args.secret_output.write_text(
            json.dumps(secret_payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(args.secret_output, 0o600)
        args.sanitized_output.parent.mkdir(parents=True, exist_ok=True)
        args.sanitized_output.write_text(
            json.dumps(sanitize_registration(secret_payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(args.sanitized_output, 0o600)
    finally:
        restore_payload = settings_payload(
            settings,
            enabled=pre_enabled,
            allow_unauthenticated=pre_open,
        )
        request_json(SET_SECURITY, method="PUT", token=pat, payload=restore_payload)

    print("DCR_PRE_ENABLED=" + str(pre_enabled).lower())
    print("DCR_PRE_ALLOW_UNAUTHENTICATED=" + str(pre_open).lower())
    print("DCR_CONFIDENTIAL_REGISTER_HTTP=201")
    print("DCR_CLIENT_SECRET_PRESENT=true")
    print("DCR_REGISTRATION_ACCESS_TOKEN_PRESENT=" + str(bool(secret_payload.get("registration_access_token"))).lower())
    print("DCR_PREIMAGE_RESTORED=true")
    print("SECRET_MATERIAL_STDOUT=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
