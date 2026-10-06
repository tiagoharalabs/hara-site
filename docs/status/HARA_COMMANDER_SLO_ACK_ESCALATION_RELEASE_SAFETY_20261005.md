# H.A.R.A. Commander — SLO ack/escalation and versioned release safety

Date: 2026-10-05

## Trigger-sync defect found and corrected

The production Worker uses a cron declared in wrangler.jsonc:
- 17 * * * *

Versioned Worker rollout with versions upload + versions deploy does not by
itself guarantee that Cron Triggers/routes are synchronized.

Observed symptom:
- SLO incident schema and Worker were live;
- portal observed SLO was healthy;
- commander_slo_state remained empty across expected natural cron windows.

Correction applied live:
- wrangler triggers deploy --config wrangler.jsonc
- custom domain retained
- cron 17 * * * * explicitly deployed

A canonical promotion helper now requires this order:
1. validate current 100% rollback version
2. validate required secrets on target Worker version
3. deploy target Worker version at 100%
4. deploy triggers
5. read back exact Worker version

The helper has an explicit --execute gate.

## SLO incident acknowledgement and escalation

Migration 0027 adds metadata-only operator state:
- acknowledged_at_utc
- acknowledged_by_subject_id
- escalation_level
- escalated_at_utc
- index for open incidents by escalation level

No command/payload/result/customer-content field is introduced.

Portal admin mutations:
- POST /api/portal/slo/ack
- POST /api/portal/slo/escalate

Security:
- same-origin mutation guard
- authenticated session required
- OWNER/ADMIN gate
- portal mutation rate limit
- OPEN incident only
- acknowledgement is idempotent
- escalation level is monotonic and capped at L3

Automatic escalation:
- L1 at 1 hour open
- L2 at 4 hours open
- L3 at 12 hours open
- never auto-downgrades

Portal UI:
- open incident displays current escalation level and acknowledgement state
- Reconhecer action
- Escalar Lx action
- cache key advanced to 20261005-sloincident2

## DEV live proof

Migration:
- 0027_slo_incident_ack_escalation.sql applied to DEV

Worker:
- 8f5f05e5-9f73-42d0-bcb7-316262d61e25
- rollback: 2a253fb2-272c-4449-89f9-1d6beabd5d32

Existing hysteresis:
- first breach PASS
- second breach opens incident PASS
- first recovery keeps incident open PASS
- second recovery resolves PASS
- cleanup PASS

Automatic escalation canary:
- L1 PASS
- L2 PASS
- L3 PASS

Mutation fail-closed:
- ack no session -> 401 AUTH_REQUIRED
- ack cross-origin -> 403 PORTAL_ORIGIN_DENIED
- escalate no session -> 401 AUTH_REQUIRED
- escalate cross-origin -> 403 PORTAL_ORIGIN_DENIED

Assets:
- cache key 20261005-sloincident2 PASS
- ack/escalate UI wiring PASS

## State

VERSIONED_PROMOTION_TRIGGER_SYNC_CONTRACT=CLOSED_PASS
PROD_CRON_TRIGGER_SYNC=CLOSED_PASS
SLO_ACK_ESCALATION_SOURCE=CLOSED_PASS
SLO_ACK_ESCALATION_PREPROD=CLOSED_PASS
SLO_ACK_ESCALATION_DEV_LIVE=CLOSED_PASS
SLO_ACK_ESCALATION_PROD=CLOSED_PASS
PROD_WORKER=f21917b0-b02e-46f4-aad6-fb0f333643ca
PROD_ROLLBACK=2975e2e4-f544-459e-8c91-b78a8aa1e1c7
VERSIONED_PROMOTION_HELPER_LIVE=CLOSED_PASS
PROD_CRON_TRIGGER_SYNC=CLOSED_PASS
NATURAL_CRON_STATE_ROW=CLOSED_PASS

## PROD live proof

Migration 0027:
- no pending migrations after rollout
- acknowledgement/escalation columns present

Versioned promotion helper:
- target secret guard PASS
- rollback-current guard PASS
- Worker deployment PASS
- triggers deployment PASS
- exact-version readback PASS

Fail-closed:
- ack without session -> 401 AUTH_REQUIRED
- ack cross-origin -> 403 PORTAL_ORIGIN_DENIED
- escalate without session -> 401 AUTH_REQUIRED
- escalate cross-origin -> 403 PORTAL_ORIGIN_DENIED

First natural cron evaluation after trigger synchronization:
- profile INTERNAL_BETA_V1
- state DEGRADED
- breach_streak 1
- recovery_streak 0
- incident not opened yet
- weighted success 98.728%
- worst p50 634 ms
- worst p95 3,875 ms
- worst p99 10,323 ms
- hysteresis correctly prevented incident opening on a single degraded sample

This natural degraded sample is operational evidence, not a contractual SLA breach.
If the next natural evaluation remains degraded, the existing 2-breach rule will
open an incident and the new acknowledgement/escalation workflow becomes active.

EXTERNAL_NOTIFICATION_TRANSPORT=PENDING_EXTERNAL_DESTINATION
