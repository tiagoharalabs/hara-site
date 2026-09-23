#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import urllib.error
import urllib.request

UPDATE_FIELDS = (
    "allowUsernamePassword",
    "allowRegister",
    "allowExternalIdp",
    "forceMfa",
    "passwordlessType",
    "hidePasswordReset",
    "ignoreUnknownUsernames",
    "defaultRedirectUri",
    "passwordCheckLifetime",
    "externalLoginCheckLifetime",
    "mfaInitSkipLifetime",
    "secondFactorCheckLifetime",
    "multiFactorCheckLifetime",
    "allowDomainDiscovery",
    "disableLoginWithEmail",
    "disableLoginWithPhone",
    "forceMfaLocalOnly",
)


def request(base: str, token: str, method: str, path: str, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        base.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "HARA-Identity-Default-Redirect-Align/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode()
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise SystemExit(f"{method} {path} -> HTTP {exc.code}: {detail[:600]}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://auth.haralabs.com.br")
    parser.add_argument("--pat-file", required=True)
    parser.add_argument("--default-redirect-uri", default="https://commander.haralabs.com.br/")
    args = parser.parse_args()

    token = pathlib.Path(args.pat_file).read_text().strip()
    if not token:
        raise SystemExit("EMPTY_PAT")

    status, current = request(args.base_url, token, "GET", "/admin/v1/policies/login")
    if status != 200 or not isinstance(current.get("policy"), dict):
        raise SystemExit("LOGIN_POLICY_READ_FAILED")
    policy = current["policy"]
    before = str(policy.get("defaultRedirectUri") or "")

    update = {key: policy[key] for key in UPDATE_FIELDS if key in policy}
    update["defaultRedirectUri"] = args.default_redirect_uri
    status, _ = request(args.base_url, token, "PUT", "/admin/v1/policies/login", update)
    if status != 200:
        raise SystemExit("LOGIN_POLICY_UPDATE_FAILED")

    status, verify = request(args.base_url, token, "GET", "/admin/v1/policies/login")
    if status != 200 or not isinstance(verify.get("policy"), dict):
        raise SystemExit("LOGIN_POLICY_READBACK_FAILED")
    after = str(verify["policy"].get("defaultRedirectUri") or "")
    if after != args.default_redirect_uri:
        raise SystemExit("LOGIN_DEFAULT_REDIRECT_READBACK_MISMATCH")

    # Do not print the PAT or the complete policy. Only safe mutation evidence.
    print("HARA_IDENTITY_LOGIN_POLICY_READ=PASS")
    print("HARA_IDENTITY_DEFAULT_REDIRECT_PREVIOUS=" + before)
    print("HARA_IDENTITY_DEFAULT_REDIRECT_CURRENT=" + after)
    print("HARA_IDENTITY_DEFAULT_REDIRECT_ALIGN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
