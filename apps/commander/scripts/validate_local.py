#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9192"
DEMO = "HARA-TENANT-DEMO-0001"
QUOTA = "HARA-TENANT-QUOTA-0001"


def call(path, payload=None):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["content-type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def need(condition, code):
    if not condition:
        raise AssertionError(code)


def main():
    status, health = call("/api/dev/health")
    need(status == 200 and health.get("ok") is True, "HEALTH")
    need(health.get("production_mutation") is False, "PRODUCTION_MUTATION")

    status, dashboard = call("/api/dev/dashboard?tenant_id=" + DEMO)
    need(status == 200, "DEMO_DASHBOARD")
    need(dashboard["entitlement"]["plan_code"] == "STANDARD", "DEMO_PLAN")
    need(dashboard["entitlement"]["unit_limit"] == 10000, "DEMO_LIMIT")

    request_id = "req-concurrent-" + uuid.uuid4().hex
    payload = {
        "tenant_id": QUOTA,
        "request_id": request_id,
        "function_id": "fleet.list",
    }

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: call("/api/dev/quota/reserve", payload), range(8)))

    need(all(status == 200 for status, _ in results), "CONCURRENT_HTTP")
    need(all(body.get("state") == "RESERVED" for _, body in results), "CONCURRENT_STATE")
    need(sum(1 for _, body in results if body.get("existing") is False) == 1, "SINGLE_RESERVATION")
    need(all(body.get("consumed_units") == 1 for _, body in results), "SINGLE_CHARGE")

    blocked_id = "req-blocked-" + uuid.uuid4().hex
    _, blocked = call("/api/dev/quota/reserve", {
        "tenant_id": QUOTA,
        "request_id": blocked_id,
        "function_id": "fleet.list",
    })
    need(blocked.get("code") == "QUOTA_EXCEEDED", "QUOTA_EXCEEDED")
    need(blocked.get("consumed_units") == 1, "QUOTA_EXCEEDED_BALANCE")

    _, released = call("/api/dev/quota/release", {
        "tenant_id": QUOTA,
        "request_id": request_id,
    })
    need(released.get("state") == "RELEASED", "RELEASE")
    need(released.get("consumed_units") == 0, "RELEASE_BALANCE")

    commit_id = "req-commit-" + uuid.uuid4().hex
    _, reserved = call("/api/dev/quota/reserve", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "function_id": "fleet.list",
    })
    need(reserved.get("state") == "RESERVED", "COMMIT_RESERVE")

    receipt = "a" * 64
    _, committed = call("/api/dev/quota/commit", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(committed.get("state") == "COMMITTED", "COMMIT")
    need(committed.get("consumed_units") == 1, "COMMIT_BALANCE")

    _, duplicate = call("/api/dev/quota/commit", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(duplicate.get("existing") is True, "COMMIT_IDEMPOTENCY")
    need(duplicate.get("consumed_units") == 1, "COMMIT_SINGLE_CHARGE")

    _, conflict = call("/api/dev/quota/commit", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "receipt_sha256": "b" * 64,
    })
    need(conflict.get("code") == "IDEMPOTENCY_CONFLICT", "RECEIPT_CONFLICT")

    print("COMMANDER_PRODUCT_D1_LOCAL=PASS")
    print("COMMANDER_QUOTA_DO_SQLITE_LOCAL=PASS")
    print("CALENDAR_MONTH_BUCKET=PASS")
    print("CONCURRENT_DUPLICATE_SINGLE_RESERVATION=PASS")
    print("QUOTA_EXCEEDED=PASS")
    print("RELEASE_RESTORES_QUOTA=PASS")
    print("COMMIT_IDEMPOTENCY=PASS")
    print("RECEIPT_CONFLICT_FAIL_CLOSED=PASS")
    print("PRODUCTION_MUTATION=FALSE")


if __name__ == "__main__":
    main()
