#!/usr/bin/env python3
"""Read-only asset proof for an authorized 0% Cloudflare Worker version.

The 0% deployment is a separate, approval-gated production mutation. This
script only reads its deployment state and public assets with a version
override. It does not prove Worker code bytes or create a deployment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request

from stage_signed_commercial_assets import require_signed_stage
from validate_prod_runtime_drift import asset_sources, normalize_asset

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps/commander"
CONFIG = APP / "wrangler.jsonc"
WRANGLER = ROOT / "node_modules/.bin/wrangler"
ORIGIN = "https://commander.haralabs.com.br"
UUID_RE = re.compile(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", re.I)
EXPECTED_HTTP_PATHS = {
    "/", "/app.js", "/styles.css", "/assets/hara-commander-royal.webp",
    "/brand/chatgpt-official.webp", "/brand/claude-official.svg",
    "/release/v2/release-signing-public.jwk",
    "/agent/linux.py", "/agent/windows.ps1", "/install/linux.sh",
    "/install/windows.ps1", "/release/agent-manifest.json",
    "/release/agent-manifest.sig.json", "/release/release-signing-public.jwk",
    "/release/SHA256SUMS",
}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args):
        return None


def fetch_deployments() -> list[dict]:
    proc = subprocess.run(
        [str(WRANGLER), "deployments", "list", "--json", "--config", str(CONFIG)],
        cwd=APP, capture_output=True, text=True, timeout=60, check=False,
    )
    if proc.returncode:
        raise RuntimeError("VERSION_DEPLOYMENT_READBACK_FAILED")
    try:
        deployments = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("VERSION_DEPLOYMENT_READBACK_INVALID") from exc
    if not isinstance(deployments, list) or not deployments:
        raise RuntimeError("VERSION_DEPLOYMENT_READBACK_EMPTY")
    return deployments


def require_zero_percent_deployment(deployments: list[dict], version: str,
                                    rollback: str) -> None:
    try:
        rows = deployments[-1]["versions"]
        shares = {str(row["version_id"]): float(row["percentage"]) for row in rows}
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise RuntimeError("VERSION_DEPLOYMENT_INVALID") from exc
    if len(rows) != 2 or len(shares) != 2 or shares != {version: 0.0, rollback: 100.0}:
        raise RuntimeError("VERSION_DEPLOYMENT_NOT_ZERO_PERCENT")


def fetch_asset(path: str, version: str | None) -> bytes:
    worker_name = json.loads(CONFIG.read_text())["name"]
    headers = {
        "Accept": "application/octet-stream",
        "Cache-Control": "no-cache",
        "User-Agent": "HARA-Commander-Version-Asset-Readback/1",
    }
    if version is not None:
        headers["Cloudflare-Workers-Version-Overrides"] = f'{worker_name}="{version}"'
    request = urllib.request.Request(ORIGIN + path, headers=headers, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=20) as response:
            if response.status != 200:
                raise RuntimeError("VERSION_ASSET_HTTP_INVALID:" + path)
            body = response.read(5 * 1024 * 1024 + 1)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError("VERSION_ASSET_READ_FAILED:" + path) from exc
    if len(body) > 5 * 1024 * 1024:
        raise RuntimeError("VERSION_ASSET_TOO_LARGE:" + path)
    return body


def readback_version_assets(stage: Path, tree_sha256: str, version: str,
                            rollback: str, *, expected_bundle: Path | None = None) -> dict:
    if not UUID_RE.fullmatch(version) or not UUID_RE.fullmatch(rollback) or version == rollback:
        raise RuntimeError("VERSION_ID_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", tree_sha256):
        raise RuntimeError("VERSION_STAGE_DIGEST_INVALID")
    report = require_signed_stage(
        stage, expected_bundle=expected_bundle, expected_tree_sha256=tree_sha256,
    )
    sources = asset_sources(stage, expected_bundle=expected_bundle)
    if set(sources) != EXPECTED_HTTP_PATHS:
        raise RuntimeError("VERSION_ASSET_FILESET_INVALID")
    require_zero_percent_deployment(fetch_deployments(), version, rollback)

    baseline_different = []
    hashes = {}
    for path, source in sources.items():
        expected = source.read_bytes()
        baseline, _ = normalize_asset(path, fetch_asset(path, None))
        observed, _ = normalize_asset(path, fetch_asset(path, version))
        if baseline != expected:
            baseline_different.append(path)
        if observed != expected:
            raise RuntimeError("VERSION_ASSET_MISMATCH:" + path)
        hashes[path] = hashlib.sha256(observed).hexdigest()
    # Cloudflare may silently ignore an invalid override. A differing current
    # deployment is the control that proves the alternate route was selected.
    if not baseline_different:
        raise RuntimeError("VERSION_OVERRIDE_NOT_PROVEN")
    require_zero_percent_deployment(fetch_deployments(), version, rollback)
    require_signed_stage(
        stage, expected_bundle=expected_bundle, expected_tree_sha256=tree_sha256,
    )
    return {
        "state": "VERSION_ASSETS_VERIFIED_0_PERCENT",
        "version_id": version,
        "rollback_version_id": rollback,
        "stage_tree_sha256": report["stage_tree_sha256"],
        "source_public_tree": report["source_public_tree"],
        "signed_manifest_sha256": report["manifest_sha256"],
        "asset_count": len(hashes),
        "asset_sha256": hashes,
        "root_html_cloudflare_beacon_normalization_allowed": True,
        "baseline_different_paths": baseline_different,
        "version_asset_content_verified": True,
        "worker_code_verified": False,
        "cloud_mutation": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--stage-tree-sha256", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--rollback", required=True)
    args = parser.parse_args()
    report = readback_version_assets(
        args.stage, args.stage_tree_sha256, args.version, args.rollback,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
