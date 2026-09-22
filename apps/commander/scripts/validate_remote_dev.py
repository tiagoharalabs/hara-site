#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
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
    cmd = [
        "curl", "-sS",
        "-o", "-",
        "-w", "\n%{http_code}",
        "--connect-timeout", "10",
        "--max-time", "20",
    ]
    if auth:
        cmd += ["-H", "x-hara-dev-token: " + TOKEN]
    if payload is not None:
        cmd += ["-H", "content-type: application/json", "-X", "POST", "--data", json.dumps(payload)]
    cmd.append(BASE + path)
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError("CURL_FAILED:" + (completed.stderr or "").strip())
    body, status_text = completed.stdout.rsplit("\n", 1)
    status = int(status_text.strip())
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"NON_JSON_HTTP_{status}:{body[:200]}") from exc
    return status, decoded


def raw_call(path):
    cmd = [
        "curl", "-sS",
        "-o", "-",
        "-w", "\n%{http_code}",
        "--connect-timeout", "10",
        "--max-time", "20",
        BASE + path,
    ]
    completed = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError("CURL_FAILED:" + (completed.stderr or "").strip())
    body, status_text = completed.stdout.rsplit("\n", 1)
    return int(status_text.strip()), body


def need(condition, code):
    if not condition:
        raise AssertionError(code)


def main():
    public_status, public_html = raw_call("/")
    need(public_status == 200, "PUBLIC_UI")
    for token in (
        "AMBIENTE DEV", "Portal DEV", "Workspace Demo", "Tiago Demo",
        "Sair do DEV", "DEV:", "UX em DEV", "Backend DEV", "tenant DEV",
    ):
        need(token not in public_html, "PRODUCTION_LIKE_UI_LEAK:" + token)

    auth_status, auth_config = call("/api/portal/auth-config", auth=False)
    need(auth_status == 200 and auth_config.get("configured") is True, "PORTAL_AUTH_CONFIG")
    need(auth_config.get("provider") == "HARA Identity", "PORTAL_AUTH_PROVIDER")

    status, health = call("/api/dev/health", auth=False)
    need(status == 200 and health.get("ok") is True, "HEALTH")
    need(health.get("product_db") == "D1_REMOTE_DEV", "REMOTE_D1_HEALTH")
    need(health.get("quota_store") == "DURABLE_OBJECT_SQLITE_REMOTE_DEV", "REMOTE_DO_HEALTH")
    need(health.get("production_mutation") is False, "PRODUCTION_MUTATION")

    denied_status, denied = call("/api/dev/dashboard?tenant_id=" + DEMO, auth=False)
    need(denied_status == 401 and denied.get("code") == "DEV_ACCESS_DENIED", "AUTH_REQUIRED")

    status, dashboard = call("/api/dev/dashboard?tenant_id=" + DEMO)
    need(status == 200, "DASHBOARD")
    need(dashboard["tenant"]["display_name"] == "HARA Labs", "PRODUCTION_LIKE_TENANT_NAME")
    need(dashboard["entitlement"]["plan_code"] == "STANDARD", "DEMO_PLAN")
    need(dashboard["entitlement"]["unit_limit"] == 10000, "DEMO_LIMIT")
    baseline = int(dashboard["usage"]["consumed_units"])

    # Concurrency/idempotency: use the Standard tenant and release afterward,
    # so repeated validator runs return to the same commercial balance.
    request_id = "remote-concurrent-" + uuid.uuid4().hex
    payload = {"tenant_id": DEMO, "request_id": request_id, "function_id": "fleet.list"}

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: call("/api/dev/quota/reserve", payload), range(8)))

    need(all(status == 200 for status, _ in results), "CONCURRENT_HTTP")
    need(all(body.get("state") == "RESERVED" for _, body in results), "CONCURRENT_STATE")
    need(sum(1 for _, body in results if body.get("existing") is False) == 1, "SINGLE_RESERVATION")
    need(all(body.get("consumed_units") == baseline + 1 for _, body in results), "SINGLE_CHARGE")

    _, released = call("/api/dev/quota/release", {
        "tenant_id": DEMO,
        "request_id": request_id,
    })
    need(released.get("state") == "RELEASED", "RELEASE")
    need(released.get("consumed_units") == baseline, "RELEASE_BALANCE")

    # QUOTA tenant is intentionally persistently exhausted after the first
    # homologation. This makes QUOTA_EXCEEDED a stable cross-run assertion.
    q_status, q_dashboard = call("/api/dev/dashboard?tenant_id=" + QUOTA)
    need(q_status == 200, "QUOTA_DASHBOARD")
    need(q_dashboard["usage"]["limit"] == 1, "QUOTA_LIMIT")
    need(q_dashboard["usage"]["consumed_units"] == 1, "QUOTA_BASELINE")

    blocked_id = "remote-blocked-" + uuid.uuid4().hex
    _, blocked = call("/api/dev/quota/reserve", {
        "tenant_id": QUOTA,
        "request_id": blocked_id,
        "function_id": "fleet.list",
    })
    need(blocked.get("code") == "QUOTA_EXCEEDED", "QUOTA_EXCEEDED")
    need(blocked.get("consumed_units") == 1, "QUOTA_EXCEEDED_BALANCE")

    # Stable idempotency request: the first run commits one unit; subsequent
    # runs must reuse the same committed request without charging again.
    commit_id = "remote-commit-idempotency-0001"
    receipt = "c" * 64
    _, reservation = call("/api/dev/quota/reserve", {
        "tenant_id": DEMO,
        "request_id": commit_id,
        "function_id": "fleet.list",
    })
    need(reservation.get("state") in {"RESERVED", "COMMITTED"}, "COMMIT_RESERVE")

    _, committed = call("/api/dev/quota/commit", {
        "tenant_id": DEMO,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(committed.get("state") == "COMMITTED", "COMMIT")

    _, duplicate = call("/api/dev/quota/commit", {
        "tenant_id": DEMO,
        "request_id": commit_id,
        "receipt_sha256": receipt,
    })
    need(duplicate.get("existing") is True, "COMMIT_IDEMPOTENCY")

    _, conflict = call("/api/dev/quota/commit", {
        "tenant_id": DEMO,
        "request_id": commit_id,
        "receipt_sha256": "d" * 64,
    })
    need(conflict.get("code") == "IDEMPOTENCY_CONFLICT", "RECEIPT_CONFLICT")

    status, final_dashboard = call("/api/dev/dashboard?tenant_id=" + DEMO)
    need(status == 200, "FINAL_DASHBOARD")
    expected = baseline if reservation.get("state") == "COMMITTED" else baseline + 1
    need(final_dashboard["usage"]["consumed_units"] == expected, "FINAL_BALANCE")

    print("PRODUCTION_LIKE_PUBLIC_UI=PASS")
    print("PORTAL_AUTH_CONFIG=PASS")
    print("PRODUCTION_LIKE_TENANT_NAME=PASS")
    print("REMOTE_DEV_HEALTH=PASS")
    print("REMOTE_DEV_ACCESS_TOKEN=PASS")
    print("REMOTE_DEV_D1_READ=PASS")
    print("REMOTE_DEV_QUOTA_DO_SQLITE=PASS")
    print("REMOTE_DEV_CONCURRENCY=PASS")
    print("REMOTE_DEV_QUOTA_EXCEEDED=PASS")
    print("REMOTE_DEV_RELEASE=PASS")
    print("REMOTE_DEV_COMMIT_IDEMPOTENCY=PASS")
    print("REMOTE_DEV_RECEIPT_CONFLICT=PASS")
    print("REMOTE_DEV_VALIDATOR_RERUN_SAFE=PASS")
    print("PRODUCTION_MUTATION=FALSE")


if __name__ == "__main__":
    main()
