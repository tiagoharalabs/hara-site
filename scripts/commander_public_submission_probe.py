#!/usr/bin/env python3
"""Read-only public-submission preflight for H.A.R.A. Commander.

Only HTTPS GET requests to fixed, explicitly allowlisted HARA-owned URLs.
No credentials/cookies are sent or read; no Stripe/customer endpoints are mutated.
This is *not* the official OpenAI Scan Tools or an OAuth user E2E.
"""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

URLS = {
    "product_mcp": "https://commander.haralabs.com.br/api/mcp",
    "oauth_resource": "https://commander.haralabs.com.br/.well-known/oauth-protected-resource",
    "identity_discovery": "https://auth.haralabs.com.br/.well-known/openid-configuration",
    "website": "https://www.haralabs.com.br/",
    "support": "https://www.haralabs.com.br/support/",
    "privacy": "https://www.haralabs.com.br/legal/privacidade/",
    "terms": "https://www.haralabs.com.br/legal/termos/",
}
ALLOWED_HOSTS = {
    "commander.haralabs.com.br",
    "auth.haralabs.com.br",
    "www.haralabs.com.br",
}
UA = "HARA-Commander-Publication-ReadOnly/20261013"

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(" ".join(data.split()))

def probe(name: str, url: str) -> dict:
    assert urlsplit(url).scheme == "https"
    assert urlsplit(url).hostname in ALLOWED_HOSTS
    request = Request(url, headers={"User-Agent": UA}, method="GET")
    try:
        response = urlopen(request, timeout=9, context=ssl.create_default_context())
    except HTTPError as exc:
        response = exc
    with response:
        status = int(response.status)
        actual_host = urlsplit(response.url).hostname
        assert actual_host in ALLOWED_HOSTS, "Redirected outside HARA"
        payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError("Response exceeded safe scan cap")
        info: dict = {
            "status": status,
            "type": response.headers.get("Content-Type", "").split(";")[0].lower(),
            "body_sha256": hashlib.sha256(payload).hexdigest(),
        }
        if name == "product_mcp":
            hint = response.headers.get("WWW-Authenticate", "")
            assert status == 401 and "bearer" in hint.lower(), "Unauthenticated MCP not denied with Bearer challenge"
            info["bearer_challenge"] = True
        elif name in ("oauth_resource", "identity_discovery"):
            assert status == 200
            data = json.loads(payload)
            if name == "oauth_resource":
                assert data.get("resource") == URLS["product_mcp"]
                assert "https://auth.haralabs.com.br" in data.get("authorization_servers", [])
                info["issuer_reference"] = "HARA_IDENTITY"
            else:
                assert data.get("issuer") == "https://auth.haralabs.com.br"
                assert "code" in data.get("response_types_supported", [])
                info["authorization_code"] = True
        else:
            assert status == 200 and info["type"] == "text/html"
            parser = VisibleText()
            parser.feed(payload.decode("utf-8", errors="replace"))
            visible = " ".join(parser.parts)
            assert len(visible) >= 500, "Public documentation appears empty/placeholder"
            if name == "privacy":
                assert "Commander" in visible, "Privacy disclosure does not reference product"
            if name == "terms":
                assert "Commander" in visible, "Terms do not reference product"
            info["visible_text_chars"] = len(visible)
        info["pass"] = True
        return info

def main():
    outcome: dict = {"schema":"hara.commander.publication-readonly-preflight.v1",
                     "production_mutation":False,"credential_usage":False,
                     "official_openai_scan_tools":False,"checks":{}}
    for name, url in URLS.items():
        try:
            outcome["checks"][name] = probe(name, url)
        except (AssertionError, ValueError, URLError, OSError, json.JSONDecodeError) as exc:
            outcome["checks"][name] = {
                "pass":False, "error_type":type(exc).__name__, "error":str(exc)[:180]
            }
    outcome["passed"] = sum(bool(x.get("pass")) for x in outcome["checks"].values())
    outcome["total"] = len(URLS)
    outcome["gate"] = "PUBLIC_ENDPOINTS_7_OF_7_PASS" if outcome["passed"] == 7 else "PUBLIC_ENDPOINTS_PARTIAL_FAIL"
    print(json.dumps(outcome,indent=2,sort_keys=True,ensure_ascii=False))
    return 0 if outcome["passed"] == 7 else 2

if __name__ == "__main__":
    sys.exit(main())
