#!/usr/bin/env python3
"""Fail-closed source guard for DEV-only transient Event V2 RPC."""

from pathlib import Path
import json
import runpy

ROOT = Path(__file__).resolve().parents[3]
COMMANDER = ROOT / "apps" / "commander"
WORKER = COMMANDER / "src" / "worker.js"
CHANNEL = COMMANDER / "src" / "device-channel.mjs"
LOOP = COMMANDER / "experimental" / "event_v2_agent_loop.py"
TRANSPORT = COMMANDER / "experimental" / "event_v2_websocket.py"
AGENT = COMMANDER / "experimental" / "event_v2_customer_agent.py"
DEV = COMMANDER / "wrangler.dev.jsonc"
PROD = COMMANDER / "wrangler.jsonc"
MODEL = COMMANDER / "scripts" / "commander_event_v2_transient_1k_model.py"


def block(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def main() -> int:
    worker = WORKER.read_text(encoding="utf-8")
    channel = CHANNEL.read_text(encoding="utf-8")
    loop = LOOP.read_text(encoding="utf-8")
    transport = TRANSPORT.read_text(encoding="utf-8")
    agent = AGENT.read_text(encoding="utf-8")
    dev = json.loads(DEV.read_text(encoding="utf-8"))
    prod = PROD.read_text(encoding="utf-8")

    assert dev["vars"]["DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED"] == "true"
    assert "DEVICE_EVENT_V2_TRANSIENT_RPC_ENABLED" not in prod
    assert 'url.pathname === "/api/internal/device/transient-call"' in worker
    assert '"https://device-channel/dispatch"' in worker
    assert 'type: "CALL_TRANSIENT"' in channel
    assert 'payload.type === "CALL_RESULT"' in channel
    assert "MAX_TRANSIENT_INFLIGHT = 1" in channel
    assert "TRANSIENT_RPC_TIMEOUT_MS = 45 * 1000" in channel
    assert "scheduler.wait(TRANSIENT_RPC_TIMEOUT_MS)" in channel
    assert "setTimeout(" not in channel
    assert "cleanLearningSignal" in channel
    assert "customer_content_collected !== false" in channel
    assert "privileged_attempt !== false" in channel

    dispatcher = block(
        worker,
        "async function dispatchTransientDeviceCall",
        "export class TenantQuota",
    )
    assert "commander_device_calls" not in dispatcher
    assert "payload_json" not in dispatcher
    assert "result_json" not in dispatcher
    assert "canonicalDeviceToolPayload" in dispatcher
    assert "mcpProductContext" in dispatcher
    assert "selectedDeviceForSubject" in dispatcher
    assert 'selection.tunnel_mode || "") !== "EVENT_V2"' in dispatcher
    assert "persisted_customer_payload: false" in dispatcher
    assert "persisted_customer_result: false" in dispatcher

    assert 'event["type"] == "CALL_TRANSIENT"' in loop
    assert "execute_transient_call" in loop
    assert "send_transient_result" in loop
    assert '"type": "CALL_TRANSIENT"' in transport
    assert "MAX_TRANSIENT_REQUEST_BYTES = 160 * 1024" in transport
    assert "MAX_TRANSIENT_RESULT_BYTES = 320 * 1024" in transport

    assert "hara.commander-learning-signal.v1" in agent
    assert '"customer_content_collected": False' in agent
    assert '"privileged_attempt": False' in agent
    assert "hara.commander-transient-ledger.v1" in agent
    assert "TRANSIENT_LEDGER_RETENTION_SECONDS = 24 * 60 * 60" in agent
    assert "TRANSIENT_LEDGER_CLEANUP_BATCH = 32" in agent
    assert "_canonical_payload_sha256" in agent
    assert "IDEMPOTENCY_CONFLICT" in agent
    assert 'os.chmod(path, 0o600)' in agent
    signal = block(agent, "def build_learning_signal", "def execute_transient_call")
    for forbidden in ("payload_json", "result_json", "stdout", "arguments", "path"):
        assert forbidden not in signal

    for public in (
        COMMANDER / "public" / "agent" / "linux.py",
        COMMANDER / "public" / "agent" / "windows.ps1",
    ):
        source = public.read_text(encoding="utf-8")
        assert "CALL_TRANSIENT" not in source
        assert "EVENT_V2_TRANSIENT_RPC" not in source

    model = runpy.run_path(str(MODEL))
    model["self_check"]()

    print("COMMANDER_EVENT_V2_TRANSIENT_RPC_SOURCE=PASS")
    print("COMMANDER_EVENT_V2_TRANSIENT_RPC_ENV=DEV_ONLY")
    print("COMMANDER_EVENT_V2_TRANSIENT_RPC_D1_CONTENT_PERSISTENCE=ZERO")
    print("COMMANDER_EVENT_V2_LEARNING_PLANE=DERIVED_METADATA_ONLY")
    print("COMMANDER_EVENT_V2_LOCAL_IDEMPOTENCY_LEDGER_LINUX=PASS")
    print("COMMANDER_EVENT_V2_LOCAL_LEDGER_RAW_PAYLOAD=ABSENT")
    print("COMMANDER_EVENT_V2_PUBLIC_AGENT_MUTATION=FALSE")
    print("COMMANDER_EVENT_V2_PROD_CUTOVER=DENY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
