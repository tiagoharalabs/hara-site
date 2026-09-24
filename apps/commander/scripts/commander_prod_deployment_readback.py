#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
REPO = APP.parents[1]
CONFIG = APP / "wrangler.jsonc"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrangler-version", default="4.137.0")
    parser.add_argument("--expect-version", default="")
    args = parser.parse_args()

    command = [
        "npx", "--yes", f"wrangler@{args.wrangler_version}",
        "deployments", "list", "--json", "--config", str(CONFIG),
    ]
    proc = subprocess.run(command, cwd=REPO, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "DEPLOYMENT_READBACK_FAILED")

    deployments = json.loads(proc.stdout)
    if not isinstance(deployments, list) or not deployments:
        raise RuntimeError("DEPLOYMENT_READBACK_EMPTY")

    latest = deployments[-1]
    versions = latest.get("versions") or []
    if len(versions) != 1 or float(versions[0].get("percentage", 0)) != 100.0:
        raise RuntimeError("DEPLOYMENT_NOT_SINGLE_VERSION_100_PERCENT")

    current_version = str(versions[0].get("version_id") or "")
    if not current_version:
        raise RuntimeError("DEPLOYMENT_VERSION_MISSING")

    expected = args.expect_version.strip()
    if expected and current_version != expected:
        raise RuntimeError(
            f"DEPLOYMENT_VERSION_EXPECTED_{expected}_GOT_{current_version}"
        )

    rollback_version = None
    if len(deployments) >= 2:
        prior_versions = deployments[-2].get("versions") or []
        if len(prior_versions) == 1 and float(prior_versions[0].get("percentage", 0)) == 100.0:
            rollback_version = str(prior_versions[0].get("version_id") or "") or None

    report = {
        "state": "PASS",
        "current_version": current_version,
        "rollback_version": rollback_version,
        "created_on": latest.get("created_on"),
        "deployment_id": latest.get("id"),
        "source": latest.get("source"),
        "strategy": latest.get("strategy"),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    print("COMMANDER_PROD_WORKER_DEPLOYMENT=PROVEN")
    print(f"COMMANDER_PROD_WORKER_VERSION={current_version}")
    if rollback_version:
        print(f"COMMANDER_PROD_WORKER_ROLLBACK_VERSION={rollback_version}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMMANDER_PROD_WORKER_DEPLOYMENT=FAIL:{exc}")
        raise
