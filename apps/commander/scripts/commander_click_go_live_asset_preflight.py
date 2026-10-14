#!/usr/bin/env python3
"""Fail-closed preflight for UI-only Commander release against live signed assets.

This never deploys, fetches credentials, or changes PROD.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

PRODUCT = "https://commander.haralabs.com.br"
SIGNED = (
    "agent/linux.py",
    "agent/windows.ps1",
    "install/linux.sh",
    "install/windows.ps1",
    "release/agent-manifest.json",
    "release/agent-manifest.sig.json",
    "release/release-signing-public.jwk",
    "release/SHA256SUMS",
)

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--base-url", default=PRODUCT)
    args = parser.parse_args()
    stage = args.stage.resolve()
    results = {}
    failures = []
    for relative in ("app.js", *SIGNED):
        candidate = (stage / relative).resolve()
        if not candidate.is_relative_to(stage) or not candidate.is_file():
            failures.append("MISSING_STAGE_" + relative)
            continue
        try:
            request = urllib.request.Request(args.base_url.rstrip("/") + "/" + relative,
                                             headers={"User-Agent": "HARA-Commander-ClickGo-Asset-Preflight/1"})
            with urllib.request.urlopen(request, timeout=12) as response:
                if response.status != 200:
                    raise ValueError(f"HTTP_{response.status}")
                raw = response.read(10_000_000)
        except Exception as exc:
            failures.append("LIVE_READ_FAILED_" + relative + "_" + type(exc).__name__)
            continue
        candidate_hash = sha(candidate.read_bytes())
        live_hash = sha(raw)
        result = "EXACT" if live_hash == candidate_hash else "DIFF"
        results[relative] = {"state": result, "stage_sha256": candidate_hash, "live_sha256": live_hash}
        if result != "EXACT":
            failures.append("SENSITIVE_ASSET_DRIFT_" + relative)
    html = (stage / "index.html").read_text("utf8")
    css = (stage / "styles.css").read_text("utf8")
    if "styles.css?v=20261013-click-go-centered-v2" not in html:
        failures.append("CSS_CACHE_BUST_MISSING")
    if "Click & Go" not in css:
        failures.append("CENTERED_UI_STYLES_MISSING")
    out = {
        "schema": "hara.commander.clickgo.live-preflight.v1",
        "state": "PASS" if not failures else "BLOCKED",
        "production_mutation": False,
        "release_authority": "HARA_SERVICES",
        "signed_and_code_asset_readback": results,
        "failures": failures,
        "version_promotion_authorized": False,
    }
    print(json.dumps(out, sort_keys=True, indent=2))
    return 0 if not failures else 2

if __name__ == "__main__":
    raise SystemExit(main())
