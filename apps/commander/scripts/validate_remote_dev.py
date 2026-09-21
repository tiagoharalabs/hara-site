#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor

if len(sys.argv) < 3:
    raise SystemExit("usage: validate_remote_dev.py <base_url> <token_file>")

BASE = sys.argv[1].rstrip("/")
TOKEN_FILE = pathlib.Path(sys.argv[2])
TOKEN = TOKEN_FILE.read_text(encoding="utf-8").strip()
DEMO = "HARA-TENANT-DEMO-0001"
QUOTA = "HARA-TENANT-QUOTA-0001"


def call(path, payload=None, auth=True):
    data = None
    headers = {}
    if auth:
        headers["x-hara-dev-token"] = TOKEN
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["content-type"] = "application/json"
    request = urllib.request.Request(BASE + path, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def need(condition, code):
    if not condition:
        raise AssertionError(code)


def main():
    status, health = call("/api/dev/health", auth=False)
    need(status == 200 and health.get("ok") is True, "HEALTH")
    need(health.get("product_db") == "D1_REMOTE_DEV", "REMOTE_D1_HEALTH")
    need(health.get("quota_store") == "DURABLE_OBJECT_SQLITE_REMOTE_DEV", "REMOTE_DO_HEALTH")
    need(health.get("production_mutation") is False, "PRODUCTION_MUTATION")

    denied_status, denied = call("/api/dev/dashboard?tenant_id=" + DEMO, auth=False)
    need(denied_status == 401 and denied.get("code") == "DEV_ACCESS_DENIED", "AUTH_REQUIRED")

    status, dashboard = call("/api/dev/dashboard?tenant_id=" + DEMO)
    need(status == 200, "DASHBOARD")
    need(dashboard["entitlement"]["plan_code"] == "STANDARD", "DEMO_PLAN")
    need(dashboard["entitlement"]["unit_limit"] == 10000, "DEMO_LIMIT")

    request_id = "remote-concurrent-" + uuid.uuid4().hex
    payload = {"tenant_id": QUOTA, "request_id": request_id, "function_id": "fleet.list"}

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: call("/api/dev/quota/reserve", payload), range(8)))

    need(all(status == 200 for status, _ in results), "CONCURRENT_HTTP")
    need(all(body.get("state") == "RESERVED" for _, body in results), "CONCURRENT_STATE")
    need(sum(1 for _, body in results if body.get("existing") is False) == 1, "SINGLE_RESERVATION")
    need(all(body.get("consumed_units") == 1 for _, body in results), "SINGLE_CHARGE")

    blocked_id = "remote-blocked-" + uuid.uuid4().hex
    _, blocked = call("/api/dev/quota/reserve", {
        "tenant_id": QUOTA,
        "request_id": blocked_id,
        "function_id": "fleet.list",
    })
    need(blocked.get("code") == "QUOTA_EXCEEDED", "QUOTA_EXCEEDED")

    _, released = call("/api/dev/quota/release", {
        "tenant_id": QUOTA,
        "request_id": request_id,
    })
    need(released.get("state") == "RELEASED", "RELEASE")
    need(released.get("consumed_units") == 0, "RELEASE_BALANCE")

    commit_id = "remote-commit-" + uuid.uuid4().hex
    _, reserved = call("/api/dev/quota/reserve", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "function_id": "fleet.list",
    })
    need(reserved.get("state") == "RESERVED", "COMMIT_RESERVE")

    receipt = "c" * 64
    _, committed = call("/api/dev/quota/commit", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(committed.get("state") == "COMMITTED", "COMMIT")

    _, duplicate = call("/api/dev/quota/commit", {
        "tenant_id": QUOTA,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(duplicate.get("existing") is True, "COMMIT_IDEMPOTENCY")
    need(duplicate.get("consumed_units") == 1, "COMMIT_SINGLE_CHARGE")

    print("REMOTE_DEV_HEALTH=PASS")
    print("REMOTE_DEV_ACCESS_TOKEN=PASS")
    print("REMOTE_DEV_D1_READ=PASS")
    print("REMOTE_DEV_QUOTA_DO_SQLITE=PASS")
    print("REMOTE_DEV_CONCURRENCY=PASS")
    print("REMOTE_DEV_QUOTA_EXCEEDED=PASS")
    print("REMOTE_DEV_RELEASE=PASS")
    print("REMOTE_DEV_COMMIT_IDEMPOTENCY=PASS")
    print("PRODUCTION_MUTATION=FALSE")


if __name__ == "__main__":
    main()
