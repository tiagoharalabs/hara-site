#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "apps/commander/public"
ORIGIN = "https://commander.haralabs.com.br"

ASSETS = {
    "/": PUBLIC / "index.html",
    "/app.js": PUBLIC / "app.js",
    "/styles.css": PUBLIC / "styles.css",
    "/install/linux.sh": PUBLIC / "install/linux.sh",
    "/install/windows.ps1": PUBLIC / "install/windows.ps1",
    "/agent/linux.py": PUBLIC / "agent/linux.py",
    "/agent/windows.ps1": PUBLIC / "agent/windows.ps1",
    "/release/agent-manifest.json": PUBLIC / "release/agent-manifest.json",
    "/release/SHA256SUMS": PUBLIC / "release/SHA256SUMS",
    "/assets/hara-commander-royal.webp": PUBLIC / "assets/hara-commander-royal.webp",
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

CF_BEACON_RE = re.compile(
    rb'\n<script type="module" src="https://static\.cloudflareinsights\.com/'
    rb'beacon\.min\.js/[^"]+" integrity="[^"]+" data-cf-beacon=\'[^\']+\''
    rb' crossorigin="anonymous"></script>'
)

def normalize_asset(path: str, body: bytes) -> tuple[bytes, bool]:
    if path != "/":
        return body, False
    normalized, count = CF_BEACON_RE.subn(b"", body)
    if count > 1:
        raise RuntimeError("RUNTIME_HTML_MULTIPLE_CF_BEACONS")
    return normalized, count == 1

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
        normalized_live, cf_beacon_removed = normalize_asset(path, live)
        rows.append({
            "path": path,
            "content_type": content_type,
            "source_sha256": sha256(source),
            "live_sha256": sha256(live),
            "normalized_live_sha256": sha256(normalized_live),
            "cloudflare_beacon_removed": cf_beacon_removed,
            "current": source == normalized_live,
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
