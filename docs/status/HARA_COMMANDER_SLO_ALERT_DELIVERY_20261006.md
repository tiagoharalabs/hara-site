# H.A.R.A. Commander — SLO external alert delivery

Date: 2026-10-06
State: SOURCE/PREPROD IMPLEMENTATION

## Scope

This slice closes the source-level transport gap after the already-live SLO
incident, hysteresis, acknowledgement and L1/L2/L3 escalation machinery.

Implemented:
- idempotent D1 outbox keyed per incident/event/escalation level;
- OPENED, ESCALATED and RESOLVED events;
- HTTPS-only webhook destination;
- HMAC-SHA256 signature via x-hara-signature;
- bounded batch dispatch;
- retry state with sanitized error code;
- delivered-row retention;
- cron ordering: evaluate/persist first, dispatch second;
- delivery failure never rolls back or blocks SLO incident evaluation.

Privacy boundary:
- no command content;
- no tool payload content;
- no tool result content;
- no customer content;
- no secret material;
- only incident identity, escalation metadata and aggregate SLO counters/percentiles.

Runtime secrets required for live delivery:
- SLO_ALERT_WEBHOOK_URL
- SLO_ALERT_WEBHOOK_SECRET

Without both secrets, the outbox remains durable and dispatch is skipped.

## Gate

- validate_slo_alert_delivery.py
- included in validate_preprod_readiness.py

## Promotion boundary

Source/preprod can close without selecting a live notification provider.
DEV/PROD live proof requires an explicit HTTPS destination and signing secret,
followed by a signed-delivery canary and receiver-side signature verification.

EXTERNAL_ALERT_DELIVERY_SOURCE=IMPLEMENTED
EXTERNAL_ALERT_DELIVERY_DEV=PENDING_DESTINATION
EXTERNAL_ALERT_DELIVERY_PROD=PENDING_DESTINATION
