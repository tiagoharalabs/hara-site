# H.A.R.A. Commander — SLO incident state and internal alerting

Date: 2026-10-05
State: SOURCE/PREPROD PASS — DEV LIVE PENDING

## Goal

Turn the live INTERNAL_BETA_V1 SLO into persistent operational incident state
without adding an external notification dependency.

This is internal product operations, not a contractual SLA.

## Data model

Migration 0026 adds:

- commander_slo_state
  - one current state row per tenant
  - PASS / DEGRADED / INSUFFICIENT_DATA
  - breach/recovery streaks
  - current incident id
  - latest aggregate SLO summary

- commander_slo_incidents
  - OPEN / RESOLVED history
  - first/last breach timestamps
  - resolution timestamp
  - aggregate summary only

No command, payload, result, stdout, stderr or customer-content columns exist in
the SLO alert schema.

Resolved incident retention:
- 90 days
- bounded deletion batch of 500 per scheduled maintenance

## Evaluation

The hourly Worker scheduled handler evaluates current 24h device snapshots.

Device eligibility:
- active and not revoked
- last_seen within 120 seconds

Snapshot freshness:
- 180 seconds

Tenant state:
- DEGRADED when an online device is DEGRADED, missing its snapshot or has a
  stale snapshot;
- PASS when there is at least one PASS device and no degraded/missing/stale
  device;
- INSUFFICIENT_DATA when online devices have snapshots but none have enough
  evidence for an SLO decision.

Safe aggregate fields:
- online/pass/degraded/insufficient device counts
- missing/stale snapshot counts
- weighted success rate
- worst-device p50/p95/p99
- latest snapshot timestamp

## Hysteresis

Open:
- first consecutive DEGRADED evaluation: breach_streak=1, no incident
- second consecutive DEGRADED evaluation: OPEN incident

Resolve:
- first PASS while incident is open: recovery_streak=1, incident stays OPEN
- second consecutive PASS: RESOLVED and current_incident_id cleared

INSUFFICIENT_DATA does not open or resolve an incident.

## Surfaces

Portal:
- GET /api/portal/slo
- authenticated
- OWNER/ADMIN only
- read-only
- current state + last 10 incidents

DEV-only canary:
- POST /api/dev/slo-maintenance
- only exists in DEV runtime
- authenticated with the existing MCP product canary token
- invokes the same maintenance function used by cron

Production:
- no manual maintenance endpoint
- cron only

## Source/preprod

PASS:
- schema constraints/indexes
- 2-evaluation breach hysteresis
- 2-evaluation recovery hysteresis
- data-gap degradation
- 90-day retention
- scheduled handler wiring
- portal admin gate
- DEV canary route auth
- migration smoke test
- deterministic open/resolve policy test
- E2E harness
- full preprod readiness

## Promotion boundary

1. apply migration 0026 to DEV;
2. deploy DEV Worker;
3. run disposable live canary:
   DEGRADED -> DEGRADED -> PASS -> PASS;
4. prove OPEN then RESOLVED + cleanup;
5. apply migration to PROD;
6. deploy PROD and let cron evaluate natural snapshots;
7. external notification delivery remains a later transport concern.
