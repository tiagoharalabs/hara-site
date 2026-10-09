#!/usr/bin/env python3
"""Read-only live OAuth/DCR readiness gate for the customer Cloud MCP.

Does not retrieve, issue, register, revoke, or log credentials. The DCR POST
probe is intentionally invalid, so the gateway must reject it. This probe
does not substitute for real ChatGPT OAuth consent or client-registration E2E.
"""
from __future__ import annotations

import argparse
import json
import ssl
import urllib.error
import urllib.request

ISSUER = "https://auth.haralabs.com.br"
MCP = "https://commander.haralabs.com.br/api/mcp"
RESOURCE = MCP
REGISTRATION = ISSUER + "/oauth/v2/register"
UA = "HARA-Commander-Cloud-OAuth-Readiness/1"


def request(url: str, method: str = "GET", payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        method=method,
        data=body,
        headers={
            "accept": "application/json",
            "content-type": "application/json",
            "user-agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=15) as response:
            data = response.read(16384)
            return response.status, json.loads(data) if data.strip().startswith(b"{") else {}
    except urllib.error.HTTPError as exc:
        data = exc.read(4096)
        try:
            parsed = json.loads(data) if data.strip().startswith(b"{") else {}
        except ValueError:
            parsed = {}
        return exc.code, parsed


def need(condition, code):
    if not condition:
        raise AssertionError(code)
    print("HARA_CLOUD_OAUTH_" + code + "=PASS")


def main():
    parser = argparse.ArgumentParser(description="Probe live HARA Identity registration and commercial MCP readiness, without credentials")
    parser.add_argument("--expect", choices=("closed", "guarded"), default="closed")
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()

    o_status, oidc = request(ISSUER + "/.well-known/openid-configuration")
    r_status, rfc = request(ISSUER + "/.well-known/oauth-authorization-server")
    p_status, protected = request("https://commander.haralabs.com.br/.well-known/oauth-protected-resource/api/mcp")
    m_status, challenge = request(MCP + "?profile=simple")

    need(o_status == r_status == p_status == 200, "ALL_METADATA_HTTP")
    need(oidc.get("issuer") == rfc.get("issuer") == ISSUER, "ISSUER")
    need(oidc.get("authorization_endpoint") == rfc.get("authorization_endpoint"), "AUTHORIZATION_ENDPOINT")
    need(oidc.get("token_endpoint") == rfc.get("token_endpoint"), "TOKEN_ENDPOINT")
    need("S256" in oidc.get("code_challenge_methods_supported", [])
         and "S256" in rfc.get("code_challenge_methods_supported", []), "PKCE_S256")
    need(protected.get("resource") == RESOURCE and ISSUER in protected.get("authorization_servers", []), "PROTECTED_RESOURCE_BOUND")
    need(m_status == 401, "UNAUTHENTICATED_MCP_DENIED")

    advertised = rfc.get("registration_endpoint") == REGISTRATION
    # Public OIDC may advertise ZITADEL's registration endpoint even when the
    # guarded public DCR gateway is intentionally closed. RFC8414 is authoritative.
    print("HARA_CLOUD_OAUTH_OIDC_REGISTRATION_ADVERTISED=" +
          str(oidc.get("registration_endpoint") == REGISTRATION).upper())
    print("HARA_CLOUD_OAUTH_RFC8414_DCR_ADVERTISED=" + str(advertised).upper())

    registration_status, registration_result = request(
        REGISTRATION, method="POST", payload={
            "client_name": "HARA invalid DCR policy probe",
            "application_type": "web",
            "redirect_uris": ["http://example.invalid/callback"],
            "response_types": ["code"],
            "grant_types": ["authorization_code", "refresh_token"],
            "token_endpoint_auth_method": "none",
        },
    )
    print("HARA_CLOUD_OAUTH_INVALID_REGISTRATION_HTTP=" + str(registration_status))
    if args.expect == "closed":
        need(not advertised, "DCR_METADATA_CLOSED")
        need(registration_status == 404, "DCR_GATEWAY_CLOSED")
        print("HARA_CLOUD_OAUTH_CHATGPT_DCR_REGISTRATION=BLOCKED_BY_CURRENT_CONFIGURATION")
        if args.require_ready:
            print("HARA_CLOUD_OAUTH_READINESS=FAIL_DCR_GATEWAY_CLOSED")
            return 2
        print("HARA_CLOUD_OAUTH_READINESS=CLOSED_GATE_CONFIRMED")
    else:
        need(advertised, "DCR_METADATA_GUARDED")
        need(registration_status == 400 and
             registration_result.get("error") == "invalid_client_metadata",
             "DCR_INVALID_REDIRECT_DENIED")
        print("HARA_CLOUD_OAUTH_CHATGPT_DCR_REGISTRATION=REQUIRES_REAL_CLIENT_E2E")
        print("HARA_CLOUD_OAUTH_READINESS=GUARDED_PRECHECK_PASS")
    print("HARA_CLOUD_OAUTH_CHATGPT_TOKEN_EXCHANGE=NOT_TESTED")
    print("HARA_CLOUD_OAUTH_CHATGPT_PLUGIN_INSTALLED=NOT_VERIFIED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, ValueError, urllib.error.URLError) as exc:
        print("HARA_CLOUD_OAUTH_READINESS=FAIL:" + type(exc).__name__ +
              ("_" + str(exc) if isinstance(exc, AssertionError) else ""))
        raise SystemExit(3)
