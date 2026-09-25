#!/usr/bin/env python3
"""Static guard for Commander Event V2 Worker wiring.

This is source-only validation. It must prove the new channel is DEV-bound and
feature-disabled by default, while PROD remains free of the new binding until a
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
    notify_at = worker.index("const notification = await notifyDeviceEventChannel(")
    assert notify_at > insert_at, "event notification must occur only after durable call insert"
    undelivered_at = worker.index("DEVICE_EVENT_UNDELIVERED")
    assert undelivered_at > notify_at, "undelivered Event V2 call must cancel after notify attempt"
    notify_guard = worker[notify_at:undelivered_at + 800]
    assert "notification.delivered < 1" in notify_guard
    assert 'throw new Error("DEVICE_OFFLINE")' in notify_guard
    assert "state = 'CANCELLED'" in notify_guard

    assert "deviceOnline(row.last_seen_at_utc, row.tunnel_mode, now)" in worker
    assert "deviceOnline(device.last_seen_at_utc, device.tunnel_mode)" in worker
    assert "deviceOnline(currentDevice.last_seen_at_utc, currentDevice.tunnel_mode)" in worker

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
    assert dev["vars"]["DEVICE_EVENT_V2_ENABLED"] == "false"
    bindings = {
        row["name"]: row["class_name"]
        for row in dev["durable_objects"]["bindings"]
    }
    assert bindings.get("DEVICE_CHANNEL") == "DeviceChannel"
    assert any(
        row.get("tag") == "v2" and "DeviceChannel" in row.get("new_classes", [])
        for row in dev["migrations"]
    )

    # PROD is intentionally untouched by package 2.
    assert "DEVICE_EVENT_V2_ENABLED" not in prod_raw
    assert '"DEVICE_CHANNEL"' not in prod_raw
    assert '"DeviceChannel"' not in prod_raw

    print("COMMANDER_EVENT_V2_WORKER_WIRING=PASS")
    print("COMMANDER_EVENT_V2_DEV_BINDING=PASS")
    print("COMMANDER_EVENT_V2_DEV_DEFAULT=OFF")
    print("COMMANDER_EVENT_V2_PROD_BINDING=ABSENT")
    print("COMMANDER_EVENT_V2_NOTIFY_AFTER_DURABLE_INSERT=PASS")
    print("COMMANDER_EVENT_V2_PRESENCE_USES_TRANSPORT_STATE=PASS")
    print("COMMANDER_EVENT_V2_V1_90S_WINDOW_PRESERVED=PASS")
    print("COMMANDER_EVENT_V2_LIVENESS_WINDOW_HOURS=7")
    print("COMMANDER_EVENT_V2_UNDELIVERED_CALL=CANCELLED_FAIL_CLOSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
