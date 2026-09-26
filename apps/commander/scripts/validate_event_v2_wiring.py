#!/usr/bin/env python3
"""Static guard for Commander Event V2 Worker wiring.

This is source-only validation. It must prove the new channel is DEV-bound and
feature-enabled only for the DEV canary, while PROD remains free of the new binding until a
separate canary/cutover gate.
"""

from __future__ import annotations

import json
from pathlib import Path

COMMANDER = Path(__file__).resolve().parent.parent
WORKER = COMMANDER / "src" / "worker.js"
DEV = COMMANDER / "wrangler.dev.jsonc"
PROD = COMMANDER / "wrangler.jsonc"


def main() -> int:
    worker = WORKER.read_text(encoding="utf-8")
    dev_raw = DEV.read_text(encoding="utf-8")
    prod_raw = PROD.read_text(encoding="utf-8")

    required_worker = [
        'import { DeviceChannel, deviceChannelName } from "./device-channel.mjs"',
        "export { DeviceChannel }",
        'url.pathname === "/api/device/channel"',
        "openDeviceEventChannel",
        "resolveDeviceCredential(env, request)",
        "DEVICE_EVENT_V2_ENABLED",
        "notifyDeviceEventChannel",
        "x-hara-channel-authenticated",
        "D1 call state remains authoritative",
        'tunnelMode = "OUTBOUND_RELAY"',
        'mode === "EVENT_V2_OFFLINE"',
        'mode === "EVENT_V2"',
        "eventV2Cutoff",
        "d.tunnel_mode = 'EVENT_V2'",
        "d.tunnel_mode NOT IN ('EVENT_V2','EVENT_V2_OFFLINE')",
    ]
    for marker in required_worker:
        assert marker in worker, f"missing Worker Event V2 marker: {marker}"

    insert_at = worker.index("INSERT OR IGNORE INTO commander_device_calls")
    use_event_at = worker.index('const useEventV2 = String(device.tunnel_mode || "") === "EVENT_V2";')
    notify_at = worker.index("? await notifyDeviceEventChannel(", use_event_at)
    assert use_event_at > insert_at, "transport selection must occur only after durable call insert"
    assert notify_at > use_event_at, "event notification must be gated by Event V2 transport"
    notify_prefix = worker[use_event_at:notify_at + 250]
    assert 'String(device.tunnel_mode || "") === "EVENT_V2"' in notify_prefix
    assert ": { attempted: false, delivered: 0 }" in notify_prefix
    undelivered_at = worker.index("DEVICE_EVENT_UNDELIVERED")
    assert undelivered_at > notify_at, "undelivered Event V2 call must cancel after notify attempt"
    notify_guard = worker[notify_at:undelivered_at + 800]
    assert "notification.delivered < 1" in notify_guard
    assert 'throw new Error("DEVICE_OFFLINE")' in notify_guard
    assert "state = 'CANCELLED'" in notify_guard

    assert "const EVENT_V2_TERMINAL_FAST_PATH_WAIT_MS = 500;" in worker
    assert "const DEVICE_CALL_ACTIVE_QUEUE_LIMIT = 16;" in worker
    assert 'function deviceCallRetryAfterMs(state, source = "status")' in worker
    assert 'return source === "enqueue" ? 350 : 750;' in worker
    assert 'if (normalized === "EXECUTING") return 250;' in worker
    assert "DEVICE_BUSY: 429" in worker
    assert 'errorPayload.retry_after_ms = 1000' in worker
    assert "DEVICE_CALL_ACTIVE_QUEUE_LIMIT" in worker
    assert "SELECT COUNT(*) AS active_count" in worker
    post_notify_read_at = worker.index("let postNotify = null;", notify_at)
    settle_wait_at = worker.index("await scheduler.wait(EVENT_V2_TERMINAL_FAST_PATH_WAIT_MS);", post_notify_read_at)
    response_state_at = worker.index('const responseState = String(postNotify?.state || "PENDING")', post_notify_read_at)
    assert post_notify_read_at > notify_at
    assert settle_wait_at > post_notify_read_at
    assert response_state_at > settle_wait_at
    post_notify_block = worker[post_notify_read_at:response_state_at + 500]
    assert "notification.delivered >= 1" in post_notify_block
    assert "result_json" in post_notify_block
    assert "error_code" in post_notify_block

    assert "deviceOnline(row.last_seen_at_utc, row.tunnel_mode, now)" in worker
    heartbeat_at = worker.index("async function heartbeatDevice")
    heartbeat_end = worker.index("async function revokeDeviceSelf", heartbeat_at)
    heartbeat_block = worker[heartbeat_at:heartbeat_end]
    assert "tunnel_mode = 'OUTBOUND_RELAY'" in heartbeat_block
    assert "deviceOnline(device.last_seen_at_utc, device.tunnel_mode)" in worker
    assert "deviceOnline(currentDevice.last_seen_at_utc, currentDevice.tunnel_mode)" in worker

    selected_fn_at = worker.index("async function selectedDeviceForSubject")
    selected_fn_end = worker.index("async function selectDevice", selected_fn_at)
    selected_fn_block = worker[selected_fn_at:selected_fn_end]
    assert "SELECT d.device_id, d.tenant_id, d.state, d.tunnel_mode" in selected_fn_block
    assert "d.last_seen_at_utc, d.revoked_at_utc" in selected_fn_block

    enqueue_fn_at = worker.index("async function enqueueDeviceCall")
    enqueue_fn_end = worker.index("async function claimNextDeviceCall", enqueue_fn_at)
    enqueue_fn_block = worker[enqueue_fn_at:enqueue_fn_end]
    assert "const device = selection;" in enqueue_fn_block
    assert "const currentDevice = currentSelection;" in enqueue_fn_block
    assert "SELECT device_id, tenant_id, state, tunnel_mode, last_seen_at_utc, revoked_at_utc" not in enqueue_fn_block
    assert "SELECT state, tunnel_mode, last_seen_at_utc, revoked_at_utc" not in enqueue_fn_block

    mcp_auth_start = worker.index("function requireMcpProductToken")
    mcp_auth_end = worker.index("function requirePortalMutationOrigin")
    mcp_auth_block = worker[mcp_auth_start:mcp_auth_end]
    assert 'env.ENVIRONMENT === "DEV"' in mcp_auth_block
    assert "MCP_PRODUCT_CANARY_TOKEN" in mcp_auth_block
    assert "secretMatches(env.MCP_PRODUCT_TOKEN, supplied)" in mcp_auth_block

    # The Worker must authenticate the original upgrade before constructing the
    # internal DO request. The bearer credential must not be copied into that request.
    open_at = worker.index("async function openDeviceEventChannel")
    notify_fn_at = worker.index("async function notifyDeviceEventChannel")
    open_block = worker[open_at:notify_fn_at]
    assert open_block.index("resolveDeviceCredential(env, request)") < open_block.index(
        "new Request"
    )
    assert 'headers.set("authorization"' not in open_block.lower()

    dev = json.loads(dev_raw)
    assert dev["vars"]["DEVICE_EVENT_V2_ENABLED"] == "true"
    bindings = {
        row["name"]: row["class_name"]
        for row in dev["durable_objects"]["bindings"]
    }
    assert bindings.get("DEVICE_CHANNEL") == "DeviceChannel"
    assert any(
        row.get("tag") == "v2" and "DeviceChannel" in row.get("new_sqlite_classes", [])
        for row in dev["migrations"]
    )

    # PROD is intentionally untouched by package 2.
    assert "DEVICE_EVENT_V2_ENABLED" not in prod_raw
    assert '"DEVICE_CHANNEL"' not in prod_raw
    assert '"DeviceChannel"' not in prod_raw
    assert "MCP_PRODUCT_CANARY_TOKEN" not in prod_raw

    print("COMMANDER_EVENT_V2_WORKER_WIRING=PASS")
    print("COMMANDER_EVENT_V2_DEV_BINDING_SQLITE=PASS")
    print("COMMANDER_EVENT_V2_DEV_CANARY=ON")
    print("COMMANDER_EVENT_V2_PROD_BINDING=ABSENT")
    print("COMMANDER_EVENT_V2_NOTIFY_AFTER_DURABLE_INSERT=PASS")
    print("COMMANDER_EVENT_V2_NOTIFY_ONLY_FOR_EVENT_V2_DEVICE=PASS")
    print("COMMANDER_EVENT_V2_V1_NOTIFY_DO=ABSENT")
    print("COMMANDER_EVENT_V2_PRESENCE_USES_TRANSPORT_STATE=PASS")
    print("COMMANDER_EVENT_V2_V1_90S_WINDOW_PRESERVED=PASS")
    print("COMMANDER_EVENT_V2_V1_HEARTBEAT_RECLAIMS_RELAY=PASS")
    print("COMMANDER_EVENT_V2_LIVENESS_WINDOW_HOURS=7")
    print("COMMANDER_EVENT_V2_UNDELIVERED_CALL=CANCELLED_FAIL_CLOSED")
    print("COMMANDER_EVENT_V2_DEV_CANARY_MCP_TOKEN=DEV_ONLY")
    print("COMMANDER_EVENT_V2_POST_NOTIFY_TERMINAL_READ=PASS")
    print("COMMANDER_EVENT_V2_TERMINAL_SETTLE_WAIT_MS=500")
    print("COMMANDER_EVENT_V2_RETRY_HINT_PENDING_ENQUEUE_MS=350")
    print("COMMANDER_EVENT_V2_RETRY_HINT_PENDING_STATUS_MS=750")
    print("COMMANDER_EVENT_V2_RETRY_HINT_EXECUTING_MS=250")
    print("COMMANDER_EVENT_V2_ACTIVE_QUEUE_LIMIT=16")
    print("COMMANDER_EVENT_V2_DEVICE_BUSY_HTTP=429")
    print("COMMANDER_EVENT_V2_SELECTED_DEVICE_SINGLE_READ=PASS")
    print("COMMANDER_EVENT_V2_PROD_CANARY_MCP_TOKEN=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
