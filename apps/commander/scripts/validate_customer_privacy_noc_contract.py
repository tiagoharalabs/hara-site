#!/usr/bin/env python3
"""Fail-closed architecture guard for Commander customer privacy/NOC separation."""

from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parent.parent
EVENT = ROOT.parent.parent / "docs" / "architecture" / "HARA_COMMANDER_SCALE_V2_EVENT_TRANSPORT.md"
TELEMETRY = ROOT.parent.parent / "docs" / "architecture" / "HARA_COMMANDER_PRIVACY_FIRST_TELEMETRY.md"
CHANNEL = ROOT / "src" / "device-channel.mjs"
WORKER = ROOT / "src" / "worker.js"
LEARNING_SCHEMA = ROOT / "contracts" / "commander_learning_signal_v1.schema.json"
DEV_CONFIG = ROOT / "wrangler.dev.jsonc"
PROD_CONFIG = ROOT / "wrangler.jsonc"


def require(text: str, marker: str) -> None:
    assert marker in text, f"missing required marker: {marker}"


def main() -> int:
    event = EVENT.read_text(encoding="utf-8")
    telemetry = TELEMETRY.read_text(encoding="utf-8")

    required_event = (
        "CUSTOMER_TRAFFIC_THROUGH_HARA_SERVICES=false",
        "HARA_SERVICES_CUSTOMER_PROXY=false",
        "HTTP_HEARTBEAT_30S=FALSE",
        "IDLE_HTTP_POLLING=FALSE",
        "WEBSOCKET_PROTOCOL_PING_IDLE_TARGET=60s",
        "DURABLE_LIVENESS_CHECKPOINT_TARGET=6h",
        "RECONNECT_FULL_JITTER=true",
        "POLL_V1_FALLBACK_DEFAULT=OFF",
        "CUSTOMER_CONTENT_PRIVATE_BY_DEFAULT=true",
        "CUSTOMER_CONTENT_FOR_MODEL_TRAINING=false",
        "NOC_METADATA_ONLY=true",
        "TRANSIENT_RPC_ENV=DEV_ONLY",
        "D1_CUSTOMER_PAYLOAD_PERSISTENCE=FALSE",
        "D1_CUSTOMER_RESULT_PERSISTENCE=FALSE",
        "LEARNING_SIGNAL_DERIVED_METADATA_ONLY=TRUE",
        "LEARNING_SIGNAL_CUSTOMER_CONTENT=FALSE",
        "REDACTION_CAPACITY_PER_DAY=12288",
    )
    for marker in required_event:
        require(event, marker)

    required_telemetry = (
        "HARA_SERVICES_INLINE_CUSTOMER_PROXY=FALSE",
        "HARA_SERVICES_NOC_AGGREGATION=TRUE",
        "CUSTOMER_CONTENT_TO_SERVICES=FALSE",
        "CUSTOMER_CONTENT_COLLECTION=FALSE",
        "CUSTOMER_CONTENT_FOR_MODEL_TRAINING=FALSE",
        "CUSTOMER_OPERATIONAL_METADATA_ONLY=TRUE",
        "CUSTOMER_TRAFFIC_INSPECTION_DEFAULT=FALSE",
        "MANAGED_RELAY_CONTENT_DURABLE_COLLECTION=FALSE",
        "CUSTOMER_CONTENT_IN_LEARNING_PLANE=FALSE",
        "RAW_DIAGNOSTICS_EXPLICIT_OPT_IN_REQUIRED=TRUE",
        "DURABLE_CALL_TTL_SECONDS=50",
        "DURABLE_PAYLOAD_AFTER_REDACTION=SHA256_TOMBSTONE_ONLY",
        "DURABLE_RESULT_AFTER_REDACTION=SHA256_TOMBSTONE_OR_NULL",
        "DURABLE_STATUS_RETURNS_TOMBSTONE=FALSE",
        "DURABLE_IDEMPOTENCY_AFTER_REDACTION=SHA256_STRICT",
    )
    for marker in required_telemetry:
        require(telemetry, marker)

    # Product privacy cannot silently become an observability exception.
    forbidden = (
        "CUSTOMER_CONTENT_COLLECTION=TRUE",
        "CUSTOMER_CONTENT_FOR_MODEL_TRAINING=TRUE",
        "HARA_SERVICES_CUSTOMER_PROXY=true",
        "HARA_SERVICES_INLINE_CUSTOMER_PROXY=TRUE",
        "IDLE_HTTP_POLLING=TRUE",
        "HTTP_HEARTBEAT_30S=TRUE",
    )
    combined = event + "\n" + telemetry
    for marker in forbidden:
        assert marker not in combined, f"forbidden architecture marker: {marker}"

    schema = json.loads(LEARNING_SCHEMA.read_text(encoding="utf-8"))
    assert schema.get("$id") == "hara.commander-learning-signal.v1"
    assert schema.get("additionalProperties") is False
    properties = schema.get("properties") or {}
    required_fields = set(schema.get("required") or [])
    assert required_fields == set(properties), "learning schema must require its exact allowlist"
    assert properties["privileged_attempt"].get("const") is False
    assert properties["customer_content_collected"].get("const") is False

    channel = CHANNEL.read_text(encoding="utf-8")
    match = re.search(
        r"function cleanLearningSignal\(value\) \{.*?const allowed = \[(.*?)\];",
        channel,
        re.S,
    )
    assert match, "learning signal allowlist missing from DeviceChannel"
    source_fields = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    assert source_fields == set(properties), (source_fields, set(properties))
    assert 'value.schema !== "hara.commander-learning-signal.v1"' in channel
    assert 'value.privileged_attempt !== false' in channel
    assert 'value.customer_content_collected !== false' in channel

    dev_config = json.loads(DEV_CONFIG.read_text(encoding="utf-8"))
    prod_config = json.loads(PROD_CONFIG.read_text(encoding="utf-8"))
    dev_analytics = dev_config.get("analytics_engine_datasets") or []
    assert dev_analytics == [{
        "binding": "LEARNING_ANALYTICS",
        "dataset": "hara_commander_learning_dev",
    }]
    assert not (prod_config.get("analytics_engine_datasets") or [])

    worker = WORKER.read_text(encoding="utf-8")
    assert 'const DEVICE_CALL_TTL_SECONDS = 50;' in worker
    assert 'const DEVICE_CALL_CONTENT_REDACTION_BATCH = 64;' in worker
    assert 'const DEVICE_CALL_CONTENT_REDACTION_MAX_BATCHES = 8;' in worker
    assert 'const DEVICE_CALL_REDACTED_PREFIX = "HARA_REDACTED_SHA256:";' in worker
    assert "async function redactExpiredDeviceCallContent" in worker
    assert "state IN ('COMPLETED','FAILED','CANCELLED','EXPIRED')" in worker
    assert "SET payload_json = ?, result_json = ?" in worker
    assert "await sha256(String(value))" in worker
    assert "deviceCallStoredContentMatches" in worker
    assert "content_redacted:" in worker
    assert "!isRedactedDeviceCallContent(row.result_json)" in worker

    analytics_at = worker.index("function recordLearningSignal")
    analytics_end = worker.index("async function dispatchTransientDeviceCall", analytics_at)
    analytics_block = worker[analytics_at:analytics_end]
    assert "env.LEARNING_ANALYTICS.writeDataPoint" in analytics_block
    assert "customer_content_collected !== false" in analytics_block
    assert "privileged_attempt !== false" in analytics_block
    assert "LEARNING_SIGNAL_KEYS" in worker
    forbidden_analytics_patterns = (
        "tenant_id",
        "subject_id",
        "device_id",
        "request_id",
        "call_id",
        "receipt_sha256",
        ".payload",
        " payload:",
        " result:",
        ".email",
        " email:",
        ".issuer",
        " issuer:",
    )
    for forbidden_identifier in forbidden_analytics_patterns:
        assert forbidden_identifier not in analytics_block, forbidden_identifier
    assert not re.search(r"signal\.result(?!_bytes_bucket)", analytics_block)
    assert "recordLearningSignal(env, payload.learning_signal);" in worker

    raw_fields = {
        "prompt", "arguments", "argv", "path", "filename", "command",
        "stdout", "stderr", "raw_result", "raw_payload", "authorization",
        "cookie", "device_token", "file_content",
    }
    assert raw_fields.isdisjoint(properties), "raw customer field admitted by learning schema"

    print("COMMANDER_CUSTOMER_DATA_PLANE_PRIVACY=PASS")
    print("COMMANDER_CUSTOMER_SERVICES_PROXY=ABSENT")
    print("COMMANDER_CUSTOMER_CONTENT_COLLECTION=FALSE")
    print("COMMANDER_CUSTOMER_MODEL_TRAINING_FROM_CONTENT=FALSE")
    print("COMMANDER_EVENT_V2_IDLE_HTTP_POLLING=FALSE")
    print("COMMANDER_EVENT_V2_PROTOCOL_KEEPALIVE=60S_TARGET")
    print("COMMANDER_DURABLE_LIVENESS_CHECKPOINT=6H_TARGET")
    print("COMMANDER_NOC_METADATA_ONLY=PASS")
    print("COMMANDER_LEARNING_SIGNAL_SCHEMA=PASS")
    print("COMMANDER_LEARNING_SIGNAL_SOURCE_ALLOWLIST=PASS")
    print("COMMANDER_LEARNING_SIGNAL_RAW_CONTENT=DENY")
    print("COMMANDER_LEARNING_ANALYTICS_DEV_BINDING=PASS")
    print("COMMANDER_LEARNING_ANALYTICS_PROD_BINDING=ABSENT")
    print("COMMANDER_LEARNING_ANALYTICS_CUSTOMER_IDENTIFIERS=ABSENT")
    print("COMMANDER_LEARNING_ANALYTICS_CUSTOMER_CONTENT=ABSENT")
    print("COMMANDER_DURABLE_FALLBACK_RAW_CONTENT_AFTER_TTL=REDACTION_TARGET")
    print("COMMANDER_DURABLE_FALLBACK_IDEMPOTENCY=SHA256_AFTER_REDACTION")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
