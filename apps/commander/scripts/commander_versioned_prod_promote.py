#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WRANGLER = ROOT / "node_modules" / ".bin" / "wrangler"
CONFIG = APP / "wrangler.jsonc"
READBACK = APP / "scripts" / "commander_prod_deployment_readback.py"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
REQUIRED_VERSION_SECRETS = {
    "AUTH_CLIENT_SECRET",
    "MCP_PRODUCT_TOKEN",
    "PRODUCT_LEASE_PRIVATE_JWK",
}


def run(argv: list[str], timeout: int = 120) -> str:
    proc = subprocess.run(
        argv,
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError("COMMAND_FAILED:" + " ".join(argv) + "\n" + proc.stdout[-2000:])
    return proc.stdout


def require_version_secrets(version: str) -> set[str]:
    out = run([str(WRANGLER), "versions", "view", version, "--config", str(CONFIG)])
    found = set(re.findall(r"Secret Name:\s+([A-Z0-9_]+)", out))
    missing = REQUIRED_VERSION_SECRETS - found
    if missing:
        raise RuntimeError("TARGET_VERSION_SECRET_MISSING:" + ",".join(sorted(missing)))
    return found


def require_current_rollback(version: str) -> None:
    out = run([str(WRANGLER), "deployments", "list", "--config", str(CONFIG)])
    if f"(100%) {version}" not in out:
        raise RuntimeError("ROLLBACK_VERSION_NOT_CURRENT_100_PERCENT")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--rollback", required=True)
    parser.add_argument("--message", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    if not UUID_RE.fullmatch(args.version) or not UUID_RE.fullmatch(args.rollback):
        raise SystemExit("VERSION_ID_INVALID")
    if args.version == args.rollback:
        raise SystemExit("VERSION_AND_ROLLBACK_MUST_DIFFER")

    require_current_rollback(args.rollback)
    found = require_version_secrets(args.version)

    print("COMMANDER_VERSIONED_PROMOTE_PREFLIGHT=PASS")
    print("COMMANDER_VERSIONED_PROMOTE_TARGET=" + args.version)
    print("COMMANDER_VERSIONED_PROMOTE_ROLLBACK=" + args.rollback)
    print("COMMANDER_VERSIONED_PROMOTE_REQUIRED_SECRETS=PASS")
    print("COMMANDER_VERSIONED_PROMOTE_TRIGGER_SYNC=REQUIRED")

    if not args.execute:
        print("COMMANDER_VERSIONED_PROMOTE_EXECUTE=NO")
        return 0

    run([
        str(WRANGLER), "versions", "deploy",
        args.version + "@100%",
        "--config", str(CONFIG),
        "--message", args.message,
        "--yes",
    ])
    # Version deployment does not guarantee cron/routes are synchronized.
    run([str(WRANGLER), "triggers", "deploy", "--config", str(CONFIG)])
    run([
        "python3", str(READBACK),
        "--expect-version", args.version,
    ])

    print("COMMANDER_VERSIONED_PROMOTE_WORKER=PASS")
    print("COMMANDER_VERSIONED_PROMOTE_TRIGGERS=PASS")
    print("COMMANDER_VERSIONED_PROMOTE_READBACK=PASS")
    print("COMMANDER_VERSIONED_PROMOTE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
