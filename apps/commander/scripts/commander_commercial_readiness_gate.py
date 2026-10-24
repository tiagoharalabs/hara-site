#!/usr/bin/env python3
"""Commercial release gate: enforce evidence, never infer users from HTTP health.

This module is entirely local/offline. It never reads credentials, talks to cloud
or modifies a Worker, D1 database, Stripe, devices or signed installers.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
P0_EVIDENCE = ROOT / "docs/evidence/commander-pty-drain-20261011/acceptance.json"
BETA_EVIDENCE = ROOT / "docs/evidence/commander-stripe-free-validation-20261011/summary.json"
MIN_EVIDENCE_HOURS = 72
MAX_SOAK_ERRORS_PERCENT = 0.5
MAX_SOAK_P95_MS = 6000

@dataclass(frozen=True)
class Gate:
    code: str
    passed: bool
    basis: str
    required_for: tuple[str, ...]

    def as_json(self):
        return {"code": self.code, "passed": self.passed, "basis": self.basis,
                "required_for": list(self.required_for)}


def only_dict(obj, name):
    if not isinstance(obj, dict):
        raise ValueError("RELEASE_EVIDENCE_INVALID_" + name)
    return obj


def read_json(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 512 * 1024:
        raise ValueError("RELEASE_EVIDENCE_FILE_UNSAFE")
    return only_dict(json.loads(path.read_text(encoding="utf-8")), "JSON")


def validate_windows_fixture(evidence):
    """A Windows runtime proof must be separate from Linux source-only RC tests."""
    if not evidence:
        return False
    d = only_dict(evidence, "WINDOWS")
    return (
        d.get("schema") == "hara.commander-windows-runtime-acceptance.v1"
        and d.get("platform") == "WINDOWS"
        and d.get("version_signed") is True
        and d.get("installer_clean_pass") is True
        and d.get("uninstall_clean_pass") is True
        and d.get("mcp_authenticated_roundtrip_pass") is True
        and d.get("reconnect_and_receipt_replay_pass") is True
        and d.get("file_process_parity_pass") is True
        and d.get("agent_runs_without_desktop_commander") is True
    )


def validate_scale_fixture(evidence):
    """Do not treat a 1k HTTP health burst as 1k authenticated customers."""
    if not evidence:
        return False
    d = only_dict(evidence, "SCALE")
    required = (
        d.get("schema") == "hara.commander-1000-customer-soak.v1"
        and type(d.get("distinct_tenants")) is int
        and d["distinct_tenants"] >= 1000
        and type(d.get("simultaneous_authenticated_agents")) is int
        and d["simultaneous_authenticated_agents"] >= 1000
        and type(d.get("soak_hours")) is (int if type(d.get("soak_hours")) is int else float)
        and d["soak_hours"] >= 24
        and d.get("tenant_isolation_pass") is True
        and d.get("reconnect_deduplication_pass") is True
        and d.get("quota_enforcement_pass") is True
        and d.get("error_budget_measured") is True
        and d.get("cost_workers_d1_do_measured") is True
        and d.get("cleanup_verified") is True
        and isinstance(d.get("error_rate_percent"), (int, float))
        and not isinstance(d.get("error_rate_percent"), bool)
        and 0 <= d["error_rate_percent"] <= MAX_SOAK_ERRORS_PERCENT
        and isinstance(d.get("p95_ms"), (int, float))
        and not isinstance(d.get("p95_ms"), bool)
        and 0 < d["p95_ms"] <= MAX_SOAK_P95_MS
    )
    return bool(required)


def evaluate(p0, beta, *, windows=None, soak=None, billing=None, openai=None):
    """Progressive profiles. A claim can never be promoted by model-only tests."""
    p0 = only_dict(p0, "P0")
    beta = only_dict(beta, "BETA")
    release = only_dict(p0.get("signed_release"), "SIGNATURE")
    fleet = only_dict(p0.get("real_commercial_mcp"), "FLEET")
    historical = only_dict(beta.get("founder"), "FOUNDER")
    gate = only_dict(beta.get("gate"), "OFFLINE_GATE")
    profile = ["FOUNDER_TECHNICAL", "COMMERCIAL_BETA", "GENERAL_AVAILABILITY"]
    def add(code, ok, basis, *profiles):
        checks.append(Gate(code, bool(ok), basis, tuple(profiles)))
    checks = []

    add("FOUNDERS_7_LINUX_CURRENT",
        fleet.get("fleet_online_0346_count") == 7
        and fleet.get("fleet_online_total") == 7
        and historical.get("online_linux") == 7,
        "Signed Founder Agent fleet receipts", *profile)
    lines = fleet.get("fleet_each_lines_passed")
    add("REAL_PTY_POST_EXIT_7_OF_7",
        isinstance(lines, dict) and len(lines) == 7
        and all(type(n) is int and n == 120 for n in lines.values()),
        "Seven real Agent receipts for 120 retained lines", *profile)
    add("SIGNED_FOUNDER_RELEASE",
        release.get("agent_version") == "0.3.46"
        and release.get("channel") == "FOUNDER_LINUX_ONLY"
        and release.get("signed_files") == 7
        and release.get("private_key_exported") is False,
        "RS256 Founder-only release; not commercial distribution", *profile)
    add("LOCAL_GATE_AND_HOSTED_CI",
        p0.get("hosted_ci", {}).get("conclusion") == "success"
        and p0.get("regression", {}).get("failed") == 0
        and gate.get("failed") == 0 and gate.get("checked", 0) >= 80,
        "Offline and GitHub Actions evidence, not a cloud soak", *profile)
    add("STRIPE_INDEPENDENT_BETA",
        beta.get("billing", {}).get("no_stripe_mode_tests", {}).get("passed") == 13
        and beta.get("billing", {}).get("real_payment_requests") == 0,
        "Technical beta must not require payment services", "FOUNDER_TECHNICAL")
    add("CUSTOMER_SIGNED_DISTRIBUTION",
        False, "Public signed Agent and installer must be rebuilt and verified from current source",
        "COMMERCIAL_BETA","GENERAL_AVAILABILITY")
    add("SECOND_TENANT_ISOLATION",
        False, "Separate authenticated customer identity, device and receipt proof required",
        "COMMERCIAL_BETA","GENERAL_AVAILABILITY")
    add("WINDOWS_LIVE_PARITY",
        validate_windows_fixture(windows),
        "Windows RC source checks alone never count as a Windows runtime acceptance",
        "GENERAL_AVAILABILITY")
    add("CLOUD_1000_TENANT_24H_SOAK",
        validate_scale_fixture(soak),
        "Authenticated Agents, DO/D1/Worker costs, reconnect and cleanup",
        "GENERAL_AVAILABILITY")
    add("STRIPE_TEST_WEBHOOK_AND_ENTITLEMENT",
        bool(billing and billing.get("test_checkout_webhook_entitlement_cancel_pass") is True),
        "Stripe test-mode, separate tenant, signed webhook and cancel",
        "GENERAL_AVAILABILITY")
    add("OPENAI_PUBLIC_APPROVAL",
        bool(openai and openai.get("approved") is True
             and openai.get("verified_business") is True),
        "Provider app review and business identity",
        "GENERAL_AVAILABILITY")
    profiles={}
    for key in profile:
        failures=[item.code for item in checks if key in item.required_for and not item.passed]
        profiles[key] = {"state":"PASS" if not failures else "HOLD",
                         "blockers":failures}
    return {
        "schema":"hara.commander-commercial-readiness-gate.v1",
        "profiles":profiles,
        "evidence_verification_only":True,
        "real_stripe_or_cloud_mutation":False,
        "windows_source_only_not_counted_as_live":True,
        "http_health_burst_not_counted_as_1000_clients":True,
        "checks":[item.as_json() for item in checks],
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--p0-evidence",default=str(P0_EVIDENCE))
    parser.add_argument("--beta-evidence",default=str(BETA_EVIDENCE))
    parser.add_argument("--windows-evidence")
    parser.add_argument("--scale-evidence")
    parser.add_argument("--billing-evidence")
    parser.add_argument("--openai-evidence")
    parser.add_argument("--require",choices=("FOUNDER_TECHNICAL","COMMERCIAL_BETA","GENERAL_AVAILABILITY"))
    args=parser.parse_args()
    optional=lambda val:read_json(val) if val else None
    result=evaluate(read_json(args.p0_evidence),read_json(args.beta_evidence),
                    windows=optional(args.windows_evidence),soak=optional(args.scale_evidence),
                    billing=optional(args.billing_evidence),openai=optional(args.openai_evidence))
    print(json.dumps(result,sort_keys=True))
    return 0 if args.require is None or result["profiles"][args.require]["state"]=="PASS" else 2

if __name__=="__main__":
    raise SystemExit(main())
