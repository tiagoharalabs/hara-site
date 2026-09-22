#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import urllib.error
import urllib.request

BASE = "https://auth.haralabs.com.br"
PAT_FILE = Path.home() / "Documents/.hara-identity/identity-owner.pat"
CREDS_FILE = Path.home() / "Documents/.hara-identity/openai-reviewer.credentials"

def read_kv(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        data[key.strip()] = value
    return data

def main() -> int:
    token = PAT_FILE.read_text(encoding="utf-8").strip()
    creds = read_kv(CREDS_FILE)
    username = creds.get("username", "").strip()
    password = creds.get("password", "")
    if not token or not username or not password:
        raise SystemExit("REVIEWER_IDENTITY_INPUT_MISSING")

    payload = {
        "username": username,
        "profile": {
            "givenName": "OpenAI",
            "familyName": "Reviewer",
            "displayName": "OpenAI Reviewer",
            "preferredLanguage": "en",
        },
        "email": {
            "email": username,
            "isVerified": True,
        },
        "password": {
            "password": password,
            "changeRequired": False,
        },
    }
    req = urllib.request.Request(
        BASE + "/v2/users/human",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "HARA-Identity-Reviewer-Provisioner/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
            if resp.status != 200:
                print(f"REVIEWER_IDENTITY_CREATE=FAIL_HTTP_{resp.status}")
                return 2
            user_id = str(body.get("userId") or body.get("user_id") or "").strip()
            if not user_id:
                print("REVIEWER_IDENTITY_CREATE=FAIL_USER_ID")
                return 3
            print("REVIEWER_IDENTITY_CREATE=PASS")
            print("REVIEWER_IDENTITY_USER_ID=" + user_id)
            print("REVIEWER_IDENTITY_EMAIL_VERIFIED=TRUE")
            print("REVIEWER_IDENTITY_CHANGE_REQUIRED=FALSE")
            print("REVIEWER_IDENTITY_CREDENTIAL_EXPOSED=FALSE")
            return 0
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(f"REVIEWER_IDENTITY_CREATE=FAIL_HTTP_{exc.code}")
        print(detail[:500])
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
