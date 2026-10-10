#!/usr/bin/env python3
"""Read-only, credential-safe Cloudflare commercial Commander traffic comparison.

Query exactly two UTC windows of equal duration. Report aggregated Worker and
device-queue HTTP counts, Cloudflare adaptive sample interval, and commercial
operation counts from PROD D1. A matched workload is NOT a causal device-level
cost claim. Never print or persist Wrangler OAuth tokens.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "apps" / "commander"
WRANGLER = ROOT / "node_modules" / ".bin" / "wrangler"
CF_ACCOUNT_ID = "c8631a3ac0ac5a043af08903b8308227"
CF_ZONE_ID = "7aa1a1b65d0250ebf7bc6d9bbff172d8"
WORKER_NAME = "hara-commander"
QUEUE_ENDPOINT = "/api/device/calls/next"
DEFAULT_BEFORE = "2026-10-10T00:20:00Z"
DEFAULT_AFTER = "2026-10-10T02:05:00Z"
SCHEMA = "hara.commander-cloudflare-transport-efficiency.v1"


def fail(code: str) -> RuntimeError:
    return RuntimeError("COMMANDER_CF_TRAFFIC_" + code)


def utc(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise fail("UTC_TIMESTAMP_INVALID") from exc
    if not value.endswith("Z") or result.utcoffset() != timedelta(0):
        raise fail("UTC_TIMESTAMP_REQUIRED")
    if result.second != 0 or result.microsecond:
        raise fail("UTC_MINUTE_PRECISION_REQUIRED")
    return result.astimezone(timezone.utc)


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def windows(before: str, after: str, minutes: int) -> dict:
    if not 5 <= minutes <= 120:
        raise fail("WINDOW_MINUTES_INVALID")
    b = utc(before)
    a = utc(after)
    if b + timedelta(minutes=minutes) > a:
        raise fail("WINDOWS_OVERLAP_OR_ORDER_INVALID")
    if a + timedelta(minutes=minutes) > datetime.now(timezone.utc) - timedelta(minutes=2):
        raise fail("AFTER_WINDOW_NOT_COMPLETE")
    return {
        "before": (iso(b), iso(b + timedelta(minutes=minutes))),
        "after": (iso(a), iso(a + timedelta(minutes=minutes))),
    }


def auth_token() -> str:
    proc = subprocess.run(
        [str(WRANGLER), "auth", "token", "--json"],
        cwd=APP, capture_output=True, text=True, timeout=30,
        check=False,
    )
    if proc.returncode:
        raise fail("WRANGLER_AUTH_UNAVAILABLE")
    try:
        token = json.loads(proc.stdout)["token"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise fail("WRANGLER_AUTH_RESPONSE_INVALID") from exc
    if not isinstance(token, str) or len(token) < 30:
        raise fail("WRANGLER_AUTH_INVALID")
    return token


def window_filters(start: str, end: str, *, queue: bool) -> str:
    fields = {
        "datetime_geq": start,
        "datetime_lt": end,
    }
    fields.update({"clientRequestPath": QUEUE_ENDPOINT} if queue
                  else {"scriptName": WORKER_NAME})
    return ",".join(name + ":" + json.dumps(value) for name, value in fields.items())


def graphql_query(ranges: dict) -> str:
    b0, b1 = ranges["before"]
    a0, a1 = ranges["after"]
    return (
        "query HaraCommanderTrafficComparison {viewer {"
        " accounts(filter:{accountTag:" + json.dumps(CF_ACCOUNT_ID) + "}) {"
        " before:workersInvocationsAdaptive(limit:20,filter:{"
        + window_filters(b0, b1, queue=False)
        + "}) { sum{requests errors subrequests} }"
        " after:workersInvocationsAdaptive(limit:20,filter:{"
        + window_filters(a0, a1, queue=False)
        + "}) { sum{requests errors subrequests} }"
        " }"
        " zones(filter:{zoneTag:" + json.dumps(CF_ZONE_ID) + "}) {"
        " before:httpRequestsAdaptiveGroups(limit:20,filter:{"
        + window_filters(b0, b1, queue=True)
        + "}) { count avg{sampleInterval} }"
        " after:httpRequestsAdaptiveGroups(limit:20,filter:{"
        + window_filters(a0, a1, queue=True)
        + "}) { count avg{sampleInterval} }"
        " }}}"
    )


def request_graphql(query: str) -> dict:
    token = auth_token()
    try:
        req = urllib.request.Request(
            "https://api.cloudflare.com/client/v4/graphql",
            data=json.dumps({"query": query}, separators=(",", ":")).encode(),
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "HARA-Commander-ReadOnly-Efficiency/1",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            raise fail("GRAPHQL_HTTP_" + str(exc.code)) from None
        except urllib.error.URLError as exc:
            raise fail("GRAPHQL_NETWORK_UNAVAILABLE") from exc
        if result.get("errors"):
            raise fail("GRAPHQL_RESPONSE_ERRORS")
        return result
    finally:
        token = ""


def select_prod_d1_count(start: str, end: str) -> int:
    # SQL only builds from ISO-validated UTC strings and is always SELECT.
    sql = ("SELECT COUNT(*) AS operations FROM commander_device_calls "
           "WHERE created_at_utc >= '" + start + "' "
           "AND created_at_utc < '" + end + "';")
    proc = subprocess.run(
        [str(WRANGLER), "d1", "execute", "hara-commander-product-prod",
         "--remote", "--config", str(APP / "wrangler.jsonc"),
         "--json", "--command", sql],
        cwd=APP, capture_output=True, text=True, timeout=40,
        check=False,
    )
    if proc.returncode:
        raise fail("PROD_D1_READ_FAILED")
    try:
        data = json.loads(proc.stdout)
        return int(data[0]["results"][0]["operations"])
    except (json.JSONDecodeError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise fail("PROD_D1_COUNT_INVALID") from exc


def group_metrics(account: dict, zone: dict, period: str) -> dict:
    worker_rows = account.get(period) or []
    queue_rows = zone.get(period) or []
    samples = [float(r.get("avg", {}).get("sampleInterval") or 1)
               for r in queue_rows]
    return {
        "worker_requests": sum(int((r.get("sum") or {}).get("requests") or 0)
                               for r in worker_rows),
        "worker_errors": sum(int((r.get("sum") or {}).get("errors") or 0)
                             for r in worker_rows),
        "worker_subrequests": sum(int((r.get("sum") or {}).get("subrequests") or 0)
                                  for r in worker_rows),
        "queue_http_requests": sum(int(r.get("count") or 0) for r in queue_rows),
        "queue_sample_interval_max": max(samples, default=None),
        "queue_unsampled": bool(queue_rows) and all(i == 1 for i in samples),
    }


def difference(before: int, after: int) -> dict:
    if before <= 0:
        raise fail("BEFORE_COUNT_NOT_POSITIVE")
    return {
        "absolute": after - before,
        "percent": round(100.0 * (after - before) / before, 2),
    }


def measure(ranges: dict) -> dict:
    result = request_graphql(graphql_query(ranges))
    viewer = (result.get("data") or {}).get("viewer") or {}
    accounts, zones = viewer.get("accounts") or [], viewer.get("zones") or []
    if len(accounts) != 1 or len(zones) != 1:
        raise fail("GRAPHQL_SCOPE_UNAVAILABLE")
    periods = {}
    for part in ("before", "after"):
        start, end = ranges[part]
        periods[part] = {
            "start_utc": start,
            "end_utc": end,
            **group_metrics(accounts[0], zones[0], part),
            "commercial_device_calls": select_prod_d1_count(start, end),
        }
    before, after = periods["before"], periods["after"]
    return {
        "schema": SCHEMA,
        "source": "CLOUDFLARE_GRAPHQL_PLUS_PROD_D1_READ_ONLY",
        "script": WORKER_NAME,
        "path": QUEUE_ENDPOINT,
        "periods": periods,
        "worker_request_change": difference(
            before["worker_requests"], after["worker_requests"]),
        "queue_request_change": difference(
            before["queue_http_requests"], after["queue_http_requests"]),
        "matched_commercial_call_count":
            before["commercial_device_calls"] == after["commercial_device_calls"],
        "attributable_to_nucleo_only": False,
        "actual_billing_cost_verified": False,
        "client_content_collected": False,
        "oauth_token_in_output": False,
    }


def save_protected(path: str, payload: dict) -> None:
    output = Path(path).expanduser().absolute()
    if not str(output).startswith("/tmp_hara/") or output.exists() or output.is_symlink():
        raise fail("OUTPUT_PATH_DENIED_OR_EXISTS")
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(raw)
    print("COMMANDER_CF_EFFICIENCY_REPORT_WRITTEN=TRUE")


def self_test() -> None:
    test = {"before": ("2026-10-10T00:20:00Z", "2026-10-10T01:00:00Z"),
            "after": ("2026-10-10T02:05:00Z", "2026-10-10T02:45:00Z")}
    query = graphql_query(test)
    assert WORKER_NAME in query and QUEUE_ENDPOINT in query
    assert "Bearer" not in query and "token" not in query
    assert difference(1756, 1392) == {"absolute": -364, "percent": -20.73}
    good = group_metrics(
        {"before": [{"sum": {"requests": 2066, "errors": 0, "subrequests": 1}}]},
        {"before": [{"count": 1756, "avg": {"sampleInterval": 1}}]},
        "before",
    )
    assert good["queue_unsampled"] is True and good["queue_http_requests"] == 1756
    assert group_metrics({}, {}, "before")["queue_unsampled"] is False
    try:
        utc("2026-10-10T00:20:00+02:00")
    except RuntimeError:
        pass
    else:
        raise AssertionError("NONUTC_TIMESTAMP_ACCEPTED")
    print("COMMANDER_CF_EFFICIENCY_SOURCE=PASS")
    print("COMMANDER_CF_EFFICIENCY_READONLY=PASS")
    print("COMMANDER_CF_EFFICIENCY_AUTH_OUTPUT=ABSENT")
    print("COMMANDER_CF_EFFICIENCY_SAMPLING_GUARD=PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--before-start")
    parser.add_argument("--after-start")
    parser.add_argument("--minutes", type=int, default=40)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.check:
        self_test()
        return 0
    if not args.before_start or not args.after_start:
        raise fail("WINDOWS_EXPLICIT_START_REQUIRED")
    intervals = windows(args.before_start, args.after_start, args.minutes)
    output = measure(intervals)
    if args.output:
        save_protected(args.output, output)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        code = str(exc)
        if not code.startswith("COMMANDER_CF_TRAFFIC_"):
            code = "COMMANDER_CF_TRAFFIC_UNEXPECTED_ERROR"
        print(code, file=sys.stderr)
        raise SystemExit(1)
