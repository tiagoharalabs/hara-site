#!/usr/bin/env python3
from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ORIGIN = "https://commander.haralabs.com.br"

def call(path: str, *, method: str = "GET", headers=None, payload=None):
    data = None
    request_headers = {"User-Agent": "HARA-Commander-FailClosed/1"}
    if headers:
        request_headers.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"
    req = Request(
        ORIGIN + path,
        data=data,
        headers=request_headers,
        method=method,
    )
    try:
        with urlopen(req, timeout=15) as response:
            body = response.read()
            return response.status, body
    except HTTPError as exc:
        return exc.code, exc.read()

def expect(name: str, path: str, status: int, code: str, **kwargs):
    actual_status, body = call(path, **kwargs)
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name}_BODY_NOT_JSON") from exc
    actual_code = str(payload.get("code") or "")
    if actual_status != status or actual_code != code:
        raise RuntimeError(
            f"{name}_EXPECTED_{status}_{code}_GOT_{actual_status}_{actual_code}"
        )
    print(f"{name}=PASS:{actual_status}:{actual_code}")

def main() -> int:
    expect("COMMANDER_PROD_FAIL_CLOSED_SESSION",
           "/api/portal/session", 401, "AUTH_REQUIRED")
    expect("COMMANDER_PROD_FAIL_CLOSED_DASHBOARD",
           "/api/portal/dashboard", 401, "AUTH_REQUIRED")
    expect("COMMANDER_PROD_FAIL_CLOSED_DEVICES",
           "/api/portal/devices", 401, "AUTH_REQUIRED")

    same_origin = {
        "Origin": ORIGIN,
        "Sec-Fetch-Site": "same-origin",
    }
    expect(
        "COMMANDER_PROD_FAIL_CLOSED_PAIRING_NO_SESSION",
        "/api/portal/devices/pairing",
        401,
        "AUTH_REQUIRED",
        method="POST",
        headers=same_origin,
        payload={},
    )
    expect(
        "COMMANDER_PROD_FAIL_CLOSED_PAIRING_CROSS_ORIGIN",
        "/api/portal/devices/pairing",
        403,
        "PORTAL_ORIGIN_DENIED",
        method="POST",
        headers={
            "Origin": "https://evil.example",
            "Sec-Fetch-Site": "cross-site",
        },
        payload={},
    )

    expect(
        "COMMANDER_PROD_FAIL_CLOSED_HEARTBEAT",
        "/api/device/heartbeat",
        401,
        "DEVICE_AUTH_REQUIRED",
        method="POST",
        payload={},
    )
    expect(
        "COMMANDER_PROD_FAIL_CLOSED_CALL_NEXT",
        "/api/device/calls/next",
        401,
        "DEVICE_AUTH_REQUIRED",
        method="POST",
    )
    expect(
        "COMMANDER_PROD_FAIL_CLOSED_MCP_INTERNAL",
        "/api/internal/mcp/authorize",
        401,
        "MCP_PRODUCT_ACCESS_DENIED",
        method="POST",
        payload={},
    )

    expect(
        "COMMANDER_PROD_FAIL_CLOSED_DEV_ROUTE",
        "/api/dev/health",
        404,
        "DEV_ENDPOINT_DISABLED",
    )
    print("COMMANDER_PROD_FAIL_CLOSED=PASS")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"COMMANDER_PROD_FAIL_CLOSED=FAIL:{exc}")
        raise
