#!/usr/bin/env python3
"""Fail-closed, network-free prelaunch validation of H.A.R.A. Commander.

This runs only established offline validators, mocked MCP, local SQLite stress,
and deterministic capacity/reconnect models. It never calls Wrangler, production
D1, live customer MCP, Stripe, or real client device agents. A PASS is *not*
a public-release authorization or a substitute for independent E2E/soak tests.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "apps/commander/scripts"
GATE = "HARA_COMMANDER_PRELAUNCH_OFFLINE"
TIMEOUT = 65
PYTHON = (
    "validate_canonical_functions_hardening.py",
    "validate_mcp_process_risk_annotations.py",
    "validate_process_output_memory_budgets.py",
    "validate_preimage_storage_budget.py",
    "validate_concurrent_device_queue_sql.py",
    "validate_device_installers.py",
    "validate_clean_linux_lifecycle.py",
    "validate_device_lifecycle_races.py",
    "validate_claim_revoke_race.py",
    "validate_invite_claim_race.py",
    "validate_multitenant_isolation.py",
    "validate_quota_reservation_ttl.py",
    "validate_tenant_quota_storage_efficiency.py",
    "validate_local_budget_blocks.py",
    "validate_agent_request_efficiency.py",
    "validate_event_v2_websocket_client.py",
    "validate_event_v2_wiring.py",
    "validate_event_v2_persistent_guard.py",
    "validate_event_v2_clean_shutdown.py",
    "validate_event_v2_linux_rc_install.py",
    "validate_event_v2_transient_rpc.py",
    "validate_dev_config.py",
    "validate_prod_contracts.py",
    "validate_prod_static.py",
    "validate_release_signature.py",
    "validate_billing_v1.py",
    "validate_local_activity_store.py",
    "validate_first_device_preflight.py",
    "validate_fresh_customer_acceptance.py",
)
JS = (
    "test_oidc_helpers.mjs",
    "test_auth_helpers.mjs",
    "test_hara_identity_customer_mcp.mjs",
    "test_customer_mcp_simple_profile.mjs",
    "test_customer_mcp_device_routing.mjs",
    "validate_device_tool_contract.mjs",
    "test_security_rate_limit.mjs",
    "test_customer_mcp_edge.mjs",
    "billing_sqlite_webhook_e2e.mjs",
    "billing_v1_selftest.mjs",
    "validate_event_v2_fleet_allowlist.mjs",
)
MODELS = (
    "commander_scale_capacity_model.py",
    "commander_event_v2_active_1k_model.py",
    "commander_event_v2_reconnect_storm_model.py",
    "commander_event_v2_dev_multidevice_lab.py",
    "commander_event_v2_dev_multidevice_probe.py",
    "commander_event_v2_dev_burst_probe.py",
    "commander_event_v2_dev_latency_profile.py",
)


def checked_file(filename: str) -> Path:
    path = SCRIPTS / filename
    if path.is_symlink() or not path.is_file() or path.parent.resolve() != SCRIPTS.resolve():
        raise RuntimeError("GATE_UNTRUSTED_VALIDATOR:" + filename)
    return path


def invoke(name: str, *, stress: int, threads: int) -> dict:
    script = checked_file(name)
    if name.endswith(".mjs"):
        command = ["node", str(script)]
    else:
        command = [sys.executable, "-B", str(script)]
    if name in MODELS:
        command.append("--check")
    if name == "validate_concurrent_device_queue_sql.py":
        command += ["--attempts", str(stress), "--threads", str(threads)]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    start = time.monotonic()
    try:
        output = subprocess.run(
            command, cwd=ROOT, env=env, check=False, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"test": name, "state": "TIMEOUT", "seconds": TIMEOUT}
    seconds = round(time.monotonic() - start, 3)
    return {
        "test": name,
        "state": "PASS" if output.returncode == 0 else "FAIL",
        "seconds": seconds,
        "exit_code": output.returncode,
        # Errors only expose a short bounded sanitized excerpt, never dumps.
        "error": "REGRESSION_FAILED" if output.returncode else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stress", type=int, default=1000)
    parser.add_argument("--threads", type=int, default=24)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if not 64 <= args.stress <= 1000 or not 2 <= args.threads <= 32:
        raise SystemExit("GATE_STRESS_LIMIT_DENIED")
    results = []
    for name in (*PYTHON, *JS, *MODELS):
        row = invoke(name, stress=args.stress, threads=args.threads)
        results.append(row)
        if not args.json:
            print(row["state"] + " " + name, flush=True)
    failed = [row for row in results if row["state"] != "PASS"]
    data = {
        "schema": "hara.commander-prelaunch-offline-gate.v1",
        "source_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "checked": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "stress_attempts_per_scenario": args.stress,
        "stress_threads": args.threads,
        "scope": "LOCAL_ONLY_OFFLINE_NO_CLOUDFLARE_MUTATION",
        "production_rollout_authorized": False,
        "real_multitenant_tested": False,
        "real_cloudflare_1k_clients_tested": False,
        "tests": results,
    }
    if args.json:
        print(json.dumps(data, separators=(",", ":"), sort_keys=True))
    else:
        print(GATE + "_CHECKED=" + str(data["checked"]))
        print(GATE + "_PASSED=" + str(data["passed"]))
        print(GATE + "_FAILED=" + str(data["failed"]))
        print(GATE + "_SOURCE_HEAD=" + data["source_head"])
        print(GATE + "_PROD_MUTATION=FALSE")
        print(GATE + "_PUBLIC_LAUNCH_AUTHORIZED=FALSE")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
