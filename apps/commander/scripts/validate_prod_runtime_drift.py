#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "apps/commander/public"
ORIGIN = "https://commander.haralabs.com.br"

ASSETS = {
    "/": PUBLIC / "index.html",
    "/app.js": PUBLIC / "app.js",
    "/styles.css": PUBLIC / "styles.css",
}

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def fetch(path: str) -> tuple[bytes, int, str]:
    req = Request(ORIGIN + path, headers={"User-Agent": "HARA-Commander-Readback/1"})
    with urlopen(req, timeout=15) as response:
        return response.read(), response.status, response.headers.get("content-type", "")

def fetch_json(path: str) -> dict:
    body, status, content_type = fetch(path)
    if status != 200 or "application/json" not in content_type:
        raise RuntimeError(f"RUNTIME_JSON_INVALID:{path}:{status}:{content_type}")
    return json.loads(body)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--expect-assets",
        choices=("stale", "current", "any"),
        default="any",
    )
    args = parser.parse_args()

    rows = []
    for path, source_path in ASSETS.items():
        live, status, content_type = fetch(path)
        source = source_path.read_bytes()
        if status != 200:
            raise RuntimeError(f"RUNTIME_ASSET_HTTP:{path}:{status}")
        rows.append({
            "path": path,
            "content_type": content_type,
            "source_sha256": sha256(source),
            "live_sha256": sha256(live),
            "current": source == live,
        })

    current_count = sum(1 for row in rows if row["current"])
    if current_count == len(rows):
        asset_state = "CURRENT"
    elif current_count == 0:
        asset_state = "STALE"
    else:
        asset_state = "MIXED"

    expected = args.expect_assets.upper()
    if expected == "CURRENT" and asset_state != "CURRENT":
        raise RuntimeError(f"RUNTIME_ASSETS_EXPECTED_CURRENT_GOT_{asset_state}")
    if expected == "STALE" and asset_state != "STALE":
        raise RuntimeError(f"RUNTIME_ASSETS_EXPECTED_STALE_GOT_{asset_state}")

    health = fetch_json("/api/health")
    auth = fetch_json("/api/portal/auth-config")
    if health.get("ok") is not True or health.get("environment") != "PROD":
        raise RuntimeError("RUNTIME_HEALTH_INVALID")
    if auth.get("configured") is not True:
        raise RuntimeError("RUNTIME_AUTH_NOT_CONFIGURED")

    report = {
        "origin": ORIGIN,
        "asset_state": asset_state,
        "assets": rows,
        "health": health,
        "auth": auth,
    }

    print(json.dumps(report, indent=2, sort_keys=True))
    print("COMMANDER_PROD_RUNTIME_HEALTH=PASS")
    print("COMMANDER_PROD_RUNTIME_AUTH=PASS")
    print(f"COMMANDER_PROD_RUNTIME_ASSETS={asset_state}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMMANDER_PROD_RUNTIME_DRIFT=FAIL:{exc}")
        raise
