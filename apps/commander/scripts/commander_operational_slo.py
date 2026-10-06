#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WRANGLER = ROOT / "node_modules" / ".bin" / "wrangler"
ENVIRONMENTS = {
    "dev": ("hara-commander-product-dev", APP / "wrangler.dev.jsonc"),
    "prod": ("hara-commander-product-prod", APP / "wrangler.jsonc"),
}
ONLINE_GRACE_SECONDS = 120
SNAPSHOT_GRACE_SECONDS = 120


def parse_time(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def summarize(rows: list[dict], window: str, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    online_cutoff = now - timedelta(seconds=ONLINE_GRACE_SECONDS)
    snapshot_cutoff = now - timedelta(seconds=SNAPSHOT_GRACE_SECONDS)
    devices = []
    total_completed = 0
    total_failed = 0
    total_client_failed = 0
    total_policy_failed = 0
    total_service_failed = 0
    evaluable = 0
    passed = 0
    degraded = 0
    insufficient = 0
    missing_snapshot = 0
    stale_snapshot = 0
    percentiles = {"p50": [], "p95": [], "p99": []}

    for row in rows:
        last_seen = parse_time(row.get("last_seen_at_utc"))
        if not last_seen or last_seen < online_cutoff:
            continue
        snap_at = parse_time(row.get("activity_summary_at_utc"))
        raw = row.get("activity_summary_json")
        if not raw:
            missing_snapshot += 1
            devices.append({
                "device_name": row.get("device_name"),
                "agent_version": row.get("agent_version"),
                "state": "MISSING_SNAPSHOT",
            })
            continue
        if not snap_at or snap_at < snapshot_cutoff:
            stale_snapshot += 1
        try:
            snap = json.loads(raw)
        except Exception:
            missing_snapshot += 1
            continue
        payload = (snap.get("windows") or {}).get(window) or {}
        summary = payload.get("summary") or {}
        slo = payload.get("slo") or {}
        status = str(slo.get("status") or "INSUFFICIENT_DATA")
        completed = int(summary.get("completed") or 0)
        failed = int(summary.get("failed") or 0)
        service_failed = int(summary.get("service_failed") if summary.get("service_failed") is not None else failed)
        total_completed += completed
        total_failed += failed
        total_client_failed += int(summary.get("client_failed") or 0)
        total_policy_failed += int(summary.get("policy_failed") or 0)
        total_service_failed += service_failed
        if status == "PASS":
            evaluable += 1
            passed += 1
        elif status == "DEGRADED":
            evaluable += 1
            degraded += 1
        else:
            insufficient += 1
        for key, field in (("p50", "latency_p50_ms"), ("p95", "latency_p95_ms"), ("p99", "latency_p99_ms")):
            value = summary.get(field)
            if value is not None:
                percentiles[key].append(float(value))
        devices.append({
            "device_name": row.get("device_name"),
            "platform": row.get("platform"),
            "agent_version": row.get("agent_version"),
            "snapshot_at_utc": row.get("activity_summary_at_utc"),
            "slo_status": status,
            "success_rate_percent": summary.get("success_rate_percent"),
            "availability_success_rate_percent": summary.get(
                "availability_success_rate_percent",
                summary.get("success_rate_percent"),
            ),
            "client_failed": summary.get("client_failed", 0),
            "policy_failed": summary.get("policy_failed", 0),
            "service_failed": service_failed,
            "p50_ms": summary.get("latency_p50_ms"),
            "p95_ms": summary.get("latency_p95_ms"),
            "p99_ms": summary.get("latency_p99_ms"),
            "latency_sample_size": summary.get("latency_sample_size"),
        })

    terminal = total_completed + total_failed
    availability_terminal = total_completed + total_service_failed
    weighted_outcome = round(total_completed * 100 / terminal, 3) if terminal else None
    weighted_availability = (
        round(total_completed * 100 / availability_terminal, 3)
        if availability_terminal
        else None
    )
    if missing_snapshot or stale_snapshot:
        fleet_state = "DEGRADED"
    elif degraded:
        fleet_state = "DEGRADED"
    elif evaluable:
        fleet_state = "PASS"
    else:
        fleet_state = "INSUFFICIENT_DATA"

    return {
        "schema": "hara.commander-operational-slo.v1",
        "profile": "INTERNAL_BETA_V1",
        "window": window,
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "fleet_state": fleet_state,
        "online_devices": len(devices),
        "evaluable_devices": evaluable,
        "pass_devices": passed,
        "degraded_devices": degraded,
        "insufficient_devices": insufficient,
        "missing_snapshot_devices": missing_snapshot,
        "stale_snapshot_devices": stale_snapshot,
        "client_failed": total_client_failed,
        "policy_failed": total_policy_failed,
        "service_failed": total_service_failed,
        "weighted_success_rate_percent": weighted_availability,
        "weighted_availability_success_rate_percent": weighted_availability,
        "weighted_outcome_success_rate_percent": weighted_outcome,
        "worst_device_p50_ms": max(percentiles["p50"]) if percentiles["p50"] else None,
        "worst_device_p95_ms": max(percentiles["p95"]) if percentiles["p95"] else None,
        "worst_device_p99_ms": max(percentiles["p99"]) if percentiles["p99"] else None,
        "devices": devices,
    }


def self_test() -> None:
    now = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc)
    good = {
        "schema": "hara.commander-local-activity-snapshots.v1",
        "windows": {
            "24h": {
                "summary": {
                    "completed": 99,
                    "failed": 1,
                    "client_failed": 1,
                    "policy_failed": 0,
                    "service_failed": 0,
                    "success_rate_percent": 99.0,
                    "availability_success_rate_percent": 100.0,
                    "latency_p50_ms": 700,
                    "latency_p95_ms": 5000,
                    "latency_p99_ms": 10000,
                    "latency_sample_size": 100,
                },
                "slo": {"status": "PASS"},
            }
        },
    }
    sparse = {
        "schema": "hara.commander-local-activity-snapshots.v1",
        "windows": {
            "24h": {
                "summary": {
                    "completed": 5,
                    "failed": 0,
                    "client_failed": 0,
                    "policy_failed": 0,
                    "service_failed": 0,
                    "success_rate_percent": 100.0,
                    "availability_success_rate_percent": 100.0,
                    "latency_p50_ms": 300,
                    "latency_p95_ms": 500,
                    "latency_p99_ms": 500,
                    "latency_sample_size": 5,
                },
                "slo": {"status": "INSUFFICIENT_DATA"},
            }
        },
    }
    rows = [
        {
            "device_name": "A", "platform": "LINUX", "agent_version": "0.3.40",
            "last_seen_at_utc": (now - timedelta(seconds=10)).isoformat(),
            "activity_summary_at_utc": (now - timedelta(seconds=10)).isoformat(),
            "activity_summary_json": json.dumps(good),
        },
        {
            "device_name": "B", "platform": "LINUX", "agent_version": "0.3.40",
            "last_seen_at_utc": (now - timedelta(seconds=10)).isoformat(),
            "activity_summary_at_utc": (now - timedelta(seconds=10)).isoformat(),
            "activity_summary_json": json.dumps(sparse),
        },
    ]
    out = summarize(rows, "24h", now)
    assert out["fleet_state"] == "PASS", out
    assert out["online_devices"] == 2
    assert out["evaluable_devices"] == 1
    assert out["insufficient_devices"] == 1
    assert out["weighted_success_rate_percent"] == 100.0
    assert out["weighted_availability_success_rate_percent"] == 100.0
    assert out["weighted_outcome_success_rate_percent"] == 99.048
    assert out["client_failed"] == 1
    assert out["service_failed"] == 0
    assert out["worst_device_p95_ms"] == 5000.0
    print("COMMANDER_OPERATIONAL_SLO_SELFTEST=PASS")


def fetch_rows(environment: str) -> list[dict]:
    db, config = ENVIRONMENTS[environment]
    sql = (
        "SELECT device_name,platform,agent_version,state,last_seen_at_utc,"
        "activity_summary_at_utc,activity_summary_json "
        "FROM commander_devices WHERE state='ACTIVE' ORDER BY device_name;"
    )
    proc = subprocess.run(
        [str(WRANGLER), "d1", "execute", db, "--remote", "--config", str(config),
         "--command", sql, "--json"],
        cwd=APP, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=90, check=False,
    )
    if proc.returncode:
        raise RuntimeError("D1_EXECUTE_FAILED")
    payload = json.loads(proc.stdout)
    return payload[-1].get("results") or []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=sorted(ENVIRONMENTS), default="prod")
    parser.add_argument("--window", choices=("24h", "7d", "30d"), default="24h")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not WRANGLER.is_file():
        raise SystemExit("WRANGLER_MISSING")
    out = summarize(fetch_rows(args.environment), args.window)
    print(json.dumps(out, indent=2, sort_keys=True))
    if args.check:
        print("COMMANDER_OPERATIONAL_SLO=" + out["fleet_state"])
        return 0 if out["fleet_state"] == "PASS" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
