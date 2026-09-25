#!/usr/bin/env python3
"""Static source guard for the source-only Commander Event V2 DeviceChannel."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANNEL = ROOT / "src" / "device-channel.mjs"


def main() -> int:
    source = CHANNEL.read_text(encoding="utf-8")

    required = [
        'import { DurableObject } from "cloudflare:workers"',
        "class DeviceChannel extends DurableObject",
        "this.ctx.acceptWebSocket",
        "serializeAttachment",
        'type: "CALL_AVAILABLE"',
        "CHANNEL_INTERNAL_AUTH_REQUIRED",
        "SUPERSEDED_BY_NEW_CHANNEL",
        "webSocketMessage",
        "getWebSockets",
        "markConnected",
        "refreshLiveness",
        "markDisconnected",
        "EVENT_V2_OFFLINE",
        'payload.type === "LIVENESS"',
        "async webSocketClose",
        "deserializeAttachment",
    ]
    for marker in required:
        assert marker in source, f"missing required marker: {marker}"

    forbidden = [
        "child_process",
        "exec(",
        "spawn(",
        "shell.run",
        "filesystem",
        "HARA_DEVICE_TOKEN",
        "device_token",
        "authorization",
        "eval(",
        "setInterval(",
        "setTimeout(",
    ]
    for marker in forbidden:
        assert marker not in source, f"forbidden Event V2 marker: {marker}"

    assert source.count("CALL_AVAILABLE") == 1
    assert "/connect" in source
    assert "/notify" in source
    assert "/status" in source
    assert "tunnel_mode = 'EVENT_V2'" in source
    assert "tunnel_mode = 'EVENT_V2_OFFLINE'" in source
    assert "last_seen_at_utc = ?" in source
    assert 'Object.keys(payload).sort().join(",") === "schema,type"' in source

    print("COMMANDER_EVENT_V2_DEVICE_CHANNEL_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_HIBERNATION=PASS")
    print("COMMANDER_EVENT_V2_SECRET_ATTACHMENT=ABSENT")
    print("COMMANDER_EVENT_V2_ARBITRARY_EXECUTION_SURFACE=ABSENT")
    print("COMMANDER_EVENT_V2_CONNECT_DISCONNECT_PRESENCE=PASS")
    print("COMMANDER_EVENT_V2_LIVENESS_CONTENT_FIELDS=DENIED")
    print("COMMANDER_EVENT_V2_DO_TIMERS=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
