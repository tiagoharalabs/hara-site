#!/usr/bin/env python3
"""Fail-closed architecture guard for Commander customer privacy/NOC separation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENT = ROOT.parent.parent / "docs" / "architecture" / "HARA_COMMANDER_SCALE_V2_EVENT_TRANSPORT.md"
TELEMETRY = ROOT.parent.parent / "docs" / "architecture" / "HARA_COMMANDER_PRIVACY_FIRST_TELEMETRY.md"


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

    print("COMMANDER_CUSTOMER_DATA_PLANE_PRIVACY=PASS")
    print("COMMANDER_CUSTOMER_SERVICES_PROXY=ABSENT")
    print("COMMANDER_CUSTOMER_CONTENT_COLLECTION=FALSE")
    print("COMMANDER_CUSTOMER_MODEL_TRAINING_FROM_CONTENT=FALSE")
    print("COMMANDER_EVENT_V2_IDLE_HTTP_POLLING=FALSE")
    print("COMMANDER_EVENT_V2_PROTOCOL_KEEPALIVE=60S_TARGET")
    print("COMMANDER_DURABLE_LIVENESS_CHECKPOINT=6H_TARGET")
    print("COMMANDER_NOC_METADATA_ONLY=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
