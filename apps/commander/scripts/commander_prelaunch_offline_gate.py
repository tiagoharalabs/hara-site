#!/usr/bin/env python3
"""Fail-closed, external-network-free prelaunch H.A.R.A. Commander gate.

Runs offline validators, mocked MCP, temporary SQLite stress, an ephemeral-key
installer simulation over localhost and deterministic capacity/reconnect models.
It never calls Wrangler, production D1, live customer MCP, Stripe, or real
client device agents. A PASS is *not*
a public-release authorization or a substitute for independent E2E/soak tests.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "apps/commander/scripts"
GATE = "HARA_COMMANDER_PRELAUNCH_OFFLINE"
TIMEOUT = 65
PYTHON = (
    "validate_signed_windows_044_v4_rc.py",
    "validate_signed_windows_045_v5_rc.py",
    "validate_signed_windows_046_v6_rc.py",
    "validate_signed_windows_047_v7_rc.py",
    "validate_signed_windows_048_v8_rc.py",
    "validate_windows_044_approval_contract.py",
    "validate_windows_045_privacy_contract.py",
    "validate_windows_local_approval_expiry.py",
    "validate_windows_047_approval_expiry.py",
    "validate_windows_048_approval_expiry.py",
    "validate_windows_048_operator_startup.py",
    "validate_event_v2_terminal_release.py",
    "validate_process_terminal_drain.py",
    "validate_process_continuous_drain.py",
    "validate_process_oneshot_pagination.py",
    "validate_process_session_policy.py",
    "validate_result_delivery_outbox.py",
    "validate_result_envelope_budget.py",
    "validate_file_cas_atomicity.py",
    "validate_relay_burst_dispatch.py",
    "validate_mount_aware_resources.py",
    "validate_agent_selftest_workspace_boundary.py",
    "validate_commander_submission_package.py",
    "validate_cloud_launch_contract.py",
    "validate_stripe_test_wizard.py",
    "commander_paid_dev_health_ramp.py",
    "validate_event_v2_telemetry_signed_release.py",
    "validate_event_v2_local_telemetry.py",
    "test_commander_cf_cost_audit.py",
    "validate_portal_read_capacity.py",
    "validate_canonical_functions_hardening.py",
    "validate_mcp_process_risk_annotations.py",
    "validate_manual_on_demand_commercial.py",
    "verify_commander_public_artifacts.py",
    "validate_signed_commercial_v2_bundle.py",
    "validate_signed_commercial_v3_bundle.py",
    "test_signed_distribution_stage.py",
    "test_versioned_prod_release_preflight.py",
    "test_versioned_prod_upload_preflight.py",
    "test_versioned_asset_readback.py",
    "validate_versioned_prod_promote.py",
    "build_commander_commercial_terminal_drain_candidate.py",
    "stage_signed_commercial_assets.py",
    "commander_linux_clean_lifecycle.py",
    "validate_process_output_memory_budgets.py",
    "validate_preimage_storage_budget.py",
    "validate_concurrent_device_queue_sql.py",
    "validate_device_installers.py",
    "validate_bootstrap_supply_chain.py",
    "validate_linux_tunnel_start_modes.py",
    "validate_clean_linux_lifecycle.py",
    "validate_device_lifecycle_races.py",
    "validate_claim_revoke_race.py",
    "validate_session_retention.py",
    "validate_human_scale_v2.py",
    "validate_invite_claim_race.py",
    "validate_multitenant_isolation.py",
    "validate_quota_reservation_ttl.py",
    "validate_tenant_quota_storage_efficiency.py",
    "validate_local_budget_blocks.py",
    "validate_agent_request_efficiency.py",
    "validate_event_v2_websocket_client.py",
    "validate_event_v2_durable_batch_continuation.py",
    "validate_event_v2_wiring.py",
    "validate_event_v2_persistent_guard.py",
    "validate_event_v2_clean_shutdown.py",
    "validate_event_v2_presence_reconnect.py",
    "validate_event_v2_linux_rc_install.py",
    "validate_event_v2_transient_rpc.py",
    "validate_dev_config.py",
    "validate_prod_contracts.py",
    "validate_prod_static.py",
    "validate_release_signature.py",
    "validate_billing_v1.py",
    "test_commercial_model_20261020.py",
    "validate_local_activity_store.py",
    "validate_first_device_preflight.py",
    "validate_fresh_customer_acceptance.py",
    "validate_signed_windows_049_v9_rc.py",
    "validate_signed_windows_050_v10_rc.py",
    "validate_signed_windows_051_v11_rc.py",
    "validate_signed_windows_052_v12_rc.py",
    "validate_windows_r10_candidate.py",
    "test_live_release_integrity_gate.py",
    "test_linux_r11_pre_enroll.py",
    "test_linux_r13_enrollment_ack.py",
    "validate_windows_r11_installer_candidate.py",
    "validate_windows_r13_enrollment_intent.py",
    "test_windows_052_release_guards.py",
    "validate_windows_052_approval_expiry.py",
    "validate_windows_052_operator_startup.py",
    "validate_windows_052_approval_window.py",
    "test_windows_051_release_guards.py",
    "validate_windows_051_approval_expiry.py",
    "validate_windows_051_operator_startup.py",
    "validate_windows_051_approval_window.py",
    "validate_windows_049_approval_expiry.py",
    "validate_windows_049_operator_startup.py",
    "validate_windows_049_approval_window.py",
    "validate_windows_050_approval_expiry.py",
    "validate_windows_050_operator_startup.py",
    "validate_windows_050_approval_window.py",
)
JS = (
    "test_json_utf8_response.mjs",
    "test_windows_044_capability_gate.mjs",
    "test_windows_r10_capability_contract.mjs",
    "test_no_stripe_technical_mode.mjs",
    "test_commercial_policy_20261020.mjs",
    "test_device_enrollment_limit.mjs",
    "test_device_enrollment_recovery.mjs",
    "test_event_v2_notify_delivery.mjs",
    "test_portal_session_isolation.mjs",
    "test_device_status_poll.mjs",
    "test_recent_call_expiry_projection.mjs",
    "test_device_telemetry.mjs",
    "test_customer_mcp_admin_profile.mjs",
    "test_customer_argument_pipeline.mjs",
    "test_mcp_result_consistency.mjs",
    "test_full_mcp_result_consistency.mjs",
    "test_mcp_public_error_allowlist.mjs",
    "test_portal_read_boundaries.mjs",
    "test_usage_activity_concurrency.mjs",
    "test_device_version_observation.mjs",
    "test_portal_read_coordinator.mjs",
    "test_portal_history_read.mjs",
    "test_devices_minimalist_ui.mjs",
    "test_device_discovery_evidence.mjs",
    "test_activity_latency_diagnostics.mjs",
    "test_devices_setup_commands_ui.mjs",
    "test_nav_no_duplicate_titles.mjs",
    "test_plan_cards_centered_ui.mjs",
    "test_oidc_helpers.mjs",
    "test_auth_helpers.mjs",
    "test_auth_retention_capacity.mjs",
    "test_auth_maintenance_observer.mjs",
    "test_hara_identity_customer_mcp.mjs",
    "test_hara_identity_customer_auth_pressure.mjs",
    "test_public_result_projection.mjs",
    "test_customer_mcp_simple_profile.mjs",
    "test_customer_mcp_device_routing.mjs",
    "validate_device_tool_contract.mjs",
    "test_security_rate_limit.mjs",
    "test_customer_mcp_edge.mjs",
    "billing_sqlite_webhook_e2e.mjs",
    "billing_v1_selftest.mjs",
    "test_billing_checkout_attempts.mjs",
    "test_paid_entitlement_expiry.mjs",
    "validate_event_v2_fleet_allowlist.mjs",
    "test_approval_async_quota_ttl.mjs",
    "test_device_call_usage_settlement.mjs",
    "test_approval_async_storage.mjs",
    "test_quota_1000_local_workload.mjs",
    "test_approval_async_queue_claim.mjs",
)
MODELS = (
    "commander_scale_capacity_model.py",
    "validate_commander_1k_10k_capacity.py",
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
    if name == "build_commander_commercial_terminal_drain_candidate.py":
        command.append("--check")
    if name == "commander_linux_clean_lifecycle.py":
        # Ephemerally signed candidate over localhost + fake systemctl only.
        command.append("--execute")
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
    # Only static test-stage markers and the harness source line are retained.
    # Never surface installer output, tokens, paths or command arguments.
    diagnostic = {}
    if name == "commander_linux_clean_lifecycle.py" and output.returncode:
        stages = re.findall(
            r"(?m)^COMMANDER_CLEAN_LINUX_[A-Z0-9_]+=PASS$", output.stdout
        )
        lines = re.findall(
            r'commander_linux_clean_lifecycle[.]py", line ([0-9]+)',
            output.stderr,
        )
        diagnostic = {
            "last_passed_stage": stages[-1] if stages else None,
            "harness_failure_line": int(lines[-1]) if lines else None,
        }
    return {
        **diagnostic,
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
