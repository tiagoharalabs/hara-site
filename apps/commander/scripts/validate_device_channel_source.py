#!/usr/bin/env python3
"""Static source guard for the source-only Commander Event V2 DeviceChannel."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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
    ]
    for marker in forbidden:
        assert marker not in source, f"forbidden Event V2 marker: {marker}"

    assert source.count("CALL_AVAILABLE") == 1
    assert "/connect" in source
    assert "/notify" in source
    assert "/status" in source

    print("COMMANDER_EVENT_V2_DEVICE_CHANNEL_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_HIBERNATION=PASS")
    print("COMMANDER_EVENT_V2_SECRET_ATTACHMENT=ABSENT")
    print("COMMANDER_EVENT_V2_ARBITRARY_EXECUTION_SURFACE=ABSENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
